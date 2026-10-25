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
    CancelarPagosWindow,
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
from ui.asignar_locker_diario_window import AsignarLockerDiarioWindow
from ui.historial_lockers_window import HistorialLockersWindow
from utils.monitor_entradas_fastapi import MonitorEntradasFastAPI
from database.postgres_manager import PostgresManager


def _limite_notificaciones():
    """
    Cuántos avisos de entrada pueden estar abiertos a la vez.

    Cada notificación abierta ocupa unos 2.3 MB. Sin tope, una jornada con el
    torniquete activo llegaba a cientos de ventanas y la máquina se arrastraba.
    Ajustable con NOTIFICACIONES_MAX_VISIBLES en el .env.
    """
    crudo = (os.getenv('NOTIFICACIONES_MAX_VISIBLES') or '').strip()
    if crudo:
        try:
            valor = int(crudo)
            if 1 <= valor <= 50:
                return valor
            logging.warning(
                f"[AVISO] NOTIFICACIONES_MAX_VISIBLES={valor} fuera de rango (1-50); "
                f"se usa 8."
            )
        except ValueError:
            logging.warning(
                f"[AVISO] NOTIFICACIONES_MAX_VISIBLES={crudo!r} no es un numero; "
                f"se usa 8."
            )
    return 8


MAX_NOTIFICACIONES_VISIBLES = _limite_notificaciones()


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
        
        # Monitor de entradas FastAPI
        self.monitor_entradas = None
        self.notificaciones_activas = []  # Lista de notificaciones abiertas
        
        # Aplicar estilos Windows Phone
        apply_windows_phone_stylesheet(self)
        
        self.setup_ui()
        
        # Iniciar monitor de entradas
        self.iniciar_monitor_entradas()

    def _role_lower(self) -> str:
        return (self.user_data.get('rol') or '').lower()

    def _sales_disabled_for_role(self) -> bool:
        return self._role_lower() == 'administrador'

    def _tiene_permiso(self, permiso) -> bool:
        """
        Si el usuario de la sesión tiene un permiso.

        Ante cualquier fallo responde False: más vale esconder una pestaña de
        más que mostrar una a quien no le toca.
        """
        try:
            id_usuario = (self.user_data or {}).get('id_usuario')
            if not id_usuario or not self.pg_manager:
                return False
            return bool(self.pg_manager.tiene_permiso(id_usuario, permiso))
        except Exception as e:
            logging.error(f"[ERROR] No se pudo comprobar el permiso {permiso!r}: {e}")
            return False

    def puede_ver_inventario(self) -> bool:
        """
        Quién ve la pestaña Inventario.

        Se exige `inventario.actualizar`, que es un permiso OTORGABLE: así un
        administrador puede dárselo a una recepcionista concreta y la pestaña
        le aparece. Administración lo trae de serie por su rol.
        """
        from database.permisos import INVENTARIO_ACTUALIZAR

        return self._tiene_permiso(INVENTARIO_ACTUALIZAR)

    def puede_ver_administracion(self) -> bool:
        """Quién ve la pestaña Admin: solo quien puede gestionar cuentas."""
        from database.permisos import USUARIOS_GESTIONAR

        return self._tiene_permiso(USUARIOS_GESTIONAR)

    def puede_cambiar_contrasenas(self) -> bool:
        """
        Quién puede cambiar contraseñas: solo administración.

        Una recepcionista ya no cambia la suya desde el POS; se la cambia un
        administrador desde Admin -> Gestionar Usuarios.
        """
        from database.permisos import USUARIOS_GESTIONAR

        return self._tiene_permiso(USUARIOS_GESTIONAR)

    def puede_ver_configuracion(self) -> bool:
        """
        Quién ve la pestaña Configuración.

        Para una recepcionista quedaría vacía: sin sincronizar, sin respaldar,
        sin cambio de contraseña, y con el cierre de sesión ya en la barra
        inferior. Así que directamente no se le muestra.
        """
        return self.puede_cambiar_contrasenas()

    def _default_tab_index(self) -> int:
        # Para administrador arrancar en Admin (evitar ver Ventas)
        if self._sales_disabled_for_role():
            return 3
        return 0
        
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

        # Seleccionar pestaña inicial según rol
        desired_index = self._default_tab_index()
        available_indices = [getattr(btn, '_tab_index', None) for btn in getattr(self, 'tab_buttons', [])]
        available_indices = [idx for idx in available_indices if isinstance(idx, int)]
        if available_indices and desired_index not in available_indices:
            desired_index = available_indices[0]
        self.switch_tab(desired_index)
        
    def create_bottom_nav(self, parent_layout):
        """Crear barra de navegación inferior usando TabButton"""
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("navBar")
        self.nav_bar.setFixedHeight(WindowsPhoneTheme.NAV_BAR_HEIGHT)
        
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        
        # Definir pestañas con iconos y colores
        role = self._role_lower()
        tabs = [
            {"name": "Ventas", "icon": "fa5s.shopping-cart", "color": WindowsPhoneTheme.TILE_RED, "index": 0},
            {"name": "Inventario", "icon": "fa5s.boxes", "color": WindowsPhoneTheme.TILE_GREEN, "index": 1},
            {"name": "Miembros", "icon": "fa5s.users", "color": WindowsPhoneTheme.TILE_ORANGE, "index": 2},
            {"name": "Admin", "icon": "fa5s.user-shield", "color": WindowsPhoneTheme.TILE_PURPLE, "index": 3},
            {"name": "Config", "icon": "fa5s.cog", "color": WindowsPhoneTheme.TILE_GRAY, "index": 4},
        ]

        # Las pestañas se deciden por PERMISOS, no por el nombre del rol. Antes
        # se ocultaban con `if role == 'recepcionista'`, así que otorgarle
        # inventario a una recepcionista no servía de nada: el permiso quedaba
        # guardado y era efectivo, pero la pestaña seguía sin aparecer.
        if not self.puede_ver_inventario():
            tabs = [t for t in tabs if t['name'] != 'Inventario']

        if not self.puede_ver_administracion():
            tabs = [t for t in tabs if t['name'] != 'Admin']

        if not self.puede_ver_configuracion():
            tabs = [t for t in tabs if t['name'] != 'Config']

        # Administrador: ocultar Ventas
        if self._sales_disabled_for_role():
            tabs = [t for t in tabs if t['name'] != 'Ventas']
        
        # Crear botones usando componente TabButton
        self.tab_buttons = []
        for tab in tabs:
            btn = TabButton(tab['name'], tab['icon'], tab['color'])
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn._tab_index = tab['index']
            btn.clicked.connect(lambda checked, idx=tab['index']: self.switch_tab(idx))
            nav_layout.addWidget(btn)
            self.tab_buttons.append(btn)

        # Cerrar sesión en la barra inferior para quien no tiene pestaña de
        # Configuración, que es donde vive ese botón para administración.
        # No es una pestaña: no cambia de página, ejecuta la acción.
        if not self.puede_ver_configuracion():
            btn_salir = TabButton("Salir", "fa5s.sign-out-alt", WindowsPhoneTheme.TILE_RED)
            btn_salir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn_salir.setCheckable(False)
            btn_salir.clicked.connect(self.handle_logout)
            nav_layout.addWidget(btn_salir)
            self.boton_salir = btn_salir

        # El check inicial lo define setup_ui() vía switch_tab

        parent_layout.addWidget(self.nav_bar)
        
    def switch_tab(self, index):
        """Cambiar de pestaña"""
        self.current_tab = index
        self.stacked_widget.setCurrentIndex(index)
        
        # Actualizar estado visual de botones
        for btn in self.tab_buttons:
            btn_index = getattr(btn, '_tab_index', None)
            btn.setChecked(btn_index == index)
            
        logging.info(f"Cambio a pestaña: {index}")
        
    # ========== PÁGINAS DE CONTENIDO ==========
    
    def create_sales_page(self):
        """Página de ventas usando TileButton"""
        page = QWidget()
        layout = create_page_layout("PUNTO DE VENTA")
        page.setLayout(layout)
        
        # Grid de tiles - 2 filas: dos arriba, Cierre de Caja a lo ancho abajo
        grid = create_tile_grid_layout()

        # Botones de acciones usando componente TileButton
        btn_nueva_venta = TileButton("Nueva Venta", "fa5s.cash-register", WindowsPhoneTheme.TILE_RED)
        btn_nueva_venta.clicked.connect(self.abrir_nueva_venta)
        grid.addWidget(btn_nueva_venta, 0, 0)
        
        btn_ventas_dia = TileButton("Ventas del Día", "fa5s.list-alt", WindowsPhoneTheme.TILE_ORANGE)
        btn_ventas_dia.clicked.connect(self.abrir_ventas_dia)
        grid.addWidget(btn_ventas_dia, 0, 1)
        
        btn_cierre = TileButton("Cierre de Caja", "fa5s.lock", WindowsPhoneTheme.TILE_MAGENTA)
        btn_cierre.clicked.connect(self.abrir_cierre_caja)
        grid.addWidget(btn_cierre, 1, 0, 1, 2)
        
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
        btn_lockers.clicked.connect(self.abrir_asignaciones_lockers)  # Mensuales
        
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
            btn_usuarios = TileButton("Gestionar\nUsuarios", "fa5s.user-shield", WindowsPhoneTheme.TILE_PURPLE)
            btn_usuarios.clicked.connect(self.abrir_gestion_usuarios)
            admin_grid.addWidget(btn_usuarios, 0, 0)

            btn_permisos = TileButton("Permisos\nEspeciales", "fa5s.user-lock", WindowsPhoneTheme.TILE_MAGENTA)
            btn_permisos.clicked.connect(self.abrir_gestion_permisos)
            admin_grid.addWidget(btn_permisos, 0, 1)

            btn_personal = TileButton("Gestionar\nPersonal", "fa5s.users-cog", WindowsPhoneTheme.TILE_GREEN)
            btn_personal.clicked.connect(self.abrir_gestion_personal)
            admin_grid.addWidget(btn_personal, 0, 2)
            
            btn_dias_festivos = TileButton("Días\nFestivos", "fa5s.calendar-alt", WindowsPhoneTheme.TILE_BLUE)
            btn_dias_festivos.clicked.connect(self.abrir_dias_festivos)
            admin_grid.addWidget(btn_dias_festivos, 0, 3)
            
            # Fila 2
            btn_historial_turnos = TileButton("Historial\nTurnos", "fa5s.cash-register", WindowsPhoneTheme.TILE_TEAL)
            btn_historial_turnos.clicked.connect(self.abrir_historial_turnos)
            admin_grid.addWidget(btn_historial_turnos, 1, 0)
            
            btn_asignar_turnos = TileButton("Asignar\nTurnos", "fa5s.calendar-check", WindowsPhoneTheme.TILE_ORANGE)
            btn_asignar_turnos.clicked.connect(self.abrir_asignacion_turnos)
            admin_grid.addWidget(btn_asignar_turnos, 1, 1)
            
            btn_ubicaciones = TileButton("Gestionar\nUbicaciones", "fa5s.warehouse", WindowsPhoneTheme.TILE_BLUE)
            btn_ubicaciones.clicked.connect(self.abrir_gestion_ubicaciones)
            admin_grid.addWidget(btn_ubicaciones, 1, 2)
            
            btn_catalogo_lockers = TileButton("Catálogo\nde Lockers", "mdi.locker-multiple", WindowsPhoneTheme.TILE_TEAL)
            btn_catalogo_lockers.clicked.connect(self.abrir_catalogo_lockers)
            admin_grid.addWidget(btn_catalogo_lockers, 1, 3)
            
            btn_historial_ventas = TileButton("Historial\nVentas", "fa5s.history", WindowsPhoneTheme.TILE_PURPLE)
            btn_historial_ventas.clicked.connect(self.abrir_historial)
            admin_grid.addWidget(btn_historial_ventas, 2, 0)
            
            btn_historial_lockers = TileButton("Historial\nLockers", "fa5s.key", WindowsPhoneTheme.TILE_MAGENTA)
            btn_historial_lockers.clicked.connect(self.abrir_historial_lockers)
            admin_grid.addWidget(btn_historial_lockers, 2, 1)

            btn_cancelar_pagos = TileButton("Cancelar\nPagos", "fa5s.ban", WindowsPhoneTheme.TILE_RED)
            btn_cancelar_pagos.clicked.connect(self.abrir_cancelar_pagos)
            admin_grid.addWidget(btn_cancelar_pagos, 2, 2)
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
        
        # "Sincronizar" y "Respaldar Datos" se retiraron: eran mosaicos sin
        # ninguna acción conectada, así que no hacían nada al pulsarlos.
        columna = 0

        # El cambio de contraseña queda reservado a administración, que lo
        # gestiona desde Admin -> Gestionar Usuarios.
        if self.puede_cambiar_contrasenas():
            btn_change_password = TileButton(
                "Cambiar Contraseña", "fa5s.lock", WindowsPhoneTheme.TILE_ORANGE
            )
            btn_change_password.clicked.connect(self.cambiar_contrasena)
            config_grid.addWidget(btn_change_password, 0, columna)
            columna += 1

        # Cerrar sesión vive aquí solo para administración. Las recepcionistas
        # no ven esta pestaña, así que su botón está en la barra inferior.
        btn_logout = TileButton("Cerrar Sesión", "fa5s.sign-out-alt", WindowsPhoneTheme.TILE_RED)
        btn_logout.clicked.connect(self.handle_logout)
        config_grid.addWidget(btn_logout, 0, columna)

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
            
    def abrir_historial_lockers(self):
        """Abrir widget de historial de lockers"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("HISTORIAL DE LOCKERS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de historial de lockers
            historial_lockers_widget = HistorialLockersWindow(
                self.pg_manager, 
                self.supabase_service, 
                self.user_data, 
                self
            )
            
            # Conectar señal para volver a administración
            historial_lockers_widget.cerrar_solicitado.connect(self.volver_a_administracion)
            
            # Agregar al stack y cambiar a esa vista
            self.stacked_widget.addWidget(historial_lockers_widget)
            self.stacked_widget.setCurrentWidget(historial_lockers_widget)
            
            # Forzar actualización del layout
            QTimer.singleShot(0, self.update_layout)
            
            logging.info("Abriendo widget de historial de lockers")
        except Exception as e:
            logging.error(f"Error abriendo historial de lockers: {e}")

    def abrir_cancelar_pagos(self):
        """Abrir widget para cancelar pagos desde administración"""
        try:
            self.top_bar.set_title("CANCELAR PAGOS")
            self.nav_bar.hide()

            cancelar_pagos_widget = CancelarPagosWindow(
                self.pg_manager,
                self.supabase_service,
                self.user_data,
                self
            )
            cancelar_pagos_widget.cerrar_solicitado.connect(self.volver_a_administracion)

            self.stacked_widget.addWidget(cancelar_pagos_widget)
            self.stacked_widget.setCurrentWidget(cancelar_pagos_widget)

            QTimer.singleShot(0, self.update_layout)

            logging.info("Abriendo widget de cancelación de pagos")
        except Exception as e:
            logging.error(f"Error abriendo cancelación de pagos: {e}")
            
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
    
    def abrir_gestion_usuarios(self):
        """Abrir la gestión de cuentas de acceso al POS."""
        try:
            # Defensa en profundidad: el botón ya está oculto para otros roles,
            # pero se vuelve a comprobar aquí por si se llegara por otra vía.
            if self._role_lower() not in ('administrador', 'sistemas'):
                logging.warning(
                    f"[SEGURIDAD] Intento de abrir Gestionar Usuarios con rol "
                    f"'{self._role_lower()}' (usuario "
                    f"{self.user_data.get('username', '?')})"
                )
                show_warning_dialog(
                    self, "Acceso denegado",
                    "Solo un administrador puede gestionar usuarios."
                )
                return

            from ui.usuarios_window import UsuariosWindow

            self.top_bar.set_title("GESTIÓN DE USUARIOS")
            self.nav_bar.hide()

            usuarios_widget = UsuariosWindow(self.pg_manager, self.user_data)
            usuarios_widget.cerrar_solicitado.connect(self.volver_a_administracion)

            self.stacked_widget.addWidget(usuarios_widget)
            self.stacked_widget.setCurrentWidget(usuarios_widget)

            logging.info(
                f"[OK] Gestión de usuarios abierta por "
                f"'{self.user_data.get('username', '?')}'"
            )
        except Exception as e:
            logging.error(f"[ERROR] Error abriendo gestión de usuarios: {e}")
            show_error_dialog(self, "Error",
                              "No se pudo abrir la gestión de usuarios.", str(e))

    def abrir_gestion_permisos(self):
        """Abrir el otorgamiento de permisos especiales a recepción."""
        try:
            # Defensa en profundidad: el botón ya está oculto para otros roles,
            # pero se vuelve a comprobar aquí por si se llegara por otra vía.
            if self._role_lower() not in ('administrador', 'sistemas'):
                logging.warning(
                    f"[SEGURIDAD] Intento de abrir Permisos Especiales con rol "
                    f"'{self._role_lower()}' (usuario "
                    f"{self.user_data.get('username', '?')})"
                )
                show_warning_dialog(
                    self, "Acceso denegado",
                    "Solo un administrador puede otorgar permisos especiales."
                )
                return

            from ui.permisos_window import PermisosWindow

            self.top_bar.set_title("PERMISOS ESPECIALES")
            self.nav_bar.hide()

            permisos_widget = PermisosWindow(self.pg_manager, self.user_data)
            permisos_widget.cerrar_solicitado.connect(self.volver_a_administracion)

            self.stacked_widget.addWidget(permisos_widget)
            self.stacked_widget.setCurrentWidget(permisos_widget)

            logging.info(
                f"[OK] Permisos especiales abiertos por "
                f"'{self.user_data.get('username', '?')}'"
            )
        except Exception as e:
            logging.error(f"[ERROR] Error abriendo permisos especiales: {e}")
            show_error_dialog(self, "Error",
                              "No se pudo abrir el módulo de permisos.", str(e))

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
        """Abrir ventana de asignación de lockers mensuales"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("ASIGNACIONES DE LOCKERS MENSUALES")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de asignaciones
            asignaciones_widget = AsignacionesLockersWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            asignaciones_widget.cerrar_solicitado.connect(self.volver_a_miembros)
            
            # Conectar signal para abrir diarios desde mensuales
            asignaciones_widget.abrir_diarios_solicitado.connect(self.abrir_asignaciones_lockers_diarios)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(asignaciones_widget)
            self.stacked_widget.setCurrentWidget(asignaciones_widget)
            
            logging.info("Abriendo asignaciones de lockers mensuales")
            
        except Exception as e:
            logging.error(f"Error abriendo asignaciones de lockers: {e}")
    
    def abrir_asignaciones_lockers_diarios(self):
        """Abrir ventana de asignación de lockers diarios"""
        try:
            # Actualizar título de la barra superior
            self.top_bar.set_title("ASIGNACIONES DE LOCKERS DIARIOS")
            
            # Ocultar barra de navegación
            self.nav_bar.hide()
            
            # Crear widget de asignaciones diarias
            asignaciones_diarias_widget = AsignarLockerDiarioWindow(self.pg_manager, self.user_data)
            
            # Conectar señal de cierre
            asignaciones_diarias_widget.cerrar_solicitado.connect(self.volver_a_miembros)
            
            # Conectar signal para abrir mensuales desde diarios
            asignaciones_diarias_widget.abrir_mensuales_solicitado.connect(self.abrir_asignaciones_lockers)
            
            # Agregar al stack y mostrar
            self.stacked_widget.addWidget(asignaciones_diarias_widget)
            self.stacked_widget.setCurrentWidget(asignaciones_diarias_widget)
            
            logging.info("Abriendo asignaciones de lockers diarios")
            
        except Exception as e:
            logging.error(f"Error abriendo asignaciones de lockers diarios: {e}")
    
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
    
    # ========== MONITOR DE ENTRADAS FASTAPI ==========
    
    def iniciar_monitor_entradas(self):
        """Inicializar y arrancar el monitor de entradas FastAPI"""
        try:
            if not self.pg_manager:
                logging.warning("PostgresManager no disponible, monitor de entradas no se iniciará")
                return
            
            # Crear monitor FastAPI (servidor se inicia automáticamente)
            # listen_host=None: lo resuelve la configuración de seguridad
            # (0.0.0.0 solo si TORNIQUETE_API_TOKEN está configurado;
            #  127.0.0.1 si no, para no exponer un servidor sin autenticar).
            self.monitor_entradas = MonitorEntradasFastAPI(
                postgres_manager=self.pg_manager,
                host="127.0.0.1",
                port=8001,
                listen_host=None
            )

            # Conectar señal
            self.monitor_entradas.nueva_entrada_detectada.connect(self.mostrar_notificacion_entrada)

            # Iniciar monitoreo (esto inicia el servidor FastAPI automáticamente)
            self.monitor_entradas.iniciar()

            logging.info("[OK] Monitor de entradas FastAPI iniciado exitosamente")
            logging.info(
                f"[SERVIDOR] Escuchando en "
                f"http://{self.monitor_entradas.listen_host}:8001/entrada"
            )

        except Exception as e:
            logging.error(f"[ERROR] Error iniciando monitor de entradas: {e}")
            import traceback
            logging.error(traceback.format_exc())
            self.monitor_entradas = None
    
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
            activas_count = len(self.notificaciones_activas)
            logging.info(f"[ENTRADA] Nueva entrada detectada - ID: {id_entrada}, Miembro: {nombres} {apellido_paterno}")
            logging.info(f"[MONITOR] Notificaciones activas al recibir señal: {activas_count}")
            if activas_count >= 3:
                logging.warning(f"[MONITOR] ALERTA: hay {activas_count} notificaciones activas (>= 3). Posible bloqueo de nuevas ventanas.")
                for i, n in enumerate(self.notificaciones_activas):
                    try:
                        logging.warning(f"[MONITOR]   [{i}] visible={n.isVisible()} pos=({n.x()},{n.y()}) size=({n.width()}x{n.height()}) id={getattr(n, 'miembro_data', {}).get('id_entrada', '?')}")
                    except Exception as log_ex:
                        logging.warning(f"[MONITOR]   [{i}] error leyendo estado: {log_ex}")

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
            id_entrada = entrada_data.get('id_entrada', 'N/A')
            logging.info(f"[MONITOR] _crear_notificacion_segura inicio - ID: {id_entrada}, activas previas: {len(self.notificaciones_activas)}")

            # Limpiar referencias a notificaciones ya cerradas/destruidas
            antes = len(self.notificaciones_activas)
            self.notificaciones_activas = [n for n in self.notificaciones_activas if n.isVisible()]
            despues = len(self.notificaciones_activas)
            if antes != despues:
                logging.info(f"[MONITOR] Limpieza de notificaciones no visibles: {antes} -> {despues}")

            # Crear ventana de notificación (sin auto-cierre)
            notificacion = NotificacionEntradaWidget(
                miembro_data=entrada_data,
                parent=self,
                duracion=0  # 0 = no auto-cerrar, usuario debe cerrar manualmente
            )
            logging.info(f"[MONITOR] NotificacionEntradaWidget creada - size=({notificacion.width()}x{notificacion.height()}) windowFlags={int(notificacion.windowFlags())}")

            # Posicionar en la esquina superior derecha
            self.posicionar_notificacion(notificacion)

            # Conectar señal de cierre
            notificacion.cerrado.connect(lambda: self.remover_notificacion(notificacion))

            # Conectar señal de asignación de cargo
            notificacion.cargo_asignado.connect(self.manejar_asignacion_cargo)

            # Agregar a lista de notificaciones activas
            self.notificaciones_activas.append(notificacion)
            self._limitar_notificaciones_abiertas()
            logging.info(f"[MONITOR] Notificacion agregada a lista. Total activas ahora: {len(self.notificaciones_activas)}")

            # Mostrar
            notificacion.show()
            logging.info(f"[MONITOR] notificacion.show() llamado - isVisible={notificacion.isVisible()} pos=({notificacion.x()},{notificacion.y()})")

            logging.info(f"[OK] Notificacion mostrada para entrada ID: {id_entrada}")

        except Exception as e:
            logging.error(f"Error creando notificación segura: {e}")
            import traceback
            traceback.print_exc()

    def posicionar_notificacion(self, notificacion):
        """Posicionar notificación en la pantalla sin salirse del área visible.

        Las notificaciones se apilan verticalmente en la esquina superior derecha.
        Cuando la columna se llena, se abre una segunda columna a la izquierda,
        y así sucesivamente, garantizando que siempre sean visibles.
        """
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        screen_geom = screen.availableGeometry() if screen else self.geometry()

        margen = 20
        gap = 10
        notif_w = notificacion.width()
        notif_h = notificacion.height()

        # Límites seguros de la pantalla
        area_top = screen_geom.top() + margen
        area_bottom = screen_geom.bottom() - margen
        area_right = screen_geom.right() - margen

        # Calcular posición iterando sobre las notificaciones activas visibles
        # para encontrar el primer hueco libre que quepa dentro de la pantalla.
        # Estrategia: columnas de derecha a izquierda.
        columna = 0
        y_acum = area_top

        for notif in self.notificaciones_activas:
            if not notif.isVisible():
                continue
            y_siguiente = y_acum + notif.height() + gap
            if y_siguiente + notif_h > area_bottom:
                # Esta columna se llenó, pasar a la siguiente (más a la izquierda)
                columna += 1
                y_acum = area_top
            else:
                y_acum = y_siguiente

        x = area_right - notif_w - columna * (notif_w + gap)
        y = y_acum

        # Salvaguarda: si incluso con columnas x queda fuera, forzar al área visible
        x = max(screen_geom.left() + margen, x)
        y = max(area_top, min(y, area_bottom - notif_h))

        logging.info(
            f"[MONITOR] posicionar_notificacion - columna={columna} pos=({x},{y}) "
            f"notif_size=({notif_w}x{notif_h}) pantalla=({screen_geom.width()}x{screen_geom.height()})"
        )

        notificacion.move(x, y)
    
    def _limitar_notificaciones_abiertas(self):
        """
        Cerrar las notificaciones más antiguas cuando pasan del límite.

        En horas punta las entradas llegan más rápido de lo que recepción las
        cierra, y antes se apilaban sin tope: a partir de unas decenas la
        máquina se arrastraba. Pasado el límite se cierran las más viejas, que
        de todas formas ya nadie iba a leer. El registro de la entrada queda en
        la base; esto solo descarta el aviso en pantalla.
        """
        maximo = MAX_NOTIFICACIONES_VISIBLES
        sobrantes = len(self.notificaciones_activas) - maximo
        if sobrantes <= 0:
            return

        logging.warning(
            f"[MONITOR] {len(self.notificaciones_activas)} notificaciones abiertas, "
            f"por encima del limite de {maximo}: se cierran las {sobrantes} mas antiguas."
        )
        for vieja in list(self.notificaciones_activas[:sobrantes]):
            try:
                vieja.close()          # dispara 'cerrado' -> remover_notificacion
            except RuntimeError:
                if vieja in self.notificaciones_activas:
                    self.notificaciones_activas.remove(vieja)

    def remover_notificacion(self, notificacion):
        """Quitar la notificación de la lista activa y destruirla."""
        id_entrada = getattr(notificacion, 'miembro_data', {}).get('id_entrada', '?')
        if notificacion in self.notificaciones_activas:
            self.notificaciones_activas.remove(notificacion)
            logging.info(f"[MONITOR] Notificacion removida (ID entrada: {id_entrada}). Activas restantes: {len(self.notificaciones_activas)}")
        else:
            logging.warning(f"[MONITOR] remover_notificacion: la notificacion (ID entrada: {id_entrada}) NO estaba en la lista activa (posible doble cierre).")

        # Destruir el widget de verdad. Antes solo se quitaba la referencia de
        # la lista, pero como se crean con parent=self, Qt los conservaba vivos
        # toda la sesión: cerrar una notificación no liberaba nada. Medido,
        # cada una ocupa ~2.3 MB, así que una jornada de entradas se comía
        # cientos de megas sin que se viera ninguna ventana en pantalla.
        try:
            notificacion.deleteLater()
        except RuntimeError:
            # Ya estaba destruida (doble cierre): nada que hacer.
            pass
    
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
            
            # Detener monitor de entradas FastAPI
            if self.monitor_entradas:
                try:
                    self.monitor_entradas.detener()
                    logging.info("Monitor de entradas FastAPI detenido")
                except Exception as e:
                    logging.error(f"Error deteniendo monitor de entradas: {e}")
            
            # Cerrar todas las notificaciones activas
            for notificacion in list(self.notificaciones_activas):
                try:
                    notificacion.close()
                except:
                    pass
            
            self.notificaciones_activas.clear()
            
            # Aceptar el evento de cierre
            event.accept()
            logging.info("Aplicación cerrada correctamente")
                
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