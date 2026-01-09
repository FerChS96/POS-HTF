"""
Ventana de Gestión de Días Festivos para HTF POS
Consulta directamente a Supabase
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDateEdit, QHeaderView, QAbstractItemView, QGridLayout, 
    QFrame, QDialog, QCheckBox, QTextEdit
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QFont
import logging
from datetime import date, datetime

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog,
    aplicar_estilo_fecha
)


class FormularioDiaFestivoDialog(QDialog):
    """Diálogo con formulario para agregar/editar día festivo"""
    
    def __init__(self, supabase_service, festivo_data=None, parent=None):
        super().__init__(parent)
        self.supabase_service = supabase_service
        self.festivo_data = festivo_data
        self.setWindowTitle("Día Festivo")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(600)
        
        self.setup_ui()
        
        # Si hay datos, cargarlos
        if festivo_data:
            self.cargar_datos(festivo_data)
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = SectionTitle("Días Festivos")
        layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        # Estilo para inputs
        input_style = f"""
            QLineEdit, QComboBox, QDateEdit, QTextEdit {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{
                border-color: {WindowsPhoneTheme.TILE_BLUE};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666;
                margin-right: 10px;
            }}
            QCheckBox {{
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
        """
        
        row = 0
        
        # Fecha
        grid.addWidget(StyledLabel("Fecha:", bold=True), row, 0)
        self.input_fecha = QDateEdit()
        self.input_fecha.setDate(QDate.currentDate())
        self.input_fecha.setCalendarPopup(True)
        aplicar_estilo_fecha(self.input_fecha)
        self.input_fecha.setMinimumHeight(40)
        grid.addWidget(self.input_fecha, row, 1)
        row += 1
        
        # Nombre
        grid.addWidget(StyledLabel("Nombre:", bold=True), row, 0)
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej: Año Nuevo")
        self.input_nombre.setMinimumHeight(40)
        self.input_nombre.setStyleSheet(input_style)
        grid.addWidget(self.input_nombre, row, 1)
        row += 1
        
        # Descripción
        grid.addWidget(StyledLabel("Descripción:", bold=True), row, 0, Qt.AlignTop)
        self.input_descripcion = QTextEdit()
        self.input_descripcion.setPlaceholderText("Descripción del día festivo")
        self.input_descripcion.setMaximumHeight(80)
        self.input_descripcion.setStyleSheet(input_style)
        grid.addWidget(self.input_descripcion, row, 1)
        row += 1
        
        # Tipo de festivo
        grid.addWidget(StyledLabel("Tipo:", bold=True), row, 0)
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["nacional", "local", "interno"])
        self.combo_tipo.setMinimumHeight(40)
        self.combo_tipo.setStyleSheet(input_style)
        grid.addWidget(self.combo_tipo, row, 1)
        row += 1
        
        # Gimnasio cerrado
        grid.addWidget(StyledLabel("Gimnasio Cerrado:", bold=True), row, 0)
        self.check_gimnasio_cerrado = QCheckBox("El gimnasio permanecerá cerrado")
        self.check_gimnasio_cerrado.setStyleSheet(input_style)
        grid.addWidget(self.check_gimnasio_cerrado, row, 1)
        row += 1
        
        # Horario especial
        grid.addWidget(StyledLabel("Horario Especial:", bold=True), row, 0)
        self.input_horario_especial = QLineEdit()
        self.input_horario_especial.setPlaceholderText("Ej: 8:00 - 14:00 (opcional)")
        self.input_horario_especial.setMinimumHeight(40)
        self.input_horario_especial.setStyleSheet(input_style)
        grid.addWidget(self.input_horario_especial, row, 1)
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
    
    def cargar_datos(self, festivo):
        """Cargar datos en el formulario"""
        # Fecha
        fecha = QDate.fromString(festivo['fecha'], "yyyy-MM-dd")
        self.input_fecha.setDate(fecha)
        
        self.input_nombre.setText(festivo['nombre'])
        
        if festivo.get('descripcion'):
            self.input_descripcion.setPlainText(festivo['descripcion'])
        
        # Establecer tipo
        index = self.combo_tipo.findText(festivo.get('tipo_festivo', 'nacional'))
        if index >= 0:
            self.combo_tipo.setCurrentIndex(index)
        
        self.check_gimnasio_cerrado.setChecked(festivo.get('gimnasio_cerrado', False))
        
        if festivo.get('horario_especial'):
            self.input_horario_especial.setText(festivo['horario_especial'])
    
    def validar_formulario(self):
        """Validar datos del formulario"""
        if not self.input_nombre.text().strip():
            show_warning_dialog(self, "Validación", "El nombre es obligatorio")
            return False
        
        return True
    
    def guardar(self):
        """Guardar datos del día festivo en Supabase"""
        if not self.validar_formulario():
            return
        
        try:
            # Preparar datos
            fecha = self.input_fecha.date().toString("yyyy-MM-dd")
            datos = {
                "fecha": fecha,
                "nombre": self.input_nombre.text().strip(),
                "descripcion": self.input_descripcion.toPlainText().strip() or None,
                "tipo_festivo": self.combo_tipo.currentText(),
                "gimnasio_cerrado": self.check_gimnasio_cerrado.isChecked(),
                "horario_especial": self.input_horario_especial.text().strip() or None
            }
            
            if self.festivo_data:
                # Actualizar
                response = self.supabase_service.client.table('dias_festivos') \
                    .update(datos) \
                    .eq('id_festivo', self.festivo_data['id_festivo']) \
                    .execute()
                mensaje = "Día festivo actualizado correctamente"
            else:
                # Insertar
                response = self.supabase_service.client.table('dias_festivos') \
                    .insert(datos) \
                    .execute()
                mensaje = "Día festivo agregado correctamente"
            
            logging.info(f"Día festivo guardado: {datos}")
            show_success_dialog(self, "Éxito", mensaje)
            
            # Aceptar el diálogo
            self.accept()
            
        except Exception as e:
            logging.error(f"Error guardando día festivo: {e}")
            show_error_dialog(self, "Error", f"No se pudo guardar: {str(e)}")


class DiasFestvosWindow(QWidget):
    """Widget con grid de días festivos"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, supabase_service, parent=None):
        super().__init__(parent)
        self.supabase_service = supabase_service
        
        self.setup_ui()
        self.cargar_dias_festivos()
        
    def setup_ui(self):
        """Configurar interfaz"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # El título viene del TopBar, no duplicar aquí
        # title = SectionTitle("")
        # layout.addWidget(title)
        
        # Tabla de días festivos
        self.tabla_festivos = QTableWidget()
        self.tabla_festivos.setColumnCount(7)
        self.tabla_festivos.setHorizontalHeaderLabels([
            "ID", "Fecha", "Nombre", "Tipo", "Descripción", "Cerrado", "Horario Especial"
        ])
        
        # Configurar tabla
        self.tabla_festivos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_festivos.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla_festivos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_festivos.horizontalHeader().setStretchLastSection(True)
        self.tabla_festivos.verticalHeader().setVisible(False)
        
        # Ajustar columnas
        header = self.tabla_festivos.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Fecha
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Nombre
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Tipo
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Descripción
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Cerrado
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Horario
        
        # Aplicar estilos a la tabla
        self.tabla_festivos.setStyleSheet(f"""
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
        
        layout.addWidget(self.tabla_festivos)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_agregar = TileButton("Agregar Festivo", "fa5s.calendar-plus", WindowsPhoneTheme.TILE_GREEN)
        btn_agregar.clicked.connect(self.agregar_festivo)
        
        btn_editar = TileButton("Editar", "fa5s.edit", WindowsPhoneTheme.TILE_BLUE)
        btn_editar.clicked.connect(self.editar_festivo)
        
        btn_eliminar = TileButton("Eliminar", "fa5s.trash", WindowsPhoneTheme.TILE_RED)
        btn_eliminar.clicked.connect(self.eliminar_festivo)
        
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_TEAL)
        btn_actualizar.clicked.connect(self.cargar_dias_festivos)
        
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_ORANGE)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_agregar)
        buttons_layout.addWidget(btn_editar)
        buttons_layout.addWidget(btn_eliminar)
        buttons_layout.addWidget(btn_actualizar)
        buttons_layout.addWidget(btn_volver)
        
        layout.addLayout(buttons_layout)
        
    def cargar_dias_festivos(self):
        """Cargar lista de días festivos desde Supabase"""
        try:
            logging.info("Cargando días festivos desde Supabase...")
            
            # Consultar días festivos ordenados por fecha
            response = self.supabase_service.client.table('dias_festivos') \
                .select('*') \
                .order('fecha', desc=False) \
                .execute()
            
            festivos = response.data
            
            self.tabla_festivos.setRowCount(0)
            
            for festivo in festivos:
                row = self.tabla_festivos.rowCount()
                self.tabla_festivos.insertRow(row)
                
                # ID
                id_item = QTableWidgetItem(str(festivo['id_festivo']))
                self.tabla_festivos.setItem(row, 0, id_item)
                
                # Fecha
                fecha = festivo['fecha']
                self.tabla_festivos.setItem(row, 1, QTableWidgetItem(fecha))
                
                # Nombre
                self.tabla_festivos.setItem(row, 2, QTableWidgetItem(festivo['nombre']))
                
                # Tipo
                tipo = festivo.get('tipo_festivo', 'nacional').upper()
                self.tabla_festivos.setItem(row, 3, QTableWidgetItem(tipo))
                
                # Descripción
                desc_completa = festivo.get('descripcion') or ''
                desc = desc_completa[:50] + ('...' if len(desc_completa) > 50 else '')
                self.tabla_festivos.setItem(row, 4, QTableWidgetItem(desc))
                
                # Cerrado
                cerrado = "SÍ" if festivo.get('gimnasio_cerrado', False) else "NO"
                cerrado_item = QTableWidgetItem(cerrado)
                if festivo.get('gimnasio_cerrado', False):
                    cerrado_item.setForeground(Qt.red)
                self.tabla_festivos.setItem(row, 5, cerrado_item)
                
                # Horario especial
                horario = festivo.get('horario_especial') or 'N/A'
                self.tabla_festivos.setItem(row, 6, QTableWidgetItem(horario))
            
            logging.info(f"Días festivos cargados: {len(festivos)}")
            
        except Exception as e:
            logging.error(f"Error cargando días festivos: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar los días festivos: {str(e)}")
    
    def agregar_festivo(self):
        """Abrir formulario para agregar día festivo"""
        dialog = FormularioDiaFestivoDialog(self.supabase_service, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_dias_festivos()
    
    def editar_festivo(self):
        """Abrir formulario para editar día festivo seleccionado"""
        selected = self.tabla_festivos.selectedItems()
        if not selected:
            show_warning_dialog(self, "Selección", "Debe seleccionar un día festivo para editar")
            return
        
        row = selected[0].row()
        id_festivo = int(self.tabla_festivos.item(row, 0).text())
        
        try:
            # Obtener datos completos desde Supabase
            response = self.supabase_service.client.table('dias_festivos') \
                .select('*') \
                .eq('id_festivo', id_festivo) \
                .execute()
            
            if response.data:
                festivo = response.data[0]
                dialog = FormularioDiaFestivoDialog(
                    self.supabase_service, 
                    festivo_data=festivo,
                    parent=self
                )
                if dialog.exec() == QDialog.Accepted:
                    self.cargar_dias_festivos()
            else:
                show_error_dialog(self, "Error", "No se encontró el día festivo")
                
        except Exception as e:
            logging.error(f"Error cargando datos del festivo: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar los datos: {str(e)}")
    
    def eliminar_festivo(self):
        """Eliminar día festivo seleccionado"""
        selected = self.tabla_festivos.selectedItems()
        if not selected:
            show_warning_dialog(self, "Selección", "Debe seleccionar un día festivo para eliminar")
            return
        
        row = selected[0].row()
        id_festivo = int(self.tabla_festivos.item(row, 0).text())
        nombre = self.tabla_festivos.item(row, 2).text()
        fecha = self.tabla_festivos.item(row, 1).text()
        
        if show_confirmation_dialog(
            self,
            "Confirmar Eliminación",
            f"¿Desea eliminar el día festivo '{nombre}' ({fecha})?",
            detail="Esta acción no se puede deshacer.",
            confirm_text="Sí, eliminar",
            cancel_text="Cancelar"
        ):
            try:
                # Eliminar de Supabase
                response = self.supabase_service.client.table('dias_festivos') \
                    .delete() \
                    .eq('id_festivo', id_festivo) \
                    .execute()
                
                logging.info(f"Día festivo eliminado: {id_festivo}")
                show_success_dialog(self, "Éxito", "Día festivo eliminado correctamente")
                
                self.cargar_dias_festivos()
                
            except Exception as e:
                logging.error(f"Error eliminando festivo: {e}")
                show_error_dialog(self, "Error", f"No se pudo eliminar: {str(e)}")
