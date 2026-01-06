"""
Ventana Principal del POS HTF Gimnasio
Interfaz sencilla con pestañas en la parte inferior
Para rol: Recepcionista
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QStackedWidget, QFrame,
    QGridLayout, QScrollArea, QSizePolicy, QDialog,
    QGroupBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QCursor
import logging
import subprocess
import sys
import os

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    InfoTile,
    SectionTitle,
    StyledLabel,
    TabButton,
    TopBar,
    apply_windows_phone_stylesheet,
    create_page_layout,
    create_tile_grid_layout,
    show_success_dialog,
    show_error_dialog,
    show_warning_dialog
)

# Importar ventanas de ventas
from ui.ventas import (
    NuevaVentaWindow,
    VentasDiaWindow,
    HistorialVentasWindow,
    CierreCajaWindow
)

# Importar ventana de personal
from ui.personal_window import PersonalWindow
from ui.inventario_window import InventarioWindow
from ui.movimiento_inventario_window import MovimientoInventarioWindow
from ui.nuevo_producto_window import NuevoProductoWindow
from ui.historial_movimientos_window import HistorialMovimientosWindow
from ui.historial_acceso_window import HistorialAccesoWindow
from ui.historial_turnos_window import HistorialTurnosWindow
from ui.asignacion_turnos_window import AsignacionTurnosWindow
from ui.ubicaciones_window import UbicacionesWindow
from ui.dias_festivos_window import DiasFestvosWindow
from ui.buscar_miembro_window import BuscarMiembroWindow
from ui.dias_festivos_window import DiasFestvosWindow
from ui.notificacion_entrada_widget import NotificacionEntradaWidget
from ui.lockers_window import LockersWindow
from ui.asignar_locker_window import AsignacionesLockersWindow
from utils.monitor_entradas import MonitorEntradas
from database.postgres_manager import PostgresManager


class MainPOSWindow(QMainWindow):
    """Ventana principal del sistema POS"""
    
    logout_requested = Signal()
    
    def __init__(self, user_data, pg_manager, supabase_service, turno_id=None):
        super().__init__()
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.turno_id = turno_id  # ID del turno activo
        
        self.setWindowTitle("HTF Gimnasio - Sistema POS")
        self.setGeometry(100, 50, 1400, 900)
        
        # Establecer icono de la ventana
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'pos_icono.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Establecer tamaño mínimo para evitar problemas de layout
        self.setMinimumSize(1000, 700)
        
        # Iniciar en pantalla completa
        self.showMaximized()
        
        # Variables de estado
        self.current_tab = 0
        
        # Monitor de entradas
        self.monitor_entradas = None
        self.notificaciones_activas = []  # Lista de notificaciones abiertas
        
        # Aplicar estilos Windows Phone
        apply_windows_phone_stylesheet(self)
        
        self.setup_ui()
        
        # Iniciar monitor de entradas
        self.iniciar_monitor_entradas()
        
    def setup_ui(self):
        """Configurar interfaz principal"""
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal vertical
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Barra superior con información de usuario (usando componente)
        self.top_bar = TopBar(
            title="HTF POS",
            user_name=self.user_data['nombre_completo'],
            user_role=self.user_data['rol']
        )
        main_layout.addWidget(self.top_bar)
        
        # Área de contenido (cambia según la pestaña)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        
        # Crear las páginas de cada pestaña
        self.create_sales_page()
        self.create_inventory_page()
        self.create_members_page()
        self.create_admin_page()
        self.create_settings_page()
        
        # Barra de navegación inferior con pestañas
        self.create_bottom_nav(main_layout)
        
        # Mostrar la primera pestaña (Ventas)
        self.stacked_widget.setCurrentIndex(0)
        
    def create_bottom_nav(self, parent_layout):
        """Crear barra de navegación inferior usando TabButton"""
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("navBar")
        self.nav_bar.setFixedHeight(WindowsPhoneTheme.NAV_BAR_HEIGHT)
        
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        
        # Definir pestañas con iconos y colores
        tabs = [
            {"name": "Ventas", "icon": "fa5s.shopping-cart", "color": WindowsPhoneTheme.TILE_RED, "index": 0},
            {"name": "Inventario", "icon": "fa5s.boxes", "color": WindowsPhoneTheme.TILE_GREEN, "index": 1},
            {"name": "Miembros", "icon": "fa5s.users", "color": WindowsPhoneTheme.TILE_ORANGE, "index": 2},
            {"name": "Admin", "icon": "fa5s.user-shield", "color": WindowsPhoneTheme.TILE_PURPLE, "index": 3},
            {"name": "Config", "icon": "fa5s.cog", "color": WindowsPhoneTheme.TILE_GRAY, "index": 4},
        ]
        
        # Crear botones usando componente TabButton
        self.tab_buttons = []
        for tab in tabs:
            btn = TabButton(tab['name'], tab['icon'], tab['color'])
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.clicked.connect(lambda checked, idx=tab['index']: self.switch_tab(idx))
            nav_layout.addWidget(btn)
            self.tab_buttons.append(btn)
        
        # Activar primera pestaña
        self.tab_buttons[0].setChecked(True)
        
        parent_layout.addWidget(self.nav_bar)
        
    def switch_tab(self, index):
        """Cambiar de pestaña"""
        self.current_tab = index
        self.stacked_widget.setCurrentIndex(index)
        
        # Actualizar estado visual de botones
        for i, btn in enumerate(self.tab_buttons):
            btn.setChecked(i == index)
            
        logging.info(f"Cambio a pestaña: {index}")
        
    # ========== PÁGINAS DE CONTENIDO ==========
    
    def create_sales_page(self):
        """Página de ventas usando TileButton"""
        page = QWidget()
        layout = create_page_layout("PUNTO DE VENTA")
        page.setLayout(layout)
        
        # Grid de tiles - 2 filas x 2 columnas
        grid = create_tile_grid_layout()
        
        # Botones de acciones usando componente TileButton
        btn_nueva_venta = TileButton("Nueva Venta", "fa5s.cash-register", WindowsPhoneTheme.TILE_RED)
        btn_nueva_venta.clicked.connect(self.abrir_nueva_venta)
        grid.addWidget(btn_nueva_venta, 0, 0)
        
        btn_ventas_dia = TileButton("Ventas del Día", "fa5s.list-alt", WindowsPhoneTheme.TILE_ORANGE)
        btn_ventas_dia.clicked.connect(self.abrir_ventas_dia)
        grid.addWidget(btn_ventas_dia, 0, 1)
        
        btn_escanear_pago = TileButton("Escanear Código\nPago", "mdi.qrcode-scan", WindowsPhoneTheme.TILE_GREEN)
        btn_escanear_pago.clicked.connect(self.escanear_codigo_pago)
        grid.addWidget(btn_escanear_pago, 1, 0)
        
        btn_cierre = TileButton("Cierre de Caja", "fa5s.lock", WindowsPhoneTheme.TILE_MAGENTA)
        btn_cierre.clicked.connect(self.abrir_cierre_caja)
        grid.addWidget(btn_cierre, 1, 1)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        self.stacked_widget.addWidget(page)
        
    def create_inventory_page(self):
        """Página de inventario usando TileButton"""
        page = QWidget()
        layout = create_page_layout("INVENTARIO")
        page.setLayout(layout)
        
        # Grid de tiles
        grid = create_tile_grid_layout()
        
        actions = [
            {"text": "Nuevo Producto", "icon": "fa5s.plus-square", "color": WindowsPhoneTheme.TILE_GREEN, "callback": self.abrir_nuevo_producto},
            {"text": "Ver Inventario", "icon": "fa5s.warehouse", "color": WindowsPhoneTheme.TILE_BLUE, "callback": self.abrir_inventario},
            {"text": "Registrar Entrada", "icon": "fa5s.plus-circle", "color": WindowsPhoneTheme.TILE_GREEN, "callback": self.abrir_registro_entrada},
            {"text": "Registrar Salida", "icon": "fa5s.minus-circle", "color": WindowsPhoneTheme.TILE_RED, "callback": self.abrir_registro_salida},
            {"text": "Movimientos", "icon": "fa5s.exchange-alt", "color": WindowsPhoneTheme.TILE_PURPLE, "callback": self.abrir_historial_movimientos},
        ]
        
        # Agregar los botones al grid
        for i, action in enumerate(actions):
            btn = TileButton(action["text"], action["icon"], action["color"])
            if action["callback"]:
                btn.clicked.connect(action["callback"])
            row = i // 3
            col = i % 3
            grid.addWidget(btn, row, col)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        self.stacked_widget.addWidget(page)
        
    def create_members_page(self):
        """Página de miembros usando InfoTile - Consulta desde Supabase"""
        page = QWidget()
        layout = create_page_layout("MIEMBROS Y LOCKERS")
        page.setLayout(layout)
        
        # Widgets informativos
        widgets_layout = QHBoxLayout()
        widgets_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        # Widget de miembros usando InfoTile - CONSULTA DESDE SUPABASE
        members_tile = InfoTile("MIEMBROS", "fa5s.users", WindowsPhoneTheme.TILE_TEAL)
        try:
            # Consultar directamente a Supabase
            total_members = self.supabase_service.get_total_members()
            active_today = self.supabase_service.get_active_members_today()
        except Exception as e:
            logging.error(f"Error consultando miembros desde Supabase: {e}")
            total_members = 0
            active_today = 0
        
        members_tile.add_main_value(total_members)
        members_tile.add_secondary_value(f"Activos Hoy: {active_today}")
        members_tile.add_stretch()
        widgets_layout.addWidget(members_tile)
        
        # Widget de lockers usando InfoTile - CONSULTA DESDE SUPABASE
        lockers_tile = InfoTile("LOCKERS", "fa5s.key", WindowsPhoneTheme.TILE_MAGENTA)
        try:
            lockers_status = self.supabase_service.get_lockers_status()
            total_lockers = lockers_status['total']
            occupied_lockers = lockers_status['occupied']
            available_lockers = lockers_status['available']
        except Exception as e:
            logging.error(f"Error consultando lockers desde Supabase: {e}")
            total_lockers = 0
            occupied_lockers = 0
            available_lockers = 0
        
        lockers_tile.add_main_value(available_lockers)
        lockers_tile.add_secondary_value(f"Ocupados: {occupied_lockers}/{total_lockers}")
        lockers_tile.add_stretch()
        widgets_layout.addWidget(lockers_tile)
        
        layout.addLayout(widgets_layout)
        
        # Botones de acción
        actions_grid = create_tile_grid_layout()
        
        btn_search = TileButton("Buscar Miembro", "fa5s.search", WindowsPhoneTheme.TILE_ORANGE)
        btn_search.clicked.connect(self.abrir_buscar_miembro)
        btn_historial = TileButton("Historial de Acceso", "fa5s.history", WindowsPhoneTheme.TILE_PURPLE)
        btn_historial.clicked.connect(self.abrir_historial_acceso)
        btn_lockers = TileButton("Asignar\nLockers", "mdi.locker", WindowsPhoneTheme.TILE_BLUE)
        btn_lockers.clicked.connect(self.abrir_asignaciones_lockers)
        
        actions_grid.addWidget(btn_search, 0, 0)
        actions_grid.addWidget(btn_historial, 0, 1)
        actions_grid.addWidget(btn_lockers, 0, 2)
        
        layout.addLayout(actions_grid)
        layout.addStretch()
        
        self.stacked_widget.addWidget(page)
        
    def create_admin_page(self):
        """Página de administración usando TileButton"""
        page = QWidget()
        layout = create_page_layout("ADMINISTRACIÓN")
        page.setLayout(layout)
        
        # Grid de administración
        admin_grid = create_tile_grid_layout()
        
        # Solo mostrar si es administrador
        if self.user_data['rol'] in ['administrador', 'sistemas']:
            # Fila 1
            btn_personal = TileButton("Gestionar\nPersonal", "fa5s.users-cog", WindowsPhoneTheme.TILE_GREEN)
            btn_personal.clicked.connect(self.abrir_gestion_personal)
            admin_grid.addWidget(btn_personal, 0, 0)
            
            btn_dias_festivos = TileButton("Días\nFestivos", "fa5s.calendar-alt", WindowsPhoneTheme.TILE_BLUE)
            btn_dias_festivos.clicked.connect(self.abrir_dias_festivos)
            admin_grid.addWidget(btn_dias_festivos, 0, 1)
            
            btn_historial_turnos = TileButton("Historial\nTurnos", "fa5s.cash-register", WindowsPhoneTheme.TILE_TEAL)
            btn_historial_turnos.clicked.connect(self.abrir_historial_turnos)
            admin_grid.addWidget(btn_historial_turnos, 0, 2)
            
            btn_asignar_turnos = TileButton("Asignar\nTurnos", "fa5s.calendar-check", WindowsPhoneTheme.TILE_ORANGE)
            btn_asignar_turnos.clicked.connect(self.abrir_asignacion_turnos)
            admin_grid.addWidget(btn_asignar_turnos, 0, 3)
            
            # Fila 2
            btn_ubicaciones = TileButton("Gestionar\nUbicaciones", "fa5s.warehouse", WindowsPhoneTheme.TILE_BLUE)
            btn_ubicaciones.clicked.connect(self.abrir_gestion_ubicaciones)
            admin_grid.addWidget(btn_ubicaciones, 1, 0)
            
            btn_catalogo_lockers = TileButton("Catálogo\nde Lockers", "mdi.locker-multiple", WindowsPhoneTheme.TILE_TEAL)
            btn_catalogo_lockers.clicked.connect(self.abrir_catalogo_lockers)
            admin_grid.addWidget(btn_catalogo_lockers, 1, 1)
            
            btn_historial_ventas = TileButton("Historial\nVentas", "fa5s.history", WindowsPhoneTheme.TILE_PURPLE)
            btn_historial_ventas.clicked.connect(self.abrir_historial)
            admin_grid.addWidget(btn_historial_ventas, 1, 2)
        else:
            # Si no es administrador, mostrar mensaje
            no_access_label = StyledLabel(
                "Acceso restringido a administradores",
                bold=True,
                size=WindowsPhoneTheme.FONT_SIZE_TITLE
            )
            no_access_label.setAlignment(Qt.AlignCenter)
            no_access_label.setStyleSheet(f"color: {WindowsPhoneTheme.TEXT_SECONDARY}; padding: 50px;")
            layout.addWidget(no_access_label)
        
        layout.addLayout(admin_grid)
        layout.addStretch()
        
        self.stacked_widget.addWidget(page)
    
    def create_settings_page(self):
        """Página de configuración usando TileButton"""
        page = QWidget()
        layout = create_page_layout("CONFIGURACIÓN")
        page.setLayout(layout)
        
        # Grid de configuración
        config_grid = create_tile_grid_layout()
        
        btn_change_password = TileButton("Cambiar Contraseña", "fa5s.lock", WindowsPhoneTheme.TILE_ORANGE)
        btn_change_password.clicked.connect(self.cambiar_contrasena)
        btn_sync = TileButton("Sincronizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_backup = TileButton("Respaldar Datos", "fa5s.database", WindowsPhoneTheme.TILE_TEAL)
        btn_logout = TileButton("Cerrar Sesión", "fa5s.sign-out-alt", WindowsPhoneTheme.TILE_RED)
        btn_logout.clicked.connect(self.handle_logout)
        
        # Posicionar botones
        config_grid.addWidget(btn_change_password, 0, 0)
        config_grid.addWidget(btn_sync, 0, 1)
        config_grid.addWidget(btn_backup, 1, 0)
        config_grid.addWidget(btn_logout, 1, 1)
        
        layout.addLayout(config_grid)
        layout.addStretch()
        
        self.stacked_widget.addWidget(page)
        
    def handle_logout(self):
        """Manejar cierre de sesión"""
        logging.info(f"Usuario {self.user_data['username']} cerró sesión")
        self.logout_requested.emit()
        self.close()
    
    def cambiar_contrasena(self):
        """Abrir diálogo para cambiar contraseña"""
        from PySide6.QtWidgets import QDialog, QLineEdit
        import bcrypt
        
        class CambiarContrasenaDialog(QDialog):
            def __init__(self, parent, pg_manager, user_data):
                super().__init__(parent)
                self.pg_manager = pg_manager
                self.user_data = user_data
                
                self.setModal(True)
                self.setWindowTitle("Cambiar Contraseña")
                self.setMinimumWidth(500)
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                
                # Layout principal
                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)
                
                # Header
                header = QFrame()
                header.setStyleSheet(f"background-color: {WindowsPhoneTheme.PRIMARY_BLUE};")
                header_layout = QHBoxLayout(header)
                header_layout.setContentsMargins(28, 24, 28, 24)
                
                title_label = QLabel("CAMBIAR CONTRASEÑA")
                title_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_LARGE, QFont.Bold))
                title_label.setStyleSheet("color: white;")
                title_label.setAlignment(Qt.AlignCenter)
                header_layout.addWidget(title_label)
                
                layout.addWidget(header)
                
                # Content
                content = QFrame()
                content.setStyleSheet("background-color: white;")
                content_layout = QVBoxLayout(content)
                content_layout.setContentsMargins(40, 30, 40, 30)
                content_layout.setSpacing(20)
                
                # Contraseña actual
                lbl_actual = StyledLabel("Contraseña Actual:", bold=True)
                content_layout.addWidget(lbl_actual)
                
                self.input_actual = QLineEdit()
                self.input_actual.setEchoMode(QLineEdit.Password)
                self.input_actual.setPlaceholderText("Ingrese su contraseña actual")
                self.input_actual.setMinimumHeight(45)
                self.input_actual.setStyleSheet(f"""
                    QLineEdit {{
                        padding: 10px 15px;
                        border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                        font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                    }}
                    QLineEdit:focus {{
                        border-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                    }}
                """)
                self._toggle_actual_action = self._add_password_toggle(self.input_actual)
                content_layout.addWidget(self.input_actual)
                
                content_layout.addSpacing(10)
                
                # Nueva contraseña
                lbl_nueva = StyledLabel("Nueva Contraseña:", bold=True)
                content_layout.addWidget(lbl_nueva)
                
                self.input_nueva = QLineEdit()
                self.input_nueva.setEchoMode(QLineEdit.Password)
                self.input_nueva.setPlaceholderText("Ingrese nueva contraseña")
                self.input_nueva.setMinimumHeight(45)
                self.input_nueva.setStyleSheet(f"""
                    QLineEdit {{
                        padding: 10px 15px;
                        border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                        font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                    }}
                    QLineEdit:focus {{
                        border-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                    }}
                """)
                self._toggle_nueva_action = self._add_password_toggle(self.input_nueva)
                content_layout.addWidget(self.input_nueva)
                
                content_layout.addSpacing(10)
                
                # Confirmar contraseña
                lbl_confirmar = StyledLabel("Confirmar Nueva Contraseña:", bold=True)
                content_layout.addWidget(lbl_confirmar)
                
                self.input_confirmar = QLineEdit()
                self.input_confirmar.setEchoMode(QLineEdit.Password)
                self.input_confirmar.setPlaceholderText("Confirme nueva contraseña")
                self.input_confirmar.setMinimumHeight(45)
                self.input_confirmar.setStyleSheet(f"""
                    QLineEdit {{
                        padding: 10px 15px;
                        border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                        font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                    }}
                    QLineEdit:focus {{
                        border-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                    }}
                """)
                self._toggle_confirmar_action = self._add_password_toggle(self.input_confirmar)
                content_layout.addWidget(self.input_confirmar)
                
                content_layout.addSpacing(20)
                
                # Botones
                buttons_layout = QHBoxLayout()
                buttons_layout.setSpacing(14)
                buttons_layout.addStretch()
                
                btn_cancelar = QPushButton("Cancelar")
                btn_cancelar.setMinimumSize(120, 45)
                btn_cancelar.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
                btn_cancelar.setCursor(QCursor(Qt.PointingHandCursor))
                btn_cancelar.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {WindowsPhoneTheme.TILE_GRAY};
                        color: white;
                        border: none;
                        padding: 10px 20px;
                    }}
                    QPushButton:hover {{
                        background-color: #8a8a8a;
                    }}
                """)
                btn_cancelar.clicked.connect(self.reject)
                buttons_layout.addWidget(btn_cancelar)
                
                btn_cambiar = QPushButton("Cambiar")
                btn_cambiar.setMinimumSize(120, 45)
                btn_cambiar.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
                btn_cambiar.setCursor(QCursor(Qt.PointingHandCursor))
                btn_cambiar.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {WindowsPhoneTheme.TILE_GREEN};
                        color: white;
                        border: none;
                        padding: 10px 20px;
                    }}
                    QPushButton:hover {{
                        background-color: #00b300;
                    }}
                """)
                btn_cambiar.clicked.connect(self.cambiar)
                btn_cambiar.setDefault(True)
                buttons_layout.addWidget(btn_cambiar)
                
                content_layout.addLayout(buttons_layout)
                layout.addWidget(content)

            def _add_password_toggle(self, line_edit: QLineEdit):
                """Agrega acción de mostrar/ocultar contraseña al QLineEdit."""
                try:
                    import qtawesome as qta
                except Exception:
                    return None

                # Reservar espacio para el icono dentro del input
                line_edit.setTextMargins(0, 0, 36, 0)
                action = line_edit.addAction(
                    qta.icon('fa5s.eye', color=WindowsPhoneTheme.PRIMARY_BLUE),
                    QLineEdit.TrailingPosition
                )
                action.setToolTip("Mostrar contraseña")
                action.triggered.connect(
                    lambda checked=False, le=line_edit, act=action: self._toggle_password_visibility(le, act)
                )
                return action

            def _toggle_password_visibility(self, line_edit: QLineEdit, action):
                """Alterna visibilidad de contraseña para un campo."""
                try:
                    import qtawesome as qta
                except Exception:
                    return

                if line_edit.echoMode() == QLineEdit.Password:
                    line_edit.setEchoMode(QLineEdit.Normal)
                    action.setIcon(qta.icon('fa5s.eye-slash', color=WindowsPhoneTheme.PRIMARY_BLUE))
                    action.setToolTip("Ocultar contraseña")
                else:
                    line_edit.setEchoMode(QLineEdit.Password)
                    action.setIcon(qta.icon('fa5s.eye', color=WindowsPhoneTheme.PRIMARY_BLUE))
                    action.setToolTip("Mostrar contraseña")
            
            def cambiar(self):
                """Validar y cambiar contraseña"""
                actual = self.input_actual.text().strip()
                nueva = self.input_nueva.text().strip()
                confirmar = self.input_confirmar.text().strip()
                
                # Validaciones
                if not actual or not nueva or not confirmar:
                    show_warning_dialog(self, "Campos Vacíos", "Todos los campos son obligatorios.")
                    return
                
                if len(nueva) < 6:
                    show_warning_dialog(self, "Contraseña Débil", "La nueva contraseña debe tener al menos 6 caracteres.")
                    return
                
                if nueva != confirmar:
                    show_warning_dialog(self, "No Coinciden", "La nueva contraseña y la confirmación no coinciden.")
                    return
                
                try:
                    # Verificar contraseña actual
                    result = self.pg_manager.client.table('usuarios').select('contrasenia').eq('nombre_usuario', self.user_data['username']).execute()
                    
                    if not result.data:
                        show_error_dialog(self, "Error", "No se encontró el usuario.")
                        return
                    
                    stored_password = result.data[0]['contrasenia']
                    
                    # Verificar contraseña actual con bcrypt
                    if not bcrypt.checkpw(actual.encode('utf-8'), stored_password.encode('utf-8')):
                        show_error_dialog(self, "Contraseña Incorrecta", "La contraseña actual no es correcta.")
                        return
                    
                    # Cambiar contraseña usando el método del manager
                    if self.pg_manager.update_user_password(self.user_data['username'], nueva):
                        show_success_dialog(self, "Contraseña Actualizada", "Su contraseña ha sido cambiada exitosamente.")
                        self.accept()
                    else:
                        show_error_dialog(self, "Error", "No se pudo actualizar la contraseña.")
                
                except Exception as e:
                    logging.error(f"Error cambiando contraseña: {e}")
                    show_error_dialog(self, "Error", f"Error al cambiar contraseña:\n{str(e)}")
        
        # Mostrar diálogo
        dialog = CambiarContrasenaDialog(self, self.pg_manager, self.user_data)
        dialog.exec()
        
    # ========== MÉTODOS DE VENTAS ==========
    
    def abrir_nueva_venta(self):
        """Abrir widget de nueva venta"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("NUEVA VENTA")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de nueva venta
            nueva_venta_widget = NuevaVentaWindow(
                self.pg_manager, 
                self.supabase_service, 
                self.user_data,
                self.turno_id,  # Pasar ID del turno actual
                self
            )
            nueva_venta_widget.venta_completada.connect(self.on_venta_completada)
            nueva_venta_widget.cerrar_solicitado.connect(self.volver_a_ventas)
            
            # Agregar al stack y cambiar a esa vista
            self.stacked_widget.addWidget(nueva_venta_widget)
            self.stacked_widget.setCurrentWidget(nueva_venta_widget)
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo widget de nueva venta")
        except Exception as e:
            logging.error(f"Error abriendo nueva venta: {e}")
            
    def abrir_ventas_dia(self):
        """Abrir widget de ventas del turno"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("VENTAS DEL TURNO")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de ventas del turno
            ventas_dia_widget = VentasDiaWindow(
                self.pg_manager, 
                self.supabase_service, 
                self.user_data,
                self.turno_id,  # Pasar ID del turno actual
                self
            )
            ventas_dia_widget.cerrar_solicitado.connect(self.volver_a_ventas)
            
            # Agregar al stack y cambiar a esa vista
            self.stacked_widget.addWidget(ventas_dia_widget)
            self.stacked_widget.setCurrentWidget(ventas_dia_widget)
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo widget de ventas del turno")
        except Exception as e:
            logging.error(f"Error abriendo ventas del día: {e}")
            
    def abrir_historial(self):
        """Abrir widget de historial de ventas"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("HISTORIAL DE VENTAS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Verificar desde qué pestaña se está abriendo
            current_index = self.stacked_widget.currentIndex()
            
            # Crear widget de historial
            historial_widget = HistorialVentasWindow(
                self.pg_manager, 
                self.supabase_service, 
                self.user_data, 
                self
            )
            
            # Conectar señal según la vista actual
            # Índice 0 = Ventas, Índice 3 = Administración
            if current_index == 3:
                historial_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            else:
                historial_widget.cerrar_solicitado.connect(self.volver_a_ventas)
            
            # Agregar al stack y cambiar a esa vista
            self.stacked_widget.addWidget(historial_widget)
            self.stacked_widget.setCurrentWidget(historial_widget)
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo widget de historial")
        except Exception as e:
            logging.error(f"Error abriendo historial: {e}")
            
    def abrir_cierre_caja(self):
        """Abrir widget de cierre de caja"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("CIERRE DE CAJA")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de cierre de caja
            cierre_widget = CierreCajaWindow(
                self.pg_manager, 
                self.supabase_service, 
                self.user_data, 
                self
            )
            cierre_widget.cerrar_solicitado.connect(self.volver_a_ventas)
            
            # Agregar al stack y cambiar a esa vista
            self.stacked_widget.addWidget(cierre_widget)
            self.stacked_widget.setCurrentWidget(cierre_widget)
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo widget de cierre de caja")
        except Exception as e:
            logging.error(f"Error abriendo cierre de caja: {e}")
    
    def escanear_codigo_pago(self):
        """Abrir diálogo para confirmar pago en efectivo escaneando ID venta"""
        try:
            from ui.confirmar_pago_efectivo_dialog import ConfirmarPagoEfectivoDialog
            
            # Crear y mostrar diálogo simple de escaneo
            dialogo = ConfirmarPagoEfectivoDialog(
                self.supabase_service,
                parent=self
            )
            
            dialogo.exec()
            
        except Exception as e:
            logging.error(f"Error abriendo ventana de pagos: {e}")
            show_error_dialog(
                self,
                "Error",
                f"Error al abrir escaner:\n{str(e)}"
            )
    
    
    def debug_procesar_pago(self, dialog):
        """Procesar pago desde el diálogo de debug"""
        codigo = self.debug_scan_input.text().strip()
        
        if not codigo:
            show_warning_dialog(
                self,
                "Código vacío",
                "Por favor escanee o ingrese un código de pago"
            )
            return
        
        try:
            # Normalizar el código usando regex (maneja CASH' CASH_ CASH 506, etc.)
            import re
            codigo_original = codigo.strip()
            codigo_upper = codigo_original.upper()
            match = re.match(r'CASH[^\d]*(\d+)', codigo_upper)
            if match:
                numero = match.group(1)
                codigo_normalizado = f"CASH-{numero}"
                logging.info(f"[DEBUG] ✓ Regex matched: CASH + [{codigo_upper[4]}] + {numero} = {codigo_normalizado}")
            else:
                codigo_normalizado = codigo_upper
                logging.info(f"[DEBUG] ✗ Regex NO matched para: {codigo_original}")
            logging.info(f"[DEBUG] Código original: {codigo_original} → Normalizado: {codigo_normalizado}")
            
            notif = None
            ya_procesada = False
            
            # Buscar en Supabase
            if self.supabase_service:
                logging.info(f"[DEBUG] Buscando en Supabase...")
                response = self.supabase_service.client.table('notificaciones_pos') \
                    .select('*, miembros(nombres, apellido_paterno, apellido_materno, telefono)') \
                    .eq('codigo_pago_generado', codigo_normalizado) \
                    .eq('respondida', False) \
                    .execute()
                
                if response.data and len(response.data) > 0:
                    item = response.data[0]
                    miembro = item.get('miembros') or {}
                    
                    notif = {
                        'id_notificacion': item['id_notificacion'],
                        'id_miembro': item['id_miembro'],
                        'tipo_notificacion': item['tipo_notificacion'],
                        'asunto': item['asunto'],
                        'monto_pendiente': item.get('monto_pendiente'),
                        'codigo_pago_generado': item.get('codigo_pago_generado'),
                        'nombres': miembro.get('nombres', ''),
                        'apellido_paterno': miembro.get('apellido_paterno', ''),
                        'apellido_materno': miembro.get('apellido_materno', '')
                    }
                    logging.info(f"[DEBUG] ✓ Notificación encontrada: {notif['id_notificacion']}")
                else:
                    # Si no encuentra pendiente, buscar TODAS (incluyendo respondidas)
                    logging.info(f"[DEBUG] No encontrada como pendiente, buscando todas...")
                    response = self.supabase_service.client.table('notificaciones_pos') \
                        .select('*, miembros(nombres, apellido_paterno, apellido_materno, telefono)') \
                        .eq('codigo_pago_generado', codigo_normalizado) \
                        .execute()
                    
                    if response.data and len(response.data) > 0:
                        item = response.data[0]
                        miembro = item.get('miembros') or {}
                        
                        notif = {
                            'id_notificacion': item['id_notificacion'],
                            'id_miembro': item['id_miembro'],
                            'tipo_notificacion': item['tipo_notificacion'],
                            'asunto': item['asunto'],
                            'monto_pendiente': item.get('monto_pendiente'),
                            'codigo_pago_generado': item.get('codigo_pago_generado'),
                            'nombres': miembro.get('nombres', ''),
                            'apellido_paterno': miembro.get('apellido_paterno', ''),
                            'apellido_materno': miembro.get('apellido_materno', '')
                        }
                        
                        if item.get('respondida'):
                            ya_procesada = True
                            logging.info(f"[DEBUG] ⚠️ Código ya procesado: {notif['id_notificacion']}")
                        else:
                            logging.info(f"[DEBUG] ✓ Notificación encontrada: {notif['id_notificacion']}")
            else:
                # Fallback a PostgreSQL
                logging.info(f"[DEBUG] Buscando en PostgreSQL...")
                result = self.pg_manager.client.table('notificaciones_pos').select(
                    'id_notificacion,id_miembro,tipo_notificacion,asunto,monto_pendiente,codigo_pago_generado,respondida,miembros(nombres,apellido_paterno,apellido_materno)'
                ).eq('codigo_pago_generado', codigo_normalizado).eq('respondida', False).execute()
                
                if result.data:
                    datos = result.data[0]
                    miembro = datos.get('miembros') or {}
                    notif = {
                        'id_notificacion': datos['id_notificacion'],
                        'id_miembro': datos['id_miembro'],
                        'tipo_notificacion': datos['tipo_notificacion'],
                        'asunto': datos['asunto'],
                        'monto_pendiente': datos.get('monto_pendiente'),
                        'codigo_pago_generado': datos['codigo_pago_generado'],
                        'nombres': miembro.get('nombres', ''),
                        'apellido_paterno': miembro.get('apellido_paterno', ''),
                        'apellido_materno': miembro.get('apellido_materno', '')
                    }
                    logging.info(f"[DEBUG] ✓ Notificación encontrada: {notif['id_notificacion']}")
                else:
                    # Si no encuentra pendiente en PostgreSQL, buscar todas
                    logging.info(f"[DEBUG] No encontrada como pendiente en PostgreSQL, buscando todas...")
                    result = self.pg_manager.client.table('notificaciones_pos').select(
                        'id_notificacion,id_miembro,tipo_notificacion,asunto,monto_pendiente,codigo_pago_generado,respondida,miembros(nombres,apellido_paterno,apellido_materno)'
                    ).eq('codigo_pago_generado', codigo_normalizado).execute()
                    
                    if result.data:
                        datos = result.data[0]
                        miembro = datos.get('miembros') or {}
                        notif = {
                            'id_notificacion': datos['id_notificacion'],
                            'id_miembro': datos['id_miembro'],
                            'tipo_notificacion': datos['tipo_notificacion'],
                            'asunto': datos['asunto'],
                            'monto_pendiente': datos.get('monto_pendiente'),
                            'codigo_pago_generado': datos['codigo_pago_generado'],
                            'nombres': miembro.get('nombres', ''),
                            'apellido_paterno': miembro.get('apellido_paterno', ''),
                            'apellido_materno': miembro.get('apellido_materno', '')
                        }
                        
                        if datos.get('respondida'):
                            ya_procesada = True
                            logging.info(f"[DEBUG] ⚠️ Código ya procesado: {notif['id_notificacion']}")
                        else:
                            logging.info(f"[DEBUG] ✓ Notificación encontrada: {notif['id_notificacion']}")
            
            if notif:
                # Si ya fue procesada, mostrar advertencia
                if ya_procesada:
                    show_warning_dialog(
                        self,
                        "Código ya procesado",
                        f"Este código (CASH-{notif['id_notificacion']}) ya fue procesado.\n"
                        f"Miembro: {notif['nombres']} {notif['apellido_paterno']}\n"
                        f"Monto: ${notif.get('monto_pendiente', 0)}"
                    )
                
                logging.info(f"[DEBUG] Abriendo modal de detalles de notificación...")
                # Cerrar el diálogo de debug primero
                dialog.accept()
                
                # Usar el nuevo NotificationDetailModal
                from ui.notification_detail_modal import NotificationDetailModal
                detail_modal = NotificationDetailModal(
                    notif, 
                    self.pg_manager, 
                    self.supabase_service, 
                    self.user_data, 
                    parent=self,
                    sync_manager=getattr(self, 'sync_manager', None)
                )
                detail_modal.notificacion_procesada.connect(self._on_notificacion_procesada_debug)
                result = detail_modal.exec()
                
                if result:
                    logging.info(f"[DEBUG] ✓ Notificación procesada exitosamente")
                    show_success_dialog(
                        self,
                        "Notificación Procesada",
                        f"Notificación procesada para:\n{notif['nombres']} {notif['apellido_paterno']} {notif['apellido_materno']}\n\nCódigo: {codigo_normalizado}"
                    )
                else:
                    logging.info(f"[DEBUG] Usuario canceló el procesamiento")
            else:
                logging.info(f"[DEBUG] ✗ Código no encontrado: {codigo_normalizado}")
                show_warning_dialog(
                    self,
                    "Código No Encontrado",
                    f"No se encontró notificación pendiente con:\n{codigo_normalizado}"
                )
                
        except Exception as e:
            logging.error(f"[DEBUG] Error procesando pago: {e}")
            import traceback
            logging.error(traceback.format_exc())
            show_error_dialog(
                self,
                "Error",
                f"Error procesando pago:\n{str(e)}"
            )
    
    def _on_notificacion_procesada_debug(self, datos_notificacion):
        """Callback cuando se procesa una notificación desde el debug modal"""
        logging.info(f"[DEBUG] Notificación procesada: {datos_notificacion}")
        # Aquí se pueden actualizar contadores, actualizar UI, etc.
            
    def volver_a_ventas(self):
        """Volver a la página principal de ventas"""
        # Restaurar título
        self.top_bar.set_title("HTF POS")
        
        # Mostrar barra de navegación
        self.nav_bar.show()
        
        # Obtener el widget actual
        current_widget = self.stacked_widget.currentWidget()
        
        # Cambiar a la página de ventas (índice 0)
        self.stacked_widget.setCurrentIndex(0)
        self.switch_tab(0)
        
        # Remover el widget de ventas del stack después de un momento
        # para evitar problemas de referencia
        QTimer.singleShot(100, lambda: self.remover_widget_temporal(current_widget))
        
        # Forzar actualización del layout
        QTimer.singleShot(0, self.update_layout)
        
        logging.info("Volviendo a página de ventas")
        
    def update_layout(self):
        """Forzar actualización del layout después de cambiar de widget"""
        current_widget = self.stacked_widget.currentWidget()
        if current_widget:
            current_widget.updateGeometry()
        self.stacked_widget.updateGeometry()
        self.updateGeometry()
        
    def remover_widget_temporal(self, widget):
        """Remover un widget temporal del stack"""
        try:
            index = self.stacked_widget.indexOf(widget)
            if index > 4:  # Solo remover widgets temporales (después de las 5 páginas principales)
                self.stacked_widget.removeWidget(widget)
                widget.deleteLater()
        except Exception as e:
            logging.error(f"Error removiendo widget temporal: {e}")
            
    def on_venta_completada(self, venta_info):
        """Manejar cuando se completa una venta"""
        logging.info(f"Venta completada: ID {venta_info['id_venta']}, Total: ${venta_info['total']:.2f}")
        # Aquí se pueden agregar actualizaciones adicionales como refrescar estadísticas
    
    def abrir_gestion_personal(self):
        """Abrir widget de gestión de personal"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("GESTIÓN DE PERSONAL")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de personal
            personal_widget = PersonalWindow(
                self.pg_manager,
                self.supabase_service
            )
            
            # Conectar señal de cierre
            personal_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(personal_widget)
            self.stacked_widget.setCurrentWidget(personal_widget)
            
            logging.info("Abriendo gestión de personal")
            
        except Exception as e:
            logging.error(f"Error abriendo gestión de personal: {e}")
    
    def abrir_dias_festivos(self):
        """Abrir widget de gestión de días festivos"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("DÍAS FESTIVOS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de días festivos
            festivos_widget = DiasFestvosWindow(self.supabase_service)
            
            # Conectar señal de cierre
            festivos_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(festivos_widget)
            self.stacked_widget.setCurrentWidget(festivos_widget)
            
            logging.info("Abriendo gestión de días festivos")
            
        except Exception as e:
            logging.error(f"Error abriendo gestión de días festivos: {e}")
    
    def abrir_historial_turnos(self):
        """Abrir widget de historial de turnos de caja"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("HISTORIAL DE TURNOS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de historial de turnos
            turnos_widget = HistorialTurnosWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            turnos_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(turnos_widget)
            self.stacked_widget.setCurrentWidget(turnos_widget)
            
            logging.info("Abriendo historial de turnos")
            
        except Exception as e:
            logging.error(f"Error abriendo historial de turnos: {e}")
    
    def abrir_asignacion_turnos(self):
        """Abrir widget de asignación de turnos"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("ASIGNACIÓN DE TURNOS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de asignación de turnos
            asignacion_widget = AsignacionTurnosWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            asignacion_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(asignacion_widget)
            self.stacked_widget.setCurrentWidget(asignacion_widget)
            
            logging.info("Abriendo asignación de turnos")
            
        except Exception as e:
            logging.error(f"Error abriendo asignación de turnos: {e}")
    
    def abrir_gestion_ubicaciones(self):
        """Abrir widget de gestión de ubicaciones"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("GESTIÓN DE UBICACIONES")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de ubicaciones
            ubicaciones_widget = UbicacionesWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            ubicaciones_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(ubicaciones_widget)
            self.stacked_widget.setCurrentWidget(ubicaciones_widget)
            
            logging.info("Abriendo gestión de ubicaciones")
            
        except Exception as e:
            logging.error(f"Error abriendo gestión de ubicaciones: {e}")
    
    def abrir_catalogo_lockers(self):
        """Abrir ventana de catálogo de lockers"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("CATÁLOGO DE LOCKERS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de lockers
            lockers_widget = LockersWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            lockers_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(lockers_widget)
            self.stacked_widget.setCurrentWidget(lockers_widget)
            
            logging.info("Abriendo catálogo de lockers")
            
        except Exception as e:
            logging.error(f"Error abriendo catálogo de lockers: {e}")
    
    def abrir_asignaciones_lockers(self):
        """Abrir ventana de asignación de lockers"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("ASIGNACIONES DE LOCKERS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de asignaciones
            asignaciones_widget = AsignacionesLockersWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            asignaciones_widget.cerrar_solicitado.connect(self.volver_a_miembros)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(asignaciones_widget)
            self.stacked_widget.setCurrentWidget(asignaciones_widget)
            
            logging.info("Abriendo asignaciones de lockers")
            
        except Exception as e:
            logging.error(f"Error abriendo asignaciones de lockers: {e}")
    
    def volver_a_administracion(self):
        """Volver a la página de administración"""
        # Restaurar título
        self.top_bar.set_title("HTF POS")
        
        # Mostrar barra de navegación
        self.nav_bar.show()
        
        # Obtener el widget actual
        current_widget = self.stacked_widget.currentWidget()
        
        # Cambiar a la página de administración (índice 3)
        self.stacked_widget.setCurrentIndex(3)
        self.switch_tab(3)
        
        # Remover el widget temporal
        QTimer.singleShot(100, lambda: self.remover_widget_temporal(current_widget))
        
        # Forzar actualización del layout
        QTimer.singleShot(0, self.update_layout)
        
        logging.info("Volviendo a página de administración")
    
    # ========== MÉTODOS DE INVENTARIO ==========
    
    def abrir_nuevo_producto(self):
        """Abrir el formulario de nuevo producto."""
        try:
            self.top_bar.set_title("NUEVO PRODUCTO")
            self.nav_bar.hide()

            nuevo_producto_widget = NuevoProductoWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                self
            )
            nuevo_producto_widget.cerrar_solicitado.connect(self.volver_a_inventario)
            nuevo_producto_widget.producto_guardado.connect(self.on_producto_guardado)

            self.stacked_widget.addWidget(nuevo_producto_widget)
            self.stacked_widget.setCurrentWidget(nuevo_producto_widget)

            QTimer.singleShot(0, self.update_layout)
            logging.info("Abriendo formulario de nuevo producto.")
        except Exception as e:
            logging.error(f"Error abriendo formulario de nuevo producto: {e}")
    
    def abrir_inventario(self):
        """Abrir widget de inventario"""
        try:
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear ventana de inventario
            inventario_window = InventarioWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                self
            )
            
            # Conectar señal de cerrar
            inventario_window.cerrar_solicitado.connect(self.volver_a_inventario)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(inventario_window)
            self.stacked_widget.setCurrentWidget(inventario_window)
            
            # Actualizar título
            self.top_bar.set_title("INVENTARIO")
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo grid de inventario")
            
        except Exception as e:
            logging.error(f"Error abriendo inventario: {e}")
    
    def abrir_registro_entrada(self):
        """Abrir formulario de registro de entrada"""
        try:
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear ventana de registro de entrada
            entrada_window = MovimientoInventarioWindow(
                "entrada",
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                self
            )
            
            # Conectar señales
            entrada_window.cerrar_solicitado.connect(self.volver_a_inventario)
            entrada_window.movimiento_registrado.connect(self.on_movimiento_registrado)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(entrada_window)
            self.stacked_widget.setCurrentWidget(entrada_window)
            
            # Actualizar título
            self.top_bar.set_title("REGISTRAR ENTRADA")
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo formulario de registro de entrada")
            
        except Exception as e:
            logging.error(f"Error abriendo registro de entrada: {e}")
    
    def abrir_registro_salida(self):
        """Abrir formulario de registro de salida"""
        try:
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear ventana de registro de salida
            salida_window = MovimientoInventarioWindow(
                "salida",
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                self
            )
            
            # Conectar señales
            salida_window.cerrar_solicitado.connect(self.volver_a_inventario)
            salida_window.movimiento_registrado.connect(self.on_movimiento_registrado)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(salida_window)
            self.stacked_widget.setCurrentWidget(salida_window)
            
            # Actualizar título
            self.top_bar.set_title("REGISTRAR SALIDA")
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo formulario de registro de salida")
            
        except Exception as e:
            logging.error(f"Error abriendo registro de salida: {e}")
    
    def volver_a_inventario(self):
        """Volver a la página de inventario"""
        # Restaurar título
        self.top_bar.set_title("HTF POS")
        
        # Mostrar barra de navegación
        self.nav_bar.show()
        
        # Obtener el widget actual
        current_widget = self.stacked_widget.currentWidget()
        
        # Cambiar a la página de inventario (índice 1)
        self.stacked_widget.setCurrentIndex(1)
        self.switch_tab(1)
        
        # Remover el widget temporal
        QTimer.singleShot(100, lambda: self.remover_widget_temporal(current_widget))
        
        # Forzar actualización del layout
        QTimer.singleShot(0, self.update_layout)
        
        logging.info("Volviendo a página de inventario")
    
    def on_producto_guardado(self):
        """Manejar cuando se guarda un producto"""
        logging.info(f"Producto guardado")
        self.volver_a_inventario()
        # Aquí se pueden agregar actualizaciones adicionales
    
    def on_movimiento_registrado(self, movimiento_info):
        """Manejar cuando se registra un movimiento de inventario"""
        logging.info(
            f"Movimiento registrado: {movimiento_info['tipo']} - "
            f"{movimiento_info['producto']} - Cantidad: {movimiento_info['cantidad']}"
        )
    
    def abrir_historial_movimientos(self):
        """Abrir ventana de historial de movimientos"""
        try:
            # Crear ventana de historial
            historial_window = HistorialMovimientosWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                parent=self
            )
            
            # Conectar señal de cerrar
            historial_window.cerrar_solicitado.connect(self.volver_a_inventario)
            
            # Agregar al stacked widget
            index = self.stacked_widget.addWidget(historial_window)
            self.stacked_widget.setCurrentIndex(index)
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Actualizar título
            self.top_bar.set_title("Historial de Movimientos")
            
            logging.info("Ventana de historial de movimientos abierta")
            
        except Exception as e:
            logging.error(f"Error abriendo historial de movimientos: {e}")
    
    def abrir_historial_acceso(self):
        """Abrir ventana de historial de acceso"""
        try:
            # Crear ventana de historial de acceso
            historial_window = HistorialAccesoWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                parent=self
            )
            
            # Conectar señal de cerrar
            historial_window.cerrar_solicitado.connect(self.volver_a_miembros)
            
            # Agregar al stacked widget
            index = self.stacked_widget.addWidget(historial_window)
            self.stacked_widget.setCurrentIndex(index)
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Actualizar título
            self.top_bar.set_title("Historial de Acceso")
            
            logging.info("Ventana de historial de acceso abierta")
            
        except Exception as e:
            logging.error(f"Error abriendo historial de acceso: {e}")
    
    def abrir_buscar_miembro(self):
        """Abrir ventana de búsqueda de miembros"""
        try:
            # Crear ventana de búsqueda
            buscar_window = BuscarMiembroWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                parent=self
            )
            
            # Conectar señal de cerrar
            buscar_window.cerrar_solicitado.connect(self.volver_a_miembros)
            
            # Agregar al stacked widget
            index = self.stacked_widget.addWidget(buscar_window)
            self.stacked_widget.setCurrentIndex(index)
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Actualizar título
            self.top_bar.set_title("Buscar Miembro")
            
            logging.info("Ventana de búsqueda de miembros abierta")
            
        except Exception as e:
            logging.error(f"Error abriendo búsqueda de miembros: {e}")
    
    def volver_a_miembros(self):
        """Volver a la página de miembros"""
        # Restaurar título
        self.top_bar.set_title("HTF POS")
        
        # Mostrar barra de navegación
        self.nav_bar.show()
        
        # Obtener el widget actual
        current_widget = self.stacked_widget.currentWidget()
        
        # Cambiar a la página de miembros (índice 2)
        self.stacked_widget.setCurrentIndex(2)
        self.switch_tab(2)
        
        # Remover el widget temporal
        QTimer.singleShot(100, lambda: self.remover_widget_temporal(current_widget))
        
        # Forzar actualización del layout
        QTimer.singleShot(0, self.update_layout)
        
        logging.info("Volviendo a página de miembros")
    
    # ========== MONITOR DE ENTRADAS ==========
    
    def iniciar_monitor_entradas(self):
        """Inicializar y arrancar el monitor de entradas"""
        try:
            # Crear monitor con Supabase Realtime
            self.monitor_entradas = MonitorEntradas(
                self.pg_manager,
                supabase_service=self.supabase_service
            )

            # Conectar señal
            self.monitor_entradas.nueva_entrada_detectada.connect(self.mostrar_notificacion_entrada)

            # Iniciar monitoreo
            self.monitor_entradas.iniciar()

            logging.info("Monitor de entradas iniciado exitosamente")

        except Exception as e:
            logging.error(f"Error iniciando monitor de entradas: {e}")
            self.monitor_entradas = None
        except Exception as e:
            logging.error(f"Error iniciando monitor de entradas: {e}")
    
    def mostrar_notificacion_entrada(self, entrada_data):
        """Mostrar notificación cuando se detecta una nueva entrada"""
        try:
            # Verificar que tenemos los datos básicos
            if not isinstance(entrada_data, dict):
                logging.error(f"ERROR: entrada_data no es un diccionario: {type(entrada_data)}")
                return

            nombres = entrada_data.get('nombres', 'N/A')
            apellido_paterno = entrada_data.get('apellido_paterno', '')
            id_entrada = entrada_data.get('id_entrada', 'N/A')
            logging.info(f"🔔 Nueva entrada detectada - ID: {id_entrada}, Miembro: {nombres} {apellido_paterno}")

            # Usar QTimer.singleShot para diferir la creación al próximo ciclo del event loop
            # Esto asegura que se ejecute en el hilo principal de manera segura
            QTimer.singleShot(0, lambda: self._crear_notificacion_segura(entrada_data))

        except Exception as e:
            logging.error(f"Error en mostrar_notificacion_entrada: {e}")
            import traceback
            traceback.print_exc()

    def _crear_notificacion_segura(self, entrada_data):
        """Crear la notificación de manera segura en el hilo principal"""
        try:
            # Crear ventana de notificación (sin auto-cierre)
            notificacion = NotificacionEntradaWidget(
                miembro_data=entrada_data,
                parent=self,
                duracion=0  # 0 = no auto-cerrar, usuario debe cerrar manualmente
            )

            # Posicionar en la esquina superior derecha
            self.posicionar_notificacion(notificacion)

            # Conectar señal de cierre
            notificacion.cerrado.connect(lambda: self.remover_notificacion(notificacion))

            # Conectar señal de asignación de cargo
            notificacion.cargo_asignado.connect(self.manejar_asignacion_cargo)

            # Agregar a lista de notificaciones activas
            self.notificaciones_activas.append(notificacion)

            # Mostrar
            notificacion.show()

            logging.info(f"✅ Notificación mostrada para entrada ID: {entrada_data.get('id_entrada', 'N/A')}")

        except Exception as e:
            logging.error(f"Error creando notificación segura: {e}")
            import traceback
            traceback.print_exc()

    def posicionar_notificacion(self, notificacion):
        """Posicionar notificación en la pantalla"""
        # Obtener geometría de la ventana principal
        main_geometry = self.geometry()
        
        # Calcular posición (esquina superior derecha con margen)
        margen = 20
        x = main_geometry.right() - notificacion.width() - margen
        y = main_geometry.top() + margen
        
        # Ajustar posición si hay otras notificaciones
        offset_vertical = 0
        for notif in self.notificaciones_activas:
            if notif.isVisible():
                offset_vertical += notif.height() + 10
        
        y += offset_vertical
        
        # Establecer posición
        notificacion.move(x, y)
    
    def remover_notificacion(self, notificacion):
        """Remover notificación de la lista activa"""
        if notificacion in self.notificaciones_activas:
            self.notificaciones_activas.remove(notificacion)
            logging.debug(f"Notificación removida. Activas: {len(self.notificaciones_activas)}")
    
    def closeEvent(self, event):
        """Evento al cerrar la ventana principal"""
        try:
            # Verificar si hay turno abierto
            if self.turno_id and self.pg_manager:
                try:
                    response = self.pg_manager.client.table('turnos_caja').select(
                        'id_turno, fecha_apertura, monto_inicial, cerrado'
                    ).eq('id_turno', self.turno_id).execute()
                    
                    if response.data and len(response.data) > 0:
                        turno = response.data[0]
                        if not turno.get('cerrado'):
                            # Mostrar advertencia de turno abierto
                            from ui.components import show_confirmation_dialog
                            from datetime import datetime
                            
                            fecha_apertura = turno.get('fecha_apertura', '')
                            if isinstance(fecha_apertura, str):
                                try:
                                    fecha_obj = datetime.fromisoformat(fecha_apertura.replace('Z', '+00:00'))
                                    fecha_apertura = fecha_obj.strftime('%d/%m/%Y %H:%M')
                                except:
                                    pass
                            
                            # Preguntar si desea cerrar de todas formas
                            respuesta = show_confirmation_dialog(
                                self,
                                "Turno Abierto",
                                f"⚠️ ADVERTENCIA: Tienes un turno abierto\n\n"
                                f"Fecha apertura: {fecha_apertura}\n"
                                f"Monto inicial: ${float(turno.get('monto_inicial', 0)):.2f}\n\n"
                                f"Recuerda cerrar el turno antes de finalizar el día.",
                                detail="¿Deseas cerrar el POS de todas formas?",
                                confirm_text="Cerrar de todas formas",
                                cancel_text="Cancelar"
                            )
                            
                            # Si el usuario cancela, ignorar el evento de cierre
                            if not respuesta:
                                event.ignore()
                                return
                                
                except Exception as e:
                    logging.error(f"Error verificando turno al cerrar: {e}")
            
            # PRIMERO: Detener monitor de entradas ANTES de aceptar el cierre
            if self.monitor_entradas:
                try:
                    self.monitor_entradas.detener()
                    logging.info("Monitor de entradas detenido")
                except Exception as e:
                    logging.error(f"Error deteniendo monitor de entradas: {e}")
            
            # Cerrar todas las notificaciones activas
            for notificacion in list(self.notificaciones_activas):
                try:
                    notificacion.close()
                except:
                    pass
            
            self.notificaciones_activas.clear()
            
            # AHORA sí aceptar el evento de cierre
            event.accept()
            
        except KeyboardInterrupt:
            # Manejar interrupción del teclado (Ctrl+C)
            logging.warning("Cierre interrumpido por el usuario (Ctrl+C)")
            
            # Forzar detención de threads incluso con interrupción
            try:
                if self.monitor_entradas:
                    self.monitor_entradas.detener()
                    logging.info("Monitor de entradas detenido (forzado)")
            except:
                pass
                
            # Cerrar notificaciones
            try:
                for notificacion in list(self.notificaciones_activas):
                    try:
                        notificacion.close()
                    except:
                        pass
                self.notificaciones_activas.clear()
            except:
                pass
                
            # Aceptar el cierre incluso con interrupción
            event.accept()
                
        except Exception as e:
            logging.error(f"Error en closeEvent: {e}")
            event.accept()

    def _aplicar_multa(self, miembro_data, multa_producto):
        """Registrar multa por suplantación llamando a la Edge Function de Supabase"""
        try:
            import requests
            from datetime import datetime

            # Preparar datos para la Edge Function
            edge_function_url = "https://ufnmqxyvrfionysjeiko.supabase.co/functions/v1/create-fine-unauthorized-access"

            # Determinar el tipo de multa basado en el producto
            fine_type = 'multa_qr'  # Default
            if multa_producto.get('tipo') == 'multa_llave':
                fine_type = 'multa_llave'

            payload = {
                'member_id': miembro_data['id_miembro'],
                'fine_type': fine_type,
                'reason': 'Uso no autorizado de cuenta detectado por encargado'
            }

            # Obtener headers de autenticación de Supabase
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.pg_manager.supabase_key}'
            }

            # Llamar a la Edge Function
            response = requests.post(edge_function_url, json=payload, headers=headers)
            response.raise_for_status()  # Lanzar excepción si hay error HTTP

            result = response.json()

            if result.get('success'):
                fine_id = result.get('fine_id')
                monto = result.get('monto')
                logging.info(f"✅ Multa aplicada exitosamente via Edge Function - Recargo ID: {fine_id}")

                # Mostrar mensaje de éxito
                from ui.components import show_info_dialog
                show_info_dialog(
                    self,
                    "Multa Registrada",
                    f"Multa por suplantación registrada exitosamente al miembro {miembro_data.get('nombres', '')} {miembro_data.get('apellido_paterno', '')}.\n\nMonto: ${monto:.2f}\n\nSe ha enviado una notificación push al miembro y la multa queda pendiente de pago."
                )
            else:
                logging.error("Error en respuesta de Edge Function")
                from ui.components import show_error_dialog
                show_error_dialog(self, "Error", "No se pudo registrar la multa en el sistema.")

        except requests.exceptions.RequestException as e:
            logging.error(f"Error llamando a Edge Function: {e}")
            from ui.components import show_error_dialog
            show_error_dialog(self, "Error de Conexión", f"Error conectando con el servidor:\n{str(e)}")
        except Exception as e:
            logging.error(f"Error aplicando multa: {e}")
            import traceback
            traceback.print_exc()
            from ui.components import show_error_dialog
            show_error_dialog(self, "Error", f"Error aplicando la multa:\n{str(e)}")

    def manejar_asignacion_cargo(self, miembro_data):
        """Manejar la aplicación de multa por suplantación de identidad"""
        try:
            logging.info(f"Aplicando multa por suplantación al miembro: {miembro_data.get('nombres', 'N/A')} {miembro_data.get('apellido_paterno', '')}")

            # 1. Buscar el producto digital "multa"
            multa_producto = self.pg_manager.get_producto_digital_by_name("Multa de Identidad")
            
            if not multa_producto:
                from ui.components import show_error_dialog
                show_error_dialog(self, "Error", "No se encontró el producto digital 'Multa de Identidad' configurado en el sistema.\n\nPor favor, configure un producto digital llamado 'Multa de Identidad' en la tabla ca_productos_digitales.")
                return
            
            # 2. Mostrar diálogo de confirmación
            dialog = ConfirmarMultaDialog(
                miembro_data=miembro_data,
                multa_producto=multa_producto,
                parent=self
            )
            
            result = dialog.exec()
            
            if result == QDialog.Accepted:
                # 3. Aplicar la multa - crear venta digital
                self._aplicar_multa(miembro_data, multa_producto)
            else:
                logging.info("Aplicación de multa cancelada por el usuario")

        except Exception as e:
            logging.error(f"Error manejando aplicación de multa: {e}")
            import traceback
            traceback.print_exc()


class ConfirmarMultaDialog(QDialog):
    """Diálogo para confirmar la aplicación de multa por suplantación"""
    
    def __init__(self, miembro_data, multa_producto, parent=None):
        super().__init__(parent)
        self.miembro_data = miembro_data
        self.multa_producto = multa_producto
        
        self.setWindowTitle("Confirmar Multa por Suplantación")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = QLabel("⚠️ CONFIRMAR MULTA POR SUPLANTACIÓN")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #d32f2f;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Información del miembro
        info_group = QGroupBox("Información del Miembro")
        info_layout = QVBoxLayout(info_group)
        
        nombre_completo = f"{self.miembro_data.get('nombres', '')} {self.miembro_data.get('apellido_paterno', '')} {self.miembro_data.get('apellido_materno', '')}".strip()
        info_layout.addWidget(QLabel(f"Nombre: {nombre_completo}"))
        info_layout.addWidget(QLabel(f"ID Miembro: {self.miembro_data.get('id_miembro', 'N/A')}"))
        info_layout.addWidget(QLabel(f"Teléfono: {self.miembro_data.get('telefono', 'N/A')}"))
        
        layout.addWidget(info_group)
        
        # Información de la multa
        multa_group = QGroupBox("Detalles de la Multa")
        multa_layout = QVBoxLayout(multa_group)
        
        multa_layout.addWidget(QLabel(f"Producto: {self.multa_producto.get('nombre', 'Multa')}"))
        multa_layout.addWidget(QLabel(f"Descripción: {self.multa_producto.get('descripcion', 'Multa por suplantación de identidad')}"))
        multa_layout.addWidget(QLabel(f"Monto: ${self.multa_producto.get('precio_venta', 0):.2f}"))
        
        layout.addWidget(multa_group)
        
        # Mensaje de advertencia
        warning_label = QLabel("⚠️ Esta acción no se puede deshacer.\nLa multa será cobrada inmediatamente.")
        warning_label.setStyleSheet("color: #f57c00; font-weight: bold;")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)
        
        layout.addStretch()
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                font-size: 14px;
                background-color: #757575;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        btn_cancelar.clicked.connect(self.reject)
        
        btn_confirmar = QPushButton("✅ Aplicar Multa")
        btn_confirmar.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
        """)
        btn_confirmar.clicked.connect(self.accept)
        
        buttons_layout.addWidget(btn_cancelar)
        buttons_layout.addWidget(btn_confirmar)
        
        layout.addLayout(buttons_layout)