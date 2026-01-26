"""
Modal de Detalles de Notificación
Muestra información completa de una notificación y permite procesarla
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QFont
from typing import Optional, Dict
import logging
from datetime import datetime

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    ContentPanel,
    SectionTitle,
    StyledLabel,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)


class NotificationDetailModal(QDialog):
    """Modal para mostrar detalles de una notificación y procesarla"""
    
    notificacion_procesada = Signal(dict)
    
    def __init__(self, notificacion_data: Dict, pg_manager, supabase_service, user_data, parent=None, sync_manager=None):
        super().__init__(parent)
        self.notificacion_data = notificacion_data
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.sync_manager = sync_manager
        
        self.setWindowTitle("Detalles de Notificación")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMaximumWidth(600)
        
        # Timer para escáner (solo para pagos en efectivo)
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.setInterval(300)
        self.scanner_timer.timeout.connect(self.procesar_codigo_barras)
        
        self.setup_ui()
        self.cargar_datos()
    
    def setup_ui(self):
        """Configurar interfaz del modal"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título según tipo
        tipo = self.notificacion_data.get('tipo_notificacion', '')
        if tipo == 'pago_efectivo_pendiente':
            title_text = "PAGO EN EFECTIVO PENDIENTE"
            title_color = WindowsPhoneTheme.TILE_GREEN
        else:
            title_text = "USO DE BENEFICIO"
            title_color = WindowsPhoneTheme.TILE_BLUE
        
        title = SectionTitle(title_text)
        layout.addWidget(title)
        
        # Panel de información
        info_panel = ContentPanel()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setSpacing(15)
        
        # Información del miembro
        self.miembro_label = StyledLabel("", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        info_layout.addWidget(self.miembro_label)
        
        # Detalles específicos
        self.detalle_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        info_layout.addWidget(self.detalle_label)
        
        # Fecha
        self.fecha_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        self.fecha_label.setStyleSheet(f"color: {WindowsPhoneTheme.TEXT_SECONDARY};")
        info_layout.addWidget(self.fecha_label)
        
        layout.addWidget(info_panel)
        
        # Panel de acción (solo para pagos en efectivo)
        self.action_panel = None
        if tipo == 'pago_efectivo_pendiente':
            self.create_payment_action_panel(layout)
        else:
            self.create_benefit_action_panel(layout)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_cancelar = QPushButton("Cerrar")
        btn_cancelar.setObjectName("cancelButton")
        btn_cancelar.setStyleSheet(f"""
            QPushButton#cancelButton {{
                background-color: {WindowsPhoneTheme.TILE_RED};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton#cancelButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancelar)
        
        layout.addLayout(buttons_layout)
    
    def create_payment_action_panel(self, parent_layout):
        """Crear panel de acción para pagos en efectivo (con escáner)"""
        self.action_panel = ContentPanel()
        action_layout = QVBoxLayout(self.action_panel)
        action_layout.setContentsMargins(20, 20, 20, 20)
        action_layout.setSpacing(15)
        
        # Título
        action_title = StyledLabel("ESCANEAR CÓDIGO PARA CONFIRMAR", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        action_layout.addWidget(action_title)
        
        # Campo de escaneo
        scan_layout = QHBoxLayout()
        scan_layout.setSpacing(10)
        
        scan_label = StyledLabel("Código:", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        scan_layout.addWidget(scan_label)
        
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Escanee el código CASH-{id}")
        self.scan_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.scan_input.setMinimumHeight(45)
        self.scan_input.textChanged.connect(self._on_scan_text_changed)
        self.scan_input.installEventFilter(self)
        scan_layout.addWidget(self.scan_input, 1)
        
        action_layout.addLayout(scan_layout)
        
        # Botón confirmar (deshabilitado hasta escanear)
        self.btn_confirmar = QPushButton("Confirmar Pago")
        self.btn_confirmar.setObjectName("confirmButton")
        self.btn_confirmar.setStyleSheet(f"""
            QPushButton#confirmButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton#confirmButton:hover {{
                opacity: 0.9;
            }}
            QPushButton#confirmButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """)
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.clicked.connect(self._procesar_pago_centralizado)
        action_layout.addWidget(self.btn_confirmar)
        
        parent_layout.addWidget(self.action_panel)
    
    def create_benefit_action_panel(self, parent_layout):
        """Crear panel de acción para uso de beneficios (solo aceptar)"""
        self.action_panel = ContentPanel()
        action_layout = QVBoxLayout(self.action_panel)
        action_layout.setContentsMargins(20, 20, 20, 20)
        action_layout.setSpacing(15)
        
        # Instrucción
        instruction = StyledLabel(
            "Confirme que atendió al miembro para marcar como revisado",
            size=WindowsPhoneTheme.FONT_SIZE_SMALL
        )
        instruction.setWordWrap(True)
        action_layout.addWidget(instruction)
        
        # Botón aceptar
        self.btn_aceptar = QPushButton("Aceptar - Marcar como Revisado")
        self.btn_aceptar.setObjectName("acceptButton")
        self.btn_aceptar.setStyleSheet(f"""
            QPushButton#acceptButton {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton#acceptButton:hover {{
                opacity: 0.9;
            }}
        """)
        self.btn_aceptar.clicked.connect(self.procesar_beneficio)
        action_layout.addWidget(self.btn_aceptar)
        
        parent_layout.addWidget(self.action_panel)
    
    def cargar_datos(self):
        """Cargar datos de la notificación y del miembro"""
        try:
            # Obtener datos del miembro
            id_miembro = self.notificacion_data.get('id_miembro')
            miembro_data = self._obtener_datos_miembro(id_miembro)
            
            nombre_miembro = "N/A"
            if miembro_data:
                nombres = miembro_data.get('nombres', '')
                apellido_paterno = miembro_data.get('apellido_paterno', '')
                nombre_miembro = f"{nombres} {apellido_paterno}".strip()
                telefono = miembro_data.get('telefono', '')
                if telefono:
                    nombre_miembro += f"\nTeléfono: {telefono}"
            
            self.miembro_label.setText(f"Miembro: {nombre_miembro}")
            
            # Detalles según tipo
            tipo = self.notificacion_data.get('tipo_notificacion', '')
            if tipo == 'pago_efectivo_pendiente':
                monto = self.notificacion_data.get('monto_pendiente', 0)
                codigo = self.notificacion_data.get('codigo_pago_generado', 'N/A')
                id_venta_digital = self.notificacion_data.get('id_venta_digital')
                
                # Obtener productos incluidos
                productos_texto = ""
                if id_venta_digital and self.pg_manager:
                    productos = self.pg_manager.obtener_productos_incluidos_pago(id_venta_digital)
                    if productos:
                        productos_lista = []
                        for prod in productos:
                            nombre = prod.get('nombre', prod.get('tipo', 'Producto'))
                            productos_lista.append(f"• {nombre}")
                        productos_texto = "\n" + "\n".join(productos_lista)
                
                self.detalle_label.setText(
                    f"Monto: ${float(monto):.2f}\n"
                    f"Código: {codigo}"
                    + (f"\n\nProductos incluidos:{productos_texto}" if productos_texto else "")
                )
            else:
                # Para uso de beneficios: mostrar tipo y hora
                descripcion = self.notificacion_data.get('descripcion', 'Uso de beneficio premium')
                fecha_creacion = self.notificacion_data.get('creada_en', '')
                hora_uso = ""
                if fecha_creacion:
                    if isinstance(fecha_creacion, datetime):
                        hora_uso = fecha_creacion.strftime("%H:%M:%S")
                    else:
                        try:
                            fecha_obj = datetime.fromisoformat(str(fecha_creacion).replace('Z', '+00:00'))
                            hora_uso = fecha_obj.strftime("%H:%M:%S")
                        except:
                            hora_uso = str(fecha_creacion)[:8] if len(str(fecha_creacion)) >= 8 else ""
                
                # Determinar tipo de beneficio desde descripción o asignaciones
                tipo_beneficio = "Beneficio Premium"
                if 'regadera' in descripcion.lower() or 'regaderas' in descripcion.lower():
                    tipo_beneficio = "Regaderas Premium"
                elif 'vapor' in descripcion.lower():
                    tipo_beneficio = "Vapor"
                elif 'invitado' in descripcion.lower():
                    tipo_beneficio = "Invitado Plus"
                
                texto_beneficio = f"Tipo: {tipo_beneficio}"
                if hora_uso:
                    texto_beneficio += f"\nHora de uso: {hora_uso}"
                
                self.detalle_label.setText(texto_beneficio)
            
            # Fecha
            fecha = self.notificacion_data.get('creada_en', '')
            if isinstance(fecha, datetime):
                fecha_str = fecha.strftime("%Y-%m-%d %H:%M:%S")
            else:
                fecha_str = str(fecha)[:19] if fecha else ''
            self.fecha_label.setText(f"Fecha: {fecha_str}")
            
        except Exception as e:
            logging.error(f"Error cargando datos de notificación: {e}")
    
    def _obtener_datos_miembro(self, id_miembro: int) -> dict:
        """Obtener datos del miembro desde Supabase"""
        if not id_miembro:
            logging.warning("id_miembro es None o vacío")
            return {}
        
        try:
            # Intentar desde Supabase
            if self.supabase_service and self.supabase_service.is_connected:
                response = self.supabase_service.client.table('miembros').select('*').eq('id_miembro', id_miembro).execute()
                if response.data and len(response.data) > 0:
                    miembro = response.data[0]
                    return {
                        'nombres': miembro.get('nombres', ''),
                        'apellido_paterno': miembro.get('apellido_paterno', ''),
                        'apellido_materno': miembro.get('apellido_materno', ''),
                        'telefono': miembro.get('telefono', '')
                    }
            
        except Exception as e:
            logging.error(f"Error obteniendo datos del miembro {id_miembro}: {e}")
        return {}
    
    def eventFilter(self, obj, event):
        """Filtrar eventos para detectar Enter del scanner"""
        if obj == self.scan_input and event.type() == QEvent.KeyPress:
            key_event = event
            if key_event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.procesar_codigo_barras()
                return True
        return super().eventFilter(obj, event)
    
    def _normalizar_codigo_scanner(self, texto: str) -> str:
        """
        Normalizar código del scanner a formato CASH-{id}
        Convierte variantes como CASH'506, CASH_506, CASH 506, etc. a CASH-506
        """
        texto = texto.strip().upper()
        
        # Buscar patrón CASH seguido de cualquier carácter y números
        import re
        match = re.match(r'CASH[^\d]*(\d+)', texto)
        if match:
            id_numero = match.group(1)
            return f"CASH-{id_numero}"
        
        return texto
    
    def _on_scan_text_changed(self):
        """Detectar cuando se ingresa texto (para capturar escáner)"""
        if not hasattr(self, 'scan_input'):
            return
        
        texto_original = self.scan_input.text()
        texto = texto_original.strip()
        
        # Normalizar código del scanner
        texto_normalizado = self._normalizar_codigo_scanner(texto)
        
        # Si se normalizó, actualizar el campo (sin disparar otro evento)
        if texto_normalizado != texto and texto_normalizado.startswith("CASH-"):
            # Bloquear señal temporalmente para evitar recursión
            self.scan_input.blockSignals(True)
            self.scan_input.setText(texto_normalizado)
            self.scan_input.blockSignals(False)
            texto = texto_normalizado
        
        # Reiniciar el timer
        self.scanner_timer.stop()
        
        # Validar formato y habilitar botón
        if texto.startswith("CASH-") and len(texto) > 5:
            try:
                id_notif = int(texto.replace("CASH-", ""))
                id_notif_actual = self.notificacion_data.get('id_notificacion')
                
                # Solo habilitar si el código coincide
                if id_notif == id_notif_actual:
                    self.btn_confirmar.setEnabled(True)
                    self.scanner_timer.start()
                else:
                    self.btn_confirmar.setEnabled(False)
            except ValueError:
                self.btn_confirmar.setEnabled(False)
        else:
            self.btn_confirmar.setEnabled(False)
    
    def procesar_codigo_barras(self):
        """Procesar código de barras escaneado"""
        if not hasattr(self, 'scan_input'):
            return
        
        codigo_original = self.scan_input.text().strip()
        
        # Normalizar código del scanner
        codigo = self._normalizar_codigo_scanner(codigo_original)
        
        # Si se normalizó, actualizar el campo
        if codigo != codigo_original and codigo.startswith("CASH-"):
            self.scan_input.setText(codigo)
        
        # Validar que coincida con la notificación
        try:
            if not codigo.startswith("CASH-"):
                raise ValueError("Formato inválido")
            
            id_notif_escaneado = int(codigo.replace("CASH-", ""))
            id_notif_actual = self.notificacion_data.get('id_notificacion')
            
            if id_notif_escaneado != id_notif_actual:
                show_warning_dialog(
                    self,
                    "Código No Coincide",
                    f"El código escaneado ({codigo}) no corresponde a esta notificación.\n"
                    f"Notificación actual: CASH-{id_notif_actual}"
                )
                self.scan_input.clear()
                return
            
            # Procesar pago
            self._procesar_pago_centralizado()
            
        except ValueError:
            show_warning_dialog(self, "Código Inválido", f"El código '{codigo_original}' no es válido. Se esperaba formato CASH-{{id}}")
            self.scan_input.clear()
    
    def procesar_pago(self):
        """
        Procesar pago en efectivo usando Edge Function de Supabase.
        """
        try:
            id_notificacion = self.notificacion_data.get("id_notificacion")
            if not id_notificacion:
                show_error_dialog(
                    self,
                    "Error",
                    "La notificación no tiene un ID válido. No se puede confirmar el pago.",
                )
                return

            # Partimos de los datos que ya tiene el modal
            notif_completa = dict(self.notificacion_data)

            # Intentar obtener datos actualizados desde BD/Supabase
            notif_actualizada = self._obtener_notificacion_completa(id_notificacion)
            if notif_actualizada:
                notif_completa.update(notif_actualizada)
            else:
                logging.warning(
                    "No se pudo actualizar notificación %s, usando datos del modal",
                    id_notificacion,
                )

            # Intentar usar Edge Function de Supabase primero
            if self.supabase_service and self.supabase_service.is_connected:
                logging.info(f"[PAGO] Llamando Edge Function para notificación {id_notificacion}")

                id_venta_digital = notif_completa.get('id_venta_digital')
                if not id_venta_digital:
                    show_error_dialog(self, "Error", "La notificación no tiene id_venta_digital. No se puede confirmar el pago.")
                    return

                ids_para_contabilizar = self.pg_manager.get_ventas_digitales_pendientes_efectivo_hoy(int(id_venta_digital))
                if not ids_para_contabilizar:
                    ids_para_contabilizar = [int(id_venta_digital)]

                resultado = self.supabase_service.confirmar_pago_efectivo_edge(int(id_venta_digital))
                
                if resultado.get('success'):
                    logging.info(f"[OK] Pago confirmado por Edge Function: {resultado.get('message')}")

                    # Contabilizar para corte del POS
                    turno_id = self.pg_manager.get_turno_abierto_id(self.user_data.get('id_usuario'))
                    venta_contable_id = None
                    if turno_id:
                        venta_contable_id = self.pg_manager.contabilizar_pago_efectivo_digital_en_pos(
                            ids_para_contabilizar,
                            self.user_data.get('id_usuario'),
                            turno_id,
                        )
                    else:
                        logging.warning("No hay turno abierto: pago confirmado pero no contabilizado en POS")
                    
                    # Emitir señal de notificación procesada
                    self.notificacion_procesada.emit({
                        "id_notificacion": id_notificacion,
                        "tipo": "pago_efectivo",
                        "id_miembro": notif_completa.get("id_miembro"),
                        "monto": notif_completa.get("monto_pendiente", 0),
                    })
                    
                    if venta_contable_id:
                        show_info_dialog(self, "Pago Confirmado", f"Pago procesado exitosamente.\n\nVenta POS: {venta_contable_id}")
                    else:
                        show_warning_dialog(
                            self,
                            "Pago Confirmado (sin corte)",
                            "El pago fue confirmado, pero no se pudo registrar la venta en el POS para el corte.\n\nVerifique que exista un turno abierto.",
                        )
                    self.accept()
                    return
                else:
                    logging.warning(f"Edge Function falló: {resultado.get('message')}, usando fallback...")
            
            # Fallback: usar el método centralizado de PostgresManager
            logging.info(f"[PAGO] Intentando fallback con método local para {id_notificacion}")
            
            success = self.pg_manager.confirmar_pago_efectivo(id_notificacion)
            
            if success:
                # Intentar contabilizar también en modo local
                try:
                    id_venta_digital = notif_completa.get('id_venta_digital')
                    if id_venta_digital and self.user_data.get('id_usuario'):
                        turno_id = self.pg_manager.get_turno_abierto_id(self.user_data.get('id_usuario'))
                        if turno_id:
                            ids_para_contabilizar = self.pg_manager.get_ventas_digitales_pendientes_efectivo_hoy(int(id_venta_digital)) or [int(id_venta_digital)]
                            self.pg_manager.contabilizar_pago_efectivo_digital_en_pos(
                                ids_para_contabilizar,
                                self.user_data.get('id_usuario'),
                                turno_id,
                            )
                except Exception as contabilizar_error:
                    logging.warning(f"No se pudo contabilizar en POS (modo local): {contabilizar_error}")

                # Emitir señal de notificación procesada
                self.notificacion_procesada.emit({
                    "id_notificacion": id_notificacion,
                    "tipo": "pago_efectivo",
                    "id_miembro": notif_completa.get("id_miembro"),
                    "monto": notif_completa.get("monto_pendiente", 0),
                })
                
                show_info_dialog(self, "Pago Confirmado", "Pago procesado exitosamente (modo local).")
                self.accept()
            else:
                show_error_dialog(self, "Error", "No se pudo confirmar el pago.")

        except Exception as e:
            logging.error(
                "Error procesando pago en NotificationDetailModal: %s", e, exc_info=True
            )
            show_error_dialog(
                self,
                "Error",
                f"Ocurrió un error al confirmar el pago:\n{str(e)}",
            )
    
    def _procesar_pago_centralizado(self):
        """Wrapper para compatibilidad: delega al servicio de pagos en efectivo."""
        self.procesar_pago()
    
    def procesar_beneficio(self):
        """Procesar uso de beneficio (marcar como revisado)"""
        id_notificacion = self.notificacion_data.get('id_notificacion')
        
        # Validar que no esté ya procesada
        notif_completa = self._obtener_notificacion_completa(id_notificacion)
        if not notif_completa:
            show_error_dialog(self, "Error", f"No se encontró la notificación {id_notificacion}")
            return
        
        if notif_completa.get('respondida'):
            show_warning_dialog(
                self,
                "Ya Revisado",
                f"Este beneficio ya fue revisado anteriormente."
            )
            self.accept()
            return
        
        # Obtener datos del miembro
        id_miembro = notif_completa.get('id_miembro')
        miembro_data = self._obtener_datos_miembro(id_miembro)
        nombre_miembro = f"{miembro_data.get('nombres', '')} {miembro_data.get('apellido_paterno', '')}" if miembro_data else "N/A"
        
        # Confirmar
        respuesta = show_confirmation_dialog(
            self,
            "Confirmar Revisión",
            f"¿Confirmar que revisó el uso de beneficio?\n\n"
            f"Miembro: {nombre_miembro}\n"
            f"Descripción: {notif_completa.get('descripcion', 'Uso de beneficio premium')}"
        )
        
        if not respuesta:
            return
        
        # Obtener nombre del recepcionista
        nombre_recepcionista = self.user_data.get('nombre_completo', 'Recepcionista')
        if not nombre_recepcionista or nombre_recepcionista == 'Recepcionista':
            nombre_recepcionista = self.user_data.get('usuario', 'Recepcionista')
        
        # Marcar como respondida
        try:
            success = self.pg_manager.marcar_notificacion_como_respondida(id_notificacion, attended_by=nombre_recepcionista)
            
            if success:
                show_info_dialog(
                    self,
                    "Revisado",
                    f"Uso de beneficio marcado como revisado.\n\n"
                    f"Miembro: {nombre_miembro}\n"
                    f"Revisado por: {nombre_recepcionista}\n"
                    f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                self.notificacion_procesada.emit({
                    'id_notificacion': id_notificacion,
                    'tipo': 'uso_beneficio',
                    'id_miembro': id_miembro
                })
                
                self.accept()
                
        except Exception as e:
            logging.error(f"Error marcando notificación como revisada: {e}")
            show_error_dialog(
                self,
                "Error",
                f"Error al marcar como revisado:\n{str(e)}"
            )
    
    def _obtener_notificacion_completa(self, id_notificacion: int) -> Optional[Dict]:
        """Obtener notificación completa desde Supabase"""
        try:
            if self.supabase_service and self.supabase_service.is_connected:
                response = self.supabase_service.client.table('notificaciones_pos')\
                    .select('*')\
                    .eq('id_notificacion', id_notificacion)\
                    .execute()
                
                if response.data and len(response.data) > 0:
                    notif = response.data[0]
                    return {
                        'id_notificacion': notif.get('id_notificacion'),
                        'id_miembro': notif.get('id_miembro'),
                        'id_venta_digital': notif.get('id_venta_digital'),
                        'tipo_notificacion': notif.get('tipo_notificacion'),
                        'asunto': notif.get('asunto'),
                        'descripcion': notif.get('descripcion'),
                        'monto_pendiente': notif.get('monto_pendiente'),
                        'fecha_vencimiento': notif.get('fecha_vencimiento'),
                        'codigo_pago_generado': notif.get('codigo_pago_generado'),
                        'respondida': notif.get('respondida', False),
                        'leida': notif.get('leida', False),
                        'para_miembro': notif.get('para_miembro', True),
                        'para_recepcion': notif.get('para_recepcion', True),
                        'creada_en': notif.get('creada_en'),
                        'fecha_recordatorio': notif.get('fecha_recordatorio'),
                        'resuelve_en': notif.get('resuelve_en')
                    }
            
        except Exception as e:
            logging.error(f"Error obteniendo notificación {id_notificacion}: {e}")
        return None
