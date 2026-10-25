"""
Formularios de Movimientos de Inventario para HTF POS
Registro de entradas y salidas
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLineEdit, QTextEdit,
    QLabel, QComboBox, QDateEdit, QScrollArea,
    QFrame, QSizePolicy, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QDate, QEvent, QTimer
from PySide6.QtGui import QFont
import logging
import re
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    create_page_layout,
    ContentPanel,
    StyledLabel,
    SearchBar,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
    TouchNumericInput,
    show_success_dialog,
    aplicar_estilo_fecha
)
from database.postgres_manager import PostgresManager
from database.permisos import INVENTARIO_ACTUALIZAR
from utils.detector_escaner import DetectorEscaner

# Resultados que se muestran al buscar por nombre; más no caben ni sirven.
MAX_RESULTADOS = 30


class MovimientoInventarioWindow(QWidget):
    """Formulario para registrar entrada o salida de inventario"""
    
    cerrar_solicitado = Signal()
    movimiento_registrado = Signal(dict)
    
    def __init__(self, tipo_movimiento, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.tipo_movimiento = tipo_movimiento  # "entrada" o "salida"
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.producto_seleccionado = None
        
        # El escáner busca solo; a mano se busca con el botón o con Enter.
        # El timer cubre los escáneres que no mandan Enter al terminar.
        self.detector = DetectorEscaner()
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.setInterval(150)
        self.scanner_timer.timeout.connect(self._fin_de_rafaga)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Título según el tipo
        titulo = "REGISTRAR ENTRADA" if self.tipo_movimiento == "entrada" else "REGISTRAR SALIDA"
        color = WindowsPhoneTheme.TILE_GREEN if self.tipo_movimiento == "entrada" else WindowsPhoneTheme.TILE_RED
        
        # Contenedor principal
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_SMALL,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_SMALL
        )
        main_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # El título viene del TopBar, no necesitamos duplicarlo aquí
        # title_label = StyledLabel(titulo, bold=True, size=WindowsPhoneTheme.FONT_SIZE_TITLE)
        # title_label.setStyleSheet(f"color: {color}; padding: 10px 0;")
        # main_layout.addWidget(title_label)
        
        # Scroll Area para el formulario
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Widget de contenido del scroll
        scroll_content = QWidget()
        form_layout = QVBoxLayout(scroll_content)
        form_layout.setContentsMargins(0, 0, 10, 0)
        form_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Panel del formulario
        form_panel = ContentPanel()
        panel_layout = QVBoxLayout(form_panel)
        panel_layout.setContentsMargins(
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_SMALL,
            WindowsPhoneTheme.MARGIN_MEDIUM,
            WindowsPhoneTheme.MARGIN_SMALL
        )
        panel_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Búsqueda de producto
        search_label = StyledLabel("Buscar Producto", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(search_label)
        
        self.search_bar = SearchBar("Nombre o código, o escanea el producto...")
        self.search_bar.search_input.installEventFilter(self)
        self.search_bar.search_button.clicked.connect(self.buscar_manual)
        panel_layout.addWidget(self.search_bar)

        # Avisos de la búsqueda en línea, sin ventanas que interrumpan
        self.busqueda_aviso_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        self.busqueda_aviso_label.setWordWrap(True)
        self.busqueda_aviso_label.setStyleSheet(f"color: {WindowsPhoneTheme.TILE_RED}; padding: 4px 0;")
        self.busqueda_aviso_label.hide()
        panel_layout.addWidget(self.busqueda_aviso_label)

        # Coincidencias por nombre: se toca la correcta
        self.resultados_list = QListWidget()
        self.resultados_list.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.resultados_list.setMinimumHeight(220)
        self.resultados_list.setStyleSheet("QListWidget::item { padding: 10px; }")
        self.resultados_list.itemClicked.connect(self._elegir_resultado)
        self.resultados_list.hide()
        panel_layout.addWidget(self.resultados_list)

        # Información del producto encontrado
        self.producto_info_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        self.producto_info_label.setWordWrap(True)
        self.producto_info_label.setStyleSheet(f"color: {WindowsPhoneTheme.PRIMARY_BLUE}; padding: 10px; background-color: {WindowsPhoneTheme.BG_LIGHT}; border-radius: 4px;")
        self.producto_info_label.hide()
        panel_layout.addWidget(self.producto_info_label)
        
        # Cantidad
        cantidad_label = StyledLabel("Cantidad *", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(cantidad_label)
        
        self.cantidad_spin = TouchNumericInput(
            minimum=1,
            maximum=9999,
            default_value=1
        )
        panel_layout.addWidget(self.cantidad_spin)
        
        # Tipo de movimiento (solo para entradas)
        if self.tipo_movimiento == "entrada":
            tipo_label = StyledLabel("Tipo de Entrada *", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
            panel_layout.addWidget(tipo_label)
            
            self.tipo_combo = QComboBox()
            self.tipo_combo.addItems([
                "Compra",
                "Devolución",
                "Ajuste de inventario",
                "Donación",
                "Otro"
            ])
            self.tipo_combo.setMinimumHeight(46)
            self.tipo_combo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
            panel_layout.addWidget(self.tipo_combo)
        else:
            # Motivo de salida
            motivo_label = StyledLabel("Motivo de Salida *", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
            panel_layout.addWidget(motivo_label)
            
            self.motivo_combo = QComboBox()
            self.motivo_combo.addItems([
                "Venta",
                "Merma",
                "Vencimiento",
                "Donación",
                "Ajuste de inventario",
                "Otro"
            ])
            self.motivo_combo.setMinimumHeight(46)
            self.motivo_combo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
            panel_layout.addWidget(self.motivo_combo)
        
        # Fecha
        fecha_label = StyledLabel("Fecha", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(fecha_label)
        
        self.fecha_input = QDateEdit()
        self.fecha_input.setDate(QDate.currentDate())
        self.fecha_input.setCalendarPopup(True)
        aplicar_estilo_fecha(self.fecha_input)
        self.fecha_input.setMinimumHeight(46)
        panel_layout.addWidget(self.fecha_input)
        
        # Observaciones
        obs_label = StyledLabel("Observaciones", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(obs_label)
        
        self.observaciones_input = QTextEdit()
        self.observaciones_input.setPlaceholderText("Notas adicionales sobre el movimiento (opcional)")
        self.observaciones_input.setMaximumHeight(80)
        self.observaciones_input.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        panel_layout.addWidget(self.observaciones_input)
        
        # Agregar panel al layout del scroll
        form_layout.addWidget(form_panel)
        form_layout.addStretch()
        
        # Configurar scroll
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # Botones de acción (fuera del scroll)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_guardar = TileButton(
            "Registrar " + ("Entrada" if self.tipo_movimiento == "entrada" else "Salida"),
            "fa5s.check",
            WindowsPhoneTheme.TILE_GREEN  # Siempre verde
        )
        btn_guardar.clicked.connect(self.registrar_movimiento)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_guardar)
        buttons_layout.addWidget(btn_cancelar)
        
        main_layout.addLayout(buttons_layout)
        layout.addWidget(main_container)
    
    def eventFilter(self, obj, event):
        """Mide cada tecla del campo de búsqueda para distinguir escáner de captura a mano"""
        if obj == self.search_bar.search_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.scanner_timer.stop()
                if self.detector.es_lectura():
                    logging.info("[SCANNER] Enter tras lectura del escáner - buscando código")
                    self.buscar_lectura()
                else:
                    self.buscar_manual()
                return True  # Evento manejado

            texto = event.text()
            if len(texto) == 1 and texto.isprintable():
                self.detector.tecla(time.monotonic() * 1000, len(self.search_bar.search_input.text()))
                self.scanner_timer.start()
            else:
                # Borrar o mover el cursor es captura a mano
                self.detector.reiniciar()

        return super().eventFilter(obj, event)

    def _fin_de_rafaga(self):
        """Pasó un momento sin teclas: si fue el escáner, buscar sin esperar Enter"""
        if self.detector.es_lectura():
            logging.info("[SCANNER] Lectura del escáner sin Enter - buscando código")
            self.buscar_lectura()

    def buscar_lectura(self):
        """Buscar el código exacto que trajo el escáner"""
        codigo = self.detector.codigo_leido(self.search_bar.search_input.text())
        self.detector.reiniciar()
        self.search_bar.search_input.setText(codigo)
        if not codigo:
            return
        try:
            producto = self._buscar_por_codigo(codigo)
        except Exception as e:
            self._error_busqueda(e)
            return
        if producto:
            self._seleccionar(producto)
        else:
            self._mostrar_aviso(f"No hay ningún producto con el código '{codigo}'")

    def buscar_manual(self):
        """Buscar lo que escribió la persona: primero código exacto, luego nombre o parte del código"""
        self.detector.reiniciar()
        texto = self.search_bar.search_input.text().strip()
        if not texto:
            self._mostrar_aviso("Escribe el nombre o el código del producto")
            return
        try:
            producto = self._buscar_por_codigo(texto)
            if producto:
                self._seleccionar(producto)
                return

            # Comas y paréntesis rompen el filtro or() de PostgREST
            patron = re.sub(r"[,()]", " ", texto).strip()
            resultados = self.pg_manager.search_products(patron) if patron else []
        except Exception as e:
            self._error_busqueda(e)
            return

        if not resultados:
            self._mostrar_aviso(f"No se encontró ningún producto con '{texto}'")
        elif len(resultados) == 1:
            self._elegir_codigo(resultados[0]['codigo_interno'])
        else:
            self._mostrar_resultados(resultados)

    def _buscar_por_codigo(self, codigo):
        """Producto con stock por código interno o, si no, por código de barras"""
        producto = self.pg_manager.get_product_with_stock(codigo)
        if not producto:
            prod = self.pg_manager.get_product_by_barcode(codigo)
            if prod:
                producto = self.pg_manager.get_product_with_stock(prod.get('codigo_interno'))
        return producto

    def _mostrar_resultados(self, resultados):
        self.producto_seleccionado = None
        self.producto_info_label.hide()
        self.resultados_list.clear()
        for prod in sorted(resultados, key=lambda p: (p.get('nombre') or '').upper())[:MAX_RESULTADOS]:
            stock = prod.get('stock_actual') or 0
            item = QListWidgetItem(f"{prod.get('nombre')}   ·   código {prod.get('codigo_interno')}   ·   stock {stock}")
            item.setData(Qt.UserRole, prod.get('codigo_interno'))
            self.resultados_list.addItem(item)
        extra = len(resultados) - MAX_RESULTADOS
        aviso = f"{len(resultados)} productos coinciden: toca el correcto"
        if extra > 0:
            aviso += f" (se muestran {MAX_RESULTADOS}; escribe más para afinar)"
        self._mostrar_aviso(aviso, color=WindowsPhoneTheme.PRIMARY_BLUE)
        self.resultados_list.show()

    def _elegir_resultado(self, item):
        self._elegir_codigo(item.data(Qt.UserRole))

    def _elegir_codigo(self, codigo_interno):
        try:
            producto = self.pg_manager.get_product_with_stock(codigo_interno)
        except Exception as e:
            self._error_busqueda(e)
            return
        if producto:
            self._seleccionar(producto)
        else:
            self._mostrar_aviso(f"El producto '{codigo_interno}' no tiene registro de inventario")

    def _seleccionar(self, producto):
        """Deja el producto listo para capturar la cantidad"""
        self.producto_seleccionado = producto
        self.resultados_list.hide()
        self.busqueda_aviso_label.hide()

        stock_actual = producto.get('stock_actual') or 0
        self.producto_info_label.setText(
            f"✓ Producto encontrado\n"
            f"Código: {producto['codigo_interno']}\n"
            f"Nombre: {producto['nombre']}\n"
            f"Stock actual: {stock_actual} unidades"
        )
        self.producto_info_label.show()
        self.cantidad_spin.setFocus()
        logging.info(f"Producto encontrado: {producto['codigo_interno']} - {producto['nombre']}")

    def _mostrar_aviso(self, texto, color=None):
        self.busqueda_aviso_label.setStyleSheet(
            f"color: {color or WindowsPhoneTheme.TILE_RED}; padding: 4px 0;"
        )
        self.busqueda_aviso_label.setText(texto)
        self.busqueda_aviso_label.show()
        if color is None:
            self.producto_seleccionado = None
            self.producto_info_label.hide()
            self.resultados_list.hide()

    def _error_busqueda(self, e):
        logging.error(f"Error buscando producto: {e}")
        show_error_dialog(
            self,
            "Error de búsqueda",
            "No se pudo buscar el producto",
            detail=str(e)
        )

    def _id_usuario_actual(self):
        """Id de quien opera la ventana, o None si no se conoce."""
        user_data = getattr(self, 'user_data', None)
        if isinstance(user_data, dict):
            return user_data.get('id_usuario')
        return None

    def tiene_permiso_inventario(self):
        """
        Si quien opera puede registrar entradas y salidas de inventario.

        'inventario.actualizar' SÍ es otorgable: un administrador puede
        concedérselo a una recepcionista concreta. Ante cualquier duda (sin
        user_data, sin id_usuario o con un error al consultar) se responde que
        NO, para fallar cerrado.
        """
        id_usuario = self._id_usuario_actual()

        if not id_usuario:
            logging.warning(
                "[SEGURIDAD] Movimiento de inventario sin datos de usuario: se deniega"
            )
            return False

        try:
            return bool(self.pg_manager.tiene_permiso(id_usuario, INVENTARIO_ACTUALIZAR))
        except Exception as e:
            logging.error(f"[SEGURIDAD] No se pudo verificar '{INVENTARIO_ACTUALIZAR}': {e}")
            return False

    def registrar_movimiento(self):
        """Registrar el movimiento de inventario"""
        # Control de acceso ANTES de tocar nada: sin permiso no hay movimiento.
        if not self.tiene_permiso_inventario():
            logging.warning(
                f"[SEGURIDAD] Movimiento de inventario rechazado: usuario "
                f"{self._id_usuario_actual()} sin permiso '{INVENTARIO_ACTUALIZAR}'"
            )
            show_error_dialog(
                self,
                "Permiso requerido",
                "No tienes permiso para registrar movimientos de inventario",
                detail=(
                    "Se necesita el permiso 'Registrar entradas y salidas de "
                    "inventario'. Solicítalo a un administrador."
                )
            )
            return

        if not self.producto_seleccionado:
            show_warning_dialog(
                self,
                "Producto requerido",
                "Primero debes buscar y seleccionar un producto"
            )
            self.search_bar.search_input.setFocus()
            return
        
        cantidad = self.cantidad_spin.value()
        if cantidad <= 0:
            show_warning_dialog(
                self,
                "Cantidad inválida",
                "La cantidad debe ser mayor a 0"
            )
            return
        
        # Validar stock suficiente para salidas
        if self.tipo_movimiento == "salida":
            stock_actual = self.producto_seleccionado['stock_actual'] if self.producto_seleccionado['stock_actual'] else 0
            if cantidad > stock_actual:
                show_warning_dialog(
                    self,
                    "Stock insuficiente",
                    f"No hay suficiente stock disponible\n\nStock actual: {stock_actual}\nCantidad solicitada: {cantidad}"
                )
                return
        
        try:
            # Preparar datos del movimiento
            motivo_texto = self.tipo_combo.currentText() if self.tipo_movimiento == "entrada" else self.motivo_combo.currentText()
            fecha = self.fecha_input.date().toPython().strftime("%Y-%m-%d")
            observaciones = self.observaciones_input.toPlainText().strip() or None
            
            # Mapear el motivo seleccionado al tipo de movimiento del enum
            if self.tipo_movimiento == "entrada":
                if motivo_texto in ["Devolución", "Devolucion"]:
                    tipo_movimiento_db = "devolucion"
                elif motivo_texto == "Ajuste de inventario":
                    tipo_movimiento_db = "ajuste"
                else:
                    tipo_movimiento_db = "entrada"
            else:  # salida
                if motivo_texto == "Venta":
                    tipo_movimiento_db = "venta"
                elif motivo_texto == "Merma" or motivo_texto == "Vencimiento":
                    tipo_movimiento_db = "merma"
                elif motivo_texto == "Ajuste de inventario":
                    tipo_movimiento_db = "ajuste"
                else:
                    tipo_movimiento_db = "merma"  # Por defecto para salidas
            
            # Obtener stock actual del producto seleccionado
            stock_anterior = self.producto_seleccionado.get('stock_actual', 0)
            
            # Calcular nuevo stock
            if self.tipo_movimiento == "entrada":
                nuevo_stock = stock_anterior + cantidad
                fecha_entrada = datetime.now().isoformat()
                fecha_salida = None
            else:
                nuevo_stock = stock_anterior - cantidad
                fecha_entrada = None
                fecha_salida = datetime.now().isoformat()
            
            # TODO: Estas dos operaciones (actualizar_stock y luego
            # registrar_movimiento_inventario) NO son atómicas. Si la segunda
            # falla o se cae la red entre ambas, el stock ya quedó modificado
            # en la base pero no existe ningún movimiento que lo respalde: el
            # inventario queda descuadrado y sin rastro de quién lo movió ni
            # por qué. El arreglo correcto es una función RPC transaccional en
            # Supabase que haga ambas cosas en una sola transacción. Queda
            # fuera del alcance de este cambio (control de acceso).

            # Actualizar stock en inventario
            exito = self.pg_manager.actualizar_stock(
                self.producto_seleccionado['codigo_interno'],
                self.producto_seleccionado['tipo_producto'],
                nuevo_stock,
                fecha_entrada=fecha_entrada,
                fecha_salida=fecha_salida,
                id_usuario=self.user_data.get('id_usuario') if self.user_data else None
            )
            
            if not exito:
                show_error_dialog(
                    self,
                    "Error",
                    "No se pudo actualizar el stock",
                    detail="Hubo un error al actualizar el stock en el inventario"
                )
                return
            
            # Registrar el movimiento
            movimiento_data = {
                'codigo_interno': self.producto_seleccionado['codigo_interno'],
                'tipo_producto': self.producto_seleccionado['tipo_producto'],
                'tipo_movimiento': 'entrada' if self.tipo_movimiento == "entrada" else tipo_movimiento_db,
                'cantidad': cantidad if self.tipo_movimiento == "entrada" else -cantidad,
                'stock_anterior': stock_anterior,
                'stock_nuevo': nuevo_stock,
                'motivo': motivo_texto if self.tipo_movimiento != "entrada" else None,
                'id_usuario': self.user_data.get('id_usuario') if self.user_data else None
            }
            
            exito = self.pg_manager.registrar_movimiento_inventario(movimiento_data)
            
            if not exito:
                show_error_dialog(
                    self,
                    "Error",
                    "No se pudo registrar el movimiento",
                    detail="El movimiento de inventario no se pudo registrar"
                )
                return
            
            show_success_dialog(
                self,
                "Movimiento registrado",
                f"El movimiento de inventario ha sido registrado exitosamente",
                detail=(
                    f"Producto: {self.producto_seleccionado['nombre']}\n"
                    f"Cantidad: {cantidad}\n"
                    f"Stock nuevo: {nuevo_stock} unidades"
                )
            )
            
            # Emitir señal con información del movimiento
            self.movimiento_registrado.emit({
                'tipo': self.tipo_movimiento,
                'producto': self.producto_seleccionado['nombre'],
                'cantidad': cantidad,
                'stock_nuevo': nuevo_stock
            })
            
            logging.info(
                f"Movimiento registrado: {self.tipo_movimiento} - "
                f"{self.producto_seleccionado['codigo_interno']} - Cantidad: {cantidad}"
            )
            
            # Limpiar formulario
            self.limpiar_formulario()
            
        except Exception as e:
            logging.error(f"Error registrando movimiento: {e}")
            show_error_dialog(
                self,
                "Error al registrar",
                "No se pudo registrar el movimiento de inventario",
                detail=str(e)
            )
    
    def limpiar_formulario(self):
        """Limpiar el formulario después de registrar"""
        self.search_bar.clear()
        self.cantidad_spin.setValue(1)
        self.observaciones_input.clear()
        self.producto_info_label.hide()
        self.busqueda_aviso_label.hide()
        self.resultados_list.hide()
        self.detector.reiniciar()
        self.producto_seleccionado = None
        self.search_bar.search_input.setFocus()
        
        if self.tipo_movimiento == "entrada":
            self.tipo_combo.setCurrentIndex(0)
        else:
            self.motivo_combo.setCurrentIndex(0)