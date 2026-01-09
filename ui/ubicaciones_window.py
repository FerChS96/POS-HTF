"""
Ventana de Administración de Ubicaciones de Almacenamiento
Lista de ubicaciones con botones de acción y formulario en diálogo
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QCheckBox, QDialog, QHeaderView,
    QAbstractItemView, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import logging
import qtawesome as qta

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    show_info_dialog,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)


class FormularioUbicacionDialog(QDialog):
    """Diálogo con formulario para agregar/editar ubicación"""
    
    def __init__(self, pg_manager, ubicacion_data=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.ubicacion_data = ubicacion_data
        self.setWindowTitle("")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.setup_ui()
        
        # Si hay datos, cargarlos
        if ubicacion_data:
            self.cargar_datos(ubicacion_data)
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = SectionTitle("DATOS DE UBICACIÓN")
        layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        # Estilo para inputs
        input_style = f"""
            QLineEdit, QTextEdit {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {WindowsPhoneTheme.TILE_BLUE};
            }}
        """
        
        row = 0
        
        # Nombre
        grid.addWidget(StyledLabel("Nombre *:", bold=True), row, 0)
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej: Bodega Principal, Mostrador, etc.")
        self.input_nombre.setMinimumHeight(40)
        self.input_nombre.setStyleSheet(input_style)
        grid.addWidget(self.input_nombre, row, 1)
        row += 1
        
        # Descripción
        grid.addWidget(StyledLabel("Descripción:", bold=True), row, 0)
        self.input_descripcion = QTextEdit()
        self.input_descripcion.setPlaceholderText("Descripción de la ubicación (opcional)")
        self.input_descripcion.setMaximumHeight(100)
        self.input_descripcion.setStyleSheet(input_style)
        grid.addWidget(self.input_descripcion, row, 1)
        row += 1
        
        # Estado activo
        grid.addWidget(StyledLabel("Estado:", bold=True), row, 0)
        self.check_activa = QCheckBox("Ubicación activa")
        self.check_activa.setChecked(True)
        grid.addWidget(self.check_activa, row, 1)
        row += 1
        
        layout.addLayout(grid)
        layout.addStretch()
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_guardar = TileButton("Guardar", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_guardar.setMaximumHeight(120)
        btn_guardar.clicked.connect(self.guardar)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.setMaximumHeight(120)
        btn_cancelar.clicked.connect(self.reject)
        
        buttons_layout.addWidget(btn_guardar)
        buttons_layout.addWidget(btn_cancelar)
        
        layout.addLayout(buttons_layout)
    
    def cargar_datos(self, ubicacion):
        """Cargar datos de ubicación existente"""
        self.input_nombre.setText(ubicacion.get('nombre', ''))
        self.input_descripcion.setPlainText(ubicacion.get('descripcion', '') or '')
        self.check_activa.setChecked(ubicacion.get('activa', True))
    
    def validar(self):
        """Validar datos del formulario"""
        nombre = self.input_nombre.text().strip()
        
        if not nombre:
            show_warning_dialog(self, "Validación", "Debe ingresar un nombre para la ubicación")
            self.input_nombre.setFocus()
            return False
        
        if len(nombre) < 3:
            show_warning_dialog(self, "Validación", "El nombre debe tener al menos 3 caracteres")
            self.input_nombre.setFocus()
            return False
        
        return True
    
    def guardar(self):
        """Guardar ubicación en la base de datos"""
        if not self.validar():
            return
        
        try:
            nombre = self.input_nombre.text().strip()
            descripcion = self.input_descripcion.toPlainText().strip() or None
            activa = self.check_activa.isChecked()
            
            if self.ubicacion_data:
                # Actualizar ubicación existente
                id_ubicacion = self.ubicacion_data['id_ubicacion']
                response = self.pg_manager.client.table('ca_ubicaciones').update({
                    'nombre': nombre,
                    'descripcion': descripcion,
                    'activa': activa
                }).eq('id_ubicacion', id_ubicacion).execute()
                msg = "actualizada"
            else:
                # Crear nueva ubicación
                response = self.pg_manager.client.table('ca_ubicaciones').insert({
                    'nombre': nombre,
                    'descripcion': descripcion,
                    'activa': activa
                }).execute()
                msg = "creada"
            
            show_success_dialog(
                self,
                "Éxito",
                f"Ubicación {msg} correctamente: {nombre}"
            )
            
            logging.info(f"Ubicación {msg}: {nombre}")
            self.accept()
                
        except Exception as e:
            logging.error(f"Error guardando ubicación: {e}")
            show_error_dialog(self, "Error", f"No se pudo guardar la ubicación:\n{str(e)}")


# ============================================================
# VENTANA PRINCIPAL DE UBICACIONES
# ============================================================

class UbicacionesWindow(QWidget):
    """Ventana para administrar ubicaciones de almacenamiento"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.ubicaciones = []
        
        self.setup_ui()
        self.cargar_ubicaciones()
    
    def setup_ui(self):
        """Configurar interfaz principal"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Título
        # title = SectionTitle("ADMINISTRACIÓN DE UBICACIONES")
        # layout.addWidget(title)
        
        # Panel con info
        # info_panel = ContentPanel()
        #info_layout = QHBoxLayout(info_panel)
        #self.info_total = StyledLabel("Total: 0 ubicaciones", bold=True)
        #info_layout.addWidget(self.info_total)
        #info_layout.addStretch()
        # layout.addWidget(info_panel)
        
        # Panel de lista de ubicaciones
        lista_panel = self._setup_panel_lista()
        layout.addWidget(lista_panel)
        
        # Botones al pie (todos en una fila)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_nuevo = TileButton("Nueva Ubicación", "fa5s.plus", WindowsPhoneTheme.TILE_GREEN)
        btn_nuevo.clicked.connect(self.abrir_formulario_nuevo)
        buttons_layout.addWidget(btn_nuevo)
        
        btn_refrescar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_refrescar.clicked.connect(self.cargar_ubicaciones)
        buttons_layout.addWidget(btn_refrescar)
        
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        buttons_layout.addWidget(btn_volver)
        
        layout.addLayout(buttons_layout)
    
    def _setup_panel_lista(self):
        """Panel con la tabla de ubicaciones"""
        panel = ContentPanel()
        panel_layout = QVBoxLayout(panel)
        
        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre", "Descripción", "Estado", "Acciones"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        
        # Configurar headers
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Nombre
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Descripción
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Estado
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Acciones
        
        # Estilo de tabla
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                border: none;
                gridline-color: #e5e7eb;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid #e5e7eb;
            }}
            QTableWidget::item:selected {{
                background-color: {WindowsPhoneTheme.TILE_BLUE};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
        """)
        
        panel_layout.addWidget(self.table)
        
        return panel
    
    def cargar_ubicaciones(self):
        """Cargar ubicaciones desde la base de datos"""
        try:
            # Usar PostgresManager para obtener ubicaciones
            self.ubicaciones = self.pg_manager.get_ubicaciones()
            self.actualizar_tabla()
            # self.info_total.setText(f"Total: {len(self.ubicaciones)} ubicaciones")
            
            logging.info(f"Cargadas {len(self.ubicaciones)} ubicaciones")
                
        except Exception as e:
            logging.error(f"Error cargando ubicaciones: {e}")
            show_error_dialog(self, "Error", "No se pudieron cargar las ubicaciones")
    
    def actualizar_tabla(self):
        """Actualizar tabla con los datos de ubicaciones"""
        self.table.setRowCount(0)
        
        for i, ubicacion in enumerate(self.ubicaciones):
            self.table.insertRow(i)
            self.table.setRowHeight(i, 60)  # Altura consistente
            
            # ID
            id_item = QTableWidgetItem(str(ubicacion['id_ubicacion']))
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, id_item)
            
            # Nombre
            nombre_item = QTableWidgetItem(ubicacion['nombre'])
            self.table.setItem(i, 1, nombre_item)
            
            # Descripción
            desc = ubicacion['descripcion'] or "-"
            desc_item = QTableWidgetItem(desc)
            self.table.setItem(i, 2, desc_item)
            
            # Estado
            estado = "✓ Activa" if ubicacion['activa'] else "✗ Inactiva"
            estado_item = QTableWidgetItem(estado)
            estado_item.setTextAlignment(Qt.AlignCenter)
            if ubicacion['activa']:
                estado_item.setForeground(Qt.darkGreen)
            else:
                estado_item.setForeground(Qt.darkRed)
            self.table.setItem(i, 3, estado_item)
            
            # Botones de acción con iconos
            acciones_widget = QWidget()
            acciones_widget.setStyleSheet("background: transparent;")
            acciones_layout = QHBoxLayout(acciones_widget)
            acciones_layout.setContentsMargins(5, 5, 5, 5)
            acciones_layout.setSpacing(5)
            
            # Botón Editar con icono
            btn_editar = QPushButton()
            btn_editar.setIcon(qta.icon('fa5s.edit', color='white'))
            btn_editar.setToolTip("Editar ubicación")
            btn_editar.setMinimumHeight(30)
            btn_editar.setFixedWidth(40)
            btn_editar.setStyleSheet(f"""
                QPushButton {{
                    background-color: {WindowsPhoneTheme.TILE_BLUE};
                    color: white;
                    border: none;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: #1976d2;
                }}
            """)
            btn_editar.clicked.connect(lambda checked, u=ubicacion: self.editar_ubicacion(u))
            acciones_layout.addWidget(btn_editar)
            
            # Botón Eliminar con icono
            btn_eliminar = QPushButton()
            btn_eliminar.setIcon(qta.icon('fa5s.trash', color='white'))
            btn_eliminar.setToolTip("Eliminar ubicación")
            btn_eliminar.setMinimumHeight(30)
            btn_eliminar.setFixedWidth(40)
            btn_eliminar.setStyleSheet(f"""
                QPushButton {{
                    background-color: {WindowsPhoneTheme.TILE_RED};
                    color: white;
                    border: none;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: #c62828;
                }}
            """)
            btn_eliminar.clicked.connect(lambda checked, u=ubicacion: self.eliminar_ubicacion(u))
            acciones_layout.addWidget(btn_eliminar)
            
            self.table.setCellWidget(i, 4, acciones_widget)
    
    def abrir_formulario_nuevo(self):
        """Abrir formulario para nueva ubicación"""
        dialog = FormularioUbicacionDialog(self.pg_manager, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_ubicaciones()
    
    def editar_ubicacion(self, ubicacion):
        """Abrir formulario para editar ubicación"""
        dialog = FormularioUbicacionDialog(self.pg_manager, ubicacion, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_ubicaciones()
    
    def eliminar_ubicacion(self, ubicacion):
        """Eliminar ubicación después de confirmación"""
        # Confirmar eliminación
        if not show_confirmation_dialog(
            self,
            "Confirmar eliminación",
            f"¿Desea eliminar la ubicación '{ubicacion['nombre']}'?",
            "Esta acción no se puede deshacer."
        ):
            return
        
        try:
            id_ubicacion = ubicacion['id_ubicacion']
            
            # Verificar si tiene productos asociados
            inventario_response = self.pg_manager.client.table('inventario').select(
                'id_inventario', count='exact'
            ).eq('id_ubicacion', id_ubicacion).execute()
            
            if inventario_response.count and inventario_response.count > 0:
                show_warning_dialog(
                    self,
                    "No se puede eliminar",
                    f"La ubicación '{ubicacion['nombre']}' tiene {inventario_response.count} productos asociados.",
                    "Primero debe reubicar los productos."
                )
                return
            
            # Eliminar ubicación
            self.pg_manager.client.table('ca_ubicaciones').delete().eq(
                'id_ubicacion', id_ubicacion
            ).execute()
            
            show_success_dialog(
                self,
                "Éxito",
                f"Ubicación '{ubicacion['nombre']}' eliminada correctamente"
            )
            
            self.cargar_ubicaciones()
            logging.info(f"Ubicación eliminada: {ubicacion['nombre']}")
                
        except Exception as e:
            logging.error(f"Error eliminando ubicación: {e}")
            show_error_dialog(self, "Error", f"No se pudo eliminar la ubicación:\n{str(e)}")
