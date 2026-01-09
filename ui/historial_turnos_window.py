"""
Ventana de Historial de Turnos de Caja para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QSizePolicy, QFrame,
    QComboBox, QDateEdit, QLabel
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QFont
from datetime import datetime, timedelta
from decimal import Decimal
import logging

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    SearchBar,
    show_info_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_success_dialog,
    aplicar_estilo_fecha
)


class HistorialTurnosWindow(QWidget):
    """Widget para ver el historial completo de turnos de caja"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data
        self.turnos_data = []
        self.turnos_filtrados = []
        
        self.setup_ui()
        self.cargar_turnos()
    
    def setup_ui(self):
        """Configurar interfaz del historial"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # El título viene del TopBar, no duplicar aquí
        # title = SectionTitle("")
        # layout.addWidget(title)
        
        # Panel de filtros
        filters_panel = self.create_filters_panel()
        layout.addWidget(filters_panel)
        
        # Panel para la tabla
        table_panel = self.create_table_panel()
        layout.addWidget(table_panel)
        
        # Panel de información y botones
        info_buttons_panel = self.create_info_buttons_panel()
        layout.addLayout(info_buttons_panel)
    
    def create_filters_panel(self):
        """Crear el panel de filtros"""
        filters_panel = ContentPanel()
        filters_layout = QVBoxLayout(filters_panel)
        
        # Primera fila de filtros
        filters_row1 = QHBoxLayout()
        filters_row1.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Buscador
        self.search_bar = SearchBar("Buscar por usuario...")
        self.search_bar.connect_search(self.aplicar_filtros)
        filters_row1.addWidget(self.search_bar, stretch=2)
        
        # Filtro por estado
        estado_container = self.create_estado_filter()
        filters_row1.addWidget(estado_container, stretch=1)
        
        filters_layout.addLayout(filters_row1)
        
        # Segunda fila - Rango de fechas
        filters_row2 = self.create_fecha_filters()
        filters_layout.addLayout(filters_row2)
        
        return filters_panel
    
    def create_estado_filter(self):
        """Crear filtro de estado del turno"""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(5)
        
        label = StyledLabel("Estado:", bold=True)
        container_layout.addWidget(label)
        
        self.estado_combo = QComboBox()
        self.estado_combo.addItems(["Todos", "Abiertos", "Cerrados"])
        
        # Estilo consistente con personal_window
        input_style = f"""
            QComboBox {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QComboBox:focus {{
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
        self.estado_combo.setStyleSheet(input_style)
        self.estado_combo.setMinimumHeight(40)
        self.estado_combo.currentIndexChanged.connect(self.aplicar_filtros)
        container_layout.addWidget(self.estado_combo)
        
        return container
    
    def create_fecha_filters(self):
        """Crear filtros de rango de fechas"""
        fecha_layout = QHBoxLayout()
        fecha_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Estilo para inputs de fecha
        input_style = f"""
            QDateEdit {{
                padding: 8px;
                border: 2px solid #e5e7eb;
                border-radius: 4px;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
                background-color: white;
            }}
            QDateEdit:focus {{
                border-color: {WindowsPhoneTheme.TILE_BLUE};
            }}
        """
        
        # Fecha inicio
        fecha_inicio_container = QWidget()
        fecha_inicio_layout = QVBoxLayout(fecha_inicio_container)
        fecha_inicio_layout.setContentsMargins(0, 0, 0, 0)
        fecha_inicio_layout.setSpacing(5)
        
        label_inicio = StyledLabel("Desde:", bold=True)
        fecha_inicio_layout.addWidget(label_inicio)
        
        self.fecha_inicio = QDateEdit()
        self.fecha_inicio.setCalendarPopup(True)
        self.fecha_inicio.setDate(QDate.currentDate().addDays(-30))
        aplicar_estilo_fecha(self.fecha_inicio)
        self.fecha_inicio.setMinimumHeight(40)
        self.fecha_inicio.dateChanged.connect(self.aplicar_filtros)
        fecha_inicio_layout.addWidget(self.fecha_inicio)
        
        fecha_layout.addWidget(fecha_inicio_container, stretch=1)
        
        # Fecha fin
        fecha_fin_container = QWidget()
        fecha_fin_layout = QVBoxLayout(fecha_fin_container)
        fecha_fin_layout.setContentsMargins(0, 0, 0, 0)
        fecha_fin_layout.setSpacing(5)
        
        label_fin = StyledLabel("Hasta:", bold=True)
        fecha_fin_layout.addWidget(label_fin)
        
        self.fecha_fin = QDateEdit()
        self.fecha_fin.setCalendarPopup(True)
        self.fecha_fin.setDate(QDate.currentDate())
        aplicar_estilo_fecha(self.fecha_fin)
        self.fecha_fin.setMinimumHeight(40)
        self.fecha_fin.dateChanged.connect(self.aplicar_filtros)
        fecha_fin_layout.addWidget(self.fecha_fin)
        
        fecha_layout.addWidget(fecha_fin_container, stretch=1)
        
        # Botón limpiar filtros
        btn_limpiar = TileButton("Limpiar", "fa5s.eraser", WindowsPhoneTheme.TILE_ORANGE)
        btn_limpiar.setMaximumHeight(90)
        btn_limpiar.clicked.connect(self.limpiar_filtros)
        fecha_layout.addWidget(btn_limpiar, stretch=1)
        
        return fecha_layout
    
    def create_table_panel(self):
        """Crear panel con la tabla de turnos"""
        table_panel = ContentPanel()
        table_layout = QVBoxLayout(table_panel)
        
        # Tabla
        self.tabla_turnos = QTableWidget()
        self.tabla_turnos.setColumnCount(10)
        self.tabla_turnos.setHorizontalHeaderLabels([
            "ID", "Usuario", "Apertura", "Cierre", "Monto Inicial",
            "Ventas Efectivo", "Monto Esperado", "Monto Real", "Diferencia", "Estado"
        ])
        
        # Configurar tabla
        self.tabla_turnos.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_turnos.setSelectionMode(QTableWidget.SingleSelection)
        self.tabla_turnos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_turnos.verticalHeader().setVisible(False)
        
        # Ajustar columnas
        header = self.tabla_turnos.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Usuario
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Apertura
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Cierre
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Monto Inicial
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Ventas
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Esperado
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Real
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Diferencia
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # Estado
        
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
        
        # Conectar doble clic para ver detalles
        self.tabla_turnos.itemDoubleClicked.connect(self.mostrar_detalles_turno)
        
        table_layout.addWidget(self.tabla_turnos)
        
        return table_panel
    
    def create_info_buttons_panel(self):
        """Crear panel de información y botones"""
        panel_layout = QHBoxLayout()
        panel_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        # Label de total de registros
        self.label_total = StyledLabel("Total de turnos: 0", bold=True)
        panel_layout.addWidget(self.label_total)
        
        panel_layout.addStretch()
        
        # Botón refrescar
        btn_refrescar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_BLUE)
        btn_refrescar.setMaximumHeight(120)
        btn_refrescar.clicked.connect(self.cargar_turnos)
        panel_layout.addWidget(btn_refrescar)
        
        # Botón volver
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.setMaximumHeight(120)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        panel_layout.addWidget(btn_volver)
        
        return panel_layout
    
    def cargar_turnos(self):
        """Cargar turnos desde la base de datos"""
        try:
            response = self.pg_manager.client.table('turnos_caja').select(
                '*, usuarios(nombre_completo)'
            ).order('fecha_apertura', desc=True).execute()
            
            # Procesar datos para tener nombre_usuario disponible
            self.turnos_data = []
            for turno in (response.data or []):
                # Extraer nombre del usuario del objeto anidado
                if 'usuarios' in turno and turno['usuarios']:
                    turno['nombre_usuario'] = turno['usuarios'].get('nombre_completo', 'N/A')
                else:
                    turno['nombre_usuario'] = 'N/A'
                self.turnos_data.append(turno)
            
            self.aplicar_filtros()
                
        except Exception as e:
            logging.error(f"Error cargando turnos: {e}")
            show_error_dialog(self, "Error", f"No se pudieron cargar los turnos: {e}")
    
    def aplicar_filtros(self):
        """Aplicar filtros a los datos de turnos"""
        # Obtener valores de filtros
        texto_busqueda = self.search_bar.text().strip().lower()
        estado_filtro = self.estado_combo.currentText()
        fecha_inicio = self.fecha_inicio.date().toPython()
        fecha_fin = self.fecha_fin.date().toPython()
        
        # Filtrar datos
        self.turnos_filtrados = []
        for turno in self.turnos_data:
            # Filtro de búsqueda por usuario
            if texto_busqueda and texto_busqueda not in turno['nombre_usuario'].lower():
                continue
            
            # Filtro de estado
            if estado_filtro == "Abiertos" and turno['cerrado']:
                continue
            elif estado_filtro == "Cerrados" and not turno['cerrado']:
                continue
            
            # Filtro de fechas
            if turno['fecha_apertura']:
                try:
                    # Convertir string a datetime si es necesario
                    if isinstance(turno['fecha_apertura'], str):
                        fecha_apertura = datetime.fromisoformat(turno['fecha_apertura'].replace('Z', '+00:00')).date()
                    else:
                        fecha_apertura = turno['fecha_apertura'].date()
                    
                    if fecha_apertura < fecha_inicio or fecha_apertura > fecha_fin:
                        continue
                except Exception as e:
                    logging.error(f"Error procesando fecha de turno: {e}")
                    continue
            
            self.turnos_filtrados.append(turno)
        
        # Actualizar tabla
        self.actualizar_tabla()
    
    def actualizar_tabla(self):
        """Actualizar contenido de la tabla"""
        self.tabla_turnos.setRowCount(len(self.turnos_filtrados))
        
        for row_idx, turno in enumerate(self.turnos_filtrados):
            # ID
            self.tabla_turnos.setItem(row_idx, 0, QTableWidgetItem(str(turno['id_turno'])))
            
            # Usuario
            self.tabla_turnos.setItem(row_idx, 1, QTableWidgetItem(turno['nombre_usuario']))
            
            # Fecha apertura
            if turno['fecha_apertura']:
                try:
                    if isinstance(turno['fecha_apertura'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_apertura'].replace('Z', '+00:00'))
                        fecha_apertura = fecha_obj.strftime("%d/%m/%Y %H:%M")
                    else:
                        fecha_apertura = turno['fecha_apertura'].strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_apertura = str(turno['fecha_apertura'])
            else:
                fecha_apertura = ""
            self.tabla_turnos.setItem(row_idx, 2, QTableWidgetItem(fecha_apertura))
            
            # Fecha cierre
            if turno['fecha_cierre']:
                try:
                    if isinstance(turno['fecha_cierre'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_cierre'].replace('Z', '+00:00'))
                        fecha_cierre = fecha_obj.strftime("%d/%m/%Y %H:%M")
                    else:
                        fecha_cierre = turno['fecha_cierre'].strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_cierre = str(turno['fecha_cierre'])
            else:
                fecha_cierre = "ABIERTO"
            item_cierre = QTableWidgetItem(fecha_cierre)
            if not turno['cerrado']:
                item_cierre.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
            self.tabla_turnos.setItem(row_idx, 3, item_cierre)
            
            # Monto inicial
            monto_inicial = f"${float(turno['monto_inicial']):.2f}" if turno['monto_inicial'] is not None else "$0.00"
            self.tabla_turnos.setItem(row_idx, 4, QTableWidgetItem(monto_inicial))
            
            # Ventas efectivo
            ventas = f"${float(turno['total_ventas_efectivo']):.2f}" if turno['total_ventas_efectivo'] is not None else "$0.00"
            self.tabla_turnos.setItem(row_idx, 5, QTableWidgetItem(ventas))
            
            # Monto esperado
            esperado = f"${float(turno['monto_esperado']):.2f}" if turno['monto_esperado'] is not None else "$0.00"
            self.tabla_turnos.setItem(row_idx, 6, QTableWidgetItem(esperado))
            
            # Monto real
            if turno['monto_real_cierre'] is not None:
                real = f"${float(turno['monto_real_cierre']):.2f}"
            else:
                real = "-"
            self.tabla_turnos.setItem(row_idx, 7, QTableWidgetItem(real))
            
            # Diferencia
            if turno['diferencia'] is not None:
                diferencia_valor = float(turno['diferencia'])
                diferencia = f"${diferencia_valor:.2f}"
                item_diferencia = QTableWidgetItem(diferencia)
                
                # Colorear según si hay faltante o sobrante
                if diferencia_valor < 0:
                    item_diferencia.setForeground(Qt.red)
                    item_diferencia.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
                elif diferencia_valor > 0:
                    item_diferencia.setForeground(Qt.darkGreen)
                
                self.tabla_turnos.setItem(row_idx, 8, item_diferencia)
            else:
                self.tabla_turnos.setItem(row_idx, 8, QTableWidgetItem("-"))
            
            # Estado
            estado = "CERRADO" if turno['cerrado'] else "ABIERTO"
            item_estado = QTableWidgetItem(estado)
            if not turno['cerrado']:
                item_estado.setForeground(Qt.darkGreen)
                item_estado.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
            self.tabla_turnos.setItem(row_idx, 9, item_estado)
        
        # Actualizar label de total
        self.label_total.setText(f"Total de turnos: {len(self.turnos_filtrados)}")
    
    def mostrar_detalles_turno(self, item):
        """Mostrar detalles completos del turno seleccionado"""
        row = item.row()
        if row < 0 or row >= len(self.turnos_filtrados):
            return
        
        turno = self.turnos_filtrados[row]
        
        # Construir mensaje de detalles
        detalles = f"TURNO #{turno['id_turno']}\n"
        detalles += f"Usuario: {turno['nombre_usuario']}\n\n"
        
        detalles += "--- APERTURA ---\n"
        # Convertir fecha_apertura si es string
        if turno['fecha_apertura']:
            try:
                if isinstance(turno['fecha_apertura'], str):
                    fecha_obj = datetime.fromisoformat(turno['fecha_apertura'].replace('Z', '+00:00'))
                    fecha_apertura_str = fecha_obj.strftime('%d/%m/%Y %H:%M')
                else:
                    fecha_apertura_str = turno['fecha_apertura'].strftime('%d/%m/%Y %H:%M')
            except:
                fecha_apertura_str = str(turno['fecha_apertura'])
        else:
            fecha_apertura_str = "N/A"
        detalles += f"Fecha: {fecha_apertura_str}\n"
        detalles += f"Monto inicial: ${float(turno['monto_inicial']):.2f}\n\n"
        
        if turno['cerrado']:
            detalles += "--- CIERRE ---\n"
            # Convertir fecha_cierre si es string
            if turno['fecha_cierre']:
                try:
                    if isinstance(turno['fecha_cierre'], str):
                        fecha_obj = datetime.fromisoformat(turno['fecha_cierre'].replace('Z', '+00:00'))
                        fecha_cierre_str = fecha_obj.strftime('%d/%m/%Y %H:%M')
                    else:
                        fecha_cierre_str = turno['fecha_cierre'].strftime('%d/%m/%Y %H:%M')
                except:
                    fecha_cierre_str = str(turno['fecha_cierre'])
            else:
                fecha_cierre_str = "N/A"
            detalles += f"Fecha: {fecha_cierre_str}\n"
            detalles += f"Ventas en efectivo: ${float(turno['total_ventas_efectivo']):.2f}\n"
            detalles += f"Monto esperado: ${float(turno['monto_esperado']):.2f}\n"
            detalles += f"Monto real: ${float(turno['monto_real_cierre']):.2f}\n"
            
            diferencia = float(turno['diferencia'])
            estado_dif = "SOBRANTE" if diferencia > 0 else "FALTANTE" if diferencia < 0 else "EXACTO"
            detalles += f"Diferencia: ${abs(diferencia):.2f} ({estado_dif})\n\n"
        else:
            detalles += "--- ESTADO ---\n"
            detalles += "TURNO ABIERTO\n\n"
        
        # Mostrar notas si existen
        if turno.get('notas_apertura'):
            detalles += "--- NOTAS ---\n"
            detalles += turno['notas_apertura']
        
        show_info_dialog(self, f"Detalles del Turno #{turno['id_turno']}", detalles)
    
    def limpiar_filtros(self):
        """Limpiar todos los filtros"""
        self.search_bar.clear()
        self.estado_combo.setCurrentIndex(0)
        self.fecha_inicio.setDate(QDate.currentDate().addDays(-30))
        self.fecha_fin.setDate(QDate.currentDate())
        self.aplicar_filtros()
