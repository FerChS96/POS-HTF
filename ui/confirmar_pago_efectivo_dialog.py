"""
Diálogo para confirmar pago en efectivo
Solo escanea código de pago y llama Edge Function
Interfaz minimalista usando componentes del sistema de diseño
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import logging

from ui.components import (
    WindowsPhoneTheme,
    StyledLabel,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
)


class ConfirmarPagoEfectivoDialog(QDialog):
    """Diálogo para confirmar pago en efectivo escaneando código de pago"""
    
    def __init__(self, supabase_service, parent=None):
        super().__init__(parent)
        self.supabase_service = supabase_service
        self.setWindowTitle("Confirmar Pago en Efectivo")
        self.setMinimumWidth(500)
        self.setMinimumHeight(280)
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
        
        # Título
        titulo = StyledLabel(
            "Escanee o ingrese el código de pago para confirmar el cobro en efectivo.",
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE
        )
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setWordWrap(True)
        layout.addWidget(titulo)
        
        # Espaciador
        layout.addSpacing(20)
        
        # Etiqueta del campo
        label_codigo = StyledLabel("Código de Pago:", size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        layout.addWidget(label_codigo)
        
        # Campo de entrada
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
        self.scan_input.returnPressed.connect(self.confirmar_pago)
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
        btn_confirmar.clicked.connect(self.confirmar_pago)
        
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
        btn_cancelar.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_confirmar)
        btn_layout.addWidget(btn_cancelar)
        layout.addLayout(btn_layout)
        
        # Auto-focus
        self.scan_input.setFocus()
    
    def confirmar_pago(self):
        """Buscar código de pago y confirmar"""
        codigo_pago = self.scan_input.text().strip()
        
        if not codigo_pago:
            show_warning_dialog(self, "Campo vacío", "Debe escanear o ingresar el código de pago")
            self.scan_input.setFocus()
            return
        
        logging.info(f"Buscando código de pago: {codigo_pago}")
        self._procesar_codigo(codigo_pago)
    
    def _procesar_codigo(self, codigo_pago: str):
        """Buscar el código en notificaciones_pos y confirmar el pago"""
        try:
            # Normalizar el código antes de la consulta
            import re
            codigo_original = codigo_pago.strip()
            codigo_upper = codigo_original.upper()
            match = re.match(r'CASH[-\'\s]*(\d+)', codigo_upper)
            
            if match:
                numero = match.group(1)
                codigo_normalizado = f"CASH-{numero}"
                logging.info(f"[CONFIRMAR PAGO] Código normalizado: {codigo_original} → {codigo_normalizado}")
            else:
                codigo_normalizado = codigo_upper
                logging.info(f"[CONFIRMAR PAGO] Código: {codigo_original}")
            
            # 1. Buscar el código en notificaciones_pos (columna: codigo_pago_generado)
            response = self.supabase_service.client.table('notificaciones_pos').select(
                'id_venta_digital'
            ).eq('codigo_pago_generado', codigo_normalizado).limit(1).execute()
            
            if not response.data or len(response.data) == 0:
                logging.warning(f"[!] Código de pago no encontrado: {codigo_normalizado}")
                show_warning_dialog(
                    self,
                    "Código no encontrado",
                    f"El código '{codigo_normalizado}' no existe en notificaciones"
                )
                self.scan_input.clear()
                self.scan_input.setFocus()
                return
            
            id_venta_digital = response.data[0]['id_venta_digital']
            logging.info(f"Código encontrado - ID venta: {id_venta_digital}")
            
            # 2. Llamar Edge Function con el id_venta_digital
            self._llamar_edge_function(id_venta_digital)
        
        except Exception as e:
            logging.error(f"[ERROR] Buscando código de pago: {e}", exc_info=True)
            show_error_dialog(
                self,
                "Error",
                f"Error al buscar código: {str(e)}"
            )
            self.scan_input.clear()
            self.scan_input.setFocus()
    
    def _llamar_edge_function(self, id_venta_digital: int):
        """Llamar a la Edge Function para confirmar el pago"""
        try:
            response = self.supabase_service.client.functions.invoke(
                'confirm-cash-payment',
                invoke_options={
                    'body': {
                        'id_venta_digital': id_venta_digital
                    }
                }
            )
            
            # Convertir bytes a JSON si es necesario
            import json
            if isinstance(response, bytes):
                response = json.loads(response.decode('utf-8'))
            
            if isinstance(response, dict) and response.get('error'):
                error_msg = response.get('error', 'Error desconocido')
                logging.error(f"[ERROR] Edge Function: {error_msg}")
                show_warning_dialog(
                    self,
                    "Información",
                    f"{error_msg}"
                )
                self.scan_input.clear()
                self.scan_input.setFocus()
            else:
                # Si response es dict, usar .get(), sino asumir que es el response directo
                if isinstance(response, dict):
                    mensaje = response.get('message', 'Pago confirmado')
                    ventas_activadas = response.get('ventas_activadas', 1)
                    asignaciones = response.get('asignaciones_activadas', 0)
                else:
                    mensaje = 'Pago confirmado'
                    ventas_activadas = 1
                    asignaciones = 0
                
                logging.info(
                    f"[OK] Pago confirmado - "
                    f"Ventas activadas: {ventas_activadas}, "
                    f"Asignaciones: {asignaciones}"
                )
                
                # Actualizar notificación después de confirmar el pago
                self._actualizar_notificacion(id_venta_digital)
                
                show_info_dialog(
                    self,
                    "Pago Confirmado",
                    f"{mensaje}\n\n"
                    f"Ventas activadas: {ventas_activadas}\n"
                    f"Asignaciones: {asignaciones}"
                )
                
                self.accept()
        
        except Exception as e:
            error_msg = str(e)
            
            # Detectar si es un error específico de la Edge Function
            if 'no está pendiente' in error_msg or 'activa' in error_msg:
                logging.warning(f"[!] Pago ya fue confirmado: {error_msg}")
                show_warning_dialog(
                    self,
                    "Pago Ya Confirmado",
                    "Este pago ya fue confirmado anteriormente.\n\nIntente con otro código de pago."
                )
            elif 'no encontrada' in error_msg or 'not found' in error_msg:
                logging.warning(f"[!] Venta no encontrada: {error_msg}")
                show_warning_dialog(
                    self,
                    "Venta No Encontrada",
                    "La venta no existe o fue eliminada.\n\nVerifique el código de pago."
                )
            else:
                logging.error(f"[ERROR] Edge Function: {error_msg}", exc_info=True)
                show_error_dialog(
                    self,
                    "Error al procesar pago",
                    f"{error_msg}"
                )
            
            self.scan_input.clear()
            self.scan_input.setFocus()
    
    def _actualizar_notificacion(self, id_venta_digital: int):
        """Actualizar notificación_pos marcando como leída y respondida"""
        try:
            self.supabase_service.client.table('notificaciones_pos').update({
                'leida': True,
                'respondida': True,
                'tipo_notificacion': 'pago confirmado',
                'asunto': 'pago confirmado'
            }).eq('id_venta_digital', id_venta_digital).execute()
            
            logging.info(f"[OK] Notificación actualizada para venta: {id_venta_digital}")
        
        except Exception as e:
            logging.warning(f"[!] Error actualizando notificación: {e}", exc_info=True)
            # No es crítico, solo log de warning
