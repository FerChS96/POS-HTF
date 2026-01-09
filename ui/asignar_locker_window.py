"""
Ventana de Asignación de Lockers - Versión 2.0 (NUEVA)
Grid editable con asignaciones activas de lockers mensuales
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QHeaderView, QAbstractItemView,
    QMessageBox, QSpinBox, QDialog, QGridLayout
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QFont, QColor
import logging
from datetime import datetime, date

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


class AsignarLockerWindow(QWidget):
    """Ventana para gestionar asignaciones de lockers mensuales"""
    
    cerrar_solicitado = Signal()
    abrir_diarios_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.asignaciones_data = []
        self.cambios_pendientes = {}  # {id_asignacion: {'id_locker': nuevo_id, ...}}
        
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
        #title = SectionTitle("GESTIÓN DE LOCKERS MENSUALES")
        #layout.addWidget(title)
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Miembro",
            "Locker Actual",
            "Nuevo Locker",
            "Fecha Inicio",
            "Fecha Vencimiento",
            "Días Restantes"
        ])
        
        # Configurar tabla
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
        
        btn_diarios = TileButton("Ver Diarios", "fa5s.calendar-alt", WindowsPhoneTheme.TILE_MAGENTA)
        btn_diarios.clicked.connect(self.abrir_diarios_solicitado.emit)
        button_layout.addWidget(btn_diarios)
        
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_actualizar.clicked.connect(self.cargar_asignaciones)
        button_layout.addWidget(btn_actualizar)
        
        btn_guardar = TileButton("Guardar Cambios", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_guardar.clicked.connect(self.guardar_cambios)
        button_layout.addWidget(btn_guardar)
        
        layout.addLayout(button_layout)
    
    def cargar_asignaciones(self):
        """Cargar asignaciones activas de lockers mensuales (id_producto_digital = 9)"""
        try:
            # Consultar asignaciones activas de lockers mensuales
            response = self.pg_manager.client.table('asignaciones_activas').select(
                'id_asignacion, id_miembro, id_locker, fecha_inicio, fecha_fin, activa, '
                'miembros(nombres, apellido_paterno, apellido_materno), '
                'lockers(numero, ubicacion, tipo)'
            ).eq('id_producto_digital', 9).eq('activa', True).order('fecha_fin').execute()
            
            self.asignaciones_data = response.data or []
            self.cambios_pendientes = {}
            self.poblar_tabla()
            
            logging.info(f"Cargadas {len(self.asignaciones_data)} asignaciones de lockers")
            
        except Exception as e:
            show_error_dialog(self, "Error", f"No se pudieron cargar las asignaciones: {str(e)}")
            logging.error(f"Error cargando asignaciones: {e}")
    
    def poblar_tabla(self):
        """Llenar la tabla con las asignaciones"""
        self.table.setRowCount(0)
        hoy = date.today()
        
        for idx, asig in enumerate(self.asignaciones_data):
            self.table.insertRow(idx)
            self.table.setRowHeight(idx, 60)
            
            miembro = asig.get('miembros', {}) or {}
            locker = asig.get('lockers', {}) or {}
            
            nombre_completo = f"{miembro.get('nombres', '')} {miembro.get('apellido_paterno', '')} {miembro.get('apellido_materno', '')}".strip()
            numero_locker_actual = locker.get('numero', 'Sin asignar')
            fecha_inicio = asig.get('fecha_inicio', '')
            fecha_fin = asig.get('fecha_fin', '')
            
            # Calcular días restantes
            try:
                fecha_fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                dias_restantes = (fecha_fin_date - hoy).days
                if dias_restantes < 0:
                    color_dias = QColor('#ef4444')
                elif dias_restantes < 7:
                    color_dias = QColor('#f59e0b')
                else:
                    color_dias = QColor('#10b981')
            except:
                dias_restantes = 0
                color_dias = QColor('#666')
            
            # Columna 0: Miembro (solo lectura)
            item_miembro = QTableWidgetItem(nombre_completo)
            item_miembro.setFlags(item_miembro.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(idx, 0, item_miembro)
            
            # Columna 1: Locker actual (solo lectura)
            item_locker_actual = QTableWidgetItem(str(numero_locker_actual))
            item_locker_actual.setFlags(item_locker_actual.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(idx, 1, item_locker_actual)
            
            # Columna 2: Nuevo locker (ComboBox editable)
            combo_locker = QComboBox()
            combo_locker.setStyleSheet(f"""
                QComboBox {{
                    padding: 6px;
                    border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
                    border-radius: 4px;
                    background-color: white;
                    font-family: {WindowsPhoneTheme.FONT_FAMILY};
                    font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                }}
                QComboBox:focus {{
                    border: 2px solid {WindowsPhoneTheme.PRIMARY_BLUE};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 20px;
                }}
            """)
            self.cargar_lockers_mensuales(combo_locker, asig.get('id_locker'))
            combo_locker.currentIndexChanged.connect(
                lambda checked=False, row=idx: self.marcar_cambio(row)
            )
            self.table.setCellWidget(idx, 2, combo_locker)
            
            # Columna 3: Fecha inicio (solo lectura)
            item_inicio = QTableWidgetItem(fecha_inicio)
            item_inicio.setFlags(item_inicio.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(idx, 3, item_inicio)
            
            # Columna 4: Fecha vencimiento (solo lectura)
            item_fin = QTableWidgetItem(fecha_fin)
            item_fin.setFlags(item_fin.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(idx, 4, item_fin)
            
            # Columna 5: Días restantes (solo lectura, coloreado)
            item_dias = QTableWidgetItem(str(dias_restantes))
            item_dias.setFlags(item_dias.flags() & ~Qt.ItemIsEditable)
            item_dias.setForeground(color_dias)
            item_dias.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, 11, QFont.Bold))
            self.table.setItem(idx, 5, item_dias)
    
    def cargar_lockers_mensuales(self, combo, id_locker_actual=None):
        """Llenar combo con lockers de renta mensual disponibles (no asignados)"""
        try:
            # Obtener todos los lockers de renta mensual activos, ordenados ascendente por id
            response_todos = self.pg_manager.client.table('lockers').select(
                'id_locker, numero, ubicacion'
            ).eq('tipo', 'renta_mensual').eq('activo', True).order('id_locker', desc=False).execute()
            
            todos_lockers = response_todos.data or []
            
            # Obtener IDs de lockers ya asignados (activos)
            response_asignados = self.pg_manager.client.table('asignaciones_activas').select(
                'id_locker'
            ).eq('id_producto_digital', 9).eq('activa', True).execute()
            
            ids_asignados = {item['id_locker'] for item in (response_asignados.data or [])}
            
            # Filtrar solo lockers disponibles (no asignados) o que es el actual
            lockers_disponibles = [
                l for l in todos_lockers 
                if l['id_locker'] not in ids_asignados or l['id_locker'] == id_locker_actual
            ]
            
            # Mejorar estilo del combobox
            combo.setStyleSheet(f"""
                QComboBox {{
                    padding: 8px;
                    border: 2px solid {WindowsPhoneTheme.BORDER_COLOR};
                    border-radius: 4px;
                    background-color: white;
                    font-family: {WindowsPhoneTheme.FONT_FAMILY};
                    font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                    color: {WindowsPhoneTheme.TEXT_PRIMARY};
                    min-height: 30px;
                }}
                QComboBox:focus {{
                    border: 2px solid {WindowsPhoneTheme.PRIMARY_BLUE};
                    background-color: #f9fafb;
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 25px;
                    padding-right: 5px;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid {WindowsPhoneTheme.PRIMARY_BLUE};
                }}
                QComboBox QAbstractItemView {{
                    border: 1px solid {WindowsPhoneTheme.BORDER_COLOR};
                    background-color: white;
                    selection-background-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                    padding: 4px;
                }}
                QComboBox QAbstractItemView::item {{
                    padding: 6px;
                    min-height: 25px;
                }}
            """)
            
            combo.addItem("-- Seleccionar locker --", None)
            
            # Agregar lockers disponibles ordenados
            for locker in lockers_disponibles:
                display = f"Locker {locker['numero']} - Zona {locker['ubicacion'].split()[-1]}"
                combo.addItem(display, locker['id_locker'])
            
            # Preseleccionar locker actual
            if id_locker_actual:
                for i in range(combo.count()):
                    if combo.itemData(i) == id_locker_actual:
                        combo.setCurrentIndex(i)
                        break
        
        except Exception as e:
            logging.error(f"Error cargando lockers mensuales disponibles: {e}")
    
    def marcar_cambio(self, row):
        """Marcar que hay un cambio pendiente en esta fila"""
        if row < len(self.asignaciones_data):
            asig = self.asignaciones_data[row]
            id_asignacion = asig['id_asignacion']
            
            combo = self.table.cellWidget(row, 2)
            nuevo_id_locker = combo.currentData()
            
            if nuevo_id_locker is not None:
                self.cambios_pendientes[id_asignacion] = {
                    'id_locker': nuevo_id_locker
                }
            elif id_asignacion in self.cambios_pendientes:
                del self.cambios_pendientes[id_asignacion]
    
    def guardar_cambios(self):
        """Guardar los cambios de lockers"""
        if not self.cambios_pendientes:
            show_warning_dialog(self, "Sin cambios", "No hay cambios para guardar")
            return
        
        try:
            # Confirmar cambios
            if not show_confirmation_dialog(
                self,
                "Confirmar",
                f"¿Guardar {len(self.cambios_pendientes)} cambio(s)?"
            ):
                return
            
            # Actualizar cada asignación
            for id_asignacion, cambios in self.cambios_pendientes.items():
                self.pg_manager.client.table('asignaciones_activas').update(
                    cambios
                ).eq('id_asignacion', id_asignacion).execute()
            
            show_success_dialog(
                self,
                "Éxito",
                f"{len(self.cambios_pendientes)} locker(s) actualizado(s) correctamente"
            )
            
            self.cambios_pendientes = {}
            self.cargar_asignaciones()
            
            logging.info(f"Guardados {len(self.cambios_pendientes)} cambios")
            
        except Exception as e:
            show_error_dialog(self, "Error", f"No se pudieron guardar los cambios: {str(e)}")
            logging.error(f"Error guardando cambios: {e}")


# Alias para compatibilidad con importaciones existentes
AsignacionesLockersWindow = AsignarLockerWindow
