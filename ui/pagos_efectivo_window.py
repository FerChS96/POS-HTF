"""
Ventana para gestionar pagos en efectivo pendientes
Permite escanear códigos de barras y confirmar pagos
Sigue patrones establecidos en CierreCajaWindow y NuevaVentaWindow
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QFont
from typing import Tuple, Optional
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
)


class PagosEfectivoWindow(QDialog):
    """Ventana para gestionar pagos en efectivo pendientes"""
    
    pago_confirmado = Signal(dict)
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Timer para detectar entrada del escáner (patrón de NuevaVentaWindow)
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.setInterval(300)  # 300ms después de que deje de escribir
        self.scanner_timer.timeout.connect(self.procesar_codigo_barras)
        
        # Timer para refrescar notificaciones
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.cargar_notificaciones)
        self.refresh_timer.start(5000)  # Refrescar cada 5 segundos
        
        self.setup_ui()
        self.cargar_notificaciones()
    
    def setup_ui(self):
        """Configurar interfaz siguiendo patrón de CierreCajaWindow"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # 1. Panel de escaneo
        self.create_scan_section(layout)
        
        # 2. Panel de notificaciones pendientes
        self.create_notifications_section(layout)
        
        # 3. Espaciador flexible
        layout.addStretch()
        
        # 4. Botón volver
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_BLUE)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        layout.addWidget(btn_volver)
    
    def create_scan_section(self, parent_layout):
        """Crear sección de escaneo usando ContentPanel (patrón CierreCajaWindow)"""
        scan_panel = ContentPanel()
        scan_layout = QVBoxLayout(scan_panel)
        scan_layout.setContentsMargins(20, 20, 20, 20)
        scan_layout.setSpacing(15)
        
        # Título de sección
        title = SectionTitle("ESCANEAR CÓDIGO DE PAGO")
        scan_layout.addWidget(title)
        
        # Campo de escaneo
        scan_input_layout = QHBoxLayout()
        scan_input_layout.setSpacing(10)
        
        scan_label = StyledLabel("Código:", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        scan_input_layout.addWidget(scan_label)
        
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Escanee el código CASH-{id} o ingréselo manualmente")
        self.scan_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.scan_input.setMinimumHeight(45)
        self.scan_input.textChanged.connect(self._on_scan_text_changed)
        self.scan_input.installEventFilter(self)
        scan_input_layout.addWidget(self.scan_input, 1)
        
        scan_layout.addLayout(scan_input_layout)
        
        # Instrucciones
        instructions = StyledLabel(
            "1. El usuario pasa por puerta alternativa\n"
            "2. Recibe el efectivo completo\n"
            "3. Escanee el código de barras del celular\n"
            "4. Confirme el pago para activar la membresía",
            size=WindowsPhoneTheme.FONT_SIZE_SMALL
        )
        instructions.setWordWrap(True)
        scan_layout.addWidget(instructions)
        
        parent_layout.addWidget(scan_panel)
    
    def create_notifications_section(self, parent_layout):
        """Crear sección de notificaciones usando ContentPanel"""
        notifications_panel = ContentPanel()
        notifications_layout = QVBoxLayout(notifications_panel)
        notifications_layout.setContentsMargins(20, 20, 20, 20)
        notifications_layout.setSpacing(15)
        
        # Título de sección
        title = SectionTitle("PAGOS PENDIENTES")
        notifications_layout.addWidget(title)
        
        # Tabla de notificaciones
        self.notifications_table = QTableWidget()
        self.notifications_table.setColumnCount(6)
        self.notifications_table.setHorizontalHeaderLabels([
            "ID", "Miembro", "Monto", "Código", "Fecha", "Acción"
        ])
        self.notifications_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.notifications_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.notifications_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.notifications_table.setAlternatingRowColors(True)
        self.notifications_table.setMinimumHeight(300)
        notifications_layout.addWidget(self.notifications_table)
        
        parent_layout.addWidget(notifications_panel)
    
    def eventFilter(self, obj, event):
        """Filtrar eventos para detectar Enter del scanner (patrón NuevaVentaWindow)"""
        if obj == self.scan_input and event.type() == QEvent.KeyPress:
            key_event = event
            if key_event.key() in (Qt.Key_Return, Qt.Key_Enter):
                logging.info("[SCANNER PAGO] Enter detectado - procesando código")
                self.procesar_codigo_barras()
                return True
        return super().eventFilter(obj, event)
    
    def _on_scan_text_changed(self):
        """Detectar cuando se ingresa texto (patrón NuevaVentaWindow)"""
        texto = self.scan_input.text().strip()
        
        # Reiniciar el timer cada vez que cambia el texto
        self.scanner_timer.stop()
        
        # Si el texto tiene formato CASH-{id}
        if texto.startswith("CASH-") and len(texto) > 5:
            logging.info(f"[SCANNER PAGO] Código detectado (longitud {len(texto)}), iniciando timer...")
            # Iniciar timer para procesar después de 300ms de inactividad
            self.scanner_timer.start()
    
    def _validar_codigo_pago(self, codigo: str) -> Tuple[bool, Optional[int], str]:
        """
        Validar formato de código de pago
        
        Returns:
            (es_valido, id_notificacion, mensaje_error)
        """
        if not codigo:
            return False, None, "El código está vacío"
        
        if not codigo.startswith("CASH-"):
            return False, None, f"El código debe comenzar con 'CASH-'\nCódigo recibido: {codigo}"
        
        try:
            id_notificacion = int(codigo.replace("CASH-", ""))
            if id_notificacion <= 0:
                return False, None, "El ID de notificación debe ser mayor a 0"
            return True, id_notificacion, ""
        except ValueError:
            return False, None, f"No se pudo extraer el ID de notificación del código: {codigo}"
    
    def procesar_codigo_barras(self):
        """Procesar código de barras del escáner (patrón NuevaVentaWindow)"""
        codigo = self.scan_input.text().strip()
        
        # Limpiar campo inmediatamente para permitir siguiente escaneo
        self.scan_input.clear()
        
        if not codigo:
            return
        
        # Validar código
        es_valido, id_notificacion, mensaje_error = self._validar_codigo_pago(codigo)
        
        if not es_valido:
            show_warning_dialog(self, "Código Inválido", mensaje_error)
            return
        
        # Procesar pago
        self._procesar_pago_interno(id_notificacion)
    
    def _obtener_datos_miembro(self, id_miembro: int) -> dict:
        """Obtener datos del miembro desde la base de datos"""
        try:
            response = self.pg_manager.client.table('miembros').select(
                'nombres, apellido_paterno, apellido_materno, telefono'
            ).eq('id_miembro', id_miembro).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            logging.error(f"Error obteniendo datos del miembro {id_miembro}: {e}")
        return {}
    
    def _obtener_notificacion_completa(self, id_notificacion: int) -> Optional[dict]:
        """
        Obtener notificación completa desde la base de datos.
        Si no se encuentra localmente, intenta sincronizar desde Supabase.
        """
        try:
            # Primero intentar buscar en local
            response = self.pg_manager.client.table('notificaciones_pos').select('*').eq(
                'id_notificacion', id_notificacion
            ).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            
            # Si no se encuentra localmente, intentar sincronizar desde Supabase
            logging.info(f"Notificación {id_notificacion} no encontrada localmente, intentando sincronizar desde Supabase...")
            
            if self.supabase_service and self.supabase_service.is_connected:
                try:
                    # Buscar directamente en Supabase
                    response = self.supabase_service.client.table('notificaciones_pos')\
                        .select('*')\
                        .eq('id_notificacion', id_notificacion)\
                        .execute()
                    
                    if response.data and len(response.data) > 0:
                        notif_remota = response.data[0]
                        logging.info(f"Notificación {id_notificacion} encontrada en Supabase, sincronizando a local...")
                        
                        # Insertar en local para futuras consultas
                        self._sincronizar_notificacion_a_local(notif_remota)
                        
                        # Retornar datos formateados
                        return {
                            'id_notificacion': notif_remota.get('id_notificacion'),
                            'id_miembro': notif_remota.get('id_miembro'),
                            'id_venta_digital': notif_remota.get('id_venta_digital'),
                            'tipo_notificacion': notif_remota.get('tipo_notificacion'),
                            'asunto': notif_remota.get('asunto'),
                            'descripcion': notif_remota.get('descripcion'),
                            'monto_pendiente': notif_remota.get('monto_pendiente'),
                            'codigo_pago_generado': notif_remota.get('codigo_pago_generado'),
                            'respondida': notif_remota.get('respondida', False),
                            'leida': notif_remota.get('leida', False)
                        }
                except Exception as sync_error:
                    logging.error(f"Error sincronizando notificación {id_notificacion} desde Supabase: {sync_error}")
            
        except Exception as e:
            logging.error(f"Error obteniendo notificación {id_notificacion}: {e}")
        return None
    
    def _sincronizar_notificacion_a_local(self, notif_data: dict):
        """Sincronizar una notificación desde Supabase a la base de datos local"""
        try:
            # Verificar si ya existe
            response = self.pg_manager.client.table('notificaciones_pos').select('id_notificacion').eq(
                'id_notificacion', notif_data.get('id_notificacion')
            ).execute()
            
            notif_id = notif_data.get('id_notificacion')
            
            if response.data and len(response.data) > 0:
                # Actualizar existente
                self.pg_manager.client.table('notificaciones_pos').update({
                    'id_miembro': notif_data.get('id_miembro'),
                    'id_venta_digital': notif_data.get('id_venta_digital'),
                    'tipo_notificacion': notif_data.get('tipo_notificacion'),
                    'asunto': notif_data.get('asunto'),
                    'descripcion': notif_data.get('descripcion'),
                    'monto_pendiente': notif_data.get('monto_pendiente'),
                    'codigo_pago_generado': notif_data.get('codigo_pago_generado'),
                    'leida': notif_data.get('leida', False),
                    'respondida': notif_data.get('respondida', False),
                    'para_miembro': notif_data.get('para_miembro', True),
                    'para_recepcion': notif_data.get('para_recepcion', True),
                    'fecha_vencimiento': notif_data.get('fecha_vencimiento'),
                    'creada_en': notif_data.get('creada_en'),
                    'fecha_recordatorio': notif_data.get('fecha_recordatorio'),
                    'resuelve_en': notif_data.get('resuelve_en')
                }).eq('id_notificacion', notif_id).execute()
            else:
                # Insertar nueva
                self.pg_manager.client.table('notificaciones_pos').insert({
                    'id_notificacion': notif_id,
                    'id_miembro': notif_data.get('id_miembro'),
                    'id_venta_digital': notif_data.get('id_venta_digital'),
                    'tipo_notificacion': notif_data.get('tipo_notificacion'),
                    'asunto': notif_data.get('asunto'),
                    'descripcion': notif_data.get('descripcion'),
                    'monto_pendiente': notif_data.get('monto_pendiente'),
                    'codigo_pago_generado': notif_data.get('codigo_pago_generado'),
                    'leida': notif_data.get('leida', False),
                    'respondida': notif_data.get('respondida', False),
                    'para_miembro': notif_data.get('para_miembro', True),
                    'para_recepcion': notif_data.get('para_recepcion', True),
                    'fecha_vencimiento': notif_data.get('fecha_vencimiento'),
                    'creada_en': notif_data.get('creada_en'),
                    'fecha_recordatorio': notif_data.get('fecha_recordatorio'),
                    'resuelve_en': notif_data.get('resuelve_en')
                }).execute()
            
            logging.info(f"Notificación {notif_id} sincronizada a local")
                
        except Exception as e:
            logging.error(f"Error sincronizando notificación a local: {e}")
    
    def _procesar_pago_interno(self, id_notificacion: int):
        """Procesar un pago en efectivo usando la Edge Function de Supabase."""
        # Obtener notificación completa
        notif_dict = self._obtener_notificacion_completa(id_notificacion)
        if not notif_dict:
            show_error_dialog(self, "Error", f"No se encontró la notificación {id_notificacion}")
            return

        try:
            # Usar Edge Function de Supabase para evitar duplicados
            if self.supabase_service and self.supabase_service.is_connected:
                logging.info(f"[PAGO EFECTIVO] Llamando Edge Function para notificación {id_notificacion}")
                
                id_venta_digital = notif_dict.get('id_venta_digital')
                if not id_venta_digital:
                    show_error_dialog(self, "Error", "La notificación no tiene id_venta_digital. No se puede confirmar.")
                    return

                ids_para_contabilizar = self.pg_manager.get_ventas_digitales_pendientes_efectivo_hoy(int(id_venta_digital))
                if not ids_para_contabilizar:
                    ids_para_contabilizar = [int(id_venta_digital)]

                result = self.supabase_service.confirmar_pago_efectivo_edge(int(id_venta_digital))
                
                if result.get('success'):
                    # Contabilizar en POS para que aparezca en corte
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

                    # Refrescar lista
                    self.cargar_notificaciones()

                    # Emitir señal para que la ventana principal pueda reaccionar
                    self.pago_confirmado.emit({
                        "id_notificacion": id_notificacion,
                        "id_miembro": notif_dict.get("id_miembro"),
                        "monto": notif_dict.get("monto_pendiente", 0),
                    })
                    
                    logging.info(f"✅ Pago procesado exitosamente: {result.get('message')}")
                    if venta_contable_id:
                        show_info_dialog(self, "Pago Confirmado", f"El pago ha sido procesado exitosamente.\n\nVenta POS: {venta_contable_id}")
                    else:
                        show_warning_dialog(
                            self,
                            "Pago Confirmado (sin corte)",
                            "El pago fue confirmado, pero no se pudo registrar la venta en el POS para el corte.\n\nVerifique que exista un turno abierto.",
                        )
                else:
                    logging.warning(f"Edge Function retornó error: {result.get('message')}")
                    
                    # Fallback al método antiguo si Edge Function falla
                    logging.info("Intentando fallback al método local...")
                    success = self.pg_manager.confirmar_pago_efectivo(id_notificacion)
                    
                    if success:
                        # En modo local también intentar contabilizar (mismo mecanismo)
                        try:
                            id_venta_digital = notif_dict.get('id_venta_digital')
                            if id_venta_digital:
                                turno_id = self.pg_manager.get_turno_abierto_id(self.user_data.get('id_usuario'))
                                if turno_id:
                                    ids_para_contabilizar = self.pg_manager.get_ventas_digitales_pendientes_efectivo_hoy(int(id_venta_digital)) or [int(id_venta_digital)]
                                    self.pg_manager.contabilizar_pago_efectivo_digital_en_pos(
                                        ids_para_contabilizar,
                                        self.user_data.get('id_usuario'),
                                        turno_id,
                                    )
                        except Exception as contabilizar_error:
                            logging.warning(f"No se pudo contabilizar en POS (fallback local): {contabilizar_error}")

                        self.cargar_notificaciones()
                        self.pago_confirmado.emit({
                            "id_notificacion": id_notificacion,
                            "id_miembro": notif_dict.get("id_miembro"),
                            "monto": notif_dict.get("monto_pendiente", 0),
                        })
                        show_info_dialog(self, "Pago Confirmado", "El pago ha sido procesado (modo local).")
                    else:
                        show_error_dialog(self, "Error", "No se pudo procesar el pago en ningún método.")
            else:
                # Si no hay conexión a Supabase, usar método local
                logging.info(f"[PAGO EFECTIVO] No hay conexión Supabase, usando método local para {id_notificacion}")
                success = self.pg_manager.confirmar_pago_efectivo(id_notificacion)
                
                if success:
                    self.cargar_notificaciones()
                    self.pago_confirmado.emit({
                        "id_notificacion": id_notificacion,
                        "id_miembro": notif_dict.get("id_miembro"),
                        "monto": notif_dict.get("monto_pendiente", 0),
                    })
                    show_info_dialog(self, "Pago Confirmado", "El pago ha sido procesado (modo offline).")
                else:
                    show_error_dialog(self, "Error", "No se pudo procesar el pago.")
                
        except Exception as e:
            logging.error(f"Error procesando pago en PagosEfectivoWindow: {e}", exc_info=True)
            show_error_dialog(
                self,
                "Error",
                f"Ocurrió un error al confirmar el pago:\n{str(e)}",
            )
    
    def procesar_pago(self, id_notificacion: int):
        """Método público para procesar pago (usado por botones de tabla)"""
        self._procesar_pago_interno(id_notificacion)
    
    def cargar_notificaciones(self):
        """Cargar notificaciones de pago pendientes"""
        try:
            notificaciones = self.pg_manager.get_notificaciones_pendientes(para_recepcion=True)
            
            # Filtrar solo pagos en efectivo
            pagos_efectivo = [
                n for n in notificaciones 
                if n.get('tipo_notificacion') == 'pago_efectivo_pendiente'
            ]
            
            self.notifications_table.setRowCount(len(pagos_efectivo))
            
            for row, notif in enumerate(pagos_efectivo):
                # ID
                id_item = QTableWidgetItem(str(notif.get('id_notificacion', '')))
                id_item.setData(Qt.UserRole, notif.get('id_notificacion'))
                self.notifications_table.setItem(row, 0, id_item)
                
                # Obtener datos del miembro
                id_miembro = notif.get('id_miembro')
                miembro_data = self._obtener_datos_miembro(id_miembro)
                nombre_miembro = f"{miembro_data.get('nombres', '')} {miembro_data.get('apellido_paterno', '')}" if miembro_data else "N/A"
                
                miembro_item = QTableWidgetItem(nombre_miembro)
                self.notifications_table.setItem(row, 1, miembro_item)
                
                # Monto
                monto = notif.get('monto_pendiente', 0)
                monto_item = QTableWidgetItem(f"${monto:.2f}")
                monto_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.notifications_table.setItem(row, 2, monto_item)
                
                # Código
                codigo = notif.get('codigo_pago_generado') or notif.get('qr_pago_generado') or ''
                codigo_item = QTableWidgetItem(codigo)
                self.notifications_table.setItem(row, 3, codigo_item)
                
                # Fecha
                fecha = notif.get('creada_en', '')
                if isinstance(fecha, datetime):
                    fecha_str = fecha.strftime("%Y-%m-%d %H:%M")
                else:
                    fecha_str = str(fecha)[:16] if fecha else ''
                fecha_item = QTableWidgetItem(fecha_str)
                self.notifications_table.setItem(row, 4, fecha_item)
                
                # Botón de acción
                btn_confirmar = QPushButton("Confirmar")
                btn_confirmar.setObjectName("confirmButton")
                btn_confirmar.setStyleSheet(f"""
                    QPushButton#confirmButton {{
                        background-color: {WindowsPhoneTheme.TILE_GREEN};
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        font-weight: bold;
                    }}
                    QPushButton#confirmButton:hover {{
                        background-color: #28a745;
                    }}
                """)
                btn_confirmar.clicked.connect(
                    lambda checked, id_notif=notif.get('id_notificacion'): 
                    self.procesar_pago(id_notif)
                )
                self.notifications_table.setCellWidget(row, 5, btn_confirmar)
            
            logging.info(f"Cargadas {len(pagos_efectivo)} notificaciones de pago pendientes")
            
        except Exception as e:
            logging.error(f"Error cargando notificaciones: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar las notificaciones: {e}")
    
    def showEvent(self, event):
        """Reanudar timer cuando la ventana se muestra"""
        super().showEvent(event)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(5000)
        self.cargar_notificaciones()
    
    def hideEvent(self, event):
        """Pausar timer cuando la ventana se oculta"""
        super().hideEvent(event)
        self.refresh_timer.stop()
    
    def closeEvent(self, event):
        """Cerrar ventana y detener timers"""
        self.refresh_timer.stop()
        self.scanner_timer.stop()
        event.accept()
