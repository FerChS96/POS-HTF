"""
Ventana de Notificaciones de Pago
Grid informativo de pagos pendientes y confirmación de pagos en efectivo
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QLabel, QPushButton, QTextEdit, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QCursor
from datetime import datetime
import logging

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    SearchBar,
    show_info_dialog,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog,
    create_page_layout
)


# ============================================================
# DIÁLOGO DE CONFIRMACIÓN DE PAGO
# ============================================================

class ConfirmarPagoDialog(QDialog):
    """Diálogo para confirmar un pago en efectivo"""
    
    def __init__(self, notificacion, pg_manager, user_data, supabase_service=None, parent=None):
        super().__init__(parent)
        self.notificacion = notificacion
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.supabase_service = supabase_service
        
        self.setWindowTitle("Confirmar Pago en Efectivo")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        self.setup_ui()
        self.cargar_datos()
    
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setStyleSheet(f"background-color: {WindowsPhoneTheme.PRIMARY_BLUE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_label = StyledLabel("CONFIRMAR PAGO EN EFECTIVO", bold=True, size=WindowsPhoneTheme.FONT_SIZE_LARGE)
        title_label.setStyleSheet("color: white; background: transparent;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Contenido
        content = QFrame()
        content.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(25, 25, 25, 25)
        content_layout.setSpacing(20)
        
        # Información del miembro
        miembro_panel = ContentPanel()
        miembro_layout = QVBoxLayout(miembro_panel)
        miembro_layout.setSpacing(10)
        
        self.label_miembro = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE, bold=True)
        self.label_miembro.setStyleSheet(f"color: {WindowsPhoneTheme.PRIMARY_BLUE};")
        miembro_layout.addWidget(self.label_miembro)
        
        self.label_contacto = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        miembro_layout.addWidget(self.label_contacto)
        
        content_layout.addWidget(miembro_panel)
        
        # Información del producto
        producto_panel = ContentPanel()
        producto_layout = QVBoxLayout(producto_panel)
        producto_layout.setSpacing(10)
        
        producto_title = StyledLabel("PRODUCTO DIGITAL", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        producto_layout.addWidget(producto_title)
        
        self.label_producto = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        producto_layout.addWidget(self.label_producto)
        
        self.label_descripcion = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        self.label_descripcion.setWordWrap(True)
        producto_layout.addWidget(self.label_descripcion)
        
        content_layout.addWidget(producto_panel)
        
        # Monto a cobrar
        monto_panel = QFrame()
        monto_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                padding: 20px;
            }}
        """)
        monto_layout = QVBoxLayout(monto_panel)
        
        monto_title = StyledLabel("MONTO A COBRAR", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        monto_title.setStyleSheet("color: white; background: transparent;")
        monto_title.setAlignment(Qt.AlignCenter)
        monto_layout.addWidget(monto_title)
        
        self.label_monto = StyledLabel("$0.00", bold=True, size=WindowsPhoneTheme.FONT_SIZE_XLARGE)
        self.label_monto.setStyleSheet("color: white; background: transparent;")
        self.label_monto.setAlignment(Qt.AlignCenter)
        monto_layout.addWidget(self.label_monto)
        
        content_layout.addWidget(monto_panel)
        
        # Observaciones
        obs_label = StyledLabel("Observaciones (opcional):", bold=True)
        content_layout.addWidget(obs_label)
        
        self.observaciones_input = QTextEdit()
        self.observaciones_input.setMaximumHeight(80)
        self.observaciones_input.setPlaceholderText("Notas adicionales sobre el pago...")
        self.observaciones_input.setStyleSheet(f"""
            QTextEdit {{
                padding: 10px;
                border: 2px solid #e5e7eb;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QTextEdit:focus {{
                border-color: {WindowsPhoneTheme.TILE_BLUE};
            }}
        """)
        content_layout.addWidget(self.observaciones_input)
        
        content_layout.addStretch()
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addStretch()
        
        btn_cancelar = TileButton("Cancelar", "mdi.close", WindowsPhoneTheme.TILE_GRAY)
        btn_cancelar.setMaximumWidth(150)
        btn_cancelar.setMaximumHeight(80)
        btn_cancelar.setMinimumHeight(80)
        btn_cancelar.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancelar)
        
        btn_confirmar = TileButton("Confirmar\nPago", "mdi.cash", WindowsPhoneTheme.TILE_GREEN)
        btn_confirmar.setMaximumWidth(150)
        btn_confirmar.setMaximumHeight(80)
        btn_confirmar.setMinimumHeight(80)
        btn_confirmar.clicked.connect(self.confirmar_pago)
        buttons_layout.addWidget(btn_confirmar)
        
        content_layout.addLayout(buttons_layout)
        layout.addWidget(content)
    
    def cargar_datos(self):
        """Cargar datos de la notificación"""
        try:
            # Obtener datos desde el gestor centralizado
            datos = self.pg_manager.obtener_detalle_notificacion(self.notificacion['id_notificacion'])
            
            if datos:
                # Información del miembro
                nombre_completo = f"{datos['nombres']} {datos['apellido_paterno']} {datos['apellido_materno']}"
                self.label_miembro.setText(nombre_completo)
                
                contacto = []
                if datos['telefono']:
                    contacto.append(f"Tel: {datos['telefono']}")
                if datos['email']:
                    contacto.append(f"Email: {datos['email']}")
                self.label_contacto.setText(" | ".join(contacto) if contacto else "Sin información de contacto")
                
                # Información del producto
                self.label_producto.setText(datos['producto_nombre'] or "Producto no especificado")
                self.label_descripcion.setText(datos['producto_descripcion'] or "")
                
                # Monto
                monto = float(datos['monto_pendiente'] or 0)
                self.label_monto.setText(f"${monto:.2f}")
            
        except Exception as e:
            logging.error(f"Error cargando datos de notificación: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los datos:\n{str(e)}")
    
    def confirmar_pago(self):
        """Confirmar el pago en efectivo y actualizar registros"""
        if not show_confirmation_dialog(
            self,
            "Confirmar Pago",
            "¿Confirma que ha recibido el pago en efectivo?",
            "Esta acción activará la membresía/visita del cliente."
        ):
            return
        
        try:
            logging.info(f"Iniciando confirmación de pago para notificación: {self.notificacion}")
            
            # IMPORTANTE: Si la notificación viene de Supabase, sincronizarla a PostgreSQL primero
            if self.supabase_service:
                logging.info(f"Sincronizando notificación {self.notificacion['id_notificacion']} desde Supabase a PostgreSQL...")
                self.pg_manager.sincronizar_notificacion_supabase(
                    self.notificacion['id_notificacion'],
                    self.notificacion
                )
            
            # Obtener observaciones del usuario
            observaciones = self.observaciones_input.toPlainText().strip() or None
            
            # Usar Edge Function de Supabase para confirmar pago
            id_notificacion = self.notificacion['id_notificacion']
            id_venta_digital = self.notificacion.get('id_venta_digital')
            if not id_venta_digital:
                # Intentar obtenerlo desde BD
                detalle = self.pg_manager.obtener_detalle_notificacion(id_notificacion)
                if detalle:
                    id_venta_digital = detalle.get('id_venta_digital')
            
            if self.supabase_service and self.supabase_service.is_connected:
                logging.info(f"[PAGO] Confirmando pago {id_notificacion} con Edge Function")

                if not id_venta_digital:
                    show_error_dialog(self, "Error", "No se pudo determinar id_venta_digital para confirmar el pago.")
                    return

                ids_para_contabilizar = self.pg_manager.get_ventas_digitales_pendientes_efectivo_hoy(int(id_venta_digital))
                if not ids_para_contabilizar:
                    ids_para_contabilizar = [int(id_venta_digital)]

                resultado = self.supabase_service.confirmar_pago_efectivo_edge(int(id_venta_digital))
                
                if resultado.get('success'):
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

                    logging.info(f"✅ Pago confirmado por Edge Function: {resultado.get('message')}")
                    if venta_contable_id:
                        show_success_dialog(
                            self,
                            "Pago Confirmado",
                            f"El pago ha sido confirmado exitosamente.\nLa membresía/visita está activada.\n\nVenta POS: {venta_contable_id}"
                        )
                    else:
                        show_warning_dialog(
                            self,
                            "Pago Confirmado (sin corte)",
                            "El pago fue confirmado, pero no se pudo registrar la venta en el POS para el corte.\n\nVerifique que exista un turno abierto.",
                        )
                    logging.info(f"Pago confirmado exitosamente para notificación {id_notificacion}")
                    self.accept()
                    return
            
            # Fallback: usar método local si no hay conexión a Supabase
            logging.info(f"[PAGO] Usando fallback a método local para {id_notificacion}")
            
            exito = self.pg_manager.confirmar_pago_efectivo(
                id_notificacion,
                observaciones
            )
            
            if exito:
                # Intentar contabilizar también en modo local
                try:
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

                show_success_dialog(
                    self,
                    "Pago Confirmado",
                    "El pago ha sido confirmado exitosamente.\nLa membresía/visita está activada."
                )
                logging.info(f"Pago confirmado exitosamente para notificación {id_notificacion}")
                self.accept()
            else:
                show_error_dialog(
                    self,
                    "Error",
                    "No se pudo confirmar el pago. Por favor intente nuevamente."
                )
                
        except Exception as e:
            logging.error(f"Error confirmando pago: {e}")
            show_error_dialog(self, "Error", f"No se pudo confirmar el pago:\n{str(e)}")


# ============================================================
# VENTANA PRINCIPAL DE NOTIFICACIONES
# ============================================================

class NotificacionesPagoWindow(QWidget):
    """Ventana para visualizar y confirmar notificaciones de pago"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, supabase_service=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.supabase_service = supabase_service
        self.notificaciones_data = []
        
        self.setup_ui()
        self.cargar_notificaciones()
    
    def setup_ui(self):
        """Configurar interfaz de la ventana"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido
        content = QWidget()
        content_layout = create_page_layout("NOTIFICACIONES DE PAGO")
        content.setLayout(content_layout)
        
        # Buscador
        self.search_bar = SearchBar("Buscar por nombre, teléfono o código...")
        self.search_bar.connect_search(self.filtrar_notificaciones)
        content_layout.addWidget(self.search_bar)
        
        # Panel de acciones
        acciones_panel = ContentPanel()
        acciones_layout = QHBoxLayout(acciones_panel)
        acciones_layout.setSpacing(10)
        
        btn_actualizar = TileButton("Actualizar", "mdi.refresh", WindowsPhoneTheme.TILE_BLUE)
        btn_actualizar.setMaximumWidth(150)
        btn_actualizar.setMaximumHeight(100)
        btn_actualizar.clicked.connect(self.cargar_notificaciones)
        acciones_layout.addWidget(btn_actualizar)
        
        btn_escanear = TileButton("Escanear\nQR", "mdi.qrcode-scan", WindowsPhoneTheme.TILE_GREEN)
        btn_escanear.setMaximumWidth(150)
        btn_escanear.setMaximumHeight(100)
        btn_escanear.clicked.connect(self.escanear_qr)
        acciones_layout.addWidget(btn_escanear)
        
        acciones_layout.addStretch()
        
        # Info label
        self.info_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL, bold=True)
        self.info_label.setStyleSheet(f"color: {WindowsPhoneTheme.PRIMARY_BLUE};")
        acciones_layout.addWidget(self.info_label)
        
        content_layout.addWidget(acciones_panel)
        
        # Tabla de notificaciones
        table_panel = ContentPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabla_notificaciones = QTableWidget()
        self.tabla_notificaciones.setColumnCount(6)
        self.tabla_notificaciones.setHorizontalHeaderLabels([
            "Fecha", "Miembro", "Teléfono", "Tipo", "Monto", "Vence"
        ])
        
        # Configurar header
        header = self.tabla_notificaciones.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        # Configurar tabla
        self.tabla_notificaciones.verticalHeader().setVisible(False)
        self.tabla_notificaciones.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_notificaciones.setSelectionMode(QTableWidget.SingleSelection)
        self.tabla_notificaciones.setAlternatingRowColors(True)
        self.tabla_notificaciones.setMinimumHeight(400)
        
        table_layout.addWidget(self.tabla_notificaciones)
        content_layout.addWidget(table_panel)
        
        # Footer con botón volver
        footer = QFrame()
        footer.setMaximumHeight(100)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        footer_layout.addStretch()
        
        btn_volver = TileButton("Volver", "mdi.arrow-left", WindowsPhoneTheme.TILE_GRAY)
        btn_volver.setMaximumWidth(150)
        btn_volver.setMaximumHeight(80)
        btn_volver.setMinimumHeight(80)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        footer_layout.addWidget(btn_volver)
        
        content_layout.addWidget(footer)
        layout.addWidget(content)
    
    def cargar_notificaciones(self):
        """Cargar notificaciones pendientes"""
        try:
            if self.supabase_service:
                # Usar Supabase
                logging.info("Cargando notificaciones desde Supabase...")
                
                # Consultar notificaciones pendientes para recepción
                response = self.supabase_service.client.table('notificaciones_pos') \
                    .select('*, miembros(nombres, apellido_paterno, apellido_materno, telefono)') \
                    .eq('para_recepcion', True) \
                    .eq('respondida', False) \
                    .order('creada_en', desc=True) \
                    .execute()
                
                logging.info(f"Notificaciones encontradas en Supabase: {len(response.data)}")
                
                # Transformar datos de Supabase al formato esperado
                notificaciones = []
                for item in response.data:
                    try:
                        # miembros puede ser None si no hay JOIN o no existe el miembro
                        miembro = item.get('miembros') or {}
                        
                        # Convertir fechas de string a datetime
                        creada_en = item['creada_en']
                        if isinstance(creada_en, str):
                            creada_en = datetime.fromisoformat(creada_en.replace('Z', '+00:00'))
                        
                        fecha_vencimiento = item.get('fecha_vencimiento')
                        if fecha_vencimiento and isinstance(fecha_vencimiento, str):
                            # Si es solo fecha (YYYY-MM-DD), usar strptime
                            try:
                                fecha_vencimiento = datetime.strptime(fecha_vencimiento, '%Y-%m-%d').date()
                            except:
                                fecha_vencimiento = datetime.fromisoformat(fecha_vencimiento.replace('Z', '+00:00')).date()
                        
                        notificaciones.append({
                            'id_notificacion': item['id_notificacion'],
                            'id_miembro': item['id_miembro'],
                            'id_venta_digital': item.get('id_venta_digital'),
                            'tipo_notificacion': item['tipo_notificacion'],
                            'asunto': item['asunto'],
                            'monto_pendiente': item.get('monto_pendiente'),
                            'fecha_vencimiento': fecha_vencimiento,
                            'creada_en': creada_en,
                            'codigo_pago_generado': item.get('codigo_pago_generado'),
                            'nombres': miembro.get('nombres', ''),
                            'apellido_paterno': miembro.get('apellido_paterno', ''),
                            'apellido_materno': miembro.get('apellido_materno', ''),
                            'telefono': miembro.get('telefono', '')
                        })
                    except Exception as e:
                        logging.error(f"Error procesando notificación individual: {e}")
                        logging.error(f"Datos del item: {item}")
                        continue
                
                self.notificaciones_data = notificaciones
                logging.info(f"Se procesaron {len(notificaciones)} notificaciones correctamente")
            else:
                # Fallback a PostgreSQL local - usar método centralizado
                logging.info("Cargando notificaciones desde PostgreSQL local...")
                self.notificaciones_data = self.pg_manager.obtener_notificaciones_pendientes()
                logging.info(f"Se cargaron {len(self.notificaciones_data)} notificaciones desde PostgreSQL")
            
            self.mostrar_notificaciones(self.notificaciones_data)
                
        except Exception as e:
            logging.error(f"Error cargando notificaciones: {e}")
            import traceback
            logging.error(traceback.format_exc())
            show_error_dialog(self, "Error", f"No se pudieron cargar las notificaciones:\n{str(e)}")
    
    def mostrar_notificaciones(self, notificaciones):
        """Mostrar notificaciones en la tabla"""
        logging.info(f"Mostrando {len(notificaciones)} notificaciones en la tabla")
        self.tabla_notificaciones.setRowCount(0)
        
        for i, notif in enumerate(notificaciones):
            try:
                self.tabla_notificaciones.insertRow(i)
                
                # Fecha
                try:
                    if isinstance(notif['creada_en'], datetime):
                        fecha = notif['creada_en'].strftime("%d/%m/%Y %H:%M")
                    else:
                        fecha = str(notif['creada_en'])[:16]  # Truncar si es string
                except Exception as e:
                    logging.error(f"Error formateando fecha: {e}")
                    fecha = "N/A"
                self.tabla_notificaciones.setItem(i, 0, QTableWidgetItem(fecha))
                
                # Miembro
                nombre_completo = f"{notif.get('nombres', '')} {notif.get('apellido_paterno', '')} {notif.get('apellido_materno', '')}"
                self.tabla_notificaciones.setItem(i, 1, QTableWidgetItem(nombre_completo))
                
                # Teléfono
                telefono = notif.get('telefono') or "N/A"
                self.tabla_notificaciones.setItem(i, 2, QTableWidgetItem(str(telefono)))
                
                # Tipo
                tipo = "Membresía" if notif.get('tipo_notificacion') == 'membresia_pendiente' else "Visita"
                self.tabla_notificaciones.setItem(i, 3, QTableWidgetItem(tipo))
                
                # Monto
                try:
                    monto = f"${float(notif['monto_pendiente']):.2f}" if notif.get('monto_pendiente') else "$0.00"
                except:
                    monto = "$0.00"
                item_monto = QTableWidgetItem(monto)
                item_monto.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla_notificaciones.setItem(i, 4, item_monto)
                
                # Fecha vencimiento
                try:
                    fecha_venc = notif.get('fecha_vencimiento')
                    if fecha_venc:
                        if hasattr(fecha_venc, 'strftime'):
                            vence = fecha_venc.strftime("%d/%m/%Y")
                        else:
                            vence = str(fecha_venc)[:10]  # YYYY-MM-DD
                    else:
                        vence = "N/A"
                except Exception as e:
                    logging.error(f"Error formateando fecha vencimiento: {e}")
                    vence = "N/A"
                self.tabla_notificaciones.setItem(i, 5, QTableWidgetItem(vence))
                
                logging.info(f"Fila {i} agregada correctamente: {nombre_completo}")
                
            except Exception as e:
                logging.error(f"Error mostrando notificación {i}: {e}")
                logging.error(f"Datos: {notif}")
                continue
        
        # Actualizar label de información
        total = len(notificaciones)
        self.info_label.setText(f"Total: {total} notificaciones pendientes")
        logging.info(f"Tabla actualizada con {total} notificaciones")
    
    def filtrar_notificaciones(self):
        """Filtrar notificaciones por búsqueda"""
        texto_busqueda = self.search_bar.get_text().lower()
        
        if not texto_busqueda:
            self.mostrar_notificaciones(self.notificaciones_data)
            return
        
        filtradas = [
            n for n in self.notificaciones_data
            if texto_busqueda in f"{n['nombres']} {n['apellido_paterno']} {n['apellido_materno']}".lower()
            or texto_busqueda in (n['telefono'] or "").lower()
            or texto_busqueda in (n['codigo_pago_generado'] or "").lower()
        ]
        
        self.mostrar_notificaciones(filtradas)
    
    def escanear_qr(self):
        """Abrir diálogo para escanear código QR"""
        from ui.components import show_input_dialog
        
        codigo, ok = show_input_dialog(
            self,
            "Escanear Código de Pago",
            "Escanee o ingrese el código QR del cliente:",
            placeholder="Código del QR..."
        )
        
        if ok and codigo:
            self.buscar_por_codigo(codigo.strip())
    
    def buscar_por_codigo(self, codigo):
        """Buscar notificación por código de pago"""
        try:
            # Normalizar el código: convertir caracteres problemáticos a guiones
            # El escáner a veces envía apóstrofos (') en lugar de guiones (-)
            codigo_normalizado = codigo.replace("'", "-").replace("´", "-").replace("`", "-")
            logging.info(f"Código original: {codigo}, Normalizado: {codigo_normalizado}")
            
            notif = None
            
            # Buscar en Supabase si está disponible
            if self.supabase_service:
                logging.info(f"Buscando código en Supabase: {codigo_normalizado}")
                response = self.supabase_service.client.table('notificaciones_pos') \
                    .select('*, miembros(nombres, apellido_paterno, apellido_materno, telefono)') \
                    .eq('codigo_pago_generado', codigo_normalizado) \
                    .eq('respondida', False) \
                    .execute()
                
                if response.data and len(response.data) > 0:
                    # Convertir datos de Supabase al formato esperado
                    item = response.data[0]
                    miembro = item.get('miembros') or {}
                    
                    notif = {
                        'id_notificacion': item['id_notificacion'],
                        'id_miembro': item['id_miembro'],
                        'id_venta_digital': item.get('id_venta_digital'),
                        'tipo_notificacion': item['tipo_notificacion'],
                        'asunto': item['asunto'],
                        'monto_pendiente': item.get('monto_pendiente'),
                        'codigo_pago_generado': item.get('codigo_pago_generado'),
                        'nombres': miembro.get('nombres', ''),
                        'apellido_paterno': miembro.get('apellido_paterno', ''),
                        'apellido_materno': miembro.get('apellido_materno', ''),
                        'telefono': miembro.get('telefono', '')
                    }
                    logging.info(f"Notificación encontrada en Supabase: {notif['id_notificacion']}")
            else:
                # Fallback a PostgreSQL local - usar método centralizado
                logging.info(f"Buscando código en PostgreSQL local: {codigo_normalizado}")
                notif = self.pg_manager.buscar_notificacion_por_codigo_pago(codigo_normalizado)
                
                if notif:
                    logging.info(f"Notificación encontrada en PostgreSQL: {notif['id_notificacion']}")
            
            if notif:
                self.abrir_confirmacion(notif)
            else:
                show_warning_dialog(
                    self,
                    "Código no encontrado",
                    "No se encontró una notificación pendiente con ese código.",
                    "Verifique que el código sea correcto y que el pago no haya sido procesado."
                )
        except Exception as e:
            logging.error(f"Error buscando código: {e}")
            show_error_dialog(self, "Error", f"Error al buscar el código:\n{str(e)}")
    
    def abrir_confirmacion(self, notificacion):
        """Abrir diálogo de confirmación de pago"""
        dialog = ConfirmarPagoDialog(notificacion, self.pg_manager, self.user_data, self.supabase_service, self)
        if dialog.exec() == QDialog.Accepted:
            # Recargar notificaciones después de confirmar
            self.cargar_notificaciones()
