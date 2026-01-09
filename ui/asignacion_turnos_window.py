"""
Ventana de Asignación de Turnos de Caja para HTF POS
Permite crear y asignar turnos predefinidos a empleados
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QDateEdit, QLabel,
    QTimeEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QDate, QTime
from PySide6.QtGui import QFont
from datetime import datetime, timedelta, time
from decimal import Decimal
import logging

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_success_dialog,
    show_confirmation_dialog,
    TouchMoneyInput,
    aplicar_estilo_fecha
)


class AsignacionTurnosWindow(QWidget):
    """Widget para asignar turnos de caja a empleados"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.empleados = []
        self.turnos_asignados = []
        
        self.setup_ui()
        self.cargar_empleados()
        self.cargar_turnos_asignados()
    
    def setup_ui(self):
        """Configurar interfaz de asignación de turnos"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # El título viene del TopBar, no duplicar aquí
        # title = SectionTitle("")
        # layout.addWidget(title)
        
        # Layout horizontal para dos columnas
        content_layout = QHBoxLayout()
        content_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Columna izquierda: Panel de asignación
        asignacion_panel = self.create_asignacion_panel()
        content_layout.addWidget(asignacion_panel, stretch=1)
        
        # Columna derecha: Panel de turnos asignados
        tabla_panel = self.create_tabla_panel()
        content_layout.addWidget(tabla_panel, stretch=1)
        
        layout.addLayout(content_layout)
        
        # Panel de botones al pie
        buttons_panel = self.create_buttons_panel()
        layout.addLayout(buttons_panel)
    
    def create_asignacion_panel(self):
        """Crear panel de asignación de turnos"""
        panel = ContentPanel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # Título de sección
        title = StyledLabel("Crear Nuevo Turno", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(title)
        
        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        # Estilo para inputs
        input_style = f"""
            QDateEdit, QComboBox, QTimeEdit, QSpinBox {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QDateEdit:focus, QComboBox:focus, QTimeEdit:focus, QSpinBox:focus {{
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
        
        # Fecha
        label_fecha = StyledLabel("Fecha:", bold=True)
        grid.addWidget(label_fecha, row, 0)
        
        self.fecha_turno = QDateEdit()
        self.fecha_turno.setCalendarPopup(True)
        self.fecha_turno.setDate(QDate.currentDate())
        aplicar_estilo_fecha(self.fecha_turno)
        self.fecha_turno.setMinimumHeight(40)
        self.fecha_turno.dateChanged.connect(self.actualizar_turnos_fecha)
        grid.addWidget(self.fecha_turno, row, 1)
        row += 1
        
        # Empleado
        label_empleado = StyledLabel("Empleado:", bold=True)
        grid.addWidget(label_empleado, row, 0)
        
        self.empleado_combo = QComboBox()
        self.empleado_combo.setStyleSheet(input_style)
        self.empleado_combo.setMinimumHeight(40)
        grid.addWidget(self.empleado_combo, row, 1)
        row += 1
        
        # Turno
        label_turno = StyledLabel("Turno:", bold=True)
        grid.addWidget(label_turno, row, 0)
        
        self.turno_combo = QComboBox()
        self.turno_combo.addItems([
            "Matutino (06:00 - 14:00)",
            "Vespertino (14:00 - 22:00)",
            "Personalizado"
        ])
        self.turno_combo.setStyleSheet(input_style)
        self.turno_combo.setMinimumHeight(40)
        self.turno_combo.currentIndexChanged.connect(self.toggle_horario_personalizado)
        grid.addWidget(self.turno_combo, row, 1)
        row += 1
        
        # Hora inicio
        self.label_inicio = StyledLabel("Hora Inicio:", bold=True)
        grid.addWidget(self.label_inicio, row, 0)
        
        self.hora_inicio = QTimeEdit()
        self.hora_inicio.setTime(QTime(6, 0))
        self.hora_inicio.setMinimumHeight(40)
        self.hora_inicio.setDisplayFormat("HH:mm")
        self.hora_inicio.setStyleSheet(input_style)
        grid.addWidget(self.hora_inicio, row, 1)
        row += 1
        
        # Hora fin
        self.label_fin = StyledLabel("Hora Fin:", bold=True)
        grid.addWidget(self.label_fin, row, 0)
        
        self.hora_fin = QTimeEdit()
        self.hora_fin.setTime(QTime(14, 0))
        self.hora_fin.setMinimumHeight(40)
        self.hora_fin.setDisplayFormat("HH:mm")
        self.hora_fin.setStyleSheet(input_style)
        grid.addWidget(self.hora_fin, row, 1)
        row += 1
        
        # Monto inicial
        label_monto = StyledLabel("Monto Inicial $:", bold=True)
        grid.addWidget(label_monto, row, 0)
        
        self.monto_inicial = TouchMoneyInput(
            minimum=0.0,
            maximum=100000.0,
            decimals=2,
            default_value=None
        )
        grid.addWidget(self.monto_inicial, row, 1)
        row += 1
        
        panel_layout.addLayout(grid)
        
        # Ocultar horarios personalizados por defecto
        self.label_inicio.hide()
        self.hora_inicio.hide()
        self.label_fin.hide()
        self.hora_fin.hide()
        
        panel_layout.addStretch()
        
        # Botón crear turno
        btn_crear = TileButton("Crear Turno", "fa5s.calendar-plus", WindowsPhoneTheme.TILE_GREEN)
        btn_crear.setMaximumHeight(120)
        btn_crear.clicked.connect(self.crear_turno)
        panel_layout.addWidget(btn_crear)
        
        return panel
    
    def create_tabla_panel(self):
        """Crear panel con tabla de turnos asignados"""
        panel = ContentPanel()
        panel_layout = QVBoxLayout(panel)
        
        # Título
        title = StyledLabel("Turnos Programados", bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        panel_layout.addWidget(title)
        
        # Filtro de fecha
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        label_filtro = StyledLabel("Mostrar turnos desde:", bold=True)
        filter_layout.addWidget(label_filtro)
        
        self.fecha_filtro = QDateEdit()
        self.fecha_filtro.setCalendarPopup(True)
        self.fecha_filtro.setDate(QDate.currentDate())
        aplicar_estilo_fecha(self.fecha_filtro)
        self.fecha_filtro.setMinimumHeight(40)
        self.fecha_filtro.dateChanged.connect(self.cargar_turnos_asignados)
        filter_layout.addWidget(self.fecha_filtro)
        
        filter_layout.addStretch()
        
        panel_layout.addLayout(filter_layout)
        
        # Tabla
        self.tabla_turnos = QTableWidget()
        self.tabla_turnos.setColumnCount(7)
        self.tabla_turnos.setHorizontalHeaderLabels([
            "Fecha", "Empleado", "Hora Inicio", "Hora Fin", 
            "Monto Inicial", "Estado", "Acciones"
        ])
        
        # Configurar tabla
        self.tabla_turnos.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_turnos.setSelectionMode(QTableWidget.SingleSelection)
        self.tabla_turnos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_turnos.verticalHeader().setVisible(False)
        
        # Ajustar columnas
        header = self.tabla_turnos.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Fecha
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Empleado
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Hora Inicio
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Hora Fin
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Monto
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Estado
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Acciones
        
        # Aplicar estilos a la tabla (consistente con personal_window)
        self.tabla_turnos.setStyleSheet(f"""
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
        
        panel_layout.addWidget(self.tabla_turnos)
        
        return panel
    
    def create_buttons_panel(self):
        """Crear panel de botones"""
        panel_layout = QHBoxLayout()
        panel_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        panel_layout.addStretch()
        
        # Botón actualizar
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_actualizar.setMaximumHeight(120)
        btn_actualizar.clicked.connect(self.cargar_turnos_asignados)
        panel_layout.addWidget(btn_actualizar)
        
        # Botón volver
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.setMaximumHeight(120)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        panel_layout.addWidget(btn_volver)
        
        return panel_layout
    
    def toggle_horario_personalizado(self):
        """Mostrar/ocultar campos de horario personalizado"""
        es_personalizado = self.turno_combo.currentIndex() == 2
        
        self.label_inicio.setVisible(es_personalizado)
        self.hora_inicio.setVisible(es_personalizado)
        self.label_fin.setVisible(es_personalizado)
        self.hora_fin.setVisible(es_personalizado)
        
        # Actualizar horarios según el turno seleccionado
        if not es_personalizado:
            if self.turno_combo.currentIndex() == 0:  # Matutino
                self.hora_inicio.setTime(QTime(6, 0))
                self.hora_fin.setTime(QTime(14, 0))
            elif self.turno_combo.currentIndex() == 1:  # Vespertino
                self.hora_inicio.setTime(QTime(14, 0))
                self.hora_fin.setTime(QTime(22, 0))
    
    def cargar_empleados(self):
        """Cargar lista de empleados activos"""
        try:
            # Obtener empleados activos
            response = self.pg_manager.client.table('usuarios').select('id_usuario, nombre_completo, nombre_usuario').eq('activo', True).order('nombre_completo').execute()
            self.empleados = response.data if response.data else []
            
            self.empleado_combo.clear()
            for empleado in self.empleados:
                self.empleado_combo.addItem(
                    f"{empleado['nombre_completo']} (@{empleado['nombre_usuario']})",
                    empleado['id_usuario']
                )
                
        except Exception as e:
            logging.error(f"Error cargando empleados: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los empleados: {e}")
    
    def cargar_turnos_asignados(self):
        """Cargar turnos asignados desde la fecha filtro"""
        try:
            fecha_desde = self.fecha_filtro.date().toPython()
            
            # Obtener turnos desde la fecha
            response = self.pg_manager.client.table('turnos_caja').select('id_turno, id_usuario, fecha_apertura, monto_inicial, cerrado, fecha_cierre').gte('fecha_apertura', str(fecha_desde)).order('fecha_apertura', desc=True).execute()
            
            turnos_raw = response.data if response.data else []
            self.turnos_asignados = []
            
            for turno in turnos_raw:
                # Obtener datos del usuario
                response_usuario = self.pg_manager.client.table('usuarios').select('nombre_completo').eq('id_usuario', turno['id_usuario']).single().execute()
                usuario = response_usuario.data if response_usuario.data else {}
                
                # Construir registro completo
                turno_completo = turno.copy()
                turno_completo['nombre_completo'] = usuario.get('nombre_completo', 'Desconocido')
                self.turnos_asignados.append(turno_completo)
                self.actualizar_tabla()
                
        except Exception as e:
            logging.error(f"Error cargando turnos asignados: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los turnos: {e}")
    
    def actualizar_tabla(self):
        """Actualizar contenido de la tabla de turnos"""
        self.tabla_turnos.setRowCount(len(self.turnos_asignados))
        
        for row_idx, turno in enumerate(self.turnos_asignados):
            self.tabla_turnos.setRowHeight(row_idx, 55)
            
            # Fecha - convertir de string si es necesario
            if turno['fecha_apertura']:
                try:
                    if isinstance(turno['fecha_apertura'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_apertura'].replace('Z', '+00:00'))
                        fecha = fecha_obj.strftime("%d/%m/%Y")
                    else:
                        fecha = turno['fecha_apertura'].strftime("%d/%m/%Y")
                except:
                    fecha = str(turno['fecha_apertura'])
            else:
                fecha = ""
            self.tabla_turnos.setItem(row_idx, 0, QTableWidgetItem(fecha))
            
            # Empleado
            self.tabla_turnos.setItem(row_idx, 1, QTableWidgetItem(turno['nombre_completo']))
            
            # Hora inicio - convertir de string si es necesario
            if turno['fecha_apertura']:
                try:
                    if isinstance(turno['fecha_apertura'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_apertura'].replace('Z', '+00:00'))
                        hora_inicio = fecha_obj.strftime("%H:%M")
                    else:
                        hora_inicio = turno['fecha_apertura'].strftime("%H:%M")
                except:
                    hora_inicio = str(turno['fecha_apertura'])
            else:
                hora_inicio = ""
            self.tabla_turnos.setItem(row_idx, 2, QTableWidgetItem(hora_inicio))
            
            # Hora fin (si está cerrado) - convertir de string si es necesario
            if turno['fecha_cierre']:
                try:
                    if isinstance(turno['fecha_cierre'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_cierre'].replace('Z', '+00:00'))
                        hora_fin = fecha_obj.strftime("%H:%M")
                    else:
                        hora_fin = turno['fecha_cierre'].strftime("%H:%M")
                except:
                    hora_fin = str(turno['fecha_cierre'])
            else:
                hora_fin = "-"
            self.tabla_turnos.setItem(row_idx, 3, QTableWidgetItem(hora_fin))
            
            # Monto inicial
            monto = f"${float(turno['monto_inicial']):.2f}"
            self.tabla_turnos.setItem(row_idx, 4, QTableWidgetItem(monto))
            
            # Estado
            estado = "CERRADO" if turno['cerrado'] else "ABIERTO"
            item_estado = QTableWidgetItem(estado)
            if not turno['cerrado']:
                item_estado.setForeground(Qt.darkGreen)
                item_estado.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
            self.tabla_turnos.setItem(row_idx, 5, item_estado)
            
            # Botón eliminar (solo si no está cerrado)
            if not turno['cerrado']:
                btn_eliminar = QPushButton("Eliminar")
                btn_eliminar.setMinimumHeight(30)
                btn_eliminar.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {WindowsPhoneTheme.TILE_RED};
                        color: white;
                        border: none;
                        border-radius: 3px;
                    }}
                    QPushButton:hover {{
                        background-color: #b30f00;
                    }}
                """)
                btn_eliminar.clicked.connect(lambda checked, id_t=turno['id_turno']: self.eliminar_turno(id_t))
                self.tabla_turnos.setCellWidget(row_idx, 6, btn_eliminar)
            else:
                self.tabla_turnos.setItem(row_idx, 6, QTableWidgetItem(""))
    
    def actualizar_turnos_fecha(self):
        """Sincronizar fecha del filtro con la fecha de creación"""
        self.fecha_filtro.setDate(self.fecha_turno.date())
    
    def crear_turno(self):
        """Crear y asignar un nuevo turno"""
        try:
            # Validar empleado seleccionado
            if self.empleado_combo.currentIndex() < 0:
                show_warning_dialog(self, "Advertencia", "Debe seleccionar un empleado")
                return
            
            id_usuario = self.empleado_combo.currentData()
            fecha_turno = self.fecha_turno.date().toPython()
            monto_inicial = self.monto_inicial.value()
            
            # Obtener horarios
            hora_inicio = self.hora_inicio.time().toPython()
            hora_fin = self.hora_fin.time().toPython()
            
            # Validar que hora fin sea después de hora inicio
            if hora_fin <= hora_inicio:
                show_warning_dialog(self, "Advertencia", "La hora de fin debe ser posterior a la hora de inicio")
                return
            
            # Crear datetime completos
            fecha_apertura = datetime.combine(fecha_turno, hora_inicio)
            
            # Verificar si ya existe un turno para ese usuario en esa fecha
            response = self.pg_manager.client.table('turnos_caja').select('id_turno').eq('id_usuario', id_usuario).eq('cerrado', False).execute()
            turnos_mismo_dia = [t for t in (response.data or []) if t.get('fecha_apertura', '').startswith(str(fecha_turno))]
            
            if len(turnos_mismo_dia) > 0:
                show_warning_dialog(
                    self, 
                    "Advertencia", 
                    "Ya existe un turno abierto para este empleado en esta fecha"
                )
                return
            
            # Confirmar creación
            turno_nombre = self.turno_combo.currentText()
            empleado_nombre = self.empleado_combo.currentText()
            
            if not show_confirmation_dialog(
                self,
                "Confirmar Turno",
                f"¿Crear turno para {empleado_nombre}?",
                detail=f"Fecha: {fecha_turno.strftime('%d/%m/%Y')}\n"
                       f"Turno: {turno_nombre}\n"
                       f"Horario: {hora_inicio.strftime('%H:%M')} - {hora_fin.strftime('%H:%M')}\n"
                       f"Monto inicial: ${monto_inicial:.2f}"
            ):
                return
            
            # Insertar turno
            turno_data = {
                'id_usuario': id_usuario,
                'fecha_apertura': str(fecha_apertura),
                'monto_inicial': monto_inicial,
                'monto_esperado': monto_inicial,  # Inicialmente el esperado es igual al inicial
                'notas_apertura': f"Turno {turno_nombre}",
                'cerrado': False
            }
            self.pg_manager.client.table('turnos_caja').insert(turno_data).execute()
            
            show_success_dialog(self, "Éxito", "Turno creado y asignado correctamente")
            
            # Recargar turnos
            self.cargar_turnos_asignados()
                
        except Exception as e:
            logging.error(f"Error creando turno: {e}")
            show_error_dialog(self, "Error", f"No se pudo crear el turno: {e}")
    
    def eliminar_turno(self, id_turno):
        """Eliminar un turno programado que no ha iniciado"""
        try:
            if not show_confirmation_dialog(
                self,
                "Confirmar Eliminación",
                "¿Está seguro de eliminar este turno programado?"
            ):
                return
            
            # Verificar que el turno no esté cerrado
            response = self.pg_manager.client.table('turnos_caja').select('cerrado').eq('id_turno', id_turno).single().execute()
            turno = response.data if response.data else None
            
            if turno and turno.get('cerrado'):
                show_warning_dialog(self, "Advertencia", "No se puede eliminar un turno cerrado")
                return
            
            # Eliminar turno
            self.pg_manager.client.table('turnos_caja').delete().eq('id_turno', id_turno).execute()
            
            show_success_dialog(self, "Éxito", "Turno eliminado correctamente")
            
            # Recargar tabla
            self.cargar_turnos_asignados()
                
        except Exception as e:
            logging.error(f"Error eliminando turno: {e}")
            show_error_dialog(self, "Error", f"No se pudo eliminar el turno: {e}")
