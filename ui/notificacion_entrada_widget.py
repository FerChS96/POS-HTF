"""
Widget de Notificación de Entrada de Miembro
Ventana emergente que muestra cuando un miembro registra su entrada
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsOpacityEffect, QWidget
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, Signal, QThread
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath, QColor, QCursor
import logging
from datetime import datetime
import os

from ui.components import (
    WindowsPhoneTheme
)


class NotificacionEntradaWidget(QDialog):
    """
    Widget emergente que muestra la información del miembro al registrar entrada.
    Se muestra automáticamente y se cierra solo después de unos segundos.
    """
    
    cerrado = Signal()  # Emite cuando se cierra la notificación
    cargo_asignado = Signal(dict)  # Emite cuando se asigna un cargo por suplantación
    
    def __init__(self, miembro_data, parent=None, duracion=0):
        """
        Args:
            miembro_data: Diccionario con los datos del miembro
            parent: Widget padre
            duracion: Tiempo en milisegundos antes de cerrar automáticamente (0 = no auto-cerrar)
        """
        try:
            # Verificar que miembro_data sea válido
            if not isinstance(miembro_data, dict):
                logging.error(f"ERROR: miembro_data no es un diccionario: {type(miembro_data)}")
                raise ValueError("miembro_data debe ser un diccionario")

            super().__init__(parent)
            self.miembro_data = miembro_data
            self.duracion = duracion

            # Variables para arrastre
            self.dragging = False
            self.drag_position = None

            # Configuración de ventana
            self.setWindowTitle("Acceso Registrado")
            self.setModal(False)  # No bloquea la ventana principal
            self.setWindowFlags(
                Qt.Window |
                Qt.WindowStaysOnTopHint |
                Qt.FramelessWindowHint
            )
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.setFixedSize(600, 700)

            # Inicializar componentes antes de aplicar estilos
            self.setup_ui()
            self.aplicar_estilos()

        except Exception as e:
            logging.error(f"Error inicializando NotificacionEntradaWidget: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Configurar timers después de inicializar componentes
        self.setup_timers()
        
        # Configurar efectos de animación
        self.setup_animations()
        
    def setup_timers(self):
        """Configurar los timers para actualización y cierre automático"""
        # Timer para cerrar automáticamente
        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.timeout.connect(self.cerrar_con_animacion)
        
        # Timer para actualizar el tiempo transcurrido
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.actualizar_tiempo)
        
    def setup_animations(self):
        """Configurar las animaciones del widget"""
        # Efecto de opacidad para animaciones
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        
    def setup_ui(self):
        """Configurar interfaz del widget"""
        # Layout principal con margen para sombra
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_SMALL,
            WindowsPhoneTheme.MARGIN_SMALL,
            WindowsPhoneTheme.MARGIN_SMALL,
            WindowsPhoneTheme.MARGIN_SMALL
        )
        
        # Contenedor principal
        container = QFrame()
        container.setObjectName("notificacionContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # ===== ENCABEZADO =====
        header = self.create_header()
        container_layout.addWidget(header)
        
        # ===== CONTENIDO =====
        content = self.create_content()
        container_layout.addWidget(content)
        
        main_layout.addWidget(container)
        
    def create_header(self):
        """Crear el encabezado de la notificación"""
        header = QFrame()
        header.setObjectName("notificacionHeader")
        header.setFixedHeight(100)
        header.setCursor(QCursor(Qt.OpenHandCursor))  # Cursor para indicar que se puede arrastrar
        
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM
        )
        header_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        title = QLabel("✓ ACCESO REGISTRADO")
        title.setObjectName("notificacionTitle")
        title.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; background-color: transparent;")
        header_layout.addWidget(title)
        
        self.hora_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.hora_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background-color: transparent;")
        self.hora_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.hora_label)
        
        return header
        
    def create_content(self):
        """Crear el contenido principal de la notificación"""
        content = QWidget()
        content.setObjectName("notificacionContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_LARGE,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_LARGE,
            WindowsPhoneTheme.MARGIN_MEDIUM
        )
        content_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # ===== FOTO DEL MIEMBRO =====
        foto_layout = QHBoxLayout()
        foto_layout.setAlignment(Qt.AlignCenter)
        
        self.foto_label = QLabel()
        self.foto_label.setFixedSize(180, 180)
        self.foto_label.setAlignment(Qt.AlignCenter)
        self.foto_label.setObjectName("fotoMiembro")
        
        # Cargar foto de forma asíncrona para no bloquear la UI
        self.cargar_foto_async()
        
        foto_layout.addWidget(self.foto_label)
        content_layout.addLayout(foto_layout)
        
        # ===== NOMBRE DEL MIEMBRO =====
        try:
            nombres = self.miembro_data.get('nombres', 'N/A')
            apellido_paterno = self.miembro_data.get('apellido_paterno', '')
            apellido_materno = self.miembro_data.get('apellido_materno', '')
            nombre_completo = f"{nombres} {apellido_paterno} {apellido_materno}".strip()
            if not nombre_completo or nombre_completo == 'N/A':
                nombre_completo = "MIEMBRO DESCONOCIDO"
        except Exception as e:
            logging.error(f"Error procesando nombre del miembro: {e}")
            nombre_completo = "ERROR EN NOMBRE"
            
        nombre_label = QLabel(nombre_completo.upper())
        nombre_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 18, QFont.Bold))
        nombre_label.setAlignment(Qt.AlignCenter)
        nombre_label.setStyleSheet(f"color: {WindowsPhoneTheme.PRIMARY_BLUE};")
        nombre_label.setWordWrap(True)
        content_layout.addWidget(nombre_label)
        
        # ===== INFORMACIÓN ADICIONAL =====
        info_container = self.create_info_container()
        content_layout.addWidget(info_container)
        
        # Espaciador
        content_layout.addStretch()
        
        # ===== BOTONES DE ACCIÓN =====
        btn_layout = self.create_buttons_layout()
        content_layout.addLayout(btn_layout)
        
        return content
        
    def create_info_container(self):
        """Crear el contenedor con información adicional del miembro"""
        info_container = QFrame()
        info_container.setObjectName("infoContainer")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM
        )
        info_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # ID Miembro
        try:
            id_miembro = self.miembro_data.get('id_miembro', 'N/A')
            self.agregar_info_row(info_layout, "ID:", f"#{id_miembro}")
        except Exception as e:
            logging.error(f"Error procesando ID del miembro: {e}")
            self.agregar_info_row(info_layout, "ID:", "#ERROR")
        
        # Fecha de registro
        fecha_registro = self.miembro_data.get('fecha_registro', 'N/A')
        self.agregar_info_row(info_layout, "Miembro desde:", fecha_registro)
        
        # Teléfono
        telefono = self.miembro_data.get('telefono', 'No registrado')
        self.agregar_info_row(info_layout, "Teléfono:", telefono)
        
        return info_container
        
    def create_buttons_layout(self):
        """Crear el layout con los botones de acción"""
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, WindowsPhoneTheme.MARGIN_SMALL, 0, 0)
        btn_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Botón Asignar Cargo
        btn_cargo = QPushButton("⚠️ ASIGNAR CARGO")
        btn_cargo.setObjectName("btnCargo")
        btn_cargo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14, QFont.Bold))
        btn_cargo.setMinimumHeight(70)
        btn_cargo.setCursor(QCursor(Qt.PointingHandCursor))
        btn_cargo.clicked.connect(self.asignar_cargo)
        btn_layout.addWidget(btn_cargo)
        
        # Botón Cerrar
        btn_cerrar = QPushButton("✕ CERRAR")
        btn_cerrar.setObjectName("btnCerrar")
        btn_cerrar.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 16, QFont.Bold))
        btn_cerrar.setMinimumHeight(70)
        btn_cerrar.setCursor(QCursor(Qt.PointingHandCursor))
        btn_cerrar.clicked.connect(self.cerrar_con_animacion)
        btn_layout.addWidget(btn_cerrar)
        
        return btn_layout
    
    def agregar_info_row(self, layout, etiqueta, valor):
        """Agregar una fila de información"""
        row = QHBoxLayout()
        row.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Etiqueta
        label_etiqueta = QLabel(etiqueta)
        label_etiqueta.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14, QFont.Bold))
        label_etiqueta.setStyleSheet("color: #4b5563;")
        label_etiqueta.setMinimumWidth(150)
        row.addWidget(label_etiqueta)
        
        # Valor
        label_valor = QLabel(str(valor))
        label_valor.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14))
        label_valor.setStyleSheet("color: #111827; font-weight: 500;")
        label_valor.setWordWrap(True)
        row.addWidget(label_valor, 1)
        
        layout.addLayout(row)
    
    def cargar_foto_async(self):
        """Cargar foto del miembro de forma asíncrona para no bloquear la UI"""
        # Primero mostrar placeholder
        self.mostrar_placeholder()
        
        # Priorizar foto_url sobre foto (path local)
        foto_url = self.miembro_data.get('foto_url')
        foto_path = self.miembro_data.get('foto')
        
        foto_a_cargar = foto_url or foto_path
        
        if foto_a_cargar:
            # Crear un hilo para cargar la foto
            self.foto_thread = FotoThread(foto_a_cargar)
            self.foto_thread.foto_loaded.connect(self.on_foto_loaded)
            self.foto_thread.start()
    
    def on_foto_loaded(self, pixmap):
        """Manejar la carga de la foto cuando el hilo termina"""
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap = self.crear_imagen_circular(pixmap)
            self.foto_label.setPixmap(pixmap)
    
    def crear_imagen_circular(self, pixmap):
        """Crear una imagen circular a partir de un pixmap"""
        size = min(pixmap.width(), pixmap.height())
        rounded = QPixmap(size, size)
        rounded.fill(Qt.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        
        x = (size - pixmap.width()) // 2
        y = (size - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        painter.end()
        
        return rounded
    
    def mostrar_placeholder(self):
        """Mostrar placeholder cuando no hay foto"""
        iniciales = self.obtener_iniciales()
        
        placeholder = QPixmap(180, 180)
        placeholder.fill(Qt.transparent)
        
        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setBrush(QColor(WindowsPhoneTheme.TILE_GREEN))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 180, 180)
        
        painter.setPen(Qt.white)
        painter.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 55, QFont.Bold))
        painter.drawText(0, 0, 180, 180, Qt.AlignCenter, iniciales)
        
        painter.end()
        self.foto_label.setPixmap(placeholder)
    
    def obtener_iniciales(self):
        """Obtener iniciales del nombre del miembro"""
        nombres = self.miembro_data.get('nombres', 'X').strip()
        apellido = self.miembro_data.get('apellido_paterno', 'X').strip()
        
        inicial_nombre = nombres[0].upper() if nombres else 'X'
        inicial_apellido = apellido[0].upper() if apellido else 'X'
        
        return f"{inicial_nombre}{inicial_apellido}"
    
    def actualizar_tiempo(self):
        """Actualizar etiqueta de tiempo transcurrido"""
        self.hora_label.setText(datetime.now().strftime("%H:%M:%S"))
    
    def showEvent(self, event):
        """Evento cuando se muestra el widget"""
        super().showEvent(event)
        
        # Iniciar animación de entrada
        self.animar_entrada()
        
        # Iniciar timer de auto-cierre solo si duracion > 0
        if self.duracion > 0:
            self.auto_close_timer.start(self.duracion)
        
        self.update_timer.start(1000)  # Actualizar cada segundo
        
        logging.debug(f"Notificación de entrada mostrada para miembro ID: {self.miembro_data['id_miembro']}")
    
    def animar_entrada(self):
        """Animar la aparición del widget"""
        # Animación de opacidad de 0 a 1
        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(400)
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.opacity_animation.start()
    
    def cerrar_con_animacion(self):
        """Cerrar el widget con animación"""
        # Detener timers
        self.auto_close_timer.stop()
        self.update_timer.stop()
        
        # Detener hilo de carga de foto si está activo
        if hasattr(self, 'foto_thread') and self.foto_thread.isRunning():
            self.foto_thread.terminate()
            self.foto_thread.wait()
        
        # Animación de salida
        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(300)
        self.opacity_animation.setStartValue(1.0)
        self.opacity_animation.setEndValue(0.0)
        self.opacity_animation.setEasingCurve(QEasingCurve.InCubic)
        self.opacity_animation.finished.connect(self.close)
        self.opacity_animation.start()
        
        logging.debug("Notificación de entrada cerrada")
    
    def asignar_cargo(self):
        """Asignar cargo por suplantación de identidad"""
        logging.debug(f"Asignando cargo por suplantación para miembro ID: {self.miembro_data['id_miembro']}")
        
        # Emitir señal con los datos del miembro
        self.cargo_asignado.emit(self.miembro_data)
        
        # Cerrar la ventana después de asignar cargo
        self.cerrar_con_animacion()
    
    def mousePressEvent(self, event):
        """Iniciar arrastre cuando se presiona el mouse"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Mover la ventana mientras se arrastra"""
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Terminar arrastre cuando se suelta el mouse"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
    
    def closeEvent(self, event):
        """Evento al cerrar el widget"""
        # Asegurarse de detener todos los hilos y timers
        if hasattr(self, 'foto_thread') and self.foto_thread.isRunning():
            self.foto_thread.terminate()
            self.foto_thread.wait()
            
        self.cerrado.emit()
        super().closeEvent(event)
    
    def aplicar_estilos(self):
        """Aplicar estilos personalizados al widget"""
        self.setStyleSheet(f"""
            #notificacionContainer {{
                background-color: white;
                border: 3px solid {WindowsPhoneTheme.TILE_GREEN};
                border-radius: 0px;
            }}
            
            #notificacionHeader {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
            }}
            
            #notificacionTitle {{
                color: white;
            }}
            
            #notificacionContent {{
                background-color: white;
            }}
            
            #infoContainer {{
                background-color: {WindowsPhoneTheme.BG_LIGHT};
                border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 0px;
            }}
            
            #fotoMiembro {{
                border: 4px solid {WindowsPhoneTheme.TILE_GREEN};
                border-radius: 90px;
                background-color: white;
            }}
            
            #btnCargo {{
                background-color: {WindowsPhoneTheme.TILE_ORANGE};
                color: white;
                border: none;
                border-radius: 0px;
                font-size: 14px;
                font-weight: bold;
            }}
            
            #btnCargo:hover {{
                background-color: #ff6d00;
            }}
            
            #btnCargo:pressed {{
                background-color: #e65100;
            }}
            
            #btnCerrar {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
                border: none;
                border-radius: 0px;
                font-size: 16px;
                font-weight: bold;
            }}
            
            #btnCerrar:hover {{
                background-color: {WindowsPhoneTheme.PRIMARY_BLUE};
            }}
            
            #btnCerrar:pressed {{
                background-color: #003d82;
            }}
        """)


class FotoThread(QThread):
    """Hilo para cargar la foto del miembro de forma asíncrona"""
    foto_loaded = Signal(QPixmap)
    
    def __init__(self, foto_path_or_url):
        super().__init__()
        self.foto_path_or_url = foto_path_or_url
    
    def run(self):
        """Cargar la foto en un hilo separado"""
        try:
            # Primero intentar como path local
            if self.foto_path_or_url and os.path.exists(self.foto_path_or_url):
                pixmap = QPixmap(self.foto_path_or_url)
                if not pixmap.isNull():
                    self.foto_loaded.emit(pixmap)
                    return
            
            # Si no es un path válido, intentar como URL
            if self.foto_path_or_url and self.foto_path_or_url.startswith(('http://', 'https://')):
                import requests
                from io import BytesIO
                
                try:
                    response = requests.get(self.foto_path_or_url, timeout=10)
                    response.raise_for_status()
                    
                    # Crear QPixmap desde los bytes de la respuesta
                    image_data = BytesIO(response.content)
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data.getvalue())
                    
                    if not pixmap.isNull():
                        self.foto_loaded.emit(pixmap)
                        return
                except Exception as e:
                    logging.warning(f"Error cargando foto desde URL {self.foto_path_or_url}: {e}")
        
        except Exception as e:
            logging.warning(f"Error general cargando foto: {e}")
        
        # Si no hay foto o hay error, no emitir nada (se mantiene el placeholder)