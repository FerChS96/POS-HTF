"""
Ventana de Gestión de Personal para HTF POS
Grid con lista de personal y formulario separado en diálogo
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDateEdit, QHeaderView, QAbstractItemView, QGridLayout, QFrame, QDialog
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QFont
import logging
from datetime import date, datetime
import uuid

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


class FormularioPersonalDialog(QDialog):
    """Diálogo con formulario para agregar/editar personal"""
    
    def __init__(self, pg_manager, personal_data=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.personal_data = personal_data
        self.setWindowTitle("")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)
        
        self.setup_ui()
        
        # Si hay datos, cargarlos
        if personal_data:
            self.cargar_datos(personal_data)
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = SectionTitle("DATOS DEL PERSONAL")
        layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        row = 0
        
        # Estilo para inputs
        input_style = f"""
            QLineEdit, QComboBox, QDateEdit {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius:4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
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
        """
        
        # Nombres
        grid.addWidget(StyledLabel("Nombres:", bold=True), row, 0)
        self.input_nombres = QLineEdit()
        self.input_nombres.setPlaceholderText("Nombre(s) del empleado")
        self.input_nombres.setMinimumHeight(40)
        self.input_nombres.setStyleSheet(input_style)
        grid.addWidget(self.input_nombres, row, 1)
        row += 1
        
        # Apellido Paterno
        grid.addWidget(StyledLabel("Apellido Paterno:", bold=True), row, 0)
        self.input_apellido_paterno = QLineEdit()
        self.input_apellido_paterno.setPlaceholderText("Apellido paterno")
        self.input_apellido_paterno.setMinimumHeight(40)
        self.input_apellido_paterno.setStyleSheet(input_style)
        grid.addWidget(self.input_apellido_paterno, row, 1)
        row += 1
        
        # Apellido Materno
        grid.addWidget(StyledLabel("Apellido Materno:", bold=True), row, 0)
        self.input_apellido_materno = QLineEdit()
        self.input_apellido_materno.setPlaceholderText("Apellido materno")
        self.input_apellido_materno.setMinimumHeight(40)
        self.input_apellido_materno.setStyleSheet(input_style)
        grid.addWidget(self.input_apellido_materno, row, 1)
        row += 1
        
        # Rol
        grid.addWidget(StyledLabel("Rol:", bold=True), row, 0)
        self.combo_rol = QComboBox()
        self.combo_rol.addItems(["entrenador", "limpieza", "mantenimiento", "nutriologo"])
        self.combo_rol.setMinimumHeight(40)
        self.combo_rol.setStyleSheet(input_style)
        grid.addWidget(self.combo_rol, row, 1)
        row += 1
        
        # Teléfono
        grid.addWidget(StyledLabel("Teléfono:", bold=True), row, 0)
        self.input_telefono = QLineEdit()
        self.input_telefono.setPlaceholderText("10 dígitos")
        self.input_telefono.setMaxLength(20)
        self.input_telefono.setMinimumHeight(40)
        self.input_telefono.setStyleSheet(input_style)
        grid.addWidget(self.input_telefono, row, 1)
        row += 1
        
        # Email
        grid.addWidget(StyledLabel("Email:", bold=True), row, 0)
        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("correo@ejemplo.com")
        self.input_email.setMinimumHeight(40)
        self.input_email.setStyleSheet(input_style)
        grid.addWidget(self.input_email, row, 1)
        row += 1
        
        # Número de Empleado
        grid.addWidget(StyledLabel("Núm. Empleado:", bold=True), row, 0)
        self.input_num_empleado = QLineEdit()
        self.input_num_empleado.setPlaceholderText("Opcional")
        self.input_num_empleado.setMinimumHeight(40)
        self.input_num_empleado.setStyleSheet(input_style)
        grid.addWidget(self.input_num_empleado, row, 1)
        row += 1
        
        # Fecha de Contratación
        grid.addWidget(StyledLabel("Fecha Contratación:", bold=True), row, 0)
        self.input_fecha_contratacion = QDateEdit()
        self.input_fecha_contratacion.setDate(QDate.currentDate())
        self.input_fecha_contratacion.setCalendarPopup(True)
        aplicar_estilo_fecha(self.input_fecha_contratacion)
        self.input_fecha_contratacion.setMinimumHeight(40)
        grid.addWidget(self.input_fecha_contratacion, row, 1)
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
    
    def cargar_datos(self, persona):
        """Cargar datos en el formulario"""
        self.input_nombres.setText(persona['nombres'])
        self.input_apellido_paterno.setText(persona['apellido_paterno'])
        self.input_apellido_materno.setText(persona['apellido_materno'])
        
        # Establecer rol
        index = self.combo_rol.findText(persona['rol'])
        if index >= 0:
            self.combo_rol.setCurrentIndex(index)
            
        self.input_telefono.setText(persona['telefono'] or "")
        self.input_email.setText(persona['email'] or "")
        self.input_num_empleado.setText(persona['numero_empleado'] or "")
        
        # Fecha de contratación
        if persona['fecha_contratacion']:
            fecha = QDate.fromString(persona['fecha_contratacion'], "yyyy-MM-dd")
            self.input_fecha_contratacion.setDate(fecha)
    
    def validar_formulario(self):
        """Validar datos del formulario"""
        if not self.input_nombres.text().strip():
            show_warning_dialog(self, "Validación", "El nombre es obligatorio")
            return False
            
        if not self.input_apellido_paterno.text().strip():
            show_warning_dialog(self, "Validación", "El apellido paterno es obligatorio")
            return False
            
        if not self.input_apellido_materno.text().strip():
            show_warning_dialog(self, "Validación", "El apellido materno es obligatorio")
            return False
            
        return True
    
    def guardar(self):
        """Guardar datos del personal"""
        if not self.validar_formulario():
            return
            
        try:
            
            # Generar código QR único si es nuevo
            if not self.personal_data:
                codigo_qr = f"PER-{uuid.uuid4().hex[:8].upper()}"
            else:
                codigo_qr = self.personal_data['codigo_qr']
            
            # Preparar datos
            fecha_contratacion = self.input_fecha_contratacion.date().toString("yyyy-MM-dd")
            
            if self.personal_data:
                # Actualizar
                self.pg_manager.client.table('personal').update({
                    'nombres': self.input_nombres.text().strip(),
                    'apellido_paterno': self.input_apellido_paterno.text().strip(),
                    'apellido_materno': self.input_apellido_materno.text().strip(),
                    'rol': self.combo_rol.currentText(),
                    'telefono': self.input_telefono.text().strip() or None,
                    'email': self.input_email.text().strip() or None,
                    'numero_empleado': self.input_num_empleado.text().strip() or None,
                    'fecha_contratacion': fecha_contratacion
                }).eq('id_personal', self.personal_data['id_personal']).execute()
                mensaje = "Personal actualizado correctamente"
            else:
                # Insertar
                self.pg_manager.client.table('personal').insert({
                    'nombres': self.input_nombres.text().strip(),
                    'apellido_paterno': self.input_apellido_paterno.text().strip(),
                    'apellido_materno': self.input_apellido_materno.text().strip(),
                    'rol': self.combo_rol.currentText(),
                    'telefono': self.input_telefono.text().strip() or None,
                    'email': self.input_email.text().strip() or None,
                    'numero_empleado': self.input_num_empleado.text().strip() or None,
                    'codigo_qr': codigo_qr,
                    'fecha_contratacion': fecha_contratacion,
                    'activo': 1
                }).execute()
                mensaje = "Personal registrado correctamente"
            
            show_success_dialog(self, "Éxito", mensaje)
            
            # Aceptar el diálogo
            self.accept()
            
        except Exception as e:
            logging.error(f"Error guardando personal: {e}")
            show_error_dialog(self, "Error", f"No se pudo guardar: {e}")


class PersonalWindow(QWidget):
    """Widget con grid de personal"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        
        self.setup_ui()
        self.cargar_personal()
        
    def setup_ui(self):
        """Configurar interfaz"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # El título viene del TopBar, no duplicar aquí
        # title = SectionTitle("GESTIÓN DE PERSONAL")
        # layout.addWidget(title)
        
        # Tabla de personal
        self.tabla_personal = QTableWidget()
        self.tabla_personal.setColumnCount(6)
        self.tabla_personal.setHorizontalHeaderLabels([
            "ID", "Nombre Completo", "Rol", "Teléfono", "Email", "Estado"
        ])
        
        # Configurar tabla
        self.tabla_personal.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_personal.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla_personal.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_personal.horizontalHeader().setStretchLastSection(True)
        self.tabla_personal.verticalHeader().setVisible(False)
        
        # Ajustar columnas
        header = self.tabla_personal.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Nombre
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Rol
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Teléfono
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Email
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Estado
        
        # Aplicar estilos a la tabla
        self.tabla_personal.setStyleSheet(f"""
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
        
        layout.addWidget(self.tabla_personal)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_agregar = TileButton("Agregar Personal", "fa5s.user-plus", WindowsPhoneTheme.TILE_GREEN)
        btn_agregar.clicked.connect(self.agregar_personal)
        
        btn_editar = TileButton("Editar", "fa5s.edit", WindowsPhoneTheme.TILE_BLUE)
        btn_editar.clicked.connect(self.editar_personal)
        
        btn_desactivar = TileButton("Dar de Baja", "fa5s.user-times", WindowsPhoneTheme.TILE_ORANGE)
        btn_desactivar.clicked.connect(self.desactivar_personal)
        
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_agregar)
        buttons_layout.addWidget(btn_editar)
        buttons_layout.addWidget(btn_desactivar)
        buttons_layout.addWidget(btn_volver)
        
        layout.addLayout(buttons_layout)
        
    def cargar_personal(self):
        """Cargar lista de personal"""
        try:
            response = self.pg_manager.client.table('personal').select(
                'id_personal, nombres, apellido_paterno, apellido_materno, rol, telefono, email, activo'
            ).order('apellido_paterno,apellido_materno,nombres').execute()
            personal = response.data
            self.tabla_personal.setRowCount(0)
            
            for persona in personal:
                row = self.tabla_personal.rowCount()
                self.tabla_personal.insertRow(row)
                
                # ID
                id_item = QTableWidgetItem(str(persona['id_personal']))
                self.tabla_personal.setItem(row, 0, id_item)
                
                # Nombre completo
                nombre_completo = f"{persona['nombres']} {persona['apellido_paterno']} {persona['apellido_materno']}"
                self.tabla_personal.setItem(row, 1, QTableWidgetItem(nombre_completo))
                
                # Rol
                self.tabla_personal.setItem(row, 2, QTableWidgetItem(persona['rol'].title()))
                
                # Teléfono
                telefono = persona['telefono'] if persona['telefono'] else "N/A"
                self.tabla_personal.setItem(row, 3, QTableWidgetItem(telefono))
                
                # Email
                email = persona['email'] if persona['email'] else "N/A"
                self.tabla_personal.setItem(row, 4, QTableWidgetItem(email))
                
                # Estado
                estado = "Activo" if persona['activo'] else "Inactivo"
                estado_item = QTableWidgetItem(estado)
                if not persona['activo']:
                    estado_item.setForeground(Qt.red)
                self.tabla_personal.setItem(row, 5, estado_item)
                
        except Exception as e:
            logging.error(f"Error cargando personal: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar el personal: {e}")
    
    def agregar_personal(self):
        """Abrir formulario para agregar personal"""
        dialog = FormularioPersonalDialog(self.pg_manager, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_personal()
    
    def editar_personal(self):
        """Abrir formulario para editar personal seleccionado"""
        selected = self.tabla_personal.selectedItems()
        if not selected:
            show_warning_dialog(self, "Selección", "Debe seleccionar un empleado para editar")
            return
        
        row = selected[0].row()
        id_personal = int(self.tabla_personal.item(row, 0).text())
        
        try:
            response = self.pg_manager.client.table('personal').select('*').eq('id_personal', id_personal).execute()
            persona = response.data[0] if response.data else None
            if persona:
                dialog = FormularioPersonalDialog(
                    self.pg_manager, 
                    personal_data=dict(persona),
                    parent=self
                )
                if dialog.exec() == QDialog.Accepted:
                    self.cargar_personal()
                    
        except Exception as e:
            logging.error(f"Error cargando datos de personal: {e}")
            show_error_dialog(self, "Error", f"No se pudo cargar los datos: {e}")
    
    def desactivar_personal(self):
        """Dar de baja al personal seleccionado"""
        selected = self.tabla_personal.selectedItems()
        if not selected:
            show_warning_dialog(self, "Selección", "Debe seleccionar un empleado para dar de baja")
            return
        
        row = selected[0].row()
        id_personal = int(self.tabla_personal.item(row, 0).text())
        nombre_completo = self.tabla_personal.item(row, 1).text()
        
        if show_confirmation_dialog(
            self,
            "Confirmar Baja",
            f"¿Desea dar de baja a {nombre_completo}?",
            detail="Esta acción marcará al empleado como inactivo.",
            confirm_text="Sí, dar de baja",
            cancel_text="Cancelar"
        ):
            try:
                self.pg_manager.client.table('personal').update({
                    'activo': 0,
                    'fecha_baja': date.today().strftime('%Y-%m-%d')
                }).eq('id_personal', id_personal).execute()
                
                show_success_dialog(self, "Éxito", "Personal dado de baja correctamente")
                
                self.cargar_personal()
                
            except Exception as e:
                logging.error(f"Error dando de baja personal: {e}")
                show_error_dialog(self, "Error", f"No se pudo dar de baja: {e}")