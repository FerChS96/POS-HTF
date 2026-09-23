"""
Monitor de Entradas - Versión FastAPI
Recibe notificaciones de entrada vía FastAPI desde el torniquete
"""

from PySide6.QtCore import QObject, QTimer, Signal
import logging
from datetime import datetime
import queue
import threading
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import socket

# Importar módulos de FastAPI al nivel superior para que PyInstaller los detecte
try:
    from utils.fastapi_server_entradas import (
        get_entrada_queue,
        FastAPIServerThread,
        resolver_listen_host,
        log_configuracion_seguridad
    )
    FASTAPI_DISPONIBLE = True
except ImportError as e:
    logging.error(f"Error importando utils.fastapi_server_entradas: {e}")
    FASTAPI_DISPONIBLE = False
    get_entrada_queue = None
    FastAPIServerThread = None
    resolver_listen_host = None
    log_configuracion_seguridad = None


class FastAPIMonitorThread(threading.Thread):
    """Hilo separado para monitorear la cola de entradas del servidor FastAPI"""
    
    def __init__(self, entrada_queue, callback):
        super().__init__(daemon=True)
        self.entrada_queue = entrada_queue
        self.callback = callback
        self.running = False
        
    def run(self):
        """Monitorear la cola de entradas"""
        self.running = True
        logging.info("[OK] Iniciando monitor de cola FastAPI")
        
        while self.running:
            try:
                # Esperar por nuevas entradas (timeout de 1 segundo para poder detener)
                entrada_data = self.entrada_queue.get(timeout=1.0)
                
                if entrada_data and self.running:
                    # Llamar al callback con los datos de entrada
                    self.callback(entrada_data)
                    
            except queue.Empty:
                # No hay entradas, continuar esperando
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"[ERROR] Error en monitor de cola: {e}")
                    
    def stop(self):
        """Detener el monitor"""
        logging.info("[SHUTDOWN] Deteniendo monitor de cola")
        self.running = False


class MonitorEntradasFastAPI(QObject):
    """
    Monitorea nuevas entradas usando FastAPI.
    Recibe notificaciones HTTP POST desde el torniquete con el ID de entrada.
    """

    nueva_entrada_detectada = Signal(dict)  # Emite los datos de la entrada y del miembro

    def __init__(self, postgres_manager, host="127.0.0.1", port=8001, listen_host=None):
        """
        Args:
            postgres_manager: Instancia de PostgresManager para manejar la base de datos
            host: Host donde corre el servidor FastAPI (para conectarse)
            port: Puerto donde corre el servidor FastAPI (8001 por defecto para evitar conflicto con IIS)
            listen_host: Interface donde escucha el servidor. Si es None (recomendado)
                se resuelve según la configuración de seguridad: 0.0.0.0 solo si
                hay TORNIQUETE_API_TOKEN configurado, 127.0.0.1 en caso contrario.
                Se puede forzar con la variable TORNIQUETE_LISTEN_HOST.
        """
        super().__init__()
        self.postgres_manager = postgres_manager
        self.host = host
        self.port = port
        if listen_host:
            self.listen_host = listen_host
        elif resolver_listen_host:
            self.listen_host = resolver_listen_host()
        else:
            self.listen_host = "127.0.0.1"

        # Cola de entradas (compartida con el servidor FastAPI)
        self.entrada_queue = None
        
        # Hilo de monitoreo
        self.monitor_thread = None
        
        # Servidor FastAPI
        self.server_thread = None

        # Estado del monitor
        self.activo = False
        
        # Timer para chequeo periódico de cola (fallback)
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_queue)
        self.timer.setInterval(500)  # Cada 500ms

        logging.info(f"Monitor de entradas FastAPI inicializado (localhost:{port})")
    
    @staticmethod
    def _build_entrada_data(entrada, include_foto=False):
        """Construir diccionario con datos de entrada y miembro.
        
        Args:
            entrada: Diccionario con datos de entrada y miembros relacionados
            include_foto: Si incluir campos de foto (foto, foto_url)
            
        Returns:
            Diccionario con estructura esperada para notificaciones
        """
        miembro = entrada.get('miembros', {})
        
        entrada_data = {
            'id_entrada': entrada.get('id_entrada'),
            'id_miembro': entrada.get('id_miembro'),
            'tipo_acceso': entrada.get('tipo_acceso'),
            'fecha_entrada': entrada.get('fecha_entrada'),
            'area_accedida': entrada.get('area_accedida'),
            'dispositivo_registro': entrada.get('dispositivo_registro'),
            'notas': entrada.get('notas'),
            'nombres': miembro.get('nombres', ''),
            'apellido_paterno': miembro.get('apellido_paterno', ''),
            'apellido_materno': miembro.get('apellido_materno', ''),
            'telefono': miembro.get('telefono', ''),
            'email': miembro.get('email', ''),
            'codigo_qr': miembro.get('codigo_qr', ''),
            'activo': miembro.get('activo', True),
            'fecha_registro': miembro.get('fecha_registro', ''),
            'fecha_nacimiento': miembro.get('fecha_nacimiento', '')
        }
        
        # Incluir foto solo si se solicita explícitamente
        if include_foto:
            entrada_data.update({
                'foto': miembro.get('foto', None),
                'foto_url': miembro.get('foto_url', None)
            })
        
        return entrada_data

    @staticmethod
    def _describir_foto_url(foto_url):
        """Generar un resumen seguro de la URL de foto para diagnóstico."""
        if not foto_url:
            return "sin_url"

        try:
            parsed = urlparse(foto_url)
            query = parse_qs(parsed.query)
            query_keys = sorted(query.keys())
            token_value = query.get('token', [''])[0]
            token_len = len(token_value) if token_value else 0
            signed = bool(token_value) or '/sign/' in parsed.path

            return (
                f"host={parsed.netloc}, path={parsed.path}, "
                f"query_keys={query_keys}, signed={signed}, token_len={token_len}"
            )
        except Exception as e:
            return f"url_invalida: {e}"
    
    def iniciar(self):
        """Iniciar el monitoreo vía FastAPI"""
        if self.activo:
            logging.warning("Monitor ya está activo")
            return

        try:
            # Verificar que FastAPI esté disponible
            if not FASTAPI_DISPONIBLE:
                raise ImportError("Módulo fastapi_server_entradas no disponible")
            
            # Obtener la cola del servidor FastAPI
            self.entrada_queue = get_entrada_queue()

            # Si ya hay un servidor respondiendo en este puerto (misma app en otra instancia
            # o servidor previamente iniciado), no intentar iniciar otro para evitar WinError 10048.
            servidor_ya_activo = self._servidor_responde()
            if servidor_ya_activo:
                logging.info(f"[SERVIDOR] Ya existe un servidor FastAPI activo en {self.host}:{self.port}")
                # El hilo del servidor no arrancó aquí, así que dejamos el
                # estado de seguridad en el log de todos modos.
                if log_configuracion_seguridad:
                    log_configuracion_seguridad(self.listen_host, self.port)

            # Si el puerto está ocupado pero NO responde /health de HTF, está en conflicto.
            if (not servidor_ya_activo) and self._puerto_ocupado():
                raise RuntimeError(
                    f"Puerto {self.port} ocupado por otro proceso. "
                    f"El torniquete requiere este puerto fijo; libera el puerto 8001."
                )
            
            # Iniciar servidor FastAPI en hilo separado si no está corriendo
            if (not servidor_ya_activo) and (not self.server_thread or not self.server_thread.is_alive()):
                self.server_thread = FastAPIServerThread(self.listen_host, self.port)
                self.server_thread.start()
                logging.info(f"[SERVIDOR] FastAPI escuchando en {self.listen_host}:{self.port}")
                
                # Dar tiempo al servidor para iniciarse completamente
                import time
                time.sleep(1)

                # Validar arranque real para no reportar estado falso de "iniciado"
                if self.server_thread.startup_error:
                    raise RuntimeError(f"Servidor FastAPI no inició: {self.server_thread.startup_error}")

                if not self._servidor_responde():
                    raise RuntimeError("Servidor FastAPI no responde en /health después del arranque")
            
            # Iniciar hilo de monitoreo de cola
            self.monitor_thread = FastAPIMonitorThread(
                self.entrada_queue, 
                self._on_entrada_recibida
            )
            self.monitor_thread.start()
            
            # Iniciar timer de chequeo periódico (fallback)
            self.timer.start()

            self.activo = True

            logging.info("[OK] Monitor de entradas FastAPI iniciado")
            logging.info(f"[INFO] Esperando peticiones POST en http://{self.host}:{self.port}/entrada")

        except Exception as e:
            logging.error(f"[ERROR] Error iniciando monitor FastAPI: {e}")
            import traceback
            logging.error(traceback.format_exc())
            raise

    def _servidor_responde(self):
        """Verificar rápidamente si el servidor FastAPI responde en /health."""
        try:
            url = f"http://{self.host}:{self.port}/health"
            with urllib.request.urlopen(url, timeout=1.0) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, Exception):
            return False

    def _puerto_ocupado(self):
        """Verificar si el puerto tiene algún listener TCP activo."""
        try:
            with socket.create_connection((self.host, self.port), timeout=0.5):
                return True
        except Exception:
            return False
    
    def detener(self):
        """Detener el monitoreo"""
        if not self.activo:
            return

        logging.info("Deteniendo monitor de entradas FastAPI...")

        # Detener timer
        self.timer.stop()
        
        # Detener hilo de monitoreo
        if self.monitor_thread:
            try:
                self.monitor_thread.stop()
                self.monitor_thread.join(timeout=5)
            except Exception as e:
                logging.error(f"Error deteniendo monitor thread: {e}")
            finally:
                self.monitor_thread = None

        # Nota: No detenemos el servidor FastAPI ya que puede estar siendo usado
        # por otros componentes. El servidor se detiene cuando el proceso termina.

        self.activo = False

        logging.info("Monitor de entradas FastAPI detenido")
    
    def _check_queue(self):
        """Chequear la cola periódicamente (método alternativo/fallback)"""
        if not self.activo or not self.entrada_queue:
            return
            
        try:
            # Intentar obtener entrada sin bloquear
            while not self.entrada_queue.empty():
                entrada_data = self.entrada_queue.get_nowait()
                self._on_entrada_recibida(entrada_data)
        except queue.Empty:
            pass
        except Exception as e:
            logging.error(f"[ERROR] Error chequeando cola: {e}")
    
    def _on_entrada_recibida(self, entrada_data):
        """
        Callback cuando se recibe una nueva entrada del torniquete.
        
        Args:
            entrada_data: Dict con {id_entrada, dispositivo, timestamp}
        """
        try:
            if not self.activo:
                return
                
            id_entrada = entrada_data.get('id_entrada')
            dispositivo = entrada_data.get('dispositivo', 'torniquete')

            logging.info(f"[ENTRADA] Procesando entrada ID: {id_entrada} desde {dispositivo}")

            # Consultar datos completos de la entrada en la base de datos
            entrada_completa = self._consultar_entrada(id_entrada)
            
            if entrada_completa:
                # Emitir señal con los datos completos
                self.nueva_entrada_detectada.emit(entrada_completa)
                
                nombre_completo = f"{entrada_completa['nombres']} {entrada_completa['apellido_paterno']}"
                logging.info(f"[OK] Nueva entrada procesada - ID: {id_entrada}, Miembro: {nombre_completo}")
            else:
                logging.warning(f"[WARN] No se encontraron datos para entrada ID: {id_entrada}")

        except Exception as e:
            logging.error(f"[ERROR] Error procesando entrada recibida: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def _consultar_entrada(self, id_entrada):
        """
        Consultar datos completos de una entrada en la base de datos.
        
        Args:
            id_entrada: ID de la entrada a consultar
            
        Returns:
            Dict con datos de entrada y miembro, o None si no se encuentra
        """
        try:
            # 1. Primero consultar los datos de la entrada
            response_entrada = self.postgres_manager.client.table('registro_entradas').select(
                'id_entrada, id_miembro, tipo_acceso, fecha_entrada, area_accedida, '
                'dispositivo_registro, notas'
            ).eq('id_entrada', id_entrada).execute()
            
            if not response_entrada.data or len(response_entrada.data) == 0:
                return None
            
            entrada = response_entrada.data[0]
            id_miembro = entrada.get('id_miembro')
            
            # 2. Luego consultar datos del miembro usando id_miembro
            response_miembro = self.postgres_manager.client.table('miembros').select(
                'nombres, apellido_paterno, apellido_materno, telefono, email, '
                'codigo_qr, activo, fecha_registro, fecha_nacimiento, foto_url'
            ).eq('id_miembro', id_miembro).execute()
            
            if not response_miembro.data or len(response_miembro.data) == 0:
                # Si no hay datos del miembro, devolver solo datos de entrada
                miembro = {}
                logging.warning(
                    f"[FOTO_DIAG] Sin datos de miembro para id_miembro={id_miembro} "
                    f"(entrada={id_entrada})"
                )
            else:
                miembro = response_miembro.data[0]

            foto_url = miembro.get('foto_url') if miembro else None
            if foto_url:
                descripcion_url = self._describir_foto_url(foto_url)
                logging.info(
                    f"[FOTO_DIAG] entrada={id_entrada} miembro={id_miembro} "
                    f"foto_url_detectada -> {descripcion_url}"
                )
            else:
                logging.warning(
                    f"[FOTO_DIAG] entrada={id_entrada} miembro={id_miembro} "
                    "sin foto_url en consulta de miembros"
                )
            
            # Construir diccionario con estructura esperada
            entrada_data = {
                'id_entrada': entrada.get('id_entrada'),
                'id_miembro': entrada.get('id_miembro'),
                'tipo_acceso': entrada.get('tipo_acceso'),
                'fecha_entrada': entrada.get('fecha_entrada'),
                'area_accedida': entrada.get('area_accedida'),
                'dispositivo_registro': entrada.get('dispositivo_registro'),
                'notas': entrada.get('notas', ''),
                'nombres': miembro.get('nombres', ''),
                'apellido_paterno': miembro.get('apellido_paterno', ''),
                'apellido_materno': miembro.get('apellido_materno', ''),
                'telefono': miembro.get('telefono', ''),
                'email': miembro.get('email', ''),
                'codigo_qr': miembro.get('codigo_qr', ''),
                'activo': miembro.get('activo', True),
                'fecha_registro': miembro.get('fecha_registro', ''),
                'fecha_nacimiento': miembro.get('fecha_nacimiento', ''),
                'foto': None,  # Campo foto no se usa
                'foto_url': miembro.get('foto_url')  # Obtenido de tabla miembros
            }
            
            return entrada_data
                
        except Exception as e:
            logging.error(f"[ERROR] Error consultando entrada {id_entrada}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None
    
    def reiniciar(self):
        """Reiniciar el monitor"""
        was_active = self.activo

        if was_active:
            self.detener()
            # Pequeña pausa para asegurar cierre limpio
            import time
            time.sleep(0.5)
            self.iniciar()

        logging.info("Monitor de entradas FastAPI reiniciado")
