"""
Ventana de Gestión de Lockers Diarios - Grid editable
Visualiza y edita asignaciones activas de lockers de renta diaria (id_producto_digital = 19)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QHeaderView, QAbstractItemView, QMessageBox,
    QDialog, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
import logging
from datetime import datetime, date, timedelta
import qtawesome as qta

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    StyledLabel,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)

logging.basicConfig(level=logging.INFO)


class AsignarLockerDiarioWindow(QWidget):
    """Ventana para gestionar asignaciones de lockers diarios (renta_diaria)"""
    
    cerrar_solicitado = Signal()
    abrir_mensuales_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.asignaciones_data = []
        
        self.setWindowTitle("")
        self.setMinimumSize(1200, 700)
        
        self.setup_ui()
        self.cargar_asignaciones()
    
    def setup_ui(self):
        """Configurar interfaz"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Título
        #title = SectionTitle("GESTIÓN DE LOCKERS DIARIOS")
        #layout.addWidget(title)
        
        # Table widget (solo lectura, no editable)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Miembro",
            "Locker",
            "Hora de Creación",
            "Acción"
        ])
        
        # Configurar tabla
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Columna Acción
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(60)  # Altura de fila consistente
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                alternate-background-color: {WindowsPhoneTheme.BG_LIGHT};
                border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
            }}
        """)
        
        layout.addWidget(self.table)
        
        # Botones
        button_layout = QHBoxLayout()
        button_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.cerrar_solicitado.emit)
        button_layout.addWidget(btn_cancelar)
        
        btn_asignar_nuevo = TileButton("Asignar Nuevo", "fa5s.plus", WindowsPhoneTheme.TILE_GREEN)
        btn_asignar_nuevo.clicked.connect(self.abrir_asignar_nuevo)
        button_layout.addWidget(btn_asignar_nuevo)
        
        btn_mensuales = TileButton("Ver Mensuales", "mdi.locker", WindowsPhoneTheme.TILE_ORANGE)
        btn_mensuales.clicked.connect(self.abrir_mensuales_solicitado.emit)
        button_layout.addWidget(btn_mensuales)
        
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_actualizar.clicked.connect(self.cargar_asignaciones)
        button_layout.addWidget(btn_actualizar)
        
        layout.addLayout(button_layout)
    
    def cargar_asignaciones(self):
        """Cargar asignaciones activas de lockers diarios del historial"""
        try:
            # Query con JOINs para obtener datos relacionados del historial de lockers diarios
            # Solo obtener los registros del día de hoy que aún no han sido devueltos
            from datetime import date
            hoy = str(date.today())
            
            response = self.pg_manager.client.table('historial_lockers_diarios').select(
                '*, miembros(nombres, apellido_paterno, apellido_materno), lockers(numero, ubicacion, tipo)'
            ).eq('fecha_asignacion', hoy).eq('devuelto', False).order('hora_asignacion', desc=True).execute()
            
            self.asignaciones_data = response.data or []
            self.poblar_tabla()
            
            logging.info(f"Cargadas {len(self.asignaciones_data)} asignaciones de lockers diarios")
            
        except Exception as e:
            show_error_dialog(self, "Error", f"Error cargando asignaciones: {str(e)}")
            logging.error(f"Error cargando asignaciones: {e}")
    
    def poblar_tabla(self):
        """Llenar tabla con datos de asignaciones (solo lectura)"""
        self.table.setRowCount(0)
        
        try:
            for idx, asig in enumerate(self.asignaciones_data):
                self.table.insertRow(idx)
                
                # Datos
                miembro = asig.get('miembros', {})
                locker = asig.get('lockers', {})
                id_historial = asig['id_historial']
                hora_asignacion = asig.get('hora_asignacion', '')
                
                # Columna 1: Miembro (read-only)
                nombre_completo = f"{miembro.get('nombres', '')} {miembro.get('apellido_paterno', '')} {miembro.get('apellido_materno', '')}".strip()
                item_miembro = QTableWidgetItem(nombre_completo)
                item_miembro.setFlags(item_miembro.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(idx, 0, item_miembro)
                
                # Columna 2: Locker (read-only)
                numero_locker = locker.get('numero', '?')
                ubicacion = locker.get('ubicacion', '?')
                item_locker = QTableWidgetItem(f"Locker {numero_locker} - {ubicacion}")
                item_locker.setFlags(item_locker.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(idx, 1, item_locker)
                
                # Columna 3: Hora de Creación (read-only)
                try:
                    # Convertir timestamp a hora legible
                    if hora_asignacion:
                        if 'T' in str(hora_asignacion):
                            dt = datetime.fromisoformat(str(hora_asignacion).replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromisoformat(str(hora_asignacion))
                        hora_texto = dt.strftime('%d/%m/%Y %H:%M:%S')
                    else:
                        hora_texto = '-'
                except:
                    hora_texto = str(hora_asignacion) if hora_asignacion else '-'
                
                item_hora = QTableWidgetItem(hora_texto)
                item_hora.setFlags(item_hora.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(idx, 2, item_hora)
                
                # Columna 4: Botón Devolver Llave
                btn_devolver = QPushButton()
                btn_devolver.setIcon(qta.icon('fa5s.key', color='white'))
                btn_devolver.setToolTip("Devolver llave")
                btn_devolver.setMinimumHeight(30)
                btn_devolver.setFixedWidth(40)
                btn_devolver.setStyleSheet(f"""
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
                btn_devolver.clicked.connect(lambda checked, hist_id=id_historial: self.devolver_locker(hist_id))
                self.table.setCellWidget(idx, 3, btn_devolver)
                
                # Altura de fila
                self.table.setRowHeight(idx, 60)
        
        except Exception as e:
            logging.error(f"Error poblando tabla: {e}")
    
    
    def devolver_locker(self, id_historial):
        """Marcar locker como devuelto en el historial"""
        try:
            # Confirmar devolución
            if not show_confirmation_dialog(
                self,
                "Confirmar Devolución",
                "¿Está seguro de que desea devolver esta llave?"
            ):
                return
            
            # Actualizar historial: devuelto = True, hora_devolucion = NOW()
            from datetime import datetime
            update_data = {
                'devuelto': True,
                'hora_devolucion': datetime.now().isoformat()
            }
            
            response = self.pg_manager.client.table('historial_lockers_diarios').update(
                update_data
            ).eq('id_historial', id_historial).execute()
            
            if response.data:
                show_success_dialog(
                    self,
                    "Éxito",
                    "Llave devuelta correctamente. El locker ha sido liberado."
                )
                
                logging.info(f"Locker devuelto - Historial {id_historial} marcado como devuelto")
                
                # Recargar tabla
                self.cargar_asignaciones()
            else:
                show_error_dialog(self, "Error", "No se pudo devolver la llave")
        
        except Exception as e:
            show_error_dialog(self, "Error", f"Error al devolver la llave: {str(e)}")
            logging.error(f"Error devolviendo locker: {e}")
    
    def abrir_asignar_nuevo(self):
        """Abrir diálogo para asignar nuevo locker diario"""
        dialog = AsignarLockerDiarioDialog(self.pg_manager, self.user_data, self)
        if dialog.exec():
            self.cargar_asignaciones()


class AsignarLockerDiarioDialog(QDialog):
    """Diálogo para asignar lockers de renta diaria a miembros"""
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.setWindowTitle("Asignar Locker Diario")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(250)
        
        self.setup_ui()
        self.cargar_miembros()
        self.cargar_lockers_diarios()
    
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        from PySide6.QtWidgets import QGridLayout
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Título
        title = SectionTitle("ASIGNAR LOCKER DIARIO")
        layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        # Miembro
        grid.addWidget(StyledLabel("Miembro *:", bold=True), 0, 0)
        self.combo_miembro = QComboBox()
        self.combo_miembro.setMinimumHeight(40)
        self.combo_miembro.setStyleSheet(f"""
            QComboBox {{
                padding: 8px;
                border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 4px;
                background-color: white;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                min-height: 30px;
            }}
            QComboBox:focus {{
                border: 2px solid {WindowsPhoneTheme.PRIMARY_BLUE};
                background-color: #f9fafb;
            }}
        """)
        grid.addWidget(self.combo_miembro, 0, 1)
        
        # Locker
        grid.addWidget(StyledLabel("Locker Diario *:", bold=True), 1, 0)
        self.combo_locker = QComboBox()
        self.combo_locker.setMinimumHeight(40)
        self.combo_locker.setStyleSheet(f"""
            QComboBox {{
                padding: 8px;
                border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                border-radius: 4px;
                background-color: white;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                min-height: 30px;
            }}
            QComboBox:focus {{
                border: 2px solid {WindowsPhoneTheme.PRIMARY_BLUE};
                background-color: #f9fafb;
            }}
        """)
        grid.addWidget(self.combo_locker, 1, 1)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_asignar = TileButton("Asignar", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_asignar.clicked.connect(self.asignar_locker_diario)
        buttons_layout.addWidget(btn_asignar)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancelar)
        
        layout.addLayout(buttons_layout)
    
    def cargar_miembros(self):
        """Cargar miembros activos sin locker asignado hoy"""
        try:
            # Obtener todos los miembros activos
            response_miembros = self.pg_manager.client.table('miembros').select(
                'id_miembro, nombres, apellido_paterno, apellido_materno'
            ).eq('activo', True).execute()
            
            miembros = response_miembros.data or []
            
            # Obtener IDs de miembros que TUVIERON UN LOCKER HOY (sin importar si lo devolvieron)
            hoy = str(date.today())
            response_asignados = self.pg_manager.client.table('historial_lockers_diarios').select(
                'id_miembro'
            ).eq('fecha_asignacion', hoy).execute()
            
            ids_con_locker_diario_hoy = {item['id_miembro'] for item in (response_asignados.data or [])}
            
            # Filtrar solo miembros SIN locker diario asignado hoy
            miembros_disponibles = [m for m in miembros if m['id_miembro'] not in ids_con_locker_diario_hoy]
            
            self.combo_miembro.addItem("-- Seleccionar miembro --", None)
            
            for miembro in miembros_disponibles:
                nombre_completo = f"{miembro['nombres']} {miembro['apellido_paterno']} {miembro['apellido_materno']}".strip()
                self.combo_miembro.addItem(nombre_completo, miembro['id_miembro'])
        
        except Exception as e:
            logging.error(f"Error cargando miembros: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los miembros: {str(e)}")
    
    def cargar_lockers_diarios(self):
        """Cargar lockers de renta diaria disponibles hoy"""
        try:
            # Obtener todos los lockers de tipo 'renta_diaria' activos, ordenados por id
            response_todos = self.pg_manager.client.table('lockers').select(
                'id_locker, numero, ubicacion'
            ).eq('tipo', 'renta_diaria').eq('activo', True).order('id_locker', desc=False).execute()
            
            todos_lockers = response_todos.data or []
            
            # Obtener IDs de lockers ya asignados hoy (no devueltos)
            hoy = str(date.today())
            response_asignados = self.pg_manager.client.table('historial_lockers_diarios').select(
                'id_locker'
            ).eq('fecha_asignacion', hoy).eq('devuelto', False).execute()
            
            ids_asignados = {item['id_locker'] for item in (response_asignados.data or [])}
            
            # Filtrar solo lockers disponibles
            lockers_disponibles = [l for l in todos_lockers if l['id_locker'] not in ids_asignados]
            
            self.combo_locker.addItem("-- Seleccionar locker --", None)
            
            for locker in lockers_disponibles:
                display = f"Locker {locker['numero']} - Zona {locker['ubicacion'].split()[-1]}"
                self.combo_locker.addItem(display, locker['id_locker'])
        
        except Exception as e:
            logging.error(f"Error cargando lockers diarios: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los lockers: {str(e)}")
    
    def asignar_locker_diario(self):
        """Asignar locker diario al miembro seleccionado"""
        id_miembro = self.combo_miembro.currentData()
        id_locker = self.combo_locker.currentData()
        
        if not id_miembro:
            show_warning_dialog(self, "Validación", "Debe seleccionar un miembro")
            return
        
        if not id_locker:
            show_warning_dialog(self, "Validación", "Debe seleccionar un locker")
            return
        
        try:
            # Obtener hoy como fecha
            hoy = str(date.today())
            
            # Insertar en historial_lockers_diarios
            asignacion_data = {
                'id_miembro': id_miembro,
                'id_locker': id_locker,
                'fecha_asignacion': hoy,
                'hora_asignacion': datetime.now().isoformat(),
                'entregado': True,
                'devuelto': False
            }
            
            response = self.pg_manager.client.table('historial_lockers_diarios').insert(asignacion_data).execute()
            
            if response.data:
                nombre_miembro = self.combo_miembro.currentText()
                
                show_success_dialog(
                    self,
                    "Éxito",
                    f"Locker diario asignado a {nombre_miembro}"
                )
                
                logging.info(f"Locker diario asignado: Miembro {id_miembro}, Locker {id_locker}")
                self.accept()
            else:
                show_error_dialog(self, "Error", "No se pudo asignar el locker")
        
        except Exception as e:
            logging.error(f"Error asignando locker diario: {e}")
            show_error_dialog(self, "Error", f"No se pudo asignar el locker: {str(e)}")


# Alias para compatibilidad
AsignarLockerDiarioWindow = AsignarLockerDiarioWindow
