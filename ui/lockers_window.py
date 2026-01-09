"""
Ventana de Gestión de Catálogo de Lockers
Grid de lockers con formulario para crear/editar
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QCheckBox, QDialog, QHeaderView, QPushButton,
    QAbstractItemView
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
    SearchBar,
    show_info_dialog,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)


class FormularioLockerDialog(QDialog):
    """Diálogo con formulario para agregar/editar locker"""
    
    def __init__(self, pg_manager, locker_data=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.locker_data = locker_data
        self.setWindowTitle("Nuevo Locker" if not locker_data else "Editar Locker")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.setup_ui()
        
        if locker_data:
            self.cargar_datos(locker_data)
    
    def setup_ui(self):
        """Configurar interfaz del formulario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = SectionTitle("DATOS DEL LOCKER")
        layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        # Estilo para inputs
        input_style = f"""
            QLineEdit, QComboBox {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QLineEdit:focus, QComboBox:focus {{
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
        
        row = 0
        
        # Número
        grid.addWidget(StyledLabel("Número *:", bold=True), row, 0)
        self.input_numero = QLineEdit()
        self.input_numero.setPlaceholderText("Ej: L01, L02, 101, etc.")
        self.input_numero.setMinimumHeight(40)
        self.input_numero.setStyleSheet(input_style)
        grid.addWidget(self.input_numero, row, 1)
        row += 1
        
        # Ubicación
        grid.addWidget(StyledLabel("Ubicación:", bold=True), row, 0)
        self.input_ubicacion = QLineEdit()
        self.input_ubicacion.setPlaceholderText("Zona Lockers, Vestidores, etc.")
        self.input_ubicacion.setText("Zona Lockers")
        self.input_ubicacion.setMinimumHeight(40)
        self.input_ubicacion.setStyleSheet(input_style)
        grid.addWidget(self.input_ubicacion, row, 1)
        row += 1
        
        # Tipo
        grid.addWidget(StyledLabel("Tipo:", bold=True), row, 0)
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["estándar"])
        self.combo_tipo.setMinimumHeight(40)
        self.combo_tipo.setStyleSheet(input_style)
        grid.addWidget(self.combo_tipo, row, 1)
        row += 1
        
        # Requiere llave
        grid.addWidget(StyledLabel("Requiere llave:", bold=True), row, 0)
        self.check_llave = QCheckBox("Sí, requiere llave física")
        self.check_llave.setChecked(True)
        grid.addWidget(self.check_llave, row, 1)
        row += 1
        
        # Estado activo
        grid.addWidget(StyledLabel("Estado:", bold=True), row, 0)
        self.check_activo = QCheckBox("Locker activo")
        self.check_activo.setChecked(True)
        grid.addWidget(self.check_activo, row, 1)
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
    
    def cargar_datos(self, locker):
        """Cargar datos de locker existente"""
        self.input_numero.setText(locker.get('numero', ''))
        self.input_ubicacion.setText(locker.get('ubicacion', 'Zona Lockers'))
        
        tipo = locker.get('tipo', 'estándar')
        index = self.combo_tipo.findText(tipo)
        if index >= 0:
            self.combo_tipo.setCurrentIndex(index)
        
        self.check_llave.setChecked(locker.get('requiere_llave', True))
        self.check_activo.setChecked(locker.get('activo', True))
    
    def validar(self):
        """Validar datos del formulario"""
        numero = self.input_numero.text().strip()
        
        if not numero:
            show_warning_dialog(self, "Validación", "Debe ingresar un número para el locker")
            self.input_numero.setFocus()
            return False
        
        if len(numero) < 1:
            show_warning_dialog(self, "Validación", "El número debe tener al menos 1 carácter")
            self.input_numero.setFocus()
            return False
        
        return True
    
    def guardar(self):
        """Guardar locker en la base de datos"""
        if not self.validar():
            return
        
        try:
            numero = self.input_numero.text().strip()
            ubicacion = self.input_ubicacion.text().strip() or "Zona Lockers"
            tipo = self.combo_tipo.currentText()
            requiere_llave = self.check_llave.isChecked()
            activo = self.check_activo.isChecked()
            
            if self.locker_data:
                # Actualizar
                id_locker = self.locker_data['id_locker']
                self.pg_manager.client.table('lockers').update({
                    'numero': numero,
                    'ubicacion': ubicacion,
                    'tipo': tipo,
                    'requiere_llave': requiere_llave,
                    'activo': activo
                }).eq('id_locker', id_locker).execute()
                msg = "actualizado"
            else:
                # Crear nuevo
                self.pg_manager.client.table('lockers').insert({
                    'numero': numero,
                    'ubicacion': ubicacion,
                    'tipo': tipo,
                    'requiere_llave': requiere_llave,
                    'activo': activo
                }).execute()
                msg = "creado"
            
            show_success_dialog(
                self,
                "Éxito",
                f"Locker {msg} correctamente: {numero}"
            )
            
            logging.info(f"Locker {msg}: {numero}")
            self.accept()
                
        except Exception as e:
            logging.error(f"Error guardando locker: {e}")
            show_error_dialog(self, "Error", f"No se pudo guardar el locker:\n{str(e)}")


# ============================================================
# VENTANA PRINCIPAL DE LOCKERS
# ============================================================

class LockersWindow(QWidget):
    """Ventana para administrar catálogo de lockers"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.lockers_data = []
        
        self.setup_ui()
        self.cargar_lockers()
    
    def setup_ui(self):
        """Configurar interfaz de la ventana"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Título
        # title = SectionTitle("CATÁLOGO DE LOCKERS")
        #layout.addWidget(title)
        
        # Buscador
        self.search_bar = SearchBar("Buscar por número o ubicación...")
        self.search_bar.connect_search(self.filtrar_lockers)
        layout.addWidget(self.search_bar)
        
        # Panel con info
        info_panel = ContentPanel()
        info_layout = QHBoxLayout(info_panel)
        self.info_total = StyledLabel("Total: 0 lockers", bold=True)
        info_layout.addWidget(self.info_total)
        info_layout.addStretch()
        layout.addWidget(info_panel)
        
        # Panel de lista de lockers
        table_panel = self._setup_panel_lista()
        layout.addWidget(table_panel)
        
        # Botones al pie (todos en una fila)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_nuevo = TileButton("Nuevo Locker", "fa5s.plus", WindowsPhoneTheme.TILE_GREEN)
        btn_nuevo.clicked.connect(self.abrir_formulario_nuevo)
        buttons_layout.addWidget(btn_nuevo)
        
        btn_refrescar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_refrescar.clicked.connect(self.cargar_lockers)
        buttons_layout.addWidget(btn_refrescar)
        
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        buttons_layout.addWidget(btn_volver)
        
        layout.addLayout(buttons_layout)
    
    def _setup_panel_lista(self):
        """Panel con la tabla de lockers"""
        panel = ContentPanel()
        panel_layout = QVBoxLayout(panel)
        
        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Número", "Ubicación", "Tipo", "Requiere Llave", "Estado", "Acciones"
        ])
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        
        # Configurar headers
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Número
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Ubicación
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Tipo
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Requiere Llave
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Estado
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Acciones
        
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
    
    def cargar_lockers(self):
        """Cargar lockers desde la base de datos"""
        try:
            response = self.pg_manager.client.table('lockers').select(
                'id_locker, numero, ubicacion, tipo, requiere_llave, activo'
            ).order('numero').execute()
            
            self.lockers_data = response.data
            self.mostrar_lockers(self.lockers_data)
                
        except Exception as e:
            logging.error(f"Error cargando lockers: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los lockers:\n{str(e)}")
    
    def mostrar_lockers(self, lockers):
        """Mostrar lockers en la tabla"""
        self.table.setRowCount(0)
        
        for i, locker in enumerate(lockers):
            self.table.insertRow(i)
            self.table.setRowHeight(i, 60)
            
            # Número
            self.table.setItem(i, 0, QTableWidgetItem(locker['numero']))
            
            # Ubicación
            self.table.setItem(i, 1, QTableWidgetItem(locker['ubicacion'] or "N/A"))
            
            # Tipo
            self.table.setItem(i, 2, QTableWidgetItem(locker['tipo'] or "estándar"))
            
            # Requiere llave
            llave = "Sí" if locker['requiere_llave'] else "No"
            self.table.setItem(i, 3, QTableWidgetItem(llave))
            
            # Estado
            estado = "Activo" if locker['activo'] else "Inactivo"
            item_estado = QTableWidgetItem(estado)
            if locker['activo']:
                item_estado.setForeground(Qt.darkGreen)
            else:
                item_estado.setForeground(Qt.red)
            self.table.setItem(i, 4, item_estado)
            
            # Botones de acción
            acciones_widget = QWidget()
            acciones_layout = QHBoxLayout(acciones_widget)
            acciones_layout.setContentsMargins(5, 5, 5, 5)
            acciones_layout.setSpacing(5)
            
            btn_editar = QPushButton()
            btn_editar.setIcon(qta.icon('fa5s.edit', color='white'))
            btn_editar.setToolTip("Editar locker")
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
            btn_editar.clicked.connect(lambda checked, l=locker: self.editar_locker(l))
            acciones_layout.addWidget(btn_editar)
            
            btn_eliminar = QPushButton()
            btn_eliminar.setIcon(qta.icon('fa5s.trash', color='white'))
            btn_eliminar.setToolTip("Eliminar locker")
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
            btn_eliminar.clicked.connect(lambda checked, l=locker: self.eliminar_locker(l))
            acciones_layout.addWidget(btn_eliminar)
            
            self.table.setCellWidget(i, 5, acciones_widget)
        
        # Actualizar info
        total = len(lockers)
        activos = sum(1 for l in lockers if l['activo'])
        self.info_total.setText(f"Total: {total} lockers ({activos} activos)")
    
    def filtrar_lockers(self):
        """Filtrar lockers por búsqueda"""
        texto = self.search_bar.text().lower()
        
        if not texto:
            self.mostrar_lockers(self.lockers_data)
            return
        
        filtrados = [
            l for l in self.lockers_data
            if texto in l['numero'].lower()
            or texto in (l['ubicacion'] or "").lower()
        ]
        
        self.mostrar_lockers(filtrados)
    
    def abrir_formulario_nuevo(self):
        """Abrir formulario para nuevo locker"""
        dialog = FormularioLockerDialog(self.pg_manager, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_lockers()
    
    def editar_locker(self, locker):
        """Abrir formulario para editar locker"""
        dialog = FormularioLockerDialog(self.pg_manager, locker, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.cargar_lockers()
    
    def eliminar_locker(self, locker):
        """Eliminar un locker"""
        if not show_confirmation_dialog(
            self,
            "Confirmar eliminación",
            f"¿Desea eliminar el locker '{locker['numero']}'?",
            "Esta acción no se puede deshacer."
        ):
            return
        
        try:
            # Verificar si tiene asignaciones activas
            check_response = self.pg_manager.client.table('asignaciones_activas').select(
                'id_locker',
                count='exact'
            ).eq('id_locker', locker['id_locker']).eq('activa', True).execute()
            
            count = check_response.count if hasattr(check_response, 'count') else len(check_response.data)
            if count > 0:
                show_warning_dialog(
                    self,
                    "No se puede eliminar",
                    f"El locker '{locker['numero']}' tiene {count} asignación(es) activa(s).",
                    "Primero debe liberar el locker."
                )
                return
            
            # Eliminar
            self.pg_manager.client.table('lockers').delete().eq(
                'id_locker', locker['id_locker']
            ).execute()
            
            show_success_dialog(
                self,
                "Éxito",
                f"Locker '{locker['numero']}' eliminado correctamente"
            )
            
            self.cargar_lockers()
            logging.info(f"Locker eliminado: {locker['numero']}")
                
        except Exception as e:
            logging.error(f"Error eliminando locker: {e}")
            show_error_dialog(self, "Error", f"No se pudo eliminar el locker:\n{str(e)}")
