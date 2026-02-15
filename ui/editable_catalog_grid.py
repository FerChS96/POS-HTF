"""
Componente de Grid Editable para Catálogo de Productos
Permite editar información de suplementos y productos varios
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QTabWidget, QSizePolicy, QMessageBox, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
import logging

from ui.components import WindowsPhoneTheme, TileButton, StyledLabel, show_info_dialog, show_warning_dialog, show_error_dialog, create_page_layout, ContentPanel, SearchBar


class EditableCatalogGrid(QWidget):
    """Widget con grid editable para catálogo de productos"""
    
    # Enum de unidades de medida
    UNIDADES_MEDIDA = [
        "",  # Opción vacía
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
    ]
    
    catalogo_actualizado = Signal()
    
    def __init__(self, postgres_manager, parent=None):
        super().__init__(parent)
        self.pg_manager = postgres_manager
        self.productos_varios = []
        self.suplementos = []
        self.cambios_pendientes = {}  # {codigo_interno: {campo: valor_nuevo, ...}}
        
        self.setup_ui()
        self.cargar_datos()
    
    def setup_ui(self):
        """Configurar interfaz del grid editable"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        content = QWidget()
        content_layout = create_page_layout("CATÁLOGO DE PRODUCTOS - EDICIÓN")
        content.setLayout(content_layout)
        
        # Panel de información
        #info_panel = ContentPanel()
        #info_layout = QHBoxLayout(info_panel)
        #info_label = StyledLabel("Seleccione productos para editar. Los cambios se guardarán en la base de datos.", 
        #                        size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        #info_layout.addWidget(info_label, stretch=1)
        #content_layout.addWidget(info_panel)
        
        # Tabs para tipos de productos
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
            }}
            QTabBar::tab {{
                background-color: {WindowsPhoneTheme.BG_LIGHT};
                color: {WindowsPhoneTheme.TEXT_PRIMARY};
                padding: 8px 16px;
                border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background-color: white;
                border-bottom: 2px solid {WindowsPhoneTheme.TILE_BLUE};
            }}
            QTabBar::tab:hover {{
                background-color: #f0f0f0;
            }}
        """)
        
        # Tab Productos Varios
        self.tab_varios = QWidget()
        tab_varios_layout = QVBoxLayout(self.tab_varios)
        tab_varios_layout.setContentsMargins(10, 10, 10, 10)
        tab_varios_layout.setSpacing(10)
        
        # Panel de búsqueda para productos varios
        search_varios_panel = ContentPanel()
        search_varios_layout = QHBoxLayout(search_varios_panel)
        search_varios_layout.setSpacing(10)
        
        search_varios_layout.addWidget(StyledLabel("Buscar:", bold=True))
        self.search_varios = SearchBar("Buscar por código, nombre o descripción...")
        self.search_varios.connect_search(self.filtrar_productos_varios)
        search_varios_layout.addWidget(self.search_varios, stretch=1)
        
        search_varios_layout.addWidget(StyledLabel("Categoría:", bold=True))
        self.combo_categoria_varios = QComboBox()
        self.combo_categoria_varios.setMinimumWidth(150)
        self.combo_categoria_varios.addItem("Todas")
        self.combo_categoria_varios.currentTextChanged.connect(self.filtrar_productos_varios)
        self.combo_categoria_varios.setStyleSheet(f"""
            QComboBox {{
                padding: 6px;
                border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 4px;
                background-color: white;
            }}
        """)
        search_varios_layout.addWidget(self.combo_categoria_varios)
        
        search_varios_layout.addWidget(StyledLabel("Estado:", bold=True))
        self.combo_activo_varios = QComboBox()
        self.combo_activo_varios.addItems(["Todos", "Activos", "Inactivos"])
        self.combo_activo_varios.currentTextChanged.connect(self.filtrar_productos_varios)
        self.combo_activo_varios.setStyleSheet(f"""
            QComboBox {{
                padding: 6px;
                border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 4px;
                background-color: white;
            }}
        """)
        search_varios_layout.addWidget(self.combo_activo_varios)
        
        tab_varios_layout.addWidget(search_varios_panel)
        
        self.tabla_varios = self.crear_tabla_productos_varios()
        tab_varios_layout.addWidget(self.tabla_varios)
        self.tab_widget.addTab(self.tab_varios, "Productos Varios")
        
        # # Tab Suplementos - DESHABILITADO
        # self.tab_suplementos = QWidget()
        # tab_suplementos_layout = QVBoxLayout(self.tab_suplementos)
        # tab_suplementos_layout.setContentsMargins(10, 10, 10, 10)
        # tab_suplementos_layout.setSpacing(10)
        # 
        # # Panel de búsqueda para suplementos
        # search_suplementos_panel = ContentPanel()
        # search_suplementos_layout = QHBoxLayout(search_suplementos_panel)
        # search_suplementos_layout.setSpacing(10)
        # 
        # search_suplementos_layout.addWidget(StyledLabel("Buscar:", bold=True))
        # self.search_suplementos = SearchBar("Buscar por código, nombre o marca...")
        # self.search_suplementos.connect_search(self.filtrar_suplementos)
        # search_suplementos_layout.addWidget(self.search_suplementos, stretch=1)
        # 
        # search_suplementos_layout.addWidget(StyledLabel("Tipo:", bold=True))
        # self.combo_tipo_suplemento = QComboBox()
        # self.combo_tipo_suplemento.setMinimumWidth(150)
        # self.combo_tipo_suplemento.addItem("Todos")
        # self.combo_tipo_suplemento.currentTextChanged.connect(self.filtrar_suplementos)
        # self.combo_tipo_suplemento.setStyleSheet(f"""
        #     QComboBox {{
        #         padding: 6px;
        #         border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
        #         border-radius: 4px;
        #         background-color: white;
        #     }}
        # """)
        # search_suplementos_layout.addWidget(self.combo_tipo_suplemento)
        # 
        # search_suplementos_layout.addWidget(StyledLabel("Estado:", bold=True))
        # self.combo_activo_suplementos = QComboBox()
        # self.combo_activo_suplementos.addItems(["Todos", "Activos", "Inactivos"])
        # self.combo_activo_suplementos.currentTextChanged.connect(self.filtrar_suplementos)
        # self.combo_activo_suplementos.setStyleSheet(f"""
        #     QComboBox {{
        #         padding: 6px;
        #         border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
        #         border-radius: 4px;
        #         background-color: white;
        #     }}
        # """)
        # search_suplementos_layout.addWidget(self.combo_activo_suplementos)
        # 
        # tab_suplementos_layout.addWidget(search_suplementos_panel)
        # 
        # self.tabla_suplementos = self.crear_tabla_suplementos()
        # tab_suplementos_layout.addWidget(self.tabla_suplementos)
        # self.tab_widget.addTab(self.tab_suplementos, "Suplementos")
        
        # Panel con tabla
        table_panel = ContentPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.tab_widget)
        content_layout.addWidget(table_panel)
        
        # Panel de información de cambios
        info_cambios_panel = ContentPanel()
        info_cambios_layout = QHBoxLayout(info_cambios_panel)
        
        self.label_cambios = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        self.label_cambios.setStyleSheet(f"color: {WindowsPhoneTheme.TILE_ORANGE}; font-weight: bold;")
        info_cambios_layout.addWidget(self.label_cambios, stretch=1)
        
        content_layout.addWidget(info_cambios_panel)
        
        # Panel de botones
        botones_layout = QHBoxLayout()
        botones_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_guardar = TileButton("Guardar Cambios", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_guardar.clicked.connect(self.guardar_cambios)
        botones_layout.addWidget(btn_guardar)
        
        btn_descartar = TileButton("Descartar", "fa5s.undo", WindowsPhoneTheme.TILE_ORANGE)
        btn_descartar.clicked.connect(self.descartar_cambios)
        botones_layout.addWidget(btn_descartar)
        
        btn_recargar = TileButton("Recargar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_recargar.clicked.connect(self.cargar_datos)
        botones_layout.addWidget(btn_recargar)
        
        content_layout.addLayout(botones_layout)
        
        layout.addWidget(content)
    
    def crear_tabla_productos_varios(self):
        """Crear tabla editable para productos varios"""
        tabla = QTableWidget()
        tabla.setColumnCount(9)
        tabla.setHorizontalHeaderLabels([
            "Código", "Nombre", "Descripción", "Precio", "Categoría", "Cantidad", "Unidad", "Código Barras", "Activo"
        ])
        
        # Configurar header
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        
        tabla.verticalHeader().setVisible(False)
        tabla.verticalHeader().setDefaultSectionSize(60)
        tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tabla.setAlternatingRowColors(True)
        tabla.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Aplicar estilos
        tabla.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                border: none;
                gridline-color: #e5e7eb;
            }}
            QTableWidget::item {{
                padding: 10px;
                border-bottom: 1px solid #e5e7eb;
            }}
            QTableWidget::item:selected {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {WindowsPhoneTheme.BG_LIGHT};
                color: {WindowsPhoneTheme.PRIMARY_BLUE};
                padding: 10px 6px;
                border: none;
                border-bottom: 2px solid {WindowsPhoneTheme.TILE_BLUE};
                font-weight: bold;
                font-family: '{WindowsPhoneTheme.FONT_FAMILY}';
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
        """)
        
        tabla.itemChanged.connect(self.on_item_changed)
        
        return tabla
    
    def crear_tabla_suplementos(self):
        """Crear tabla editable para suplementos"""
        tabla = QTableWidget()
        tabla.setColumnCount(9)
        tabla.setHorizontalHeaderLabels([
            "Código", "Nombre", "Marca", "Tipo", "Precio", "Cantidad", "Unidad", "Código Barras", "Activo"
        ])
        
        # Configurar header
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        
        tabla.verticalHeader().setVisible(False)
        tabla.verticalHeader().setDefaultSectionSize(60)
        tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tabla.setAlternatingRowColors(True)
        tabla.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Aplicar estilos
        tabla.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                border: none;
                gridline-color: #e5e7eb;
            }}
            QTableWidget::item {{
                padding: 10px;
                border-bottom: 1px solid #e5e7eb;
            }}
            QTableWidget::item:selected {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {WindowsPhoneTheme.BG_LIGHT};
                color: {WindowsPhoneTheme.PRIMARY_BLUE};
                padding: 10px 6px;
                border: none;
                border-bottom: 2px solid {WindowsPhoneTheme.TILE_BLUE};
                font-weight: bold;
                font-family: '{WindowsPhoneTheme.FONT_FAMILY}';
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
        """)
        
        tabla.itemChanged.connect(self.on_item_changed)
        
        return tabla
    
    def cargar_datos(self):
        """Cargar datos de productos desde la base de datos"""
        try:
            logging.info("Cargando catálogo de productos...")
            
            # Obtener productos varios
            response_varios = self.pg_manager.client.table('ca_productos_varios').select('*').execute()
            self.productos_varios = response_varios.data or []
            
            # Obtener suplementos
            response_suplementos = self.pg_manager.client.table('ca_suplementos').select('*').execute()
            self.suplementos = response_suplementos.data or []
            
            # Actualizar combos de filtros
            self.actualizar_combos_filtros()
            
            # Poblar tablas
            self.poblar_tabla_productos_varios()
            # self.poblar_tabla_suplementos()  # DESHABILITADO
            
            self.cambios_pendientes = {}
            self.actualizar_label_cambios()
            
            logging.info(f"Catálogo cargado: {len(self.productos_varios)} productos varios")  # , {len(self.suplementos)} suplementos
            
        except Exception as e:
            logging.error(f"Error cargando catálogo: {e}")
            show_error_dialog(self, "Error al cargar", "No se pudo cargar el catálogo de productos", detail=str(e))
    
    def actualizar_combos_filtros(self):
        """Actualizar los combos de filtros con valores únicos"""
        # Categorías únicas de productos varios
        categorias = set()
        for producto in self.productos_varios:
            cat = producto.get('categoria')
            if cat:
                categorias.add(cat)
        
        self.combo_categoria_varios.clear()
        self.combo_categoria_varios.addItem("Todas")
        for cat in sorted(categorias):
            self.combo_categoria_varios.addItem(cat)
        
        # # Tipos únicos de suplementos - DESHABILITADO
        # tipos = set()
        # for suplemento in self.suplementos:
        #     tipo = suplemento.get('tipo')
        #     if tipo:
        #         tipos.add(tipo)
        # 
        # self.combo_tipo_suplemento.clear()
        # self.combo_tipo_suplemento.addItem("Todos")
        # for tipo in sorted(tipos):
        #     self.combo_tipo_suplemento.addItem(tipo)
    
    def poblar_tabla_productos_varios(self):
        """Poblar tabla de productos varios"""
        tabla = self.tabla_varios
        tabla.setRowCount(0)
        
        for row, producto in enumerate(self.productos_varios):
            tabla.insertRow(row)
            
            # Código (no editable)
            item_codigo = QTableWidgetItem(str(producto.get('codigo_interno', '')))
            item_codigo.setFlags(item_codigo.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabla.setItem(row, 0, item_codigo)
            
            # Nombre (editable)
            tabla.setItem(row, 1, QTableWidgetItem(str(producto.get('nombre', ''))))
            
            # Descripción (editable)
            tabla.setItem(row, 2, QTableWidgetItem(str(producto.get('descripcion', ''))))
            
            # Precio (editable)
            item_precio = QTableWidgetItem(f"{float(producto.get('precio_venta', 0)):.2f}")
            tabla.setItem(row, 3, item_precio)
            
            # Categoría (editable)
            tabla.setItem(row, 4, QTableWidgetItem(str(producto.get('categoria', ''))))
            
            # Cantidad de Medida (editable)
            cantidad = producto.get('cantidad_medida', '')
            item_cantidad = QTableWidgetItem(f"{float(cantidad):.2f}" if cantidad else "")
            tabla.setItem(row, 5, item_cantidad)
            
            # Unidad de Medida (editable - Combo)
            combo_unidad = QComboBox()
            combo_unidad.addItems(self.UNIDADES_MEDIDA)
            valor_actual = str(producto.get('unidad_medida', '') or '')
            if valor_actual in self.UNIDADES_MEDIDA:
                combo_unidad.setCurrentText(valor_actual)
            combo_unidad.currentTextChanged.connect(lambda text, r=row: self._on_combo_changed(r, 6, text))
            combo_unidad.setStyleSheet(f"""
                QComboBox {{
                    padding: 4px;
                    border: none;
                    background-color: white;
                }}
            """)
            tabla.setCellWidget(row, 6, combo_unidad)
            
            # Código Barras (editable)
            tabla.setItem(row, 7, QTableWidgetItem(str(producto.get('codigo_barras', '') or '')))
            
            # Activo (editable)
            item_activo = QTableWidgetItem("Sí" if producto.get('activo', True) else "No")
            tabla.setItem(row, 8, item_activo)
    
    def poblar_tabla_suplementos(self):
        """Poblar tabla de suplementos"""
        tabla = self.tabla_suplementos
        tabla.setRowCount(0)
        
        for row, suplemento in enumerate(self.suplementos):
            tabla.insertRow(row)
            
            # Código (no editable)
            item_codigo = QTableWidgetItem(str(suplemento.get('codigo_interno', '')))
            item_codigo.setFlags(item_codigo.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabla.setItem(row, 0, item_codigo)
            
            # Nombre (editable)
            tabla.setItem(row, 1, QTableWidgetItem(str(suplemento.get('nombre', ''))))
            
            # Marca (editable)
            tabla.setItem(row, 2, QTableWidgetItem(str(suplemento.get('marca', ''))))
            
            # Tipo (editable)
            tabla.setItem(row, 3, QTableWidgetItem(str(suplemento.get('tipo', ''))))
            
            # Precio (editable)
            item_precio = QTableWidgetItem(f"{float(suplemento.get('precio_venta', 0)):.2f}")
            tabla.setItem(row, 4, item_precio)
            
            # Cantidad de Medida (editable)
            cantidad = suplemento.get('cantidad_medida', '')
            item_cantidad = QTableWidgetItem(f"{float(cantidad):.2f}" if cantidad else "")
            tabla.setItem(row, 5, item_cantidad)
            
            # Unidad de Medida (editable - Combo)
            combo_unidad = QComboBox()
            combo_unidad.addItems(self.UNIDADES_MEDIDA)
            valor_actual = str(suplemento.get('unidad_medida', '') or '')
            if valor_actual in self.UNIDADES_MEDIDA:
                combo_unidad.setCurrentText(valor_actual)
            combo_unidad.currentTextChanged.connect(lambda text, r=row: self._on_combo_changed(r, 6, text))
            combo_unidad.setStyleSheet(f"""
                QComboBox {{
                    padding: 4px;
                    border: none;
                    background-color: white;
                }}
            """)
            tabla.setCellWidget(row, 6, combo_unidad)
            
            # Código Barras (editable)
            tabla.setItem(row, 7, QTableWidgetItem(str(suplemento.get('codigo_barras', '') or '')))
            
            # Activo (editable)
            item_activo = QTableWidgetItem("Sí" if suplemento.get('activo', True) else "No")
            tabla.setItem(row, 8, item_activo)
    
    def _on_combo_changed(self, row, col, text):
        """Manejar cambio en un QComboBox de unidad"""
        tabla = self.tabla_varios  # if self.tab_widget.currentIndex() == 0 else self.tabla_suplementos
        codigo_item = tabla.item(row, 0)
        
        if codigo_item:
            codigo = codigo_item.text()
            
            # Inicializar entrada si no existe
            if codigo not in self.cambios_pendientes:
                self.cambios_pendientes[codigo] = {}
            
            # Determinar el nombre del campo
            # Solo productos varios ahora
            campos = ['codigo_interno', 'nombre', 'descripcion', 'precio_venta', 'categoria', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            # if self.tab_widget.currentIndex() == 0:  # Productos varios
            #     campos = ['codigo_interno', 'nombre', 'descripcion', 'precio_venta', 'categoria', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            # else:  # Suplementos
            #     campos = ['codigo_interno', 'nombre', 'marca', 'tipo', 'precio_venta', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            
            if col < len(campos):
                campo = campos[col]
                
                # Resaltar celda modificada
                widget = tabla.cellWidget(row, col)
                if widget:
                    widget.setStyleSheet(f"""
                        QComboBox {{
                            padding: 4px;
                            border: 2px solid #ff8c00;
                            background-color: #fff3cd;
                        }}
                    """)
                
                self.cambios_pendientes[codigo][campo] = text
                self.actualizar_label_cambios()
    
    def on_item_changed(self, item):
        """Manejar cambio en un item de la tabla"""
        # Obtener código del producto
        tabla = self.tabla_varios  # if self.tab_widget.currentIndex() == 0 else self.tabla_suplementos
        row = item.row()
        codigo_item = tabla.item(row, 0)
        
        if codigo_item:
            codigo = codigo_item.text()
            col = item.column()
            
            # Determinar el nombre del campo según la tabla
            # Solo productos varios ahora
            campos = ['codigo_interno', 'nombre', 'descripcion', 'precio_venta', 'categoria', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            # if self.tab_widget.currentIndex() == 0:  # Productos varios
            #     campos = ['codigo_interno', 'nombre', 'descripcion', 'precio_venta', 'categoria', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            # else:  # Suplementos
            #     campos = ['codigo_interno', 'nombre', 'marca', 'tipo', 'precio_venta', 'cantidad_medida', 'unidad_medida', 'codigo_barras', 'activo']
            
            if col < len(campos):
                campo = campos[col]
                
                # No registrar cambios en código
                if campo == 'codigo_interno':
                    return
                
                # Inicializar entrada si no existe
                if codigo not in self.cambios_pendientes:
                    self.cambios_pendientes[codigo] = {}
                
                valor = item.text()
                
                # Resaltar celda modificada
                item.setBackground(QBrush(QColor("#fff3cd")))
                
                self.cambios_pendientes[codigo][campo] = valor
                self.actualizar_label_cambios()
    
    def actualizar_label_cambios(self):
        """Actualizar etiqueta de cambios pendientes"""
        total_cambios = sum(len(v) for v in self.cambios_pendientes.values())
        if total_cambios > 0:
            self.label_cambios.setText(f"[!] {total_cambios} cambios pendientes de guardar")
            self.label_cambios.setStyleSheet("color: #ff8c00; font-weight: bold;")
        else:
            self.label_cambios.setText("")
            self.label_cambios.setStyleSheet("")
    
    def guardar_cambios(self):
        """Guardar cambios en la base de datos"""
        if not self.cambios_pendientes:
            show_info_dialog(self, "Sin cambios", "No hay cambios pendientes para guardar")
            return
        
        try:
            total_guardados = 0
            errores = []
            
            for codigo, cambios in self.cambios_pendientes.items():
                try:
                    # Determinar si es producto varios o suplemento
                    es_producto_varios = any(p.get('codigo_interno') == codigo for p in self.productos_varios)
                    tabla_nombre = 'ca_productos_varios' if es_producto_varios else 'ca_suplementos'
                    
                    # Convertir valores booleanos
                    for campo in ['activo']:
                        if campo in cambios:
                            cambios[campo] = cambios[campo].lower() in ['sí', 'si', 'true', '1']
                    
                    # Convertir precio a float
                    if 'precio_venta' in cambios:
                        cambios['precio_venta'] = float(cambios['precio_venta'])
                    
                    # Convertir cantidad_medida a float (puede ser None/vacío)
                    if 'cantidad_medida' in cambios:
                        cambios['cantidad_medida'] = float(cambios['cantidad_medida']) if cambios['cantidad_medida'].strip() else None
                    
                    # Actualizar en base de datos
                    self.pg_manager.client.table(tabla_nombre).update(cambios).eq('codigo_interno', codigo).execute()
                    total_guardados += 1
                    
                except Exception as e:
                    errores.append(f"{codigo}: {str(e)}")
                    logging.error(f"Error actualizando {codigo}: {e}")
            
            # Limpiar cambios y recargar
            self.cambios_pendientes = {}
            self.actualizar_label_cambios()
            self.cargar_datos()
            
            mensaje = f"Se guardaron {total_guardados} productos"
            if errores:
                mensaje += f"\n\nErrores:\n" + "\n".join(errores)
                show_warning_dialog(self, "Guardado parcial", mensaje)
            else:
                show_info_dialog(self, "Éxito", mensaje)
            
            self.catalogo_actualizado.emit()
            logging.info(f"Cambios guardados: {total_guardados} productos actualizados")
            
        except Exception as e:
            logging.error(f"Error guardando cambios: {e}")
            show_error_dialog(self, "Error al guardar", "No se pudieron guardar los cambios", detail=str(e))
    
    def descartar_cambios(self):
        """Descartar cambios pendientes"""
        if not self.cambios_pendientes:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirmar",
            "¿Descartar todos los cambios pendientes?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.cambios_pendientes = {}
            self.cargar_datos()
    
    def filtrar_productos_varios(self):
        """Filtrar productos varios por búsqueda, categoría y estado"""
        texto_busqueda = self.search_varios.text().lower()
        categoria_filtro = self.combo_categoria_varios.currentText()
        estado_filtro = self.combo_activo_varios.currentText()
        
        for row in range(self.tabla_varios.rowCount()):
            mostrar_fila = True
            
            # Filtro de búsqueda
            if texto_busqueda:
                codigo = self.tabla_varios.item(row, 0).text().lower()
                nombre = self.tabla_varios.item(row, 1).text().lower()
                descripcion = self.tabla_varios.item(row, 2).text().lower() if self.tabla_varios.item(row, 2) else ""
                
                if not (texto_busqueda in codigo or texto_busqueda in nombre or texto_busqueda in descripcion):
                    mostrar_fila = False
            
            # Filtro de categoría
            if mostrar_fila and categoria_filtro != "Todas":
                categoria = self.tabla_varios.item(row, 4).text()
                if categoria != categoria_filtro:
                    mostrar_fila = False
            
            # Filtro de estado
            if mostrar_fila and estado_filtro != "Todos":
                activo = self.tabla_varios.item(row, 6).text()
                if estado_filtro == "Activos" and activo != "Sí":
                    mostrar_fila = False
                elif estado_filtro == "Inactivos" and activo != "No":
                    mostrar_fila = False
            
            self.tabla_varios.setRowHidden(row, not mostrar_fila)
    
    def filtrar_suplementos(self):
        """Filtrar suplementos por búsqueda, tipo y estado"""
        texto_busqueda = self.search_suplementos.text().lower()
        tipo_filtro = self.combo_tipo_suplemento.currentText()
        estado_filtro = self.combo_activo_suplementos.currentText()
        
        for row in range(self.tabla_suplementos.rowCount()):
            mostrar_fila = True
            
            # Filtro de búsqueda
            if texto_busqueda:
                codigo = self.tabla_suplementos.item(row, 0).text().lower()
                nombre = self.tabla_suplementos.item(row, 1).text().lower()
                marca = self.tabla_suplementos.item(row, 2).text().lower() if self.tabla_suplementos.item(row, 2) else ""
                
                if not (texto_busqueda in codigo or texto_busqueda in nombre or texto_busqueda in marca):
                    mostrar_fila = False
            
            # Filtro de tipo
            if mostrar_fila and tipo_filtro != "Todos":
                tipo = self.tabla_suplementos.item(row, 3).text()
                if tipo != tipo_filtro:
                    mostrar_fila = False
            
            # Filtro de estado
            if mostrar_fila and estado_filtro != "Todos":
                activo = self.tabla_suplementos.item(row, 6).text()
                if estado_filtro == "Activos" and activo != "Sí":
                    mostrar_fila = False
                elif estado_filtro == "Inactivos" and activo != "No":
                    mostrar_fila = False
            
            self.tabla_suplementos.setRowHidden(row, not mostrar_fila)
