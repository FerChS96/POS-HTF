"""
Ventanas de Ventas para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QFrame, QGridLayout, QComboBox,
    QHeaderView, QDateEdit, QTextEdit, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QFont
import logging
from datetime import datetime, date, time, timedelta

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    InfoTile,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    TopBar,
    apply_windows_phone_stylesheet,
    create_page_layout,
    create_tile_grid_layout,
    show_info_dialog,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog,
    TouchNumericInput,
)
from database.postgres_manager import PostgresManager


class NuevaVentaWindow(QWidget):
    """Widget para realizar nueva venta"""
    
    venta_completada = Signal(dict)
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.venta_id = None  # Initialize 'venta_id'
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Variables de venta
        self.carrito = []
        self.total_venta = 0.0
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz de nueva venta"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido principal
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        
        # Panel izquierdo - Productos
        self.create_products_panel(content_layout)
        
        # Panel derecho - Carrito y total
        self.create_cart_panel(content_layout)
        
        layout.addLayout(content_layout)
        
    def create_products_panel(self, parent_layout):
        """Panel izquierdo con búsqueda y productos"""
        panel = QFrame()
        panel.setMinimumWidth(600)
        layout = QVBoxLayout(panel)
        
        # Título
        title = SectionTitle("PRODUCTOS")
        layout.addWidget(title)
        
        # Búsqueda
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar producto por código o nombre...")
        self.search_input.textChanged.connect(self.buscar_productos)
        search_layout.addWidget(self.search_input)
        
        btn_search = TileButton("Buscar", "fa5s.search", WindowsPhoneTheme.TILE_BLUE)
        btn_search.setMaximumWidth(120)
        btn_search.clicked.connect(self.buscar_productos)
        search_layout.addWidget(btn_search)
        
        layout.addLayout(search_layout)
        
        # Tabla de productos
        self.productos_table = QTableWidget()
        self.productos_table.setColumnCount(5)
        self.productos_table.setHorizontalHeaderLabels([
            "Código", "Nombre", "Precio", "Stock", "Acción"
        ])
        
        # Configurar tabla
        header = self.productos_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.productos_table)
        
        # No cargar productos automáticamente - mostrar mensaje de búsqueda
        self.mostrar_mensaje_busqueda()
        
        parent_layout.addWidget(panel)
        
    def create_cart_panel(self, parent_layout):
        """Panel derecho con carrito de compras"""
        panel = QFrame()
        panel.setMinimumWidth(400)
        layout = QVBoxLayout(panel)
        
        # Título
        title = SectionTitle("CARRITO DE COMPRAS")
        layout.addWidget(title)
        
        # Tabla del carrito
        self.carrito_table = QTableWidget()
        self.carrito_table.setColumnCount(5)
        self.carrito_table.setHorizontalHeaderLabels([
            "Producto", "Precio", "Cant.", "Subtotal", "Quitar"
        ])
        
        header = self.carrito_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.carrito_table)
        
        # Info del total
        total_tile = InfoTile("TOTAL A PAGAR", "fa5s.dollar-sign", WindowsPhoneTheme.TILE_GREEN)
        self.total_label = total_tile.add_main_value("$0.00")
        total_tile.add_stretch()
        layout.addWidget(total_tile)
        
        # Botones de acción
        buttons_layout = QGridLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_limpiar = TileButton("Limpiar Carrito", "fa5s.trash", WindowsPhoneTheme.TILE_RED)
        btn_limpiar.clicked.connect(self.limpiar_carrito)
        
        btn_procesar = TileButton("Procesar Venta", "fa5s.credit-card", WindowsPhoneTheme.TILE_GREEN)
        btn_procesar.clicked.connect(self.procesar_venta)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_ORANGE)
        btn_cancelar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_limpiar, 0, 0)
        buttons_layout.addWidget(btn_procesar, 0, 1)
        buttons_layout.addWidget(btn_cancelar, 1, 0, 1, 2)
        
        layout.addLayout(buttons_layout)
        
        parent_layout.addWidget(panel)
        
    def cargar_productos(self):
        """Cargar productos disponibles"""
        try:
            # Usar el método get_all_products de postgres_manager
            productos = self.pg_manager.get_all_products()
            self.productos_table.setRowCount(len(productos))
            
            for row, producto in enumerate(productos):
                # Código
                self.productos_table.setItem(row, 0, QTableWidgetItem(producto['codigo_barras'] or f"P{producto['id_producto']:04d}"))
                
                # Nombre
                self.productos_table.setItem(row, 1, QTableWidgetItem(producto['nombre']))
                
                # Precio
                precio_item = QTableWidgetItem(f"${producto['precio_venta']:.2f}")
                precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.productos_table.setItem(row, 2, precio_item)
                
                # Stock
                stock_item = QTableWidgetItem(str(producto['stock_actual']))
                stock_item.setTextAlignment(Qt.AlignCenter)
                self.productos_table.setItem(row, 3, stock_item)
                
                # Botón agregar
                btn_agregar = QPushButton("Agregar")
                btn_agregar.setObjectName("tileButton")
                btn_agregar.setProperty("tileColor", WindowsPhoneTheme.TILE_GREEN)
                btn_agregar.clicked.connect(lambda checked, p=producto: self.agregar_al_carrito(p))
                self.productos_table.setCellWidget(row, 4, btn_agregar)
                
        except Exception as e:
            logging.error(f"Error cargando productos: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar los productos: {e}")
            
    def mostrar_mensaje_busqueda(self):
        """Mostrar mensaje indicando que se debe buscar productos"""
        self.productos_table.setRowCount(1)
        self.productos_table.setItem(0, 0, QTableWidgetItem(""))
        self.productos_table.setItem(0, 1, QTableWidgetItem("Escriba en el campo de búsqueda para encontrar productos..."))
        self.productos_table.setItem(0, 2, QTableWidgetItem(""))
        self.productos_table.setItem(0, 3, QTableWidgetItem(""))
        # No agregar botón en la columna de acciones
            
    def buscar_productos(self):
        """Buscar productos por texto"""
        texto = self.search_input.text().strip()
        if not texto:
            self.mostrar_mensaje_busqueda()
            return
            
        try:
            # Usar el método search_products de postgres_manager
            productos = self.pg_manager.search_products(texto)
            self.productos_table.setRowCount(len(productos))
            
            for row, producto in enumerate(productos):
                self.productos_table.setItem(row, 0, QTableWidgetItem(producto['codigo_barras'] or f"P{producto['id_producto']:04d}"))
                self.productos_table.setItem(row, 1, QTableWidgetItem(producto['nombre']))
                
                precio_item = QTableWidgetItem(f"${producto['precio_venta']:.2f}")
                precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.productos_table.setItem(row, 2, precio_item)
                
                stock_item = QTableWidgetItem(str(producto['stock_actual']))
                stock_item.setTextAlignment(Qt.AlignCenter)
                self.productos_table.setItem(row, 3, stock_item)
                
                btn_agregar = QPushButton("Agregar")
                btn_agregar.setObjectName("tileButton")
                btn_agregar.setProperty("tileColor", WindowsPhoneTheme.TILE_GREEN)
                btn_agregar.clicked.connect(lambda checked, p=producto: self.agregar_al_carrito(p))
                self.productos_table.setCellWidget(row, 4, btn_agregar)
                
        except Exception as e:
            logging.error(f"Error buscando productos: {e}")
            
    def agregar_al_carrito(self, producto):
        """Agregar producto al carrito"""
        if producto['stock_actual'] <= 0:
            show_warning_dialog(self, "Sin Stock", f"El producto '{producto['nombre']}' no tiene stock disponible.")
            return
            
        # Verificar si ya está en el carrito
        for item in self.carrito:
            if item['id_producto'] == producto['id_producto']:
                if item['cantidad'] < producto['stock_actual']:
                    item['cantidad'] += 1
                    item['subtotal'] = item['cantidad'] * item['precio']
                else:
                    show_warning_dialog(self, "Stock Insuficiente", f"Solo hay {producto['stock_actual']} unidades disponibles.")
                    return
                break
        else:
            # Nuevo producto en el carrito
            self.carrito.append({
                'id_producto': producto['id_producto'],
                'nombre': producto['nombre'],
                'precio': producto['precio_venta'],
                'cantidad': 1,
                'subtotal': producto['precio_venta'],
                'stock_disponible': producto['stock_actual']
            })
            
        self.actualizar_carrito()
        
    def actualizar_carrito(self):
        """Actualizar tabla del carrito y total"""
        self.carrito_table.setRowCount(len(self.carrito))
        self.total_venta = 0.0
        
        for row, item in enumerate(self.carrito):
            # Producto
            self.carrito_table.setItem(row, 0, QTableWidgetItem(item['nombre']))
            
            # Precio
            precio_item = QTableWidgetItem(f"${item['precio']:.2f}")
            precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.carrito_table.setItem(row, 1, precio_item)
            
            # Cantidad (editable)
            cantidad_spin = TouchNumericInput(
                minimum=1,
                maximum=item['stock_disponible'],
                default_value=item['cantidad']
            )
            cantidad_spin.valueChanged.connect(lambda val, idx=row: self.cambiar_cantidad(idx, val))
            self.carrito_table.setCellWidget(row, 2, cantidad_spin)
            
            # Subtotal
            subtotal_item = QTableWidgetItem(f"${item['subtotal']:.2f}")
            subtotal_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.carrito_table.setItem(row, 3, subtotal_item)
            
            # Botón quitar
            btn_quitar = QPushButton("Quitar")
            btn_quitar.setObjectName("tileButton")
            btn_quitar.setProperty("tileColor", WindowsPhoneTheme.TILE_RED)
            btn_quitar.clicked.connect(lambda checked, idx=row: self.quitar_del_carrito(idx))
            self.carrito_table.setCellWidget(row, 4, btn_quitar)
            
            self.total_venta += item['subtotal']
            
        # Actualizar total
        self.total_label.setText(f"${self.total_venta:.2f}")
        
    def cambiar_cantidad(self, index, nueva_cantidad):
        """Cambiar cantidad de un item del carrito"""
        if 0 <= index < len(self.carrito):
            self.carrito[index]['cantidad'] = nueva_cantidad
            self.carrito[index]['subtotal'] = nueva_cantidad * self.carrito[index]['precio']
            self.actualizar_carrito()
            
    def quitar_del_carrito(self, index):
        """Quitar item del carrito"""
        if 0 <= index < len(self.carrito):
            del self.carrito[index]
            self.actualizar_carrito()
            
    def limpiar_carrito(self):
        """Limpiar todo el carrito"""
        if show_confirmation_dialog(
            self,
            "Confirmar",
            "¿Está seguro de que desea limpiar el carrito?",
            confirm_text="Sí, limpiar",
            cancel_text="No"
        ):
            self.carrito.clear()
            self.actualizar_carrito()
            
    def registrar_venta(self, venta_data):
        try:
            # Usar el método create_sale de postgres_manager
            self.venta_id = self.pg_manager.create_sale(venta_data)
            show_success_dialog(self, "Éxito", f"Venta registrada correctamente. ID: {self.venta_id}")
        except Exception as e:
            logging.error(f"Error registrando venta: {e}")
            show_error_dialog(self, "Error", f"No se pudo registrar la venta: {e}")
            
    def procesar_venta(self):
        """Procesar la venta"""
        if not self.carrito:
            show_warning_dialog(self, "Carrito Vacío", "Agregue productos al carrito antes de procesar la venta.")
            return
            
        try:
            # Crear venta en la base de datos
            venta_data = {
                'id_usuario': self.user_data['id_usuario'],
                'productos': self.carrito,
                'total': self.total_venta
            }
            
            self.registrar_venta(venta_data)
            
            # Emitir señal de venta completada
            self.venta_completada.emit({
                'id_venta': self.venta_id,
                'total': self.total_venta,
                'productos': len(self.carrito)
            })
            
            show_success_dialog(
                self,
                "Venta Procesada",
                f"Venta procesada exitosamente.\nTotal: ${self.total_venta:.2f}\nID de venta: {self.venta_id}"
            )
            
            # Limpiar carrito
            self.carrito.clear()
            self.actualizar_carrito()
            
            # Recargar productos para actualizar stock
            self.cargar_productos()
            
        except Exception as e:
            logging.error(f"Error procesando venta: {e}")
            show_error_dialog(self, "Error", f"Error al procesar la venta: {e}")


class VentasDiaWindow(QWidget):
    """Widget para ver ventas del día"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz de ventas del día"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido
        content = QWidget()
        content_layout = create_page_layout("RESUMEN DE VENTAS - " + date.today().strftime("%d/%m/%Y"))
        content.setLayout(content_layout)
        
        # Widgets de resumen
        self.create_summary_widgets(content_layout)
        
        # Tabla de ventas
        self.create_sales_table(content_layout)
        
        # Botones
        buttons_layout = QHBoxLayout()
        
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_actualizar.clicked.connect(self.actualizar_datos)
        
        btn_imprimir = TileButton("Imprimir", "fa5s.print", WindowsPhoneTheme.TILE_GREEN)
        btn_imprimir.clicked.connect(self.imprimir_reporte)
        
        btn_cerrar = TileButton("Cerrar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cerrar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_actualizar)
        buttons_layout.addWidget(btn_imprimir)
        buttons_layout.addWidget(btn_cerrar)
        
        content_layout.addLayout(buttons_layout)
        layout.addWidget(content)
        
        # Cargar datos iniciales
        self.actualizar_datos()
        
    def create_summary_widgets(self, parent_layout):
        """Crear widgets de resumen"""
        widgets_layout = QHBoxLayout()
        widgets_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        # Total vendido
        self.total_tile = InfoTile("TOTAL VENDIDO", "fa5s.dollar-sign", WindowsPhoneTheme.TILE_GREEN)
        self.total_value = self.total_tile.add_main_value("$0.00")
        self.total_tile.add_stretch()
        widgets_layout.addWidget(self.total_tile)
        
        # Número de ventas
        self.ventas_tile = InfoTile("VENTAS", "fa5s.shopping-cart", WindowsPhoneTheme.TILE_BLUE)
        self.ventas_count = self.ventas_tile.add_main_value("0")
        self.ventas_tile.add_secondary_value("transacciones")
        self.ventas_tile.add_stretch()
        widgets_layout.addWidget(self.ventas_tile)
        
        # Promedio por venta
        self.promedio_tile = InfoTile("PROMEDIO", "fa5s.chart-line", WindowsPhoneTheme.TILE_ORANGE)
        self.promedio_value = self.promedio_tile.add_main_value("$0.00")
        self.promedio_tile.add_secondary_value("por venta")
        self.promedio_tile.add_stretch()
        widgets_layout.addWidget(self.promedio_tile)
        
        parent_layout.addLayout(widgets_layout)
        
    def create_sales_table(self, parent_layout):
        """Crear tabla de ventas"""
        self.ventas_table = QTableWidget()
        self.ventas_table.setColumnCount(5)
        self.ventas_table.setHorizontalHeaderLabels([
            "ID Venta", "Hora", "Total", "Usuario", "Estado"
        ])
        
        header = self.ventas_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        
        parent_layout.addWidget(self.ventas_table)
        
    def actualizar_datos(self):
        """Actualizar datos de ventas del día"""
        try:
            # Obtener ventas del día usando Supabase
            from datetime import date
            response = self.pg_manager.client.table('ventas').select(
                'id_venta, fecha, total, usuarios(nombre_completo)'
            ).gte('fecha', f'{date.today()}T00:00:00').lte(
                'fecha', f'{date.today()}T23:59:59'
            ).order('fecha', desc=True).execute()
            
            ventas = response.data or []
            
            # Calcular resumen
            total_vendido = sum(v.get('total', 0) for v in ventas)
            num_ventas = len(ventas)
            promedio = total_vendido / num_ventas if num_ventas > 0 else 0
            
            # Actualizar widgets
            self.total_value.setText(f"${total_vendido:.2f}")
            self.ventas_count.setText(str(num_ventas))
            self.promedio_value.setText(f"${promedio:.2f}")
            
            # Actualizar tabla
            self.ventas_table.setRowCount(len(ventas))
            
            for row, venta in enumerate(ventas):
                # ID Venta
                self.ventas_table.setItem(row, 0, QTableWidgetItem(str(venta['id_venta'])))
                
                # Hora
                hora = venta['fecha'].strftime("%H:%M") if isinstance(venta['fecha'], datetime) else venta['fecha']
                self.ventas_table.setItem(row, 1, QTableWidgetItem(str(hora)))
                
                # Total
                total_item = QTableWidgetItem(f"${venta['total']:.2f}")
                total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ventas_table.setItem(row, 2, total_item)
                
                # Usuario
                self.ventas_table.setItem(row, 3, QTableWidgetItem(venta.get('usuario', 'N/A')))
                
                # Estado
                self.ventas_table.setItem(row, 4, QTableWidgetItem("Completada"))
                
        except Exception as e:
            logging.error(f"Error actualizando datos: {e}")
            show_warning_dialog(self, "Error", f"Error al cargar datos: {e}")
            
    def imprimir_reporte(self):
        """Imprimir reporte de ventas del día"""
        show_info_dialog(self, "Imprimir", "Función de impresión por implementar")


class HistorialVentasWindow(QWidget):
    """Widget para ver historial de ventas"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz de historial"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido
        content = QWidget()
        content_layout = create_page_layout("HISTORIAL COMPLETO")
        content.setLayout(content_layout)
        
        # Filtros
        self.create_filters(content_layout)
        
        # Tabla
        self.create_history_table(content_layout)
        
        # Botones
        buttons_layout = QHBoxLayout()
        
        btn_buscar = TileButton("Buscar", "fa5s.search", WindowsPhoneTheme.TILE_BLUE)
        btn_buscar.clicked.connect(self.buscar_ventas)
        
        btn_exportar = TileButton("Exportar", "fa5s.download", WindowsPhoneTheme.TILE_GREEN)
        btn_exportar.clicked.connect(self.exportar_datos)
        
        btn_cerrar = TileButton("Cerrar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cerrar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_buscar)
        buttons_layout.addWidget(btn_exportar)
        buttons_layout.addWidget(btn_cerrar)
        
        content_layout.addLayout(buttons_layout)
        layout.addWidget(content)
        
        # Cargar datos iniciales
        self.buscar_ventas()
        
    def create_filters(self, parent_layout):
        """Crear filtros de búsqueda"""
        filters_frame = QFrame()
        filters_layout = QHBoxLayout(filters_frame)
        
        # Fecha desde
        filters_layout.addWidget(QLabel("Desde:"))
        self.fecha_desde = QDateEdit()
        self.fecha_desde.setDate(QDate.currentDate().addDays(-30))
        self.fecha_desde.setCalendarPopup(True)
        filters_layout.addWidget(self.fecha_desde)
        
        # Fecha hasta
        filters_layout.addWidget(QLabel("Hasta:"))
        self.fecha_hasta = QDateEdit()
        self.fecha_hasta.setDate(QDate.currentDate())
        self.fecha_hasta.setCalendarPopup(True)
        filters_layout.addWidget(self.fecha_hasta)
        
        filters_layout.addStretch()
        parent_layout.addWidget(filters_frame)
        
    def create_history_table(self, parent_layout):
        """Crear tabla de historial"""
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "ID", "Fecha", "Hora", "Total", "Usuario", "Detalles"
        ])
        
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        parent_layout.addWidget(self.history_table)
        
    def buscar_ventas(self):
        """Buscar ventas por rango de fechas"""
        try:
            fecha_desde = self.fecha_desde.date().toPython()
            fecha_hasta = self.fecha_hasta.date().toPython()
            
            response = self.pg_manager.client.table('ventas').select(
                'id_venta, fecha, total, usuarios(nombre_completo)'
            ).gte('fecha', f'{fecha_desde}T00:00:00').lte(
                'fecha', f'{fecha_hasta}T23:59:59'
            ).order('fecha', desc=True).execute()
            
            ventas = response.data or []
            
            self.history_table.setRowCount(len(ventas))
            
            for row, venta in enumerate(ventas):
                # ID
                self.history_table.setItem(row, 0, QTableWidgetItem(str(venta['id_venta'])))
                
                # Fecha
                fecha = venta['fecha'].strftime("%d/%m/%Y") if isinstance(venta['fecha'], datetime) else str(venta['fecha'])
                self.history_table.setItem(row, 1, QTableWidgetItem(fecha))
                
                # Hora
                hora = venta['fecha'].strftime("%H:%M") if isinstance(venta['fecha'], datetime) else "N/A"
                self.history_table.setItem(row, 2, QTableWidgetItem(hora))
                
                # Total
                total_item = QTableWidgetItem(f"${venta['total']:.2f}")
                total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.history_table.setItem(row, 3, total_item)
                
                # Usuario
                self.history_table.setItem(row, 4, QTableWidgetItem(venta.get('usuario', 'N/A')))
                
                # Botón detalles
                btn_detalles = QPushButton("Ver")
                btn_detalles.setObjectName("tileButton")
                btn_detalles.setProperty("tileColor", WindowsPhoneTheme.TILE_BLUE)
                btn_detalles.clicked.connect(lambda checked, vid=venta['id_venta']: self.ver_detalles(vid))
                self.history_table.setCellWidget(row, 5, btn_detalles)
        
        except Exception as e:
            logging.error(f"Error buscando ventas: {e}")
            show_warning_dialog(self, "Error", f"Error al buscar ventas: {e}")
            
    def ver_detalles(self, venta_id):
        """Ver detalles de una venta"""
        # TODO: Implementar ventana de detalles de venta
        show_info_dialog(self, "Detalles", f"Ver detalles de venta ID: {venta_id}")
        
    def exportar_datos(self):
        """Exportar datos a archivo"""
        show_info_dialog(self, "Exportar", "Función de exportación por implementar")


class CierreCajaWindow(QWidget):
    """Widget para cierre de caja"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.turno_abierto = None
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Verificar si hay turno abierto antes de mostrar UI
        if not self.verificar_turno_abierto():
            self.mostrar_sin_turno()
        else:
            self.setup_ui()
    
    def verificar_turno_abierto(self):
        """Verificar si el usuario tiene un turno abierto"""
        try:
            response = self.pg_manager.client.table('turnos_caja').select(
                'id_turno, monto_inicial, fecha_apertura'
            ).eq('id_usuario', self.user_data['id_usuario']).eq(
                'cerrado', False
            ).order('fecha_apertura', desc=True).limit(1).execute()
            
            if response.data and len(response.data) > 0:
                self.turno_abierto = response.data[0]
                return True
            return False
                
        except Exception as e:
            logging.error(f"Error verificando turno abierto: {e}")
            return False
    
    def mostrar_sin_turno(self):
        """Mostrar mensaje cuando no hay turno abierto"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Panel de información
        info_panel = ContentPanel()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(40, 40, 40, 40)
        info_layout.setSpacing(20)
        
        # Icono y título
        title = StyledLabel(
            "NO HAY TURNO ABIERTO",
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_TITLE
        )
        title.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(title)
        
        # Mensaje
        mensaje = StyledLabel(
            "No tienes un turno abierto actualmente.\n\n"
            "Para cerrar caja primero debes tener un turno activo.\n"
            "Contacta al administrador para que te asigne un turno.",
            size=WindowsPhoneTheme.FONT_SIZE_NORMAL
        )
        mensaje.setAlignment(Qt.AlignCenter)
        mensaje.setWordWrap(True)
        info_layout.addWidget(mensaje)
        
        layout.addWidget(info_panel)
        layout.addStretch()
        
        # Botón volver
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_BLUE)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        layout.addWidget(btn_volver)
        
    def setup_ui(self):
        """Configurar interfaz de cierre de caja"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Scroll area para el contenido
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Contenido
        self.content_widget = QWidget()
        content_layout = create_page_layout("RESUMEN DEL DÍA - " + date.today().strftime("%d/%m/%Y"))
        self.content_widget.setLayout(content_layout)
        
        # Resumen de ventas
        self.create_summary_section(content_layout)
        
        # Conteo de efectivo
        self.create_cash_count_section(content_layout)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_cerrar_caja = TileButton("Cerrar Caja", "fa5s.lock", WindowsPhoneTheme.TILE_GREEN)
        btn_cerrar_caja.setMinimumHeight(80)
        btn_cerrar_caja.setMaximumHeight(100)
        btn_cerrar_caja.clicked.connect(self.procesar_cierre)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.setMinimumHeight(80)
        btn_cancelar.setMaximumHeight(100)
        btn_cancelar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_cerrar_caja)
        buttons_layout.addWidget(btn_cancelar)
        
        content_layout.addLayout(buttons_layout)
        
        # Agregar contenido al scroll
        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll)
        
        # Cargar datos iniciales
        self.cargar_resumen()
        
    def resizeEvent(self, event):
        """Manejar evento de redimensionamiento"""
        super().resizeEvent(event)
        # Forzar actualización del layout
        if hasattr(self, 'scroll'):
            self.scroll.updateGeometry()
            if hasattr(self, 'content_widget'):
                self.content_widget.updateGeometry()
        
    def create_summary_section(self, parent_layout):
        """Crear sección de resumen"""
        # Widgets de resumen en grid
        summary_layout = QGridLayout()
        summary_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        # Total esperado
        self.esperado_tile = InfoTile("TOTAL ESPERADO", "fa5s.dollar-sign", WindowsPhoneTheme.TILE_BLUE)
        self.esperado_value = self.esperado_tile.add_main_value("$0.00")
        self.esperado_tile.add_secondary_value("según ventas")
        self.esperado_tile.add_stretch()
        summary_layout.addWidget(self.esperado_tile, 0, 0)
        
        # Número de ventas
        self.ventas_tile = InfoTile("TRANSACCIONES", "fa5s.shopping-cart", WindowsPhoneTheme.TILE_GREEN)
        self.ventas_value = self.ventas_tile.add_main_value("0")
        self.ventas_tile.add_secondary_value("ventas realizadas")
        self.ventas_tile.add_stretch()
        summary_layout.addWidget(self.ventas_tile, 0, 1)
        
        parent_layout.addLayout(summary_layout)
        
    def create_cash_count_section(self, parent_layout):
        """Crear sección de conteo de efectivo simplificada"""
        cash_frame = QFrame()
        cash_layout = QVBoxLayout(cash_frame)
        cash_layout.setSpacing(15)
        
        # Título
        title = SectionTitle("CONTEO DE EFECTIVO")
        cash_layout.addWidget(title)
        
        # Grid simplificado
        form_layout = QGridLayout()
        form_layout.setSpacing(15)
        form_layout.setColumnStretch(1, 1)  # La columna de inputs se expande
        
        # Efectivo en caja
        label_efectivo = QLabel("Efectivo en caja:")
        label_efectivo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        form_layout.addWidget(label_efectivo, 0, 0, Qt.AlignTop)
        
        self.efectivo_input = QLineEdit()
        self.efectivo_input.setPlaceholderText("0.00")
        self.efectivo_input.textChanged.connect(self.calcular_diferencia)
        self.efectivo_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14))
        self.efectivo_input.setMinimumHeight(45)
        form_layout.addWidget(self.efectivo_input, 0, 1)
        
        # Tarjetas (si aplica)
        label_tarjeta = QLabel("Pagos con tarjeta:")
        label_tarjeta.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        form_layout.addWidget(label_tarjeta, 1, 0, Qt.AlignTop)
        
        self.tarjeta_input = QLineEdit()
        self.tarjeta_input.setPlaceholderText("0.00")
        self.tarjeta_input.textChanged.connect(self.calcular_diferencia)
        self.tarjeta_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14))
        self.tarjeta_input.setMinimumHeight(45)
        form_layout.addWidget(self.tarjeta_input, 1, 1)
        
        # Otros métodos de pago
        label_otros = QLabel("Otros pagos:")
        label_otros.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        form_layout.addWidget(label_otros, 2, 0, Qt.AlignTop)
        
        self.otros_input = QLineEdit()
        self.otros_input.setPlaceholderText("0.00")
        self.otros_input.textChanged.connect(self.calcular_diferencia)
        self.otros_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14))
        self.otros_input.setMinimumHeight(45)
        form_layout.addWidget(self.otros_input, 2, 1)
        
        # Notas
        label_notas = QLabel("Notas:")
        label_notas.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
        form_layout.addWidget(label_notas, 3, 0, Qt.AlignTop)
        
        self.notas_input = QTextEdit()
        self.notas_input.setPlaceholderText("Observaciones del cierre de caja...")
        self.notas_input.setMinimumHeight(100)
        self.notas_input.setMaximumHeight(150)
        form_layout.addWidget(self.notas_input, 3, 1)
        
        cash_layout.addLayout(form_layout)
        
        # Espaciador
        cash_layout.addSpacing(10)
        
        # Total contado
        self.total_tile = InfoTile("TOTAL CONTADO", "fa5s.money-bill", WindowsPhoneTheme.TILE_GREEN)
        self.total_contado = self.total_tile.add_main_value("$0.00")
        self.diferencia_label = self.total_tile.add_secondary_value("Diferencia: $0.00")
        self.total_tile.add_stretch()
        cash_layout.addWidget(self.total_tile)
        
        parent_layout.addWidget(cash_frame)
        
    def cargar_resumen(self):
        """Cargar resumen del día"""
        try:
            # Obtener ventas del día usando Supabase
            from datetime import date
            response = self.pg_manager.client.table('ventas').select(
                'id_venta, fecha, total, usuarios(nombre_completo)'
            ).gte('fecha', f'{date.today()}T00:00:00').lte(
                'fecha', f'{date.today()}T23:59:59'
            ).order('fecha', desc=True).execute()
            
            ventas = response.data or []
            total_esperado = sum(v.get('total', 0) for v in ventas)
            num_ventas = len(ventas)
            
            # Actualizar widgets
            self.esperado_value.setText(f"${total_esperado:.2f}")
            self.ventas_value.setText(str(num_ventas))
            
            # Guardar valores para cálculos
            self.total_esperado_valor = total_esperado
            
        except Exception as e:
            logging.error(f"Error cargando resumen: {e}")
            self.total_esperado_valor = 0.0
            
    def calcular_diferencia(self):
        """Calcular diferencia entre esperado y contado"""
        try:
            # Obtener valores de los campos
            efectivo = float(self.efectivo_input.text() or 0)
            tarjeta = float(self.tarjeta_input.text() or 0)
            otros = float(self.otros_input.text() or 0)
            
            # Calcular total
            total = efectivo + tarjeta + otros
            
            # Actualizar total contado
            self.total_contado.setText(f"${total:.2f}")
            self.total_contado_valor = total
            
            # Calcular diferencia
            diferencia = total - self.total_esperado_valor
            signo = "+" if diferencia >= 0 else ""
            self.diferencia_label.setText(f"Diferencia: {signo}${diferencia:.2f}")
            
        except ValueError:
            # Si hay un error de conversión, no hacer nada
            pass
    
    def verificar_horario_turno(self):
        """Verificar si el cierre está dentro del horario esperado del turno
        
        Returns:
            tuple: (requiere_autorizacion: bool, motivo: str)
        """
        try:
            if not self.turno_abierto:
                return False, ""
            
            # Obtener hora de apertura del turno
            fecha_apertura = self.turno_abierto['fecha_apertura']
            hora_apertura = fecha_apertura.time()
            
            # Calcular hora esperada de cierre según el turno
            hora_actual = datetime.now().time()
            
            # Determinar tipo de turno basado en hora de apertura
            if time(5, 0) <= hora_apertura < time(13, 0):
                # Turno matutino
                hora_inicio_esperada = time(6, 0)
                hora_fin_esperada = time(14, 0)
                nombre_turno = "Matutino (06:00 - 14:00)"
            elif time(13, 0) <= hora_apertura < time(21, 0):
                # Turno vespertino
                hora_inicio_esperada = time(14, 0)
                hora_fin_esperada = time(22, 0)
                nombre_turno = "Vespertino (14:00 - 22:00)"
            else:
                # Turno fuera de horario estándar, requiere autorización siempre
                return True, f"Cierre de turno fuera de horario estándar\n\nTurno iniciado a las {hora_apertura.strftime('%H:%M')}"
            
            # Margen de tolerancia: 30 minutos antes o después
            margen = timedelta(minutes=30)
            
            # Convertir a datetime para comparar
            ahora = datetime.now()
            fecha_hoy = ahora.date()
            
            hora_fin_datetime = datetime.combine(fecha_hoy, hora_fin_esperada)
            hora_cierre_min = hora_fin_datetime - margen
            hora_cierre_max = hora_fin_datetime + margen
            
            # Verificar si está fuera del rango
            if ahora < hora_cierre_min:
                # Cerrando muy temprano
                diferencia = hora_cierre_min - ahora
                minutos = int(diferencia.total_seconds() / 60)
                return True, (
                    f"Cierre anticipado de turno {nombre_turno}\n\n"
                    f"Hora esperada de cierre: {hora_fin_esperada.strftime('%H:%M')}\n"
                    f"Hora actual: {hora_actual.strftime('%H:%M')}\n"
                    f"Se está cerrando {minutos} minutos antes de lo esperado"
                )
            elif ahora > hora_cierre_max:
                # Cerrando muy tarde
                diferencia = ahora - hora_cierre_max
                minutos = int(diferencia.total_seconds() / 60)
                
                # Mostrar advertencia pero no requiere autorización si es menos de 2 horas
                if minutos < 120:
                    show_warning_dialog(
                        self,
                        "Recordatorio",
                        f"⚠️ El turno {nombre_turno} debía cerrar a las {hora_fin_esperada.strftime('%H:%M')}\n\n"
                        f"Recuerda cerrar el turno puntualmente al finalizar tu horario."
                    )
                    return False, ""
                else:
                    # Más de 2 horas de retraso requiere autorización
                    return True, (
                        f"Cierre tardío de turno {nombre_turno}\n\n"
                        f"Hora esperada de cierre: {hora_fin_esperada.strftime('%H:%M')}\n"
                        f"Hora actual: {hora_actual.strftime('%H:%M')}\n"
                        f"Se está cerrando {minutos} minutos después de lo esperado"
                    )
            
            # Está dentro del rango aceptable
            return False, ""
            
        except Exception as e:
            logging.error(f"Error verificando horario de turno: {e}")
            # En caso de error, permitir el cierre sin autorización
            return False, ""
        
    def procesar_cierre(self):
        """Procesar cierre de caja"""
        if not hasattr(self, 'total_contado_valor'):
            show_warning_dialog(self, "Cierre de Caja", "Debe contar el efectivo antes de cerrar la caja.")
            return
        
        # Verificar si está dentro del horario del turno
        autorizacion_requerida, motivo = self.verificar_horario_turno()
        
        if autorizacion_requerida:
            # Solicitar autorización de administrador
            from ui.admin_auth_dialog import AdminAuthDialog
            dialog = AdminAuthDialog(self.pg_manager, motivo, self)
            
            if dialog.exec() != dialog.Accepted:
                # Autorización cancelada o denegada
                return
            
            # Obtener datos de autorización
            auth_data = dialog.get_autorizacion()
            if not auth_data['autorizado']:
                return
            
            # Guardar datos de autorización para el registro
            self.autorizacion = auth_data
        else:
            self.autorizacion = None
            
        diferencia = self.total_contado_valor - self.total_esperado_valor
        
        # Obtener valores para el resumen
        efectivo = float(self.efectivo_input.text() or 0)
        tarjeta = float(self.tarjeta_input.text() or 0)
        otros = float(self.otros_input.text() or 0)
        
        # Confirmar cierre
        resumen = (
            f"Total esperado: ${self.total_esperado_valor:.2f}\n\n"
            f"Efectivo: ${efectivo:.2f}\n"
            f"Tarjeta: ${tarjeta:.2f}\n"
            f"Otros: ${otros:.2f}\n"
            "─────────────────────\n"
            f"Total contado: ${self.total_contado_valor:.2f}\n"
            f"Diferencia: ${diferencia:.2f}"
        )

        if show_confirmation_dialog(
            self,
            "Confirmar Cierre",
            "Revise el resumen antes de confirmar.",
            detail=resumen,
            confirm_text="Sí, cerrar",
            cancel_text="Volver"
        ):
            try:
                # Obtener valores
                efectivo = float(self.efectivo_input.text() or 0)
                tarjeta = float(self.tarjeta_input.text() or 0)
                otros = float(self.otros_input.text() or 0)
                notas = self.notas_input.toPlainText()
                
                # Registrar cierre en la base de datos
                cierre_data = {
                    'fecha': date.today(),
                    'total_esperado': self.total_esperado_valor,
                    'total_contado': self.total_contado_valor,
                    'diferencia': diferencia,
                    'id_usuario': self.user_data['id_usuario'],
                    'efectivo': efectivo,
                    'tarjeta': tarjeta,
                    'otros': otros,
                    'notas': notas
                }
                
                # Registrar cierre en la base de datos
                # Usar el turno que ya verificamos que está abierto
                if not self.turno_abierto:
                    raise Exception("No hay turno abierto para cerrar")
                
                # Preparar notas incluyendo autorización si existe
                notas_cierre = cierre_data.get('notas', '')
                if self.autorizacion:
                    auth_info = (
                        f"\n\n--- AUTORIZACIÓN ADMINISTRADOR ---\n"
                        f"Autorizado por: {self.autorizacion['nombre_admin']}\n"
                        f"Justificación: {self.autorizacion['justificacion']}"
                    )
                    notas_cierre = (notas_cierre + auth_info) if notas_cierre else auth_info.strip()
                
                # Actualizar turno existente
                from datetime import datetime
                self.pg_manager.client.table('turnos_caja').update({
                    'fecha_cierre': datetime.now().isoformat(),
                    'total_ventas_efectivo': cierre_data['total_esperado'],
                    'monto_esperado': float(self.turno_abierto['monto_inicial']) + cierre_data['total_esperado'],
                    'monto_real_cierre': cierre_data['total_contado'],
                    'diferencia': cierre_data['diferencia'],
                    'cerrado': True,
                    'notas_apertura': (self.turno_abierto.get('notas_apertura', '') or '') + ('\n' + notas_cierre if self.turno_abierto.get('notas_apertura') else notas_cierre)
                }).eq('id_turno', self.turno_abierto['id_turno']).execute()
                
                show_success_dialog(self, "Cierre Completado", "Cierre de caja registrado exitosamente.")
                self.cerrar_solicitado.emit()
                
            except Exception as e:
                logging.error(f"Error procesando cierre: {e}")
                show_error_dialog(self, "Error", f"Error al procesar cierre: {e}")