"""
Gestor de impresión para impresoras instaladas como Generic/Text Only en Windows
Usa la API de Windows en lugar de puerto serial
"""

import os
import sys
import tempfile
import subprocess
import time
import json
import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN DEL TICKET
# =============================================================================
# Ancho en columnas del papel térmico. Es la ÚNICA fuente de verdad: la vista
# previa en pantalla y lo que sale impreso usan este mismo valor, para que lo
# que ve el cajero sea lo que sale en papel.
#   58 mm -> 32 columnas (Font A)   |   80 mm -> 48 columnas
VAR_ANCHO_TICKET = "TICKET_ANCHO_COLUMNAS"
ANCHO_TICKET_POR_DEFECTO = 32

# Nombre de la impresora. Configurable porque el nombre real varía por
# instalación (p. ej. "Generic / Text Only :)" con emoticono en el nombre).
VAR_IMPRESORA = "TICKET_IMPRESORA"
IMPRESORA_POR_DEFECTO = "Generic / Text Only"


def obtener_ancho_ticket() -> int:
    """Ancho de columna configurado, con límites razonables."""
    crudo = (os.getenv(VAR_ANCHO_TICKET) or "").strip()
    if not crudo:
        return ANCHO_TICKET_POR_DEFECTO
    try:
        ancho = int(crudo)
    except ValueError:
        logger.warning(
            f"[AVISO] {VAR_ANCHO_TICKET}={crudo!r} no es un número; "
            f"se usa {ANCHO_TICKET_POR_DEFECTO}."
        )
        return ANCHO_TICKET_POR_DEFECTO
    if not 20 <= ancho <= 80:
        logger.warning(
            f"[AVISO] {VAR_ANCHO_TICKET}={ancho} fuera de rango (20-80); "
            f"se usa {ANCHO_TICKET_POR_DEFECTO}."
        )
        return ANCHO_TICKET_POR_DEFECTO
    return ancho


class WindowsPrinterManager:
    """
    Gestor de impresoras instaladas en Windows
    Funciona con "Generic/Text Only" y otras impresoras instaladas
    """

    # La lista de impresoras cambia poquísimo en un POS fijo. Se consulta con la
    # API nativa (milisegundos), así que la caché es solo para evitar repetirla
    # varias veces dentro de una misma impresión.
    _CACHE_SEGUNDOS = 120
    _cache_impresoras: List[str] = []
    _cache_timestamp: float = 0.0

    @staticmethod
    def _enumerar_impresoras_nativo() -> Optional[List[str]]:
        """
        Listar impresoras con EnumPrintersW (winspool).

        Sustituye al lanzamiento de PowerShell, que tardaba ~3.4 s y congelaba
        la interfaz en cada impresión. Esta vía tarda milisegundos.

        Returns:
            Lista de nombres, o None si la API no está disponible o falla
            (entonces el llamador usa PowerShell como respaldo).
        """
        if not sys.platform.startswith('win'):
            return None

        try:
            class PRINTER_INFO_4W(ctypes.Structure):
                _fields_ = [
                    ("pPrinterName", wintypes.LPWSTR),
                    ("pServerName", wintypes.LPWSTR),
                    ("Attributes", wintypes.DWORD),
                ]

            winspool = ctypes.WinDLL("winspool.drv")
            enum_printers = winspool.EnumPrintersW
            enum_printers.argtypes = [
                wintypes.DWORD,                 # Flags
                wintypes.LPWSTR,                # Name
                wintypes.DWORD,                 # Level
                wintypes.LPBYTE,                # pPrinterEnum
                wintypes.DWORD,                 # cbBuf
                ctypes.POINTER(wintypes.DWORD),  # pcbNeeded
                ctypes.POINTER(wintypes.DWORD),  # pcReturned
            ]
            enum_printers.restype = wintypes.BOOL

            PRINTER_ENUM_LOCAL = 0x00000002
            PRINTER_ENUM_CONNECTIONS = 0x00000004
            flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
            nivel = 4

            necesario = wintypes.DWORD(0)
            devueltos = wintypes.DWORD(0)

            # Primera llamada: solo para saber cuánto buffer hace falta.
            enum_printers(flags, None, nivel, None, 0,
                          ctypes.byref(necesario), ctypes.byref(devueltos))
            if necesario.value == 0:
                return []

            buffer = ctypes.create_string_buffer(necesario.value)
            if not enum_printers(
                flags, None, nivel,
                ctypes.cast(buffer, wintypes.LPBYTE),
                necesario.value,
                ctypes.byref(necesario), ctypes.byref(devueltos)
            ):
                return None

            entradas = ctypes.cast(
                buffer, ctypes.POINTER(PRINTER_INFO_4W)
            )
            nombres = []
            for i in range(devueltos.value):
                nombre = entradas[i].pPrinterName
                if nombre:
                    nombres.append(str(nombre).strip())
            return nombres
        except Exception as e:
            logger.warning(f"[AVISO] EnumPrinters no disponible ({e}); se usará PowerShell.")
            return None

    @staticmethod
    def _subprocess_no_window_kwargs() -> Dict:
        """Parámetros para ejecutar subprocess sin mostrar ventanas en Windows."""
        kwargs: Dict = {}
        if sys.platform.startswith('win'):
            create_no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            if create_no_window:
                kwargs['creationflags'] = create_no_window

            if hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs['startupinfo'] = startupinfo
        return kwargs

    def __init__(self, nombre_impresora: str = "Generic / Text Only"):
        """
        Inicializar gestor
        
        Args:
            nombre_impresora: Nombre exacto de la impresora instalada en Windows
        """
        self.nombre_impresora = nombre_impresora
        self.conectado = False

    @staticmethod
    def _ejecutar_powershell(cmd: str, timeout: int = 12) -> str:
        """Ejecutar PowerShell de forma más estable en Windows."""
        resultado = subprocess.run(
            [
                'powershell',
                '-NoProfile',
                '-NonInteractive',
                '-ExecutionPolicy',
                'Bypass',
                '-Command',
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            **WindowsPrinterManager._subprocess_no_window_kwargs()
        )
        return (resultado.stdout or "").strip()

    @staticmethod
    def _parsear_salida_impresoras(salida: str) -> List[str]:
        """Normalizar salida de comandos de impresoras."""
        if not salida:
            return []

        impresoras = []
        for linea in salida.splitlines():
            nombre = linea.strip()
            if nombre:
                impresoras.append(nombre)
        return impresoras

    @staticmethod
    def obtener_impresora_generic_usb(puerto_preferido: Optional[str] = None) -> str:
        """Buscar impresora Generic/Text Only en cualquier USB (o uno preferido)."""
        try:
            cmd = (
                'Get-Printer | Select-Object Name,PortName | ConvertTo-Json -Compress'
            )
            salida = WindowsPrinterManager._ejecutar_powershell(cmd, timeout=12)
            if not salida:
                return None

            data = json.loads(salida)
            if isinstance(data, dict):
                data = [data]

            puerto_objetivo = (puerto_preferido or "").strip().lower()
            candidatos_generic = []

            for item in data:
                nombre = (item.get('Name') or '').strip()
                puerto = (item.get('PortName') or '').strip()
                nombre_lower = nombre.lower()
                puerto_lower = puerto.lower()

                if (
                    nombre
                    and 'generic' in nombre_lower
                    and 'text only' in nombre_lower
                ):
                    candidatos_generic.append((nombre, puerto, puerto_lower))

            if not candidatos_generic:
                return None

            if puerto_objetivo:
                for nombre, puerto, puerto_lower in candidatos_generic:
                    if puerto_lower == puerto_objetivo:
                        logger.info(f"Impresora Generic USB preferida encontrada: {nombre} ({puerto})")
                        return nombre

            for nombre, puerto, puerto_lower in candidatos_generic:
                if puerto_lower.startswith('usb'):
                    logger.info(f"Impresora Generic USB encontrada: {nombre} ({puerto})")
                    return nombre

            nombre, puerto, _ = candidatos_generic[0]
            logger.info(f"Impresora Generic encontrada (sin USB): {nombre} ({puerto})")
            return nombre
        except Exception as e:
            logger.error(f"Error al buscar impresora Generic en {puerto_preferido}: {e}")
            return None

    @staticmethod
    def obtener_info_impresora(nombre_impresora: str) -> Dict:
        """Obtener información de estado de una impresora instalada."""
        try:
            if not nombre_impresora:
                return {}

            cmd = (
                f'Get-Printer -Name "{nombre_impresora}" | '
                'Select-Object Name,PortName,PrinterStatus,WorkOffline | ConvertTo-Json -Compress'
            )
            salida = WindowsPrinterManager._ejecutar_powershell(cmd, timeout=10)
            if not salida:
                return {}

            data = json.loads(salida)
            if isinstance(data, list):
                return data[0] if data else {}
            if isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            logger.error(f"Error al obtener info de impresora '{nombre_impresora}': {e}")
            return {}
    
    @staticmethod
    def obtener_impresoras_instaladas(force_refresh: bool = False) -> List[str]:
        """
        Obtener lista de impresoras instaladas en Windows
        
        Returns:
            Lista de nombres de impresoras
        """
        ahora = time.time()
        if (
            not force_refresh
            and WindowsPrinterManager._cache_impresoras
            and (ahora - WindowsPrinterManager._cache_timestamp) < WindowsPrinterManager._CACHE_SEGUNDOS
        ):
            return WindowsPrinterManager._cache_impresoras

        try:
            # 1) Vía nativa (milisegundos). Evita congelar la interfaz.
            impresoras = WindowsPrinterManager._enumerar_impresoras_nativo()

            # 2) Respaldo por PowerShell solo si la nativa no dio resultado.
            if not impresoras:
                cmd_principal = 'Get-Printer | Select-Object -ExpandProperty Name'
                salida = WindowsPrinterManager._ejecutar_powershell(cmd_principal, timeout=12)
                impresoras = WindowsPrinterManager._parsear_salida_impresoras(salida)

            if not impresoras:
                cmd_fallback = 'Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name'
                salida_fallback = WindowsPrinterManager._ejecutar_powershell(cmd_fallback, timeout=12)
                impresoras = WindowsPrinterManager._parsear_salida_impresoras(salida_fallback)

            WindowsPrinterManager._cache_impresoras = impresoras
            WindowsPrinterManager._cache_timestamp = ahora
            logger.info(f"Impresoras encontradas: {impresoras}")
            return impresoras
        except subprocess.TimeoutExpired:
            logger.error("Timeout al obtener impresoras de Windows")
            if WindowsPrinterManager._cache_impresoras:
                logger.warning("Usando cache de impresoras por timeout")
                return WindowsPrinterManager._cache_impresoras
            return []
        except Exception as e:
            logger.error(f"Error al obtener impresoras: {e}")
            if WindowsPrinterManager._cache_impresoras:
                logger.warning("Usando cache de impresoras por error")
                return WindowsPrinterManager._cache_impresoras
            return []
    
    @staticmethod
    def _normalizar_nombre(nombre: str) -> str:
        """Dejar solo letras y dígitos en minúscula, para comparar nombres."""
        return "".join(c for c in (nombre or "").lower() if c.isalnum())

    @staticmethod
    def resolver_impresora(preferida: Optional[str] = None) -> Optional[str]:
        """
        Determinar con qué impresora imprimir, tolerando nombres inexactos.

        El nombre real varía por instalación: en el POS del gimnasio la
        impresora se llama "Generic / Text Only :)" (con emoticono), por lo que
        una comparación exacta contra "Generic / Text Only" fallaba siempre y
        solo salvaba la situación un respaldo por subcadena que tomaba la
        PRIMERA coincidencia, pudiendo elegir la impresora equivocada.

        Orden de resolución:
          1. TICKET_IMPRESORA del entorno (o el argumento `preferida`), exacto.
          2. Coincidencia exacta.
          3. Coincidencia normalizada (ignora espacios, signos y emoticonos).
          4. Mejor candidata por puntaje: se prefiere "text only" y "generic",
             y se descartan impresoras virtuales (PDF, XPS, OneNote, Fax).

        Returns:
            Nombre exacto tal como Windows lo conoce, o None si no hay ninguna.
        """
        instaladas = WindowsPrinterManager.obtener_impresoras_instaladas()
        if not instaladas:
            instaladas = WindowsPrinterManager.obtener_impresoras_instaladas(
                force_refresh=True
            )
        if not instaladas:
            logger.error("[ERROR] Windows no reporta ninguna impresora instalada")
            return None

        candidata = (preferida or os.getenv(VAR_IMPRESORA) or "").strip()
        configurada = bool(candidata)
        if not candidata:
            candidata = IMPRESORA_POR_DEFECTO

        # 1 y 2. Coincidencia exacta.
        if candidata in instaladas:
            return candidata

        # 3. Coincidencia normalizada: "Generic / Text Only" == "Generic / Text Only :)"
        objetivo = WindowsPrinterManager._normalizar_nombre(candidata)
        for nombre in instaladas:
            if WindowsPrinterManager._normalizar_nombre(nombre) == objetivo:
                logger.info(f"[OK] Impresora resuelta por nombre normalizado: {nombre!r}")
                return nombre

        # Si el usuario configuró un nombre explícito y no existe, es un error de
        # configuración: avisar en vez de imprimir en otra impresora sin querer.
        if configurada:
            logger.error(
                f"[ERROR] {VAR_IMPRESORA}={candidata!r} no coincide con ninguna "
                f"impresora instalada: {instaladas}"
            )
            return None

        # 4. Mejor candidata por puntaje.
        VIRTUALES = ("pdf", "xps", "onenote", "fax", "microsoft print to")
        mejor, mejor_puntaje = None, 0
        for nombre in instaladas:
            bajo = nombre.lower()
            if any(v in bajo for v in VIRTUALES):
                continue
            puntaje = 0
            if "text only" in bajo:
                puntaje += 3
            if "generic" in bajo:
                puntaje += 2
            if "thermal" in bajo or "pos" in bajo or "ticket" in bajo:
                puntaje += 1
            if puntaje > mejor_puntaje:
                mejor, mejor_puntaje = nombre, puntaje

        if mejor:
            logger.info(f"[OK] Impresora elegida automáticamente: {mejor!r}")
            return mejor

        logger.error(
            f"[ERROR] No se encontró una impresora de tickets. Instaladas: {instaladas}. "
            f"Configura {VAR_IMPRESORA} en el .env con el nombre exacto."
        )
        return None

    @staticmethod
    def obtener_impresora_por_tipo(tipo: str = "Generic") -> str:
        """
        Buscar impresora por tipo
        
        Args:
            tipo: Palabra clave para buscar (Generic, Thermal, Text, etc)
            
        Returns:
            Nombre de la impresora o None
        """
        try:
            tipo_lower = (tipo or "").strip().lower()
            impresoras = WindowsPrinterManager.obtener_impresoras_instaladas()

            if not impresoras:
                impresoras = WindowsPrinterManager.obtener_impresoras_instaladas(force_refresh=True)

            nombre = next(
                (impresora for impresora in impresoras if tipo_lower in impresora.lower()),
                None
            )

            if nombre:
                logger.info(f"Impresora {tipo} encontrada: {nombre}")
                return nombre
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout al buscar impresora {tipo}")
            return None
        except Exception as e:
            logger.error(f"Error al buscar impresora {tipo}: {e}")
            return None
    
    def conectar(self) -> bool:
        """Verificar que la impresora existe"""
        try:
            impresoras = self.obtener_impresoras_instaladas()
            if self.nombre_impresora in impresoras:
                self.conectado = True
                logger.info(f"✅ Conectado a: {self.nombre_impresora}")
                return True
            else:
                logger.error(f"❌ Impresora no encontrada: {self.nombre_impresora}")
                logger.info(f"Impresoras disponibles: {impresoras}")
                return False
        except Exception as e:
            logger.error(f"Error al conectar: {e}")
            return False
    
    def desconectar(self):
        """Desconectar (limpieza)"""
        self.conectado = False
        logger.info("Desconectado")
    
    def enviar_texto(self, contenido: str) -> bool:
        """
        Enviar texto directamente a la impresora
        
        Args:
            contenido: Texto a imprimir
            
        Returns:
            bool: Éxito
        """
        if not self.conectado:
            logger.error("Impresora no conectada")
            return False
        
        try:
            if not sys.platform.startswith('win'):
                logger.error("Impresión RAW soportada solo en Windows")
                return False

            class DOC_INFO_1(ctypes.Structure):
                _fields_ = [
                    ("pDocName", wintypes.LPWSTR),
                    ("pOutputFile", wintypes.LPWSTR),
                    ("pDatatype", wintypes.LPWSTR),
                ]

            winspool = ctypes.WinDLL("winspool.drv")

            open_printer = winspool.OpenPrinterW
            close_printer = winspool.ClosePrinter
            start_doc_printer = winspool.StartDocPrinterW
            end_doc_printer = winspool.EndDocPrinter
            start_page_printer = winspool.StartPagePrinter
            end_page_printer = winspool.EndPagePrinter
            write_printer = winspool.WritePrinter

            open_printer.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
            open_printer.restype = wintypes.BOOL
            close_printer.argtypes = [wintypes.HANDLE]
            close_printer.restype = wintypes.BOOL
            start_doc_printer.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
            start_doc_printer.restype = wintypes.DWORD
            end_doc_printer.argtypes = [wintypes.HANDLE]
            end_doc_printer.restype = wintypes.BOOL
            start_page_printer.argtypes = [wintypes.HANDLE]
            start_page_printer.restype = wintypes.BOOL
            end_page_printer.argtypes = [wintypes.HANDLE]
            end_page_printer.restype = wintypes.BOOL
            write_printer.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
            write_printer.restype = wintypes.BOOL

            texto_normalizado = (contenido or "").replace("\r\n", "\n").replace("\n", "\r\n")
            datos = texto_normalizado.encode("cp850", errors="replace")

            handle = wintypes.HANDLE()
            if not open_printer(self.nombre_impresora, ctypes.byref(handle), None):
                raise ctypes.WinError()

            try:
                doc_info = DOC_INFO_1("HTF Ticket", None, "RAW")
                job = start_doc_printer(handle, 1, ctypes.byref(doc_info))
                if job == 0:
                    raise ctypes.WinError()

                try:
                    if not start_page_printer(handle):
                        raise ctypes.WinError()

                    try:
                        bytes_written = wintypes.DWORD(0)
                        buffer = ctypes.create_string_buffer(datos)
                        ok_write = write_printer(
                            handle,
                            ctypes.cast(buffer, wintypes.LPVOID),
                            len(datos),
                            ctypes.byref(bytes_written),
                        )
                        if not ok_write:
                            raise ctypes.WinError()
                        if bytes_written.value != len(datos):
                            logger.error(
                                f"Escritura incompleta en impresora: {bytes_written.value}/{len(datos)} bytes"
                            )
                            return False
                    finally:
                        end_page_printer(handle)
                finally:
                    end_doc_printer(handle)
            finally:
                close_printer(handle)

            logger.info("✅ Texto enviado a impresora (RAW)")
            return True
        
        except Exception as e:
            logger.error(f"Error al enviar texto: {e}")
            return False
    
    def imprimir_archivo(self, ruta_archivo: str) -> bool:
        """
        Imprimir archivo de texto
        
        Args:
            ruta_archivo: Ruta del archivo a imprimir
            
        Returns:
            bool: Éxito
        """
        if not self.conectado:
            logger.error("Impresora no conectada")
            return False
        
        try:
            with open(ruta_archivo, 'r', encoding='utf-8', errors='replace') as archivo:
                contenido = archivo.read()

            if not self.enviar_texto(contenido):
                return False
            
            logger.info(f"✅ Archivo impreso: {ruta_archivo}")
            return True
        except Exception as e:
            logger.error(f"Error al imprimir archivo: {e}")
            return False


class TicketPrinterWindows(WindowsPrinterManager):
    """Impresora especializada en tickets para Windows"""
    
    def __init__(self, nombre_impresora: str = IMPRESORA_POR_DEFECTO,
                 ancho_linea: Optional[int] = None):
        super().__init__(nombre_impresora)
        # Mismo ancho que usa la vista previa en pantalla (ver obtener_ancho_ticket).
        self.ancho_linea = ancho_linea or obtener_ancho_ticket()

    def imprimir_ticket(self, datos_ticket: Dict) -> bool:
        """
        Imprimir ticket completo
        
        Args:
            datos_ticket: Diccionario con datos del ticket
            
        Returns:
            bool: Éxito
        """
        if not self.conectado:
            logger.error("Impresora no conectada")
            return False
        
        try:
            # Generar contenido del ticket
            contenido = self._generar_ticket(datos_ticket)
            
            # Enviar a impresora
            return self.enviar_texto(contenido)
        except Exception as e:
            logger.error(f"Error al imprimir ticket: {e}")
            return False
    
    def imprimir_corte(self, datos_corte: Dict) -> bool:
        """
        Imprimir el ticket de corte de caja (resumen de ventas del turno).

        Args:
            datos_corte: ver generar_ticket_corte()

        Returns:
            bool: Éxito
        """
        if not self.conectado:
            logger.error("[ERROR] Impresora no conectada")
            return False

        try:
            return self.enviar_texto(generar_ticket_corte(datos_corte, self.ancho_linea))
        except Exception as e:
            logger.error(f"[ERROR] Error al imprimir corte de caja: {e}")
            return False

    def _generar_ticket(self, datos: Dict) -> str:
        """Generar contenido del ticket (delegado al generador compartido)."""
        return generar_ticket_venta(datos, self.ancho_linea)


# =============================================================================
# GENERADORES DE TICKET (compartidos por la vista previa y la impresión)
# =============================================================================

def _envolver(texto: str, ancho: int) -> List[str]:
    """
    Partir un texto en líneas de como mucho `ancho` columnas, cortando por
    palabras. Antes los nombres se truncaban a 22 caracteres, lo que dejaba
    ilegible a 1 de cada 4 productos del catálogo
    ('ALEGRIA GRANDE MIEL PILONCILLO' -> 'ALEGRIA GRANDE MIEL PI').
    """
    texto = (texto or "").strip()
    if not texto:
        return [""]

    lineas, actual = [], ""
    for palabra in texto.split():
        # Palabra sola más larga que el renglón: se parte a lo bruto.
        while len(palabra) > ancho:
            if actual:
                lineas.append(actual)
                actual = ""
            lineas.append(palabra[:ancho])
            palabra = palabra[ancho:]
        if not actual:
            actual = palabra
        elif len(actual) + 1 + len(palabra) <= ancho:
            actual += " " + palabra
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _fila(izquierda: str, derecha: str, ancho: int) -> str:
    """Una línea con texto a la izquierda e importe pegado a la derecha."""
    espacios = max(1, ancho - len(izquierda) - len(derecha))
    return f"{izquierda}{' ' * espacios}{derecha}"


def generar_ticket_venta(datos: Dict, ancho: Optional[int] = None) -> str:
    """
    Ticket de una venta. Lo usan por igual la vista previa en pantalla y la
    impresión, para que el cajero vea exactamente lo que va a salir en papel.
    """
    ancho = ancho or obtener_ancho_ticket()

    ticket = "=" * ancho + "\n"
    ticket += f"{datos.get('tienda', 'HTF GIMNASIO').center(ancho)}\n"
    ticket += f"{datos.get('subtitulo', 'PUNTO DE VENTA').center(ancho)}\n"
    ticket += "=" * ancho + "\n\n"

    ticket += f"Ticket: #{datos.get('numero_ticket', 0):06d}\n"
    ticket += f"Fecha: {datos.get('fecha_hora', '')}\n"
    if datos.get('cajero'):
        for linea in _envolver(f"Cajero: {datos.get('cajero')}", ancho):
            ticket += linea + "\n"
    ticket += "-" * ancho + "\n\n"

    for producto in datos.get('productos', []):
        for linea in _envolver(str(producto.get('nombre', '')), ancho):
            ticket += linea + "\n"
        cantidad_precio = f"{float(producto.get('cantidad', 0)):.0f}x ${float(producto.get('precio', 0)):.2f}"
        subtotal = f"${float(producto.get('subtotal', 0)):.2f}"
        ticket += _fila(cantidad_precio, subtotal, ancho) + "\n"

    ticket += "-" * ancho + "\n"
    ticket += _fila("TOTAL:", f"${float(datos.get('total', 0)):.2f}", ancho) + "\n"
    ticket += "=" * ancho + "\n\n"

    ticket += f"{str(datos.get('metodo_pago', 'EFECTIVO')).center(ancho)}\n"
    ticket += "-" * ancho + "\n\n"

    ticket += "¡Gracias por su compra!".center(ancho) + "\n"
    ticket += "Vuelva pronto".center(ancho) + "\n"
    ticket += "=" * ancho + "\n"

    return ticket


def generar_ticket_corte(datos: Dict, ancho: Optional[int] = None) -> str:
    """
    Ticket de corte de caja: resumen de las ventas del turno que se cierra.

    Claves esperadas en `datos`:
        turno (int), cajero (str), fecha_hora (str),
        fecha_apertura (str, opcional),
        num_ventas (int), total_efectivo, total_transferencia, total_ventas,
        monto_inicial, total_esperado, total_contado, diferencia (numéricos,
        todos opcionales: si faltan, esa sección no se imprime).
    """
    ancho = ancho or obtener_ancho_ticket()

    ticket = "=" * ancho + "\n"
    ticket += "HTF GIMNASIO".center(ancho) + "\n"
    ticket += "CORTE DE CAJA".center(ancho) + "\n"
    ticket += "=" * ancho + "\n\n"

    if datos.get('turno') is not None:
        ticket += f"Turno: #{datos.get('turno')}\n"
    if datos.get('cajero'):
        for linea in _envolver(f"Cajero: {datos.get('cajero')}", ancho):
            ticket += linea + "\n"
    if datos.get('fecha_apertura'):
        ticket += f"Apertura: {datos.get('fecha_apertura')}\n"
    ticket += f"Cierre:   {datos.get('fecha_hora', '')}\n"
    ticket += "-" * ancho + "\n\n"

    ticket += "RESUMEN DE VENTAS".center(ancho) + "\n"
    ticket += "-" * ancho + "\n"
    ticket += _fila("Ventas del turno:", str(datos.get('num_ventas', 0)), ancho) + "\n"
    ticket += _fila("Efectivo:", f"${float(datos.get('total_efectivo', 0)):.2f}", ancho) + "\n"
    ticket += _fila("Transferencia:", f"${float(datos.get('total_transferencia', 0)):.2f}", ancho) + "\n"
    ticket += "-" * ancho + "\n"
    ticket += _fila("TOTAL VENDIDO:", f"${float(datos.get('total_ventas', 0)):.2f}", ancho) + "\n"
    ticket += "=" * ancho + "\n\n"

    # Arqueo de efectivo: solo si se proporcionaron los datos del conteo.
    if datos.get('total_contado') is not None:
        ticket += "ARQUEO DE EFECTIVO".center(ancho) + "\n"
        ticket += "-" * ancho + "\n"
        ticket += _fila("Monto inicial:", f"${float(datos.get('monto_inicial', 0)):.2f}", ancho) + "\n"
        ticket += _fila("+ Ventas efectivo:", f"${float(datos.get('total_efectivo', 0)):.2f}", ancho) + "\n"
        ticket += _fila("Esperado en caja:", f"${float(datos.get('total_esperado', 0)):.2f}", ancho) + "\n"
        ticket += _fila("Contado:", f"${float(datos.get('total_contado', 0)):.2f}", ancho) + "\n"
        ticket += "-" * ancho + "\n"

        diferencia = float(datos.get('diferencia', 0))
        if diferencia > 0.001:
            etiqueta = "SOBRANTE:"
        elif diferencia < -0.001:
            etiqueta = "FALTANTE:"
        else:
            etiqueta = "DIFERENCIA:"
        ticket += _fila(etiqueta, f"${abs(diferencia):.2f}", ancho) + "\n"
        ticket += "=" * ancho + "\n\n"

    ticket += "Firma: ____________________".center(ancho) + "\n\n"
    ticket += "=" * ancho + "\n"

    return ticket


# ===== EJEMPLO =====

if __name__ == "__main__":
    # Obtener impresoras
    print("\nImpresoras disponibles:")
    impresoras = WindowsPrinterManager.obtener_impresoras_instaladas()
    for i, imp in enumerate(impresoras, 1):
        print(f"{i}. {imp}")
    
    # Buscar impresora Generic
    print("\nBuscando impresora Generic...")
    nombre = WindowsPrinterManager.obtener_impresora_por_tipo("Generic")
    
    if nombre:
        print(f"✅ Encontrada: {nombre}")
        
        # Crear impresora de tickets
        printer = TicketPrinterWindows(nombre)
        
        if printer.conectar():
            # Datos de prueba
            datos = {
                'tienda': 'HTF GIMNASIO',
                'subtitulo': 'PUNTO DE VENTA',
                'numero_ticket': 1001,
                'fecha_hora': '19/12/2025 15:30',
                'cajero': 'TEST',
                'productos': [
                    {'nombre': 'Bebida Energética', 'cantidad': 2, 'precio': 5.00, 'subtotal': 10.00},
                    {'nombre': 'Toalla Microfibra', 'cantidad': 1, 'precio': 15.00, 'subtotal': 15.00},
                ],
                'total': 25.00,
                'metodo_pago': 'EFECTIVO'
            }
            
            if printer.imprimir_ticket(datos):
                print("✅ Ticket impreso exitosamente")
            else:
                print("❌ Error al imprimir")
            
            printer.desconectar()
    else:
        print("❌ No se encontró impresora Generic")
