"""
Ventana de escaneo de código de pago en efectivo - REFACTORIZADA
Interfaz minimalista usando componentes del sistema de diseño
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import logging
import re

from ui.components import WindowsPhoneTheme, StyledLabel, show_error_dialog


class EscanearCodigoDialogo(QDialog):
    """Diálogo para escanear código de pago - UI minimalista"""
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.notificacion = None
        
        self.setWindowTitle("Código de Pago")
        self.setMinimumWidth(500)
        self.setMinimumHeight(250)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz minimalista"""
        layout = QVBoxLayout(self)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_MEDIUM, 
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_MEDIUM, 
            WindowsPhoneTheme.MARGIN_MEDIUM
        )
        
        # Texto único y minimalista
        titulo = StyledLabel(
            "Escanee o ingrese manualmente el código",
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE
        )
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)
        
        # Espaciador
        layout.addSpacing(20)
        
        # Campo de entrada (prominente)
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Código...")
        self.scan_input.setMinimumHeight(50)
        self.scan_input.setFont(QFont(
            WindowsPhoneTheme.FONT_FAMILY, 
            WindowsPhoneTheme.FONT_SIZE_LARGE, 
            QFont.Bold
        ))
        self.scan_input.setAlignment(Qt.AlignCenter)
        self.scan_input.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {WindowsPhoneTheme.TILE_BLUE};
                border-radius: 4px;
                padding: 8px;
                font-size: 18px;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border: 2px solid {WindowsPhoneTheme.TILE_GREEN};
                background-color: #f0f8ff;
            }}
        """)
        layout.addWidget(self.scan_input)
        layout.addStretch()
        
        # Botones
        btn_layout = QHBoxLayout()
        
        btn_confirmar = QPushButton("Confirmar")
        btn_confirmar.setMinimumHeight(45)
        btn_confirmar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                font-weight: bold;
                font-size: 13px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #00b300;
            }}
            QPushButton:pressed {{
                background-color: #007a00;
            }}
        """)
        
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setMinimumHeight(45)
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_RED};
                color: white;
                border: none;
                font-weight: bold;
                font-size: 13px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #cc0a00;
            }}
            QPushButton:pressed {{
                background-color: #990800;
            }}
        """)
        
        btn_confirmar.clicked.connect(self.procesar_codigo)
        btn_cancelar.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_confirmar)
        btn_layout.addWidget(btn_cancelar)
        layout.addLayout(btn_layout)
        
        # Eventos de teclado
        self.scan_input.keyPressEvent = self.keyPressEvent_custom
        
        # Auto-focus
        self.scan_input.setFocus()
    
    def keyPressEvent_custom(self, event):
        """Manejar Enter en campo de entrada"""
        if event.key() == Qt.Key_Return:
            self.procesar_codigo()
        else:
            QLineEdit.keyPressEvent(self.scan_input, event)
    
    def procesar_codigo(self):
        """Procesar código ingresado"""
        codigo = self.scan_input.text().strip()
        
        if not codigo:
            return
        
        try:
            # Normalizar código usando regex
            codigo_original = codigo.strip()
            codigo_upper = codigo_original.upper()
            match = re.match(r'CASH[-\'\s]*(\d+)', codigo_upper)
            
            if match:
                numero = match.group(1)
                codigo_normalizado = f"CASH-{numero}"
                logging.info(f"[ESCÁNER PAGO] Código normalizado: {codigo_original} → {codigo_normalizado}")
            else:
                codigo_normalizado = codigo_upper
                logging.info(f"[ESCÁNER PAGO] Código: {codigo_original}")
            
            notif = None
            ya_procesada = False
            
            # Normalizar el código antes de cualquier consulta
            codigo_normalizado = re.sub(r"[-'\s]+", "-", codigo_normalizado)

            # Buscar en Supabase
            if self.supabase_service:
                # Primero buscar notificaciones NO respondidas
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
                    logging.info(f"[ESCÁNER PAGO] Notificación encontrada: {notif['id_notificacion']}")
                else:
                    # Si no encuentra pendiente, buscar TODAS (incluyendo respondidas)
                    # Asegurarse de que el código esté normalizado antes de la consulta
                    codigo_normalizado = re.sub(r"[-'\s]+", "-", codigo_normalizado)
                    
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
                            'apellido_materno': miembro.get('apellido_materno', ''),
                            'respondida': item.get('respondida', False)
                        }
                        
                        # Verificar si ya fue procesada
                        if item.get('respondida'):
                            ya_procesada = True
                            logging.info(f"[ESCÁNER PAGO] ⚠️ Notificación ya procesada: {notif['id_notificacion']}")
                        else:
                            logging.info(f"[ESCÁNER PAGO] Notificación encontrada: {notif['id_notificacion']}")
            else:
                # Fallback a PostgreSQL
                notif = self.pg_manager.buscar_notificacion_por_codigo_pago(codigo_normalizado)
                if notif:
                    logging.info(f"[ESCÁNER PAGO] Notificación encontrada en PostgreSQL: {notif['id_notificacion']}")
            
            if notif:
                # Guardar y cerrar
                self.notificacion = notif
                
                # Si ya fue procesada, mostrar advertencia pero permitir abrir
                if ya_procesada:
                    from ui.components import show_warning_dialog
                    show_warning_dialog(
                        self,
                        "Código ya procesado",
                        f"Este código (CASH-{notif['id_notificacion']}) ya fue procesado.\n"
                        f"Miembro: {notif['nombres']} {notif['apellido_paterno']}\n"
                        f"Monto: ${notif.get('monto_pendiente', 0)}"
                    )
                
                self.accept()
            else:
                show_error_dialog(
                    self, 
                    "No encontrado", 
                    f"El código '{codigo_normalizado}' no existe"
                )
                logging.info(f"[ESCÁNER PAGO] Código no encontrado: {codigo_normalizado}")
                self.scan_input.clear()
                self.scan_input.setFocus()
        
        except Exception as e:
            logging.error(f"[ESCÁNER PAGO] Error: {e}")
            show_error_dialog(self, "Error", f"Error procesando código: {str(e)}")
            self.scan_input.clear()
            self.scan_input.setFocus()
