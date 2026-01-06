"""
Formulario de Nuevo Producto para HTF POS
Permite agregar productos normales (varios) y suplementos
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QDateEdit, QScrollArea,
    QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer, QEvent
from PySide6.QtGui import QFont
import logging

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    create_page_layout,
    ContentPanel,
    TouchNumericInput,
    TouchMoneyInput,
    SectionTitle,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_success_dialog,
    show_confirmation_dialog
)


class NuevoProductoWindow(QWidget):
    """Formulario unificado para agregar productos normales y suplementos"""
    
    cerrar_solicitado = Signal()
    producto_guardado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        
        # Variable para evitar verificaciones duplicadas
        self.ultimo_codigo_verificado = ""
        
        # Timer para detectar entrada del escáner
        self.barcode_timer = QTimer()
        self.barcode_timer.setSingleShot(True)
        self.barcode_timer.setInterval(300)  # 300ms después de que deje de escribir
        self.barcode_timer.timeout.connect(self._verificar_codigo_barras)
        
        self.setup_ui()
        self.cargar_ubicaciones()
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido principal con scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        content_layout = create_page_layout("NUEVO PRODUCTO")
        content.setLayout(content_layout)
        
        # Panel del formulario
        form_panel = ContentPanel()
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(25)
        
        # ===== SELECTOR DE TIPO DE PRODUCTO =====
        tipo_section = QVBoxLayout()
        tipo_section.setSpacing(10)
        
        tipo_label = QLabel("TIPO DE PRODUCTO *")
        tipo_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_SUBTITLE, QFont.Bold))
        tipo_label.setStyleSheet(f"color: {WindowsPhoneTheme.PRIMARY_BLUE};")
        tipo_section.addWidget(tipo_label)
        
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(["Producto Normal (Varios)", "Suplemento"])
        self.tipo_combo.setMinimumHeight(45)
        self.tipo_combo.currentIndexChanged.connect(self.on_tipo_changed)
        tipo_section.addWidget(self.tipo_combo)
        
        form_layout.addLayout(tipo_section)
        
        # Línea divisoria
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"background-color: {WindowsPhoneTheme.PRIMARY_BLUE}; max-height: 2px;")
        form_layout.addWidget(line)
        
        # ===== CAMPOS COMUNES =====
        comunes_title = SectionTitle("INFORMACIÓN GENERAL")
        form_layout.addWidget(comunes_title)
        
        comunes_form = QFormLayout()
        comunes_form.setSpacing(15)
        comunes_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # Código Interno
        self.codigo_interno_input = QLineEdit()
        self.codigo_interno_input.setPlaceholderText("Ej: PROD001")
        self.codigo_interno_input.setMinimumHeight(40)
        self.codigo_interno_input.textChanged.connect(lambda text: self.codigo_interno_input.setText(text.upper()))
        comunes_form.addRow("Código Interno *:", self.codigo_interno_input)
        
        # Nombre
        self.nombre_input = QLineEdit()
        self.nombre_input.setPlaceholderText("Nombre completo del producto")
        self.nombre_input.setMinimumHeight(40)
        comunes_form.addRow("Nombre *:", self.nombre_input)
        
        # Descripción
        self.descripcion_input = QTextEdit()
        self.descripcion_input.setPlaceholderText("Descripción detallada (opcional)")
        self.descripcion_input.setMaximumHeight(100)
        comunes_form.addRow("Descripción:", self.descripcion_input)
        
        # Precio de Venta
        self.precio_input = TouchMoneyInput(
            minimum=0.01,
            maximum=999999.99,
            decimals=2,
            default_value=None
        )
        comunes_form.addRow("Precio de Venta *:", self.precio_input)
        
        # Activo
        self.activo_check = QCheckBox("Producto activo")
        self.activo_check.setChecked(True)
        comunes_form.addRow("Estado:", self.activo_check)
        
        # Ubicación de Almacenamiento
        self.ubicacion_combo = QComboBox()
        self.ubicacion_combo.setMinimumHeight(45)
        self.ubicacion_combo.addItem("-- Seleccionar ubicación --", None)
        # Se cargarán las ubicaciones del catálogo en __init__
        comunes_form.addRow("Ubicación *:", self.ubicacion_combo)
        
        form_layout.addLayout(comunes_form)
        
        # ===== CAMPOS DE PRODUCTOS NORMALES =====
        self.normales_widget = QWidget()
        normales_layout = QVBoxLayout(self.normales_widget)
        normales_layout.setContentsMargins(0, 0, 0, 0)
        normales_layout.setSpacing(15)
        
        normales_title = SectionTitle("DATOS DE PRODUCTO NORMAL")
        normales_layout.addWidget(normales_title)
        
        normales_form = QFormLayout()
        normales_form.setSpacing(15)
        normales_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # Código de Barras
        self.codigo_barras_input = QLineEdit()
        self.codigo_barras_input.setPlaceholderText("Ej: 7501234567890")
        self.codigo_barras_input.setMinimumHeight(40)
        # Instalar event filter para capturar Enter del scanner
        self.codigo_barras_input.installEventFilter(self)
        # Conectar señales
        self.codigo_barras_input.textChanged.connect(self._on_barcode_text_changed)
        normales_form.addRow("Código de Barras:", self.codigo_barras_input)
        
        # Categoría
        self.categoria_input = QLineEdit()
        self.categoria_input.setPlaceholderText("Ej: Bebidas, Snacks, Accesorios")
        self.categoria_input.setText("General")
        self.categoria_input.setMinimumHeight(40)
        normales_form.addRow("Categoría:", self.categoria_input)
        
        # Requiere Refrigeración
        self.refrigeracion_check = QCheckBox("Requiere refrigeración")
        normales_form.addRow("Refrigeración:", self.refrigeracion_check)
        
        # Cantidad de Medida
        self.cantidad_medida_input = TouchMoneyInput(
            minimum=0.0,
            maximum=999999.99,
            decimals=2,
            default_value=None,
            prefix=""
        )
        normales_form.addRow("Cantidad de Medida:", self.cantidad_medida_input)
        
        # Unidad de Medida
        self.unidad_medida_combo = QComboBox()
        self.unidad_medida_combo.addItems([
            "-- Seleccionar unidad --",
            "gramos",
            "kilogramos",
            "mililitros",
            "litros",
            "piezas",
            "onzas",
            "libras",
            "galones",
            "caja",
            "paquete"
        ])
        self.unidad_medida_combo.setMinimumHeight(45)
        normales_form.addRow("Unidad de Medida:", self.unidad_medida_combo)
        
        normales_layout.addLayout(normales_form)
        form_layout.addWidget(self.normales_widget)
        
        # ===== CAMPOS DE SUPLEMENTTOS =====
        self.suplementos_widget = QWidget()
        suplementos_layout = QVBoxLayout(self.suplementos_widget)
        suplementos_layout.setContentsMargins(0, 0, 0, 0)
        suplementos_layout.setSpacing(15)
        
        suplementos_title = SectionTitle("DATOS DE SUPLEMENTO")
        suplementos_layout.addWidget(suplementos_title)
        
        suplementos_form = QFormLayout()
        suplementos_form.setSpacing(15)
        suplementos_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # Marca
        self.marca_input = QLineEdit()
        self.marca_input.setPlaceholderText("Ej: Optimum Nutrition, Dymatize")
        self.marca_input.setMinimumHeight(40)
        suplementos_form.addRow("Marca *:", self.marca_input)
        
        # Tipo de Suplemento
        self.tipo_suplemento_combo = QComboBox()
        self.tipo_suplemento_combo.addItems([
            "Proteína",
            "Creatina",
            "Pre-entreno",
            "Post-entreno",
            "BCAA",
            "Glutamina",
            "Vitaminas",
            "Aminoácidos",
            "Quemador",
            "Ganador de Masa",
            "Otro"
        ])
        self.tipo_suplemento_combo.setMinimumHeight(45)
        suplementos_form.addRow("Tipo de Suplemento *:", self.tipo_suplemento_combo)
        
        # Cantidad de Medida
        self.cantidad_medida_suplemento_input = TouchMoneyInput(
            minimum=0.0,
            maximum=999999.99,
            decimals=2,
            default_value=None,
            prefix=""
        )
        suplementos_form.addRow("Cantidad de Medida:", self.cantidad_medida_suplemento_input)
        
        # Unidad de Medida
        self.unidad_medida_suplemento_combo = QComboBox()
        self.unidad_medida_suplemento_combo.addItems([
            "-- Seleccionar unidad --",
            "gramos",
            "kilogramos",
            "mililitros",
            "litros",
            "piezas",
            "onzas",
            "libras",
            "galones",
            "caja",
            "paquete"
        ])
        self.unidad_medida_suplemento_combo.setMinimumHeight(45)
        suplementos_form.addRow("Unidad de Medida:", self.unidad_medida_suplemento_combo)
        
        # Fecha de Vencimiento
        self.fecha_vencimiento_input = QDateEdit()
        self.fecha_vencimiento_input.setCalendarPopup(True)
        self.fecha_vencimiento_input.setDate(QDate.currentDate().addYears(1))
        self.fecha_vencimiento_input.setMinimumHeight(40)
        self.fecha_vencimiento_input.setDisplayFormat("dd/MM/yyyy")
        suplementos_form.addRow("Fecha Vencimiento:", self.fecha_vencimiento_input)
        
        suplementos_layout.addLayout(suplementos_form)
        form_layout.addWidget(self.suplementos_widget)
        
        # Agregar panel al contenido
        content_layout.addWidget(form_panel)
        
        # ===== BOTONES DE ACCIÓN =====
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_guardar = TileButton("Guardar Producto", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_guardar.clicked.connect(self.guardar_producto)
        
        btn_limpiar = TileButton("Limpiar Formulario", "fa5s.eraser", WindowsPhoneTheme.TILE_ORANGE)
        btn_limpiar.clicked.connect(self.limpiar_formulario)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.confirmar_cancelar)
        
        buttons_layout.addWidget(btn_guardar)
        buttons_layout.addWidget(btn_limpiar)
        buttons_layout.addWidget(btn_cancelar)
        
        content_layout.addLayout(buttons_layout)
        
        # Configurar scroll
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # Mostrar/ocultar campos según tipo inicial
        self.on_tipo_changed(0)
    
    def on_tipo_changed(self, index):
        """Manejar cambio de tipo de producto"""
        is_normal = (index == 0)
        
        # Mostrar/ocultar widgets correspondientes
        self.normales_widget.setVisible(is_normal)
        self.suplementos_widget.setVisible(not is_normal)
    
    def eventFilter(self, obj, event):
        """Filtrar eventos para detectar Enter del scanner en código de barras"""
        if obj == self.codigo_barras_input and event.type() == QEvent.KeyPress:
            key_event = event
            logging.info(f"[EVENT FILTER] Tecla presionada: {key_event.key()} (Enter={Qt.Key_Return})")
            
            if key_event.key() in (Qt.Key_Return, Qt.Key_Enter):
                logging.info("[EVENT FILTER] Enter detectado - verificando código de barras")
                self._verificar_codigo_barras()
                return True  # Evento manejado
        
        return super().eventFilter(obj, event)
    
    def _on_barcode_text_changed(self):
        """Detectar cuando se ingresa texto (para capturar escáner)"""
        texto = self.codigo_barras_input.text().strip()
        
        # Reiniciar el timer cada vez que cambia el texto
        self.barcode_timer.stop()
        
        # Resetear el último código verificado si el usuario está editando
        if len(texto) < 8:
            self.ultimo_codigo_verificado = ""
        
        # Si el texto tiene longitud suficiente para ser un código de barras
        if len(texto) >= 8:  # Códigos de barras típicamente tienen 8+ dígitos
            logging.info(f"[SCANNER TIMER] Detectado código de longitud {len(texto)}, iniciando timer...")
            # Iniciar timer para verificar después de 300ms de inactividad
            self.barcode_timer.start()
    
    def _verificar_codigo_barras(self):
        """Verificar si el código de barras ya existe cuando se presiona Enter"""
        codigo_barras = self.codigo_barras_input.text().strip()
        
        # Evitar verificar el mismo código múltiples veces
        if not codigo_barras or codigo_barras == self.ultimo_codigo_verificado:
            return
        
        logging.info(f"[SCANNER] Verificando código de barras: '{codigo_barras}' (longitud: {len(codigo_barras)})")
        self.ultimo_codigo_verificado = codigo_barras
        
        try:
            # Buscar si ya existe el código de barras
            # Buscar en productos varios
            response_varios = self.pg_manager.client.table('ca_productos_varios').select(
                'codigo_interno, nombre'
            ).eq('codigo_barras', codigo_barras).execute()
            
            producto_varios = response_varios.data[0] if response_varios.data else None
            
            if producto_varios:
                logging.warning(f"Código de barras duplicado en productos varios: {codigo_barras}")
                show_warning_dialog(
                    self,
                    "Código de barras duplicado",
                    f"El código de barras ya existe en:\n\n"
                    f"Código Interno: {producto_varios['codigo_interno']}\n"
                    f"Nombre: {producto_varios['nombre']}"
                )
                self.codigo_barras_input.setFocus()
                self.codigo_barras_input.selectAll()
                return
            
            # Buscar en suplementos
            response_suplemento = self.pg_manager.client.table('ca_suplementos').select(
                'codigo_interno, nombre'
            ).eq('codigo_barras', codigo_barras).execute()
            
            producto_suplemento = response_suplemento.data[0] if response_suplemento.data else None
            
            if producto_suplemento:
                logging.warning(f"Código de barras duplicado en suplementos: {codigo_barras}")
                show_warning_dialog(
                    self,
                    "Código de barras duplicado",
                    f"El código de barras ya existe en:\n\n"
                    f"Código Interno: {producto_suplemento['codigo_interno']}\n"
                f"Nombre: {producto_suplemento['nombre']}"
                )
                self.codigo_barras_input.setFocus()
                self.codigo_barras_input.selectAll()
                return
            
            # Si no existe, mover al siguiente campo sin diálogo
            logging.info(f"[SCANNER] Código de barras {codigo_barras} disponible - moviendo al siguiente campo")
            self.nombre_input.setFocus()
            
        except Exception as e:
            logging.error(f"Error verificando código de barras: {e}")
            show_error_dialog(
                self,
                "Error de verificación",
                "No se pudo verificar el código de barras"
            )
    
    def limpiar_formulario(self):
        """Limpiar todos los campos del formulario"""
        # Campos comunes
        self.codigo_interno_input.clear()
        self.nombre_input.clear()
        self.descripcion_input.clear()
        self.precio_input.setValue(0.0)
        self.activo_check.setChecked(True)
        self.ubicacion_combo.setCurrentIndex(0)  # Resetear a "Seleccionar"
        
        # Campos de productos normales
        self.codigo_barras_input.clear()
        self.categoria_input.setText("General")
        self.refrigeracion_check.setChecked(False)
        self.cantidad_medida_input.setValue(0.0)
        self.unidad_medida_combo.setCurrentIndex(0)
        
        # Campos de suplementos
        self.marca_input.clear()
        self.tipo_suplemento_combo.setCurrentIndex(0)
        self.cantidad_medida_suplemento_input.setValue(0.0)
        self.unidad_medida_suplemento_combo.setCurrentIndex(0)
        self.fecha_vencimiento_input.setDate(QDate.currentDate().addYears(1))
        
        # Enfocar primer campo
        self.codigo_interno_input.setFocus()
        
        logging.info("Formulario limpiado")
    
    def cargar_ubicaciones(self):
        """Cargar ubicaciones desde el catálogo ca_ubicaciones"""
        try:
            response = self.pg_manager.client.table('ca_ubicaciones').select(
                'id_ubicacion, nombre'
            ).eq('activa', True).order('nombre', desc=False).execute()
            
            ubicaciones = response.data
            
            # Agregar ubicaciones al combo
            for ubicacion in ubicaciones:
                self.ubicacion_combo.addItem(
                    ubicacion['nombre'],
                    ubicacion['id_ubicacion']
                )
            
            if ubicaciones:
                # Seleccionar la segunda opción (primera ubicación real) por defecto
                self.ubicacion_combo.setCurrentIndex(1)
                logging.info(f"Cargadas {len(ubicaciones)} ubicaciones")
            else:
                logging.warning("No hay ubicaciones disponibles en el catálogo")
                    
        except Exception as e:
            logging.error(f"Error cargando ubicaciones: {e}")
            show_error_dialog(
                self,
                "Error",
                "No se pudieron cargar las ubicaciones del catálogo"
            )
    
    def confirmar_cancelar(self):
        """Confirmar antes de cancelar"""
        if show_confirmation_dialog(
            self,
            "Cancelar",
            "¿Desea cancelar y volver sin guardar?",
            "Se perderán todos los cambios no guardados."
        ):
            self.cerrar_solicitado.emit()
    
    def validar_campos(self):
        """Validar campos del formulario"""
        is_normal = (self.tipo_combo.currentIndex() == 0)
        
        # Validar campos comunes
        if not self.codigo_interno_input.text().strip():
            show_warning_dialog(self, "Campo requerido", "Debe ingresar un código interno.")
            self.codigo_interno_input.setFocus()
            return False
        
        if not self.nombre_input.text().strip():
            show_warning_dialog(self, "Campo requerido", "Debe ingresar un nombre.")
            self.nombre_input.setFocus()
            return False
        
        if self.precio_input.value() <= 0:
            show_warning_dialog(self, "Precio inválido", "El precio debe ser mayor a cero.")
            self.precio_input.setFocus()
            return False
        
        # Validar ubicación
        if self.ubicacion_combo.currentIndex() == 0:
            show_warning_dialog(self, "Campo requerido", "Debe seleccionar una ubicación.")
            self.ubicacion_combo.setFocus()
            return False
        
        # Validar campos específicos de suplementos
        if not is_normal:
            if not self.marca_input.text().strip():
                show_warning_dialog(self, "Campo requerido", "Debe ingresar una marca para el suplemento.")
                self.marca_input.setFocus()
                return False
        
        # Verificar código interno único
        codigo = self.codigo_interno_input.text().strip().upper()
        if self.pg_manager.producto_existe(codigo):
            show_error_dialog(
                self,
                "Código duplicado",
                f"El código '{codigo}' ya existe en el sistema.",
                "Por favor, use un código diferente."
            )
            self.codigo_interno_input.setFocus()
            return False
        
        return True
    
    def guardar_producto(self):
        """Guardar el producto en la base de datos"""
        try:
            # Validar campos
            if not self.validar_campos():
                return
            
            is_normal = (self.tipo_combo.currentIndex() == 0)
            
            # Preparar datos comunes
            codigo_interno = self.codigo_interno_input.text().strip().upper()
            nombre = self.nombre_input.text().strip()
            descripcion = self.descripcion_input.toPlainText().strip() or None
            precio = self.precio_input.value()
            activo = self.activo_check.isChecked()
            
            if is_normal:
                # Guardar producto normal
                producto_data = {
                    'codigo_interno': codigo_interno,
                    'codigo_barras': self.codigo_barras_input.text().strip() or None,
                    'nombre': nombre,
                    'descripcion': descripcion,
                    'precio_venta': precio,
                    'categoria': self.categoria_input.text().strip() or 'General',
                    'requiere_refrigeracion': self.refrigeracion_check.isChecked(),
                    'cantidad_medida': self.cantidad_medida_input.value() if self.cantidad_medida_input.value() > 0 else None,
                    'unidad_medida': self.unidad_medida_combo.currentText() if self.unidad_medida_combo.currentIndex() > 0 else None,
                    'activo': activo
                }
                
                success = self.pg_manager.insertar_producto_varios(producto_data)
                tipo_msg = "producto normal"
            else:
                # Guardar suplemento
                suplemento_data = {
                    'codigo_interno': codigo_interno,
                    'codigo_barras': self.codigo_barras_input.text().strip() or None,
                    'nombre': nombre,
                    'descripcion': descripcion,
                    'marca': self.marca_input.text().strip(),
                    'tipo': self.tipo_suplemento_combo.currentText(),
                    'cantidad_medida': self.cantidad_medida_suplemento_input.value() if self.cantidad_medida_suplemento_input.value() > 0 else None,
                    'unidad_medida': self.unidad_medida_suplemento_combo.currentText() if self.unidad_medida_suplemento_combo.currentIndex() > 0 else None,
                    'precio_venta': precio,
                    'activo': activo,
                    'fecha_vencimiento': self.fecha_vencimiento_input.date().toString("yyyy-MM-dd")
                }
                
                success = self.pg_manager.insertar_suplemento(suplemento_data)
                tipo_msg = "suplemento"
            
            if success:
                # Obtener ID de ubicación seleccionada
                id_ubicacion = self.ubicacion_combo.currentData()
                
                # Crear registro en inventario con la ubicación
                inventario_data = {
                    'codigo_interno': codigo_interno,
                    'tipo_producto': 'varios' if is_normal else 'suplemento',
                    'stock_actual': 0,
                    'stock_minimo': 5,
                    'id_ubicacion': id_ubicacion,
                    'activo': activo
                }
                
                self.pg_manager.crear_inventario(inventario_data)
                
                # Mostrar mensaje de éxito
                show_info_dialog(
                    self,
                    "Producto guardado",
                    f"El {tipo_msg} '{nombre}' se guardó correctamente.",
                    f"Código: {codigo_interno}\nInventario inicial: 0 unidades"
                )
                
                # Limpiar formulario y emitir señal
                self.limpiar_formulario()
                self.producto_guardado.emit()
                
                logging.info(f"Producto guardado: {codigo_interno} - {nombre}")
            else:
                show_error_dialog(
                    self,
                    "Error al guardar",
                    "No se pudo guardar el producto.",
                    "Verifique los datos e intente nuevamente."
                )
        
        except Exception as e:
            logging.error(f"Error guardando producto: {e}")
            show_error_dialog(
                self,
                "Error",
                "Ocurrió un error al guardar el producto",
                detail=str(e)
            )
