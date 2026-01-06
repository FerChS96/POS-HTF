"""
Ventana de Nueva Venta para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem,
    QGridLayout, QSpinBox,
    QHeaderView, QSizePolicy, QPushButton,
    QDialog, QLabel, QTextEdit,
    QFrame, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QCursor, QDoubleValidator
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
import logging
import time
from datetime import datetime
import qtawesome as qta

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    InfoTile,
    SectionTitle,
    ContentPanel,
    SearchBar,
    StyledLabel,
    show_info_dialog,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)

# Importar gestores de impresión
from escpos_printer import TicketPrinter
from windows_printer_manager import TicketPrinterWindows, WindowsPrinterManager


class NuevaVentaWindow(QWidget):
    """Widget para realizar nueva venta"""
    
    venta_completada = Signal(dict)
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, turno_id=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.turno_id = turno_id  # ID del turno de caja actual
        self.codigo = ""  # Initialize 'codigo' as an empty string
        self.texto = ""   # Initialize 'texto' as an empty string
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Variables de venta
        self.carrito = []
        self.total_venta = 0.0
        
        # Timer para detectar entrada del escáner
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.setInterval(300)  # ms después de que deje de escribir
        self.scanner_timer.timeout.connect(self._on_scanner_timeout)

        # Estado para diferenciar tecleo humano vs. escáner (keyboard wedge)
        self._last_input_ts = None
        self._scan_started_ts = None
        self._scan_fast_keystrokes = 0
        self._last_text_len = 0
        self._scanner_candidate = False

        self.setup_ui()

        # Verificar turno al cargar y bloquear si no hay
        if not self.turno_id:
            self.deshabilitar_ventas()

    def _looks_like_barcode(self, text: str) -> bool:
        """Heurística: para evitar falsos positivos (ej. 'proteina'),
        tratamos como código de barras solo entradas numéricas con longitud mínima.
        """

        text = (text or "").strip()
        return len(text) >= 6 and text.isdigit()
        
    def setup_ui(self):
        """Configurar interfaz de nueva venta"""
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                       WindowsPhoneTheme.MARGIN_MEDIUM,
                                       WindowsPhoneTheme.MARGIN_MEDIUM,
                                       WindowsPhoneTheme.MARGIN_MEDIUM)
        root_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)

        productos_panel = self._build_products_panel()
        carrito_panel = self._build_cart_panel()

        root_layout.addWidget(productos_panel, 3)
        root_layout.addWidget(carrito_panel, 2)
    
    def deshabilitar_ventas(self):
        """Deshabilitar interfaz de ventas cuando no hay turno abierto"""
        show_error_dialog(
            self,
            "Turno No Disponible",
            "No hay un turno de caja abierto.\n\nNo se pueden realizar ventas sin un turno activo.\n\nPor favor, cierra sesión y vuelve a iniciar para abrir un turno."
        )
        # Deshabilitar toda la interfaz
        self.setEnabled(False)

    def _build_products_panel(self):
        """Construir panel con buscador, catálogo y total."""
        panel = ContentPanel()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)

        layout.addWidget(SectionTitle("PRODUCTOS"))

        self.search_bar = SearchBar("Buscar producto por código o nombre...")
        # Con Supabase evitamos consultas por tecla (textChanged). La búsqueda se hace solo
        # cuando el usuario presiona el botón Buscar.
        self.search_bar.search_button.clicked.connect(self.buscar_productos)

        # TextChanged: SOLO para detectar fin de escaneo (no consulta por tecla).
        self.search_bar.search_input.textChanged.connect(self._on_search_text_changed)

        # Enter: si parece escaneo -> procesar código; si no -> ejecutar búsqueda.
        self.search_bar.search_input.returnPressed.connect(self._on_search_return_pressed)
        layout.addWidget(self.search_bar)

        self.productos_table = QTableWidget()
        self.productos_table.setColumnCount(5)
        self.productos_table.setHorizontalHeaderLabels([
            "Código", "Nombre", "Precio", "Stock", "Acción"
        ])
        header = self.productos_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 80)  # Ancho de columna de acción

        self.productos_table.verticalHeader().setVisible(False)
        self.productos_table.verticalHeader().setDefaultSectionSize(55)  # Altura de fila para centrar botón
        self.productos_table.setSelectionMode(QTableWidget.NoSelection)
        self.productos_table.setFocusPolicy(Qt.NoFocus)
        self.productos_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.productos_table.setAlternatingRowColors(True)
        self.productos_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.productos_table.setStyleSheet(
            """
            QTableView::item:hover {
                background-color: rgba(30, 58, 138, 0.08);
                color: black;
            }
            QTableView::item:selected {
                background-color: rgba(30, 58, 138, 0.15);
                color: black;
            }
            """
        )

        layout.addWidget(self.productos_table, 1)

        # No cargar productos automáticamente - mostrar mensaje de búsqueda
        self.mostrar_mensaje_busqueda()

        total_tile = InfoTile("TOTAL A PAGAR", None, WindowsPhoneTheme.TILE_GREEN)
        total_tile.main_layout.insertStretch(0)
        self.total_label = total_tile.add_main_value("$0.00")
        total_tile.add_stretch()
        layout.addWidget(total_tile)

        return panel

    def mostrar_mensaje_busqueda(self):
        """Mostrar mensaje indicando que se debe buscar productos"""
        self.productos_table.setRowCount(1)
        self.productos_table.setItem(0, 0, QTableWidgetItem(""))
        self.productos_table.setItem(0, 1, QTableWidgetItem("Escriba en el campo de búsqueda para encontrar productos..."))
        self.productos_table.setItem(0, 2, QTableWidgetItem(""))
        self.productos_table.setItem(0, 3, QTableWidgetItem(""))
        # No agregar botón en la columna de acciones

    def _build_cart_panel(self):
        """Construir panel con carrito y acciones."""
        panel = ContentPanel()
        panel.setMinimumWidth(420)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL,
                                  WindowsPhoneTheme.MARGIN_SMALL)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)

        layout.addWidget(SectionTitle("CARRITO DE COMPRAS"))

        self.carrito_table = QTableWidget()
        self.carrito_table.setColumnCount(5)
        self.carrito_table.setHorizontalHeaderLabels([
            "Producto", "Precio", "Cant.", "Subtotal", "Quitar"
        ])
        header = self.carrito_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 100)  # Ancho fijo para columna de cantidad
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 56)

        self.carrito_table.verticalHeader().setVisible(False)
        self.carrito_table.verticalHeader().setDefaultSectionSize(40)  # Misma altura que tabla de productos
        self.carrito_table.setSelectionMode(QTableWidget.NoSelection)
        self.carrito_table.setFocusPolicy(Qt.NoFocus)
        self.carrito_table.setAlternatingRowColors(True)
        self.carrito_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.carrito_table.setStyleSheet(
            """
            QTableView::item:hover {
                background-color: rgba(30, 58, 138, 0.08);
                color: black;
            }
            QTableView::item:selected {
                background-color: rgba(30, 58, 138, 0.15);
            }
            """
        )

        layout.addWidget(self.carrito_table, 1)

        buttons_container = self._build_action_buttons()
        layout.addWidget(buttons_container)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)

        return panel

    def _build_action_buttons(self):
        """Crear panel con botones Tile responsivos."""
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        max_height = WindowsPhoneTheme.TILE_MIN_HEIGHT * 2 + WindowsPhoneTheme.TILE_SPACING
        container.setMaximumHeight(max_height)

        layout = QGridLayout(container)
        layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        layout.setContentsMargins(0, WindowsPhoneTheme.TILE_SPACING, 0, 0)

        btn_procesar = self._create_tile_button(
            "Procesar Venta", "fa5s.credit-card", WindowsPhoneTheme.TILE_GREEN,
            self.confirmar_venta
        )
        layout.addWidget(btn_procesar, 0, 0, 1, 2)

        btn_limpiar = self._create_tile_button(
            "Limpiar Carrito", "fa5s.trash", WindowsPhoneTheme.TILE_RED,
            self.limpiar_carrito
        )
        layout.addWidget(btn_limpiar, 1, 0)

        btn_cancelar = self._create_tile_button(
            "Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_ORANGE,
            self.confirmar_cancelar_venta
        )
        layout.addWidget(btn_cancelar, 1, 1)

        # Evitar que columnas de botones inferior cambien de tamaño relativo
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        return container

    def _create_tile_button(self, text, icon_name, color, slot):
        """Crear TileButton con política de tamaño consistente."""
        button = TileButton(text, icon_name, color)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setMinimumHeight(WindowsPhoneTheme.TILE_MIN_HEIGHT)
        button.clicked.connect(slot)
        return button

    def _create_add_button(self, producto):
        """Crear botón de agregar centrado dentro de la celda."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        
        btn = QPushButton()
        btn.setIcon(qta.icon('fa5s.plus', color='white'))
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setToolTip("Agregar al carrito")
        btn.setFixedSize(40, 40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_TEAL};
            }}
            QPushButton:pressed {{
                background-color: #1b5e20;
            }}
        """)
        
        btn.clicked.connect(lambda _, p=producto: self.agregar_al_carrito(p))
        layout.addWidget(btn, 0, Qt.AlignCenter)
        
        return container

    def _create_remove_button(self, index):
        """Crear botón de quitar con el mismo diseño que el botón de agregar"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        btn = QPushButton()
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setToolTip("Quitar del carrito")
        btn.setFixedSize(28, 28)  # Mismo tamaño que el botón de agregar
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_RED};
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_ORANGE};
            }}
        """)

        try:
            import qtawesome as qta
            btn.setIcon(qta.icon('fa5s.trash', color='white'))
            btn.setIconSize(QSize(12, 12))  # Mismo tamaño de icono
        except Exception:
            btn.setText("×")

        btn.clicked.connect(lambda _, idx=index: self.quitar_del_carrito(idx))
        layout.addWidget(btn)

        return container
        
    def cargar_productos(self):
        """Cargar productos disponibles"""
        try:
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

                btn_container = self._create_add_button(producto)
                self.productos_table.setCellWidget(row, 4, btn_container)

        except Exception as e:
            logging.error(f"Error cargando productos: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar los productos: {e}")
            
    def _on_search_text_changed(self):
        """Detecta ráfagas de entrada tipo escáner.

        Importante: aquí NO se consulta nada. Solo se arma un buffer y, si parece
        escaneo (tecleo muy rápido o pegado), se programa el procesamiento una vez
        que termina la ráfaga.
        """

        texto = self.search_bar.search_input.text().strip()

        # Reset al vaciar
        if not texto:
            self.scanner_timer.stop()
            self._last_input_ts = None
            self._scan_started_ts = None
            self._scan_fast_keystrokes = 0
            self._last_text_len = 0
            self._scanner_candidate = False
            return

        now = time.perf_counter()
        if self._last_input_ts is None:
            self._last_input_ts = now
            self._scan_started_ts = now
            self._scan_fast_keystrokes = 0
            self._last_text_len = len(texto)
            self._scanner_candidate = False
            return

        delta = now - self._last_input_ts
        prev_len = self._last_text_len
        self._last_input_ts = now
        self._last_text_len = len(texto)

        # Heurística:
        # - Escáner: caracteres muy rápidos (ej. <70ms) o salto de longitud (pegado)
        # - Humano: teclas más lentas -> no auto-agregar
        length_jump = (len(texto) - prev_len) > 1
        if delta < 0.07:
            self._scan_fast_keystrokes += 1

        scanner_like = length_jump or self._scan_fast_keystrokes >= 3
        self._scanner_candidate = scanner_like

        # Solo programar procesamiento si parece escaneo y el texto parece código
        if scanner_like and self._looks_like_barcode(texto):
            self.scanner_timer.stop()
            self.scanner_timer.start()
        else:
            # Si no es escáner, no auto-procesar
            self.scanner_timer.stop()

    def _on_scanner_timeout(self):
        """Se dispara cuando termina la ráfaga de entrada del escáner."""

        if not self._scanner_candidate:
            return

        codigo = self.search_bar.text().strip()
        if not codigo:
            return
        if not self._looks_like_barcode(codigo):
            return

        # Reset del estado para evitar doble procesamiento
        self._scanner_candidate = False
        self._scan_fast_keystrokes = 0
        self._last_input_ts = None
        self._scan_started_ts = None
        self._last_text_len = len(codigo)

        self._try_add_by_barcode(codigo, clear_on_success=True, clear_on_failure=False)

    def _on_search_return_pressed(self):
        """Enter en el campo de búsqueda.

        - Si parece código de barras (escáner): procesa el código.
        - Si es texto normal: ejecuta la búsqueda (igual que botón Buscar).
        """
        texto = self.search_bar.text().strip()
        if not texto:
            return

        # Si hay un timer pendiente por escáner, lo cancelamos y procesamos ya.
        if self.scanner_timer.isActive():
            self.scanner_timer.stop()

        # Si parece código de barras (numérico), procesarlo como escaneo.
        if self._looks_like_barcode(texto):
            self._try_add_by_barcode(texto, clear_on_success=True, clear_on_failure=False)
            return

        self.buscar_productos()
    
    def _try_add_by_barcode(self, codigo: str, *, clear_on_success: bool = True, clear_on_failure: bool = False):
        """Consulta un producto por código exacto y lo agrega al carrito (1 sola consulta)."""

        tiempo_inicio = time.perf_counter()

        try:
            producto_encontrado = self.pg_manager.get_product_by_barcode(codigo)
            if producto_encontrado:
                if producto_encontrado.get('stock_actual', 0) > 0:
                    self.agregar_al_carrito(producto_encontrado)
                    if clear_on_success:
                        self.search_bar.clear()
                    tiempo_total = (time.perf_counter() - tiempo_inicio) * 1000
                    logging.info(f"✓ Producto agregado por escáner: {producto_encontrado.get('nombre')} | Total: {tiempo_total:.1f}ms")
                    return

                show_warning_dialog(
                    self,
                    "Sin stock",
                    f"El producto {producto_encontrado.get('nombre')} no tiene stock disponible"
                )
            else:
                show_warning_dialog(
                    self,
                    "Producto no encontrado",
                    "No se encontró un producto con ese código.\n\nSi quieres buscar por nombre/código parcial, presiona Buscar o Enter."
                )

            if clear_on_failure:
                self.search_bar.clear()
            else:
                self.search_bar.search_input.selectAll()

        except Exception as e:
            logging.error(f"Error al procesar código de barras: {e}")
            show_error_dialog(
                self,
                "Error",
                f"No se pudo procesar el código de barras: {str(e)}"
            )
    
    def buscar_productos(self):
        """Buscar productos por texto"""
        texto = self.search_bar.text().strip()
        if not texto:
            self.mostrar_mensaje_busqueda()
            return
            
        try:
            productos = self.pg_manager.search_products(texto)
            self.productos_table.setRowCount(len(productos))
            
            for row, producto in enumerate(productos):
                self.productos_table.setItem(row, 0, QTableWidgetItem(producto['codigo_barras'] or f"P{producto['id_producto']:04d}"))
                self.productos_table.setItem(row, 1, QTableWidgetItem(producto['nombre']))
                
                precio = float(producto['precio_venta']) if producto['precio_venta'] is not None else 0.0
                precio_item = QTableWidgetItem(f"${precio:.2f}")
                precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.productos_table.setItem(row, 2, precio_item)
                
                stock_item = QTableWidgetItem(str(producto['stock_actual']))
                stock_item.setTextAlignment(Qt.AlignCenter)
                self.productos_table.setItem(row, 3, stock_item)
                
                btn_container = self._create_add_button(producto)
                self.productos_table.setCellWidget(row, 4, btn_container)
                
        except Exception as e:
            logging.error(f"Error buscando productos: {e}")
            show_error_dialog(self, "Error", f"No se pudo buscar productos: {e}")
            
    def agregar_al_carrito(self, producto):
        """Agregar producto al carrito"""
        if producto['stock_actual'] <= 0:
            show_warning_dialog(self, "Sin Stock", f"El producto '{producto['nombre']}' no tiene stock disponible.")
            return
        
        # Convertir precio a float para evitar problemas con Decimal
        precio = float(producto['precio_venta'])
            
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
                'codigo_interno': producto.get('codigo_interno', ''),
                'nombre': producto['nombre'],
                'precio': precio,
                'cantidad': 1,
                'subtotal': precio,
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
            cantidad_spin = QSpinBox()
            cantidad_spin.setMinimum(1)
            cantidad_spin.setMaximum(item['stock_disponible'])
            cantidad_spin.setValue(item['cantidad'])
            cantidad_spin.valueChanged.connect(lambda val, idx=row: self.cambiar_cantidad(idx, val))
            self.carrito_table.setCellWidget(row, 2, cantidad_spin)
            
            # Subtotal
            subtotal_item = QTableWidgetItem(f"${item['subtotal']:.2f}")
            subtotal_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.carrito_table.setItem(row, 3, subtotal_item)
            
            # Botón Quitar con el mismo diseño que el botón de agregar
            btn_container = self._create_remove_button(row)
            self.carrito_table.setCellWidget(row, 4, btn_container)
            
            # Convertir subtotal a float antes de sumar
            self.total_venta += float(item['subtotal'])
            
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
            
    def confirmar_cancelar_venta(self):
        """Confirmar antes de cancelar la venta"""
        # Si el carrito está vacío, cerrar directamente
        if not self.carrito:
            self.cerrar_solicitado.emit()
            return
        
        # Si hay productos en el carrito, pedir confirmación
        if show_confirmation_dialog(
            self,
            "Cancelar Venta",
            f"Hay {len(self.carrito)} producto(s) en el carrito. ¿Desea cancelar la venta?",
            detail="Se perderán todos los productos agregados.",
            confirm_text="Sí, cancelar venta",
            cancel_text="No, continuar venta"
        ):
            # Limpiar carrito y cerrar
            self.carrito.clear()
            self.actualizar_carrito()
            self.cerrar_solicitado.emit()
    
    def verificar_turno_abierto(self):
        """Verificar que haya un turno abierto consultando la base de datos"""
        try:
            # Consultar el último turno en la tabla
            response = self.pg_manager.client.table('turnos_caja').select(
                'id_turno, cerrado, fecha_apertura'
            ).order('fecha_apertura', desc=True).limit(1).execute()
            
            if response.data and len(response.data) > 0:
                ultimo_turno = response.data[0]
                # Verificar si está abierto (cerrado = false)
                if not ultimo_turno.get('cerrado', True):
                    # Actualizar turno_id con el turno actualmente abierto
                    self.turno_id = ultimo_turno['id_turno']
                    return True
            
            # No hay turno abierto
            return False
            
        except Exception as e:
            logging.error(f"Error verificando turno abierto: {e}")
            return False
    
    def mostrar_dialogo_abrir_turno(self):
        """Mostrar diálogo para que el usuario abra un turno"""
        show_warning_dialog(
            self,
            "Turno Cerrado",
            "No hay un turno de caja abierto.",
            "Para realizar ventas, debe abrir un turno primero. Por favor, cierre sesión y vuelva a iniciar para abrir un turno automáticamente."
        )
    
    def limpiar_carrito(self):
        """Limpiar todo el carrito"""
        if not self.carrito:
            return

        if show_confirmation_dialog(
            self,
            "Confirmar",
            "¿Está seguro de que desea limpiar el carrito?",
            confirm_text="Sí, limpiar",
            cancel_text="No"
        ):
            self.carrito.clear()
            self.actualizar_carrito()
            
    def confirmar_venta(self):
        """Mostrar ventana de confirmación antes de procesar la venta"""
        # Verificar que haya productos en el carrito
        if not self.carrito:
            show_warning_dialog(self, "Carrito Vacío", "Agregue productos al carrito antes de procesar la venta.")
            return
        
        # Verificar que haya un turno REALMENTE abierto consultando la BD
        if not self.verificar_turno_abierto():
            self.mostrar_dialogo_abrir_turno()
            return
        
        # Crear diálogo de confirmación
        dialog = ConfirmacionVentaDialog(self.carrito, self.total_venta, self)
        if dialog.exec() == QDialog.Accepted:
            self.procesar_venta()
            
    def procesar_venta(self):
        """Procesar la venta"""
        try:
            # Doble verificación: asegurarse que el turno sigue abierto
            if not self.verificar_turno_abierto():
                self.mostrar_dialogo_abrir_turno()
                return
            
            # Crear venta en la base de datos
            venta_data = {
                'total': self.total_venta,
                'metodo_pago': 'efectivo',
                'tipo_venta': 'producto',
                'productos': self.carrito,
                'id_usuario': self.user_data['id_usuario'],
                'id_turno': self.turno_id  # Agregar ID del turno
            }
            
            venta_id = self.pg_manager.create_sale(venta_data)
            
            if venta_id:
                # Mostrar mensaje de éxito
                show_success_dialog(
                    self, 
                    "Venta Completada", 
                    f"La venta se procesó exitosamente.\nID de venta: {venta_id}",
                    f"Total: ${self.total_venta:.2f}"
                )
                
                # Generar y mostrar ticket
                self.mostrar_ticket(venta_id)
                
                # Emitir señal de venta completada
                self.venta_completada.emit({
                    'id_venta': venta_id,
                    'total': self.total_venta,
                    'productos': len(self.carrito)
                })
                
                # Limpiar carrito
                self.carrito.clear()
                self.actualizar_carrito()
                
                # Recargar productos para actualizar stock
                self.cargar_productos()
                
                logging.info(f"Venta {venta_id} procesada exitosamente: ${self.total_venta:.2f}")
            else:
                show_error_dialog(self, "Error", "No se pudo procesar la venta.")
            
        except Exception as e:
            logging.error(f"Error procesando venta: {e}")
            show_error_dialog(
                self,
                "Error",
                f"No se pudo procesar la venta: {str(e)}"
            )
            
    def mostrar_ticket(self, venta_id):
        """Mostrar ticket de venta"""
        dialog = TicketVentaDialog(
            venta_id=venta_id,
            carrito=self.carrito,
            total=self.total_venta,
            usuario=self.user_data.get('nombre_completo', 'Usuario'),
            parent=self
        )
        dialog.exec()


class ConfirmacionVentaDialog(QDialog):
    """Diálogo de confirmación de venta"""
    
    def __init__(self, carrito, total, parent=None):
        super().__init__(parent)
        self.carrito = carrito
        self.total = total
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        self.setWindowTitle("Confirmar Venta")
        
        # Obtener geometría de la pantalla
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().availableGeometry()
        
        # Usar el ancho mínimo deseado y el alto de la pantalla
        dialog_width = 620
        dialog_height = screen.height()
        
        self.setMinimumWidth(dialog_width)
        self.setFixedHeight(dialog_height)
        
        # Centrar el diálogo horizontalmente
        x = (screen.width() - dialog_width) // 2
        y = screen.y()
        self.move(x, y)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Título
        title = QLabel("CONFIRMAR VENTA")
        title.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #000000; padding: 10px;")
        layout.addWidget(title)
        
        # Resumen de productos
        resumen_label = QLabel("Resumen de la Venta:")
        resumen_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 12, QFont.Bold))
        layout.addWidget(resumen_label)
        
        # Tabla de resumen
        tabla = QTableWidget()
        tabla.setColumnCount(4)
        tabla.setHorizontalHeaderLabels(["Producto", "Precio", "Cantidad", "Subtotal"])
        tabla.setRowCount(len(self.carrito))
        
        header = tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        tabla.setSelectionMode(QTableWidget.NoSelection)
        
        for row, item in enumerate(self.carrito):
            tabla.setItem(row, 0, QTableWidgetItem(item['nombre']))
            
            precio_item = QTableWidgetItem(f"${item['precio']:.2f}")
            precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tabla.setItem(row, 1, precio_item)
            
            cant_item = QTableWidgetItem(str(item['cantidad']))
            cant_item.setTextAlignment(Qt.AlignCenter)
            tabla.setItem(row, 2, cant_item)
            
            subtotal_item = QTableWidgetItem(f"${item['subtotal']:.2f}")
            subtotal_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tabla.setItem(row, 3, subtotal_item)
            
        layout.addWidget(tabla)
        
        # Total
        total_frame = QFrame()
        total_frame.setStyleSheet(f"background-color: {WindowsPhoneTheme.TILE_GREEN}; border-radius: 4px; padding: 15px;")
        total_layout = QVBoxLayout(total_frame)
        
        total_title = QLabel("TOTAL A PAGAR")
        total_title.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 12, QFont.Bold))
        total_title.setStyleSheet("color: white;")
        total_title.setAlignment(Qt.AlignCenter)
        
        total_value = QLabel(f"${self.total:.2f}")
        total_value.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 32, QFont.Bold))
        total_value.setStyleSheet("color: white;")
        total_value.setAlignment(Qt.AlignCenter)
        
        total_layout.addWidget(total_title)
        total_layout.addWidget(total_value)
        layout.addWidget(total_frame)
        
        # Sección de efectivo recibido (opcional)
        efectivo_frame = QFrame()
        efectivo_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 4px;")
        efectivo_layout = QVBoxLayout(efectivo_frame)
        efectivo_layout.setContentsMargins(20, 15, 20, 15)
        efectivo_layout.setSpacing(12)
        
        # Título de la sección
        efectivo_titulo = QLabel("Cálculo de Cambio (Opcional)")
        efectivo_titulo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 12, QFont.Bold))
        efectivo_titulo.setStyleSheet("color: #333;")
        efectivo_layout.addWidget(efectivo_titulo)
        
        # Grid para input de efectivo
        input_grid = QGridLayout()
        input_grid.setSpacing(10)
        
        efectivo_label = QLabel("Efectivo recibido:")
        efectivo_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 11))
        efectivo_label.setStyleSheet("color: #555;")
        input_grid.addWidget(efectivo_label, 0, 0, Qt.AlignRight | Qt.AlignVCenter)
        
        input_container = QHBoxLayout()
        input_container.setSpacing(5)
        
        dollar_label = QLabel("$")
        dollar_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14, QFont.Bold))
        dollar_label.setStyleSheet("color: #333;")
        input_container.addWidget(dollar_label)
        
        self.efectivo_input = QLineEdit()
        self.efectivo_input.setPlaceholderText("0.00")
        self.efectivo_input.setMinimumHeight(45)
        self.efectivo_input.setMinimumWidth(150)
        self.efectivo_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 14))
        self.efectivo_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #cccccc;
                border-radius: 4px;
                padding: 8px 12px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #0078d7;
            }
        """)
        
        # Validador para solo números con decimales
        validator = QDoubleValidator(0.0, 999999.99, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.efectivo_input.setValidator(validator)
        self.efectivo_input.textChanged.connect(self.calcular_cambio)
        
        input_container.addWidget(self.efectivo_input)
        input_container.addStretch()
        
        input_widget = QWidget()
        input_widget.setLayout(input_container)
        input_grid.addWidget(input_widget, 0, 1)
        
        efectivo_layout.addLayout(input_grid)
        
        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #ddd; max-height: 1px;")
        efectivo_layout.addWidget(separator)
        
        # Label de cambio
        self.cambio_label = QLabel("Cambio: $0.00")
        self.cambio_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 16, QFont.Bold))
        self.cambio_label.setStyleSheet("color: #333; padding: 5px 0;")
        self.cambio_label.setAlignment(Qt.AlignRight)
        efectivo_layout.addWidget(self.cambio_label)
        
        layout.addWidget(efectivo_frame)
        
        # Método de pago
        pago_label = QLabel("Método de Pago: EFECTIVO")
        pago_label.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 11))
        pago_label.setAlignment(Qt.AlignCenter)
        pago_label.setStyleSheet("color: #666666; padding: 10px;")
        layout.addWidget(pago_label)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setMinimumHeight(50)
        btn_cancelar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_RED};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_ORANGE};
            }}
        """)
        btn_cancelar.clicked.connect(self.reject)
        
        btn_confirmar = QPushButton("Confirmar Venta")
        btn_confirmar.setMinimumHeight(50)
        btn_confirmar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_TEAL};
            }}
        """)
        btn_confirmar.clicked.connect(self.accept)
        
        buttons_layout.addWidget(btn_cancelar)
        buttons_layout.addWidget(btn_confirmar)
        
        layout.addLayout(buttons_layout)
    
    def calcular_cambio(self):
        """Calcular y mostrar el cambio"""
        try:
            texto = self.efectivo_input.text()
            if not texto:
                self.cambio_label.setText("Cambio: $0.00")
                self.cambio_label.setStyleSheet("color: #333; padding: 10px 0;")
                return
            
            efectivo = float(texto.replace(',', '.'))
            cambio = efectivo - self.total
            
            if cambio < 0:
                self.cambio_label.setText(f"Falta: ${abs(cambio):.2f}")
                self.cambio_label.setStyleSheet("color: red; padding: 10px 0; font-weight: bold;")
            else:
                self.cambio_label.setText(f"Cambio: ${cambio:.2f}")
                if cambio > 0:
                    self.cambio_label.setStyleSheet("color: green; padding: 10px 0; font-weight: bold;")
                else:
                    self.cambio_label.setStyleSheet("color: #333; padding: 10px 0; font-weight: bold;")
        except (ValueError, AttributeError):
            self.cambio_label.setText("Cambio: $0.00")
            self.cambio_label.setStyleSheet("color: #333; padding: 10px 0;")


class TicketVentaDialog(QDialog):
    """Diálogo para mostrar el ticket de venta"""
    
    def __init__(self, venta_id, carrito, total, usuario, parent=None):
        super().__init__(parent)
        self.venta_id = venta_id
        self.carrito = carrito
        self.total = total
        self.usuario = usuario
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz del ticket"""
        self.setWindowTitle("Ticket de Venta")
        self.setMinimumWidth(400)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Área de texto para el ticket
        self.ticket_text = QTextEdit()
        self.ticket_text.setReadOnly(True)
        self.ticket_text.setFont(QFont("Courier New", 10))
        
        # Generar contenido del ticket
        ticket_content = self.generar_ticket()
        self.ticket_text.setPlainText(ticket_content)
        
        layout.addWidget(self.ticket_text)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_imprimir_termica = QPushButton("Imprimir Térmica")
        btn_imprimir_termica.setMinimumHeight(50)
        btn_imprimir_termica.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_TEAL};
            }}
        """)
        btn_imprimir_termica.clicked.connect(self.imprimir_ticket_escpos)
        
        btn_imprimir_sistema = QPushButton("Imprimir Sistema")
        btn_imprimir_sistema.setMinimumHeight(50)
        btn_imprimir_sistema.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_TEAL};
            }}
        """)
        btn_imprimir_sistema.clicked.connect(self.imprimir_ticket)
        
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setMinimumHeight(50)
        btn_cerrar.setStyleSheet(f"""
            QPushButton {{
                background-color: {WindowsPhoneTheme.TILE_ORANGE};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {WindowsPhoneTheme.TILE_RED};
            }}
        """)
        btn_cerrar.clicked.connect(self.accept)
        
        buttons_layout.addWidget(btn_imprimir_termica)
        buttons_layout.addWidget(btn_imprimir_sistema)
        buttons_layout.addWidget(btn_cerrar)
        
        layout.addLayout(buttons_layout)
        
    def generar_ticket(self):
        """Generar el contenido del ticket"""
        fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        ticket = "=" * 42 + "\n"
        ticket += "           HTF GIMNASIO\n"
        ticket += "         PUNTO DE VENTA\n"
        ticket += "=" * 42 + "\n\n"
        
        ticket += f"Ticket No.: {self.venta_id:06d}\n"
        ticket += f"Fecha: {fecha_hora}\n"
        ticket += f"Cajero: {self.usuario}\n"
        ticket += "-" * 42 + "\n\n"
        
        ticket += "PRODUCTOS:\n"
        ticket += "-" * 42 + "\n"
        
        for item in self.carrito:
            nombre = item['nombre'][:28]  # Limitar nombre
            ticket += f"{nombre}\n"
            ticket += f"  {item['cantidad']} x ${item['precio']:.2f}"
            ticket += f"{' ' * (30 - len(f'{item['cantidad']} x ${item['precio']:.2f}'))}"
            ticket += f"${item['subtotal']:.2f}\n"
            
        ticket += "-" * 42 + "\n"
        ticket += f"{'TOTAL:' + ' ' * 28}${self.total:.2f}\n"
        ticket += "=" * 42 + "\n\n"
        
        ticket += "      PAGO EN EFECTIVO\n"
        ticket += "-" * 42 + "\n\n"
        
        ticket += "       ¡Gracias por su compra!\n"
        ticket += "         Vuelva pronto\n"
        ticket += "=" * 42 + "\n"
        
        return ticket
        
    def imprimir_ticket(self):
        """Imprimir el ticket usando impresora del sistema"""
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        
        if dialog.exec() == QPrintDialog.Accepted:
            self.ticket_text.document().print(printer)
            show_success_dialog(self, "Éxito", "Ticket impreso correctamente.")
    
    def imprimir_ticket_escpos(self):
        """Imprimir el ticket en impresora térmica o Windows"""
        try:
            # Preparar datos del ticket
            productos_formateados = []
            for item in self.carrito:
                productos_formateados.append({
                    'nombre': item['nombre'],
                    'cantidad': item['cantidad'],
                    'precio': item['precio'],
                    'subtotal': item['subtotal']
                })
            
            datos_ticket = {
                'tienda': 'HTF GIMNASIO',
                'subtitulo': 'PUNTO DE VENTA',
                'numero_ticket': self.venta_id,
                'fecha_hora': datetime.now().strftime("%d/%m/%Y %H:%M"),
                'cajero': self.usuario,
                'productos': productos_formateados,
                'total': self.total,
                'metodo_pago': 'EFECTIVO',
                'abrir_caja': True,
                'cortar': True
            }
            
            # OPCIÓN 1: Intentar con Windows Generic/Text Only
            logging.info("Intentando impresión con Windows Generic/Text Only...")
            nombre_impresora = WindowsPrinterManager.obtener_impresora_por_tipo("Generic")
            
            if nombre_impresora:
                printer_windows = TicketPrinterWindows(nombre_impresora)
                if printer_windows.conectar():
                    if printer_windows.imprimir_ticket(datos_ticket):
                        show_success_dialog(
                            self,
                            "Éxito",
                            f"Ticket impreso en: {nombre_impresora}"
                        )
                        printer_windows.desconectar()
                        return
                    printer_windows.desconectar()
            
            # OPCIÓN 2: Intentar con impresora ESC/POS serial
            logging.info("Intentando impresión ESC/POS...")
            puerto = "COM3"
            
            printer_escpos = TicketPrinter(puerto)
            
            if printer_escpos.conectar():
                if printer_escpos.imprimir_ticket(datos_ticket):
                    show_success_dialog(
                        self,
                        "Éxito",
                        "Ticket impreso en la impresora térmica.\n"
                        "Caja registradora abierta."
                    )
                    printer_escpos.desconectar()
                    return
                printer_escpos.desconectar()
            
            # Si llegamos aquí, ambas fallaron
            show_error_dialog(
                self,
                "Error de Impresión",
                "No se pudo imprimir el ticket.\n\n"
                "Verifica que:\n"
                "- La impresora esté conectada\n"
                "- Los drivers estén instalados\n"
                "- Intenta reconectar la impresora\n\n"
                "Alternativa: Usa 'Imprimir Sistema'"
            )
            
        except Exception as e:
            logging.error(f"Error en impresión: {e}")
            show_error_dialog(
                self,
                "Error",
                f"Error en impresión:\n{str(e)}"
            )