"""
Módulo de Impresión ESC/POS para impresoras térmicas
Soporta impresoras como EC-PM-58110-USB
"""

import logging
from typing import List, Dict, Optional
import serial
from serial.tools import list_ports
import time
from datetime import datetime
logger = logging.getLogger(__name__)


class EscPosDriver:
    """Driver para impresoras ESC/POS"""
    
    # Comandos ESC/POS
    ESC = b'\x1b'
    GS = b'\x1d'
    DLE = b'\x10'
    EOT = b'\x04'
    
    # Modos de alineación
    ALIGN_LEFT = b'\x1b\x61\x00'
    ALIGN_CENTER = b'\x1b\x61\x01'
    ALIGN_RIGHT = b'\x1b\x61\x02'
    
    # Tamaños de fuente
    FONT_NORMAL = b'\x1b\x21\x00'
    FONT_DOUBLE_WIDTH = b'\x1b\x21\x20'
    FONT_DOUBLE_HEIGHT = b'\x1b\x21\x10'
    FONT_LARGE = b'\x1b\x21\x30'  # Double Width y Height
    
    # Estilos
    BOLD_ON = b'\x1b\x45\x01'
    BOLD_OFF = b'\x1b\x45\x00'
    
    # Corte
    CUT_PAPER = b'\x1d\x56\x00'
    PARTIAL_CUT = b'\x1d\x56\x01'
    
    # Caja registradora
    OPEN_CASH_DRAWER = b'\x1b\x70\x00\x0a\xff'
    
    def __init__(self, puerto: str = "COM1", baudrate: int = 115200, timeout: float = 2.0):
        """
        Inicializar conexión con impresora
        
        Args:
            puerto: Puerto COM (ej: COM1, COM3)
            baudrate: Velocidad de comunicación
            timeout: Timeout de conexión
        """
        self.puerto = puerto
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = timeout
        self.ser = None
        self.conectado = False
        self.hubo_error_envio = False
        
    def conectar(self) -> bool:
        """Conectar con la impresora"""
        try:
            self.ser = serial.Serial(
                port=self.puerto,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            self.conectado = True
            logger.info(f"✅ Conectado a impresora en {self.puerto}")
            return True
        except serial.SerialException as e:
            logger.error(f"❌ Error de conexión: {e}")
            self.conectado = False
            return False
    
    def desconectar(self):
        """Desconectar de la impresora"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.conectado = False
            logger.info("Desconectado de la impresora")
    
    def enviar_comando(self, comando: bytes) -> bool:
        """Enviar comando a la impresora"""
        if not self.conectado:
            self.hubo_error_envio = True
            logger.warning("Impresora no conectada")
            return False
        
        try:
            self.ser.write(comando)
            time.sleep(0.1)
            return True
        except serial.SerialTimeoutException as e:
            self.hubo_error_envio = True
            logger.error(f"Timeout al escribir en impresora ({self.puerto}): {e}")
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
            self.conectado = False
            return False
        except Exception as e:
            self.hubo_error_envio = True
            logger.error(f"Error al enviar comando: {e}")
            return False
    
    def nueva_linea(self, cantidad: int = 1):
        """Agregar líneas en blanco"""
        self.enviar_comando(b'\n' * cantidad)
    
    def alineacion(self, modo: bytes):
        """Establecer alineación"""
        self.enviar_comando(modo)
    
    def alinear_centro(self):
        """Alinear texto al centro"""
        self.alineacion(self.ALIGN_CENTER)
    
    def alinear_izquierda(self):
        """Alinear texto a la izquierda"""
        self.alineacion(self.ALIGN_LEFT)
    
    def alinear_derecha(self):
        """Alinear texto a la derecha"""
        self.alineacion(self.ALIGN_RIGHT)
    
    def fuente_normal(self):
        """Establecer fuente normal"""
        self.enviar_comando(self.FONT_NORMAL)
    
    def fuente_grande(self):
        """Establecer fuente grande"""
        self.enviar_comando(self.FONT_LARGE)
    
    def fuente_doble_ancho(self):
        """Establecer fuente doble ancho"""
        self.enviar_comando(self.FONT_DOUBLE_WIDTH)
    
    def fuente_doble_altura(self):
        """Establecer fuente doble altura"""
        self.enviar_comando(self.FONT_DOUBLE_HEIGHT)
    
    def negrita_on(self):
        """Activar negrita"""
        self.enviar_comando(self.BOLD_ON)
    
    def negrita_off(self):
        """Desactivar negrita"""
        self.enviar_comando(self.BOLD_OFF)
    
    def linea_punteada(self):
        """Imprimir línea punteada"""
        ancho = getattr(self, 'ancho_linea', 32)
        self.texto("." * ancho)
    
    def linea_solida(self):
        """Imprimir línea sólida"""
        ancho = getattr(self, 'ancho_linea', 32)
        self.texto("=" * ancho)
    
    def linea_guiones(self):
        """Imprimir línea con guiones"""
        ancho = getattr(self, 'ancho_linea', 32)
        self.texto("-" * ancho)
    
    def texto(self, contenido: str, encoding: str = 'utf-8'):
        """Imprimir texto"""
        try:
            self.enviar_comando(contenido.encode(encoding) + b'\n')
        except Exception as e:
            logger.error(f"Error al imprimir texto: {e}")
    
    def cortar_papel(self, parcial: bool = False):
        """Cortar el papel"""
        comando = self.PARTIAL_CUT if parcial else self.CUT_PAPER
        self.enviar_comando(comando)
    
    def abrir_caja_registradora(self):
        """Abrir la caja registradora"""
        self.enviar_comando(self.OPEN_CASH_DRAWER)
        logger.info("Caja registradora abierta")
    
    def inicializar(self):
        """Inicializar la impresora"""
        self.enviar_comando(b'\x1b\x40')
        logger.info("Impresora inicializada")
    
    def reset(self):
        """Reset de la impresora"""
        self.inicializar()


class TicketPrinter(EscPosDriver):
    """Impresora especializada para tickets"""
    
    def __init__(self, puerto: str = "COM1"):
        super().__init__(puerto)
        self.ancho_linea = 32  # 58 mm

    @staticmethod
    def obtener_puertos_preferidos(puerto_preferido: str = "COM3") -> List[str]:
        """Retornar puertos COM disponibles priorizando uno preferido."""
        preferido = (puerto_preferido or "").strip().upper()

        try:
            detectados = [p.device.upper() for p in list_ports.comports() if p.device]
        except Exception as e:
            logger.warning(f"No se pudieron listar puertos COM: {e}")
            detectados = []

        puertos = []
        if preferido and preferido in detectados:
            puertos.append(preferido)

        for puerto in detectados:
            if puerto not in puertos:
                puertos.append(puerto)

        return puertos
    
    def imprimir_titulo_tienda(self, nombre_tienda: str, subtitulo: str = ""):
        """Imprimir encabezado de tienda"""
        self.alinear_centro()
        self.fuente_grande()
        self.negrita_on()
        self.texto(nombre_tienda.center(self.ancho_linea))
        self.negrita_off()
        
        if subtitulo:
            self.fuente_normal()
            self.texto(subtitulo.center(self.ancho_linea))
        
        self.linea_solida()
    
    def imprimir_encabezado_ticket(self, numero_ticket: int, fecha_hora: str = None, cajero: str = ""):
        """Imprimir encabezado del ticket"""
        if not fecha_hora:
            fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        self.alinear_izquierda()
        self.fuente_normal()
        self.texto(f"Ticket: #{numero_ticket:06d}")
        self.texto(f"Fecha: {fecha_hora}")
        if cajero:
            self.texto(f"Cajero: {cajero}")
        self.linea_guiones()
    
    def imprimir_producto(self, nombre: str, cantidad: float, precio: float, subtotal: float):
        """Imprimir línea de producto"""
        self.alinear_izquierda()
        self.fuente_normal()
        
        # Nombre del producto (limitado para ticket de 58 mm)
        nombre_corto = nombre[:22]
        self.texto(nombre_corto)
        
        # Cantidad, precio y subtotal
        cantidad_str = f"{cantidad:.0f}x ${precio:.2f}"
        subtotal_str = f"${subtotal:.2f}"
        
        espacios = max(1, self.ancho_linea - len(cantidad_str) - len(subtotal_str))
        linea = cantidad_str + " " * espacios + subtotal_str
        self.texto(linea)
    
    def imprimir_total(self, total: float, metodo_pago: str = "EFECTIVO"):
        """Imprimir total y método de pago"""
        self.linea_guiones()
        self.alinear_derecha()
        self.fuente_doble_altura()
        self.negrita_on()
        
        total_str = f"${total:.2f}"
        espacios_totales = self.ancho_linea - len("TOTAL: ") - len(total_str)
        self.texto("TOTAL: " + " " * espacios_totales + total_str)
        
        self.negrita_off()
        self.fuente_normal()
        self.linea_solida()
        
        # Método de pago
        self.alinear_centro()
        self.fuente_doble_ancho()
        self.texto(metodo_pago)
        self.fuente_normal()
    
    def imprimir_pie(self):
        """Imprimir pie del ticket"""
        self.nueva_linea()
        self.alinear_centro()
        self.fuente_normal()
        self.texto("¡Gracias por su compra!")
        self.texto("Vuelva pronto")
        self.linea_solida()
        self.nueva_linea(3)
    
    def imprimir_ticket(self, datos_ticket: Dict) -> bool:
        """
        Imprimir ticket completo
        
        Args:
            datos_ticket: Diccionario con:
                - numero_ticket: int
                - fecha_hora: str (opcional)
                - cajero: str (opcional)
                - tienda: str
                - productos: List[Dict] con {nombre, cantidad, precio, subtotal}
                - total: float
                - metodo_pago: str (default: "EFECTIVO")
                - abrir_caja: bool (default: False)
                - cortar: bool (default: True)
        
        Returns:
            bool: Éxito de impresión
        """
        if not self.conectado:
            logger.error("Impresora no conectada")
            return False
        
        try:
            self.hubo_error_envio = False
            self.inicializar()
            
            # Encabezado
            self.imprimir_titulo_tienda(
                datos_ticket.get('tienda', 'HTF GIMNASIO'),
                datos_ticket.get('subtitulo', 'PUNTO DE VENTA')
            )
            
            # Info del ticket
            self.imprimir_encabezado_ticket(
                datos_ticket.get('numero_ticket', 0),
                datos_ticket.get('fecha_hora'),
                datos_ticket.get('cajero', '')
            )
            
            # Productos
            self.nueva_linea()
            for producto in datos_ticket.get('productos', []):
                self.imprimir_producto(
                    producto['nombre'],
                    producto['cantidad'],
                    producto['precio'],
                    producto['subtotal']
                )
            
            # Total
            self.nueva_linea()
            self.imprimir_total(
                datos_ticket['total'],
                datos_ticket.get('metodo_pago', 'EFECTIVO')
            )
            
            # Pie
            self.imprimir_pie()
            
            # Acciones finales
            if datos_ticket.get('abrir_caja', False):
                self.abrir_caja_registradora()
            
            if datos_ticket.get('cortar', True):
                self.cortar_papel()

            if self.hubo_error_envio:
                logger.error("❌ Ticket con errores de envío ESC/POS")
                return False
            
            logger.info("✅ Ticket impreso correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error al imprimir ticket: {e}")
            return False


# ===== EJEMPLOS =====

if __name__ == "__main__":
    # Ejemplo 1: Conexión básica
    impresora = EscPosDriver("COM3")
    if impresora.conectar():
        impresora.inicializar()
        impresora.alinear_centro()
        impresora.fuente_grande()
        impresora.texto("PRUEBA DE IMPRESORA")
        impresora.nueva_linea(3)
        impresora.cortar_papel()
        impresora.desconectar()
    
    # Ejemplo 2: Imprimir ticket
    printer = TicketPrinter("COM3")
    if printer.conectar():
        datos = {
            'tienda': 'HTF GIMNASIO',
            'subtitulo': 'PUNTO DE VENTA',
            'numero_ticket': 1001,
            'cajero': 'Juan Pérez',
            'productos': [
                {'nombre': 'Bebida Energética', 'cantidad': 2, 'precio': 5.00, 'subtotal': 10.00},
                {'nombre': 'Toalla de microfibra', 'cantidad': 1, 'precio': 15.00, 'subtotal': 15.00},
                {'nombre': 'Shaker botella', 'cantidad': 1, 'precio': 8.50, 'subtotal': 8.50},
            ],
            'total': 33.50,
            'metodo_pago': 'EFECTIVO',
            'abrir_caja': True,
            'cortar': True
        }
        
        printer.imprimir_ticket(datos)
        printer.desconectar()
