"""
Diálogo de Autenticación de Administrador para HTF POS
Para autorizar acciones especiales fuera de horario
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import bcrypt
import logging

from ui.components import (
    WindowsPhoneTheme,
    StyledLabel,
    ContentPanel
)

# Mensaje unico para cualquier fallo de credenciales. Deliberadamente NO
# distingue entre "el usuario no existe" y "la contrasenia es incorrecta":
# un mensaje distinto confirmaria a quien lo intenta que la cuenta existe.
MENSAJE_CREDENCIALES_INVALIDAS = "Usuario o contraseña incorrectos"


class AdminAuthDialog(QDialog):
    """Diálogo para solicitar autorización de administrador"""
    
    def __init__(self, pg_manager, motivo, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.motivo = motivo
        self.autorizado = False
        self.id_admin_autorizador = None
        self.nombre_admin = None
        self.justificacion = ""
        
        self.setWindowTitle("Autorización Requerida")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Panel principal
        panel = ContentPanel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(30, 30, 30, 30)
        panel_layout.setSpacing(20)
        
        # Título
        title = StyledLabel(
            "⚠️ AUTORIZACIÓN DE ADMINISTRADOR",
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE
        )
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {WindowsPhoneTheme.TILE_ORANGE};")
        panel_layout.addWidget(title)
        
        # Motivo
        motivo_label = StyledLabel("Motivo:", bold=True)
        panel_layout.addWidget(motivo_label)
        
        motivo_text = StyledLabel(self.motivo)
        motivo_text.setWordWrap(True)
        motivo_text.setStyleSheet(f"""
            background-color: #f5f5f5;
            padding: 15px;
            border-radius: 4px;
            color: {WindowsPhoneTheme.TILE_RED};
            font-weight: bold;
        """)
        panel_layout.addWidget(motivo_text)
        
        # Usuario
        usuario_label = StyledLabel("Usuario Administrador:", bold=True)
        panel_layout.addWidget(usuario_label)
        
        self.usuario_input = QLineEdit()
        self.usuario_input.setPlaceholderText("Ingrese nombre de usuario")
        self.usuario_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.usuario_input.setMinimumHeight(40)
        panel_layout.addWidget(self.usuario_input)
        
        # Contraseña
        password_label = StyledLabel("Contraseña:", bold=True)
        panel_layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Ingrese contraseña")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.password_input.setMinimumHeight(40)
        self.password_input.returnPressed.connect(self.verificar_credenciales)
        panel_layout.addWidget(self.password_input)
        
        # Justificación
        justificacion_label = StyledLabel("Justificación:", bold=True)
        panel_layout.addWidget(justificacion_label)
        
        self.justificacion_input = QTextEdit()
        self.justificacion_input.setPlaceholderText("Describa el motivo de la autorización...")
        self.justificacion_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.justificacion_input.setMinimumHeight(80)
        self.justificacion_input.setMaximumHeight(120)
        panel_layout.addWidget(self.justificacion_input)
        
        layout.addWidget(panel)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setMinimumHeight(45)
        btn_cancelar.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_RED};
                color: white;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #b30f00;
            }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancelar)
        
        btn_autorizar = QPushButton("Autorizar")
        btn_autorizar.setMinimumHeight(45)
        btn_autorizar.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        btn_autorizar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #008a00;
            }}
        """)
        btn_autorizar.clicked.connect(self.verificar_credenciales)
        buttons_layout.addWidget(btn_autorizar)
        
        layout.addLayout(buttons_layout)
        
        # Focus en usuario
        self.usuario_input.setFocus()
    
    def verificar_credenciales(self):
        """Verificar credenciales del administrador"""
        usuario = self.usuario_input.text().strip()
        password = self.password_input.text()
        justificacion = self.justificacion_input.toPlainText().strip()
        
        # Validaciones básicas
        if not usuario:
            from ui.components import show_warning_dialog
            show_warning_dialog(self, "Campo Requerido", "Debe ingresar un nombre de usuario")
            self.usuario_input.setFocus()
            return
        
        if not password:
            from ui.components import show_warning_dialog
            show_warning_dialog(self, "Campo Requerido", "Debe ingresar una contraseña")
            self.password_input.setFocus()
            return
        
        if not justificacion:
            from ui.components import show_warning_dialog
            show_warning_dialog(self, "Campo Requerido", "Debe proporcionar una justificación")
            self.justificacion_input.setFocus()
            return
        
        try:
            # Buscar usuario y verificar que sea administrador
            response = self.pg_manager.client.table('usuarios').select('id_usuario, contrasenia, rol, nombre_completo').eq('nombre_usuario', usuario).eq('activo', True).execute()
            user = response.data[0] if response.data else None
            
            if not user:
                # Mismo trato que una contraseña incorrecta: no se revela que
                # la cuenta no existe.
                self._rechazar_credenciales(usuario, "usuario inexistente o inactivo")
                return
            
            # Verificar que sea administrador o sistemas
            if user['rol'] not in ['administrador', 'sistemas']:
                logging.warning(
                    f"[SEGURIDAD] Autorización denegada a '{usuario}': "
                    f"rol '{user['rol']}' no puede autorizar"
                )
                from ui.components import show_error_dialog
                show_error_dialog(
                    self, 
                    "Acceso Denegado", 
                    "Solo administradores pueden autorizar esta acción"
                )
                self.password_input.clear()
                self.usuario_input.clear()
                self.usuario_input.setFocus()
                return
            
            # Verificar contraseña
            password_hash = user['contrasenia'].encode('utf-8')
            if bcrypt.checkpw(password.encode('utf-8'), password_hash):
                # Autorización exitosa
                self.autorizado = True
                self.id_admin_autorizador = user['id_usuario']
                self.justificacion = justificacion
                self.nombre_admin = user['nombre_completo']
                
                logging.info(f"[OK] Autorización concedida por {user['nombre_completo']} (ID: {user['id_usuario']})")
                self.accept()
            else:
                self._rechazar_credenciales(usuario, "contraseña incorrecta")
            
        except Exception as e:
            logging.error(f"Error verificando credenciales: {e}")
            from ui.components import show_error_dialog
            show_error_dialog(self, "Error", f"Error al verificar credenciales: {e}")
    
    def _rechazar_credenciales(self, usuario, motivo):
        """
        Rechazar un intento de autorización por credenciales inválidas.

        El motivo real solo va al log; al usuario se le da siempre el mismo
        mensaje y el mismo foco, para no delatar qué cuentas existen.
        """
        logging.warning(f"[SEGURIDAD] Autorización denegada a '{usuario}': {motivo}")
        from ui.components import show_error_dialog
        show_error_dialog(self, "Error", MENSAJE_CREDENCIALES_INVALIDAS)
        self.password_input.clear()
        self.password_input.setFocus()
    
    def get_autorizacion(self):
        """Obtener datos de la autorización"""
        if self.autorizado:
            return {
                'autorizado': True,
                'id_admin': self.id_admin_autorizador,
                'nombre_admin': self.nombre_admin,
                'justificacion': self.justificacion
            }
        return {'autorizado': False}
