"""
Ventana de Historial de Uso de Lockers para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDateEdit, QSizePolicy, QComboBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QFont
import logging
from datetime import datetime
import qtawesome as qta

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    CompactNavButton,
    create_page_layout,
    ContentPanel,
    StyledLabel,
    SearchBar,
    show_info_dialog,
    show_warning_dialog,
    aplicar_estilo_fecha
)


class HistorialLockersWindow(QWidget):
    """Widget para ver historial de uso de lockers"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.lockers_data = []  # Almacenar todas las asignaciones cargadas
        self.lockers_filtrados = []  # Asignaciones después de aplicar filtros
        self.pagina_actual = 0
        self.items_por_pagina = 50
        
        # Timer para detectar entrada del escáner
        self.scanner_timer = QTimer()
        self.scanner_timer.setSingleShot(True)
        self.scanner_timer.setInterval(300)  # 300ms después de que deje de escribir
        self.scanner_timer.timeout.connect(self.aplicar_filtros)
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Configurar interfaz de historial"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido
        content = QWidget()
        content_layout = create_page_layout("HISTORIAL DE LOCKERS")
        content.setLayout(content_layout)
        
        # Buscador
        self.search_bar = SearchBar("Buscar por miembro, locker o ID asignación...")
        self.search_bar.connect_search(self.on_search_changed)
        content_layout.addWidget(self.search_bar)
        
        # Filtros
        self.create_filters(content_layout)
        
        # Tabla
        self.create_history_table(content_layout)
        
        # Panel de información y paginación
        self.create_info_buttons_panel(content_layout)
        
        # Botones
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_exportar = TileButton("Exportar", "fa5s.download", WindowsPhoneTheme.TILE_GREEN)
        btn_exportar.clicked.connect(self.exportar_datos)
        
        btn_cerrar = TileButton("Cerrar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cerrar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_exportar)
        buttons_layout.addWidget(btn_cerrar)
        
        content_layout.addLayout(buttons_layout)
        layout.addWidget(content)
        
        # Cargar datos iniciales
        self.cargar_historial_completo()
        
    def create_filters(self, parent_layout):
        """Crear filtros de búsqueda"""
        filters_panel = ContentPanel()
        filters_layout = QHBoxLayout(filters_panel)
        filters_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Fecha desde
        desde_container = QWidget()
        desde_layout = QVBoxLayout(desde_container)
        desde_layout.setContentsMargins(0, 0, 0, 0)
        desde_layout.setSpacing(4)
        desde_label = StyledLabel("Desde:", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        desde_layout.addWidget(desde_label)
        self.fecha_desde = QDateEdit()
        self.fecha_desde.setDate(QDate.currentDate().addDays(-30))
        self.fecha_desde.setCalendarPopup(True)
        self.fecha_desde.setMinimumHeight(40)
        self.fecha_desde.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.fecha_desde.dateChanged.connect(self.cargar_historial_completo)
        aplicar_estilo_fecha(self.fecha_desde)
        desde_layout.addWidget(self.fecha_desde)
        filters_layout.addWidget(desde_container, stretch=1)
        
        # Fecha hasta
        hasta_container = QWidget()
        hasta_layout = QVBoxLayout(hasta_container)
        hasta_layout.setContentsMargins(0, 0, 0, 0)
        hasta_layout.setSpacing(4)
        hasta_label = StyledLabel("Hasta:", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        hasta_layout.addWidget(hasta_label)
        self.fecha_hasta = QDateEdit()
        self.fecha_hasta.setDate(QDate.currentDate())
        self.fecha_hasta.setCalendarPopup(True)
        self.fecha_hasta.setMinimumHeight(40)
        self.fecha_hasta.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.fecha_hasta.dateChanged.connect(self.cargar_historial_completo)
        aplicar_estilo_fecha(self.fecha_hasta)
        hasta_layout.addWidget(self.fecha_hasta)
        filters_layout.addWidget(hasta_container, stretch=1)
        
        # Filtro por tipo de locker
        tipo_container = QWidget()
        tipo_layout = QVBoxLayout(tipo_container)
        tipo_layout.setContentsMargins(0, 0, 0, 0)
        tipo_layout.setSpacing(4)
        tipo_label = StyledLabel("Tipo:", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        tipo_layout.addWidget(tipo_label)
        self.tipo_combo = QComboBox()
        self.tipo_combo.setMinimumHeight(40)
        self.tipo_combo.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.tipo_combo.addItems(["Todos", "Mensual", "Diario"])
        self.tipo_combo.currentTextChanged.connect(self.aplicar_filtros)
        tipo_layout.addWidget(self.tipo_combo)
        filters_layout.addWidget(tipo_container, stretch=1)
        
        # Botón limpiar filtros
        btn_limpiar_container = QWidget()
        btn_limpiar_layout = QVBoxLayout(btn_limpiar_container)
        btn_limpiar_layout.setContentsMargins(0, 0, 0, 0)
        btn_limpiar_layout.setSpacing(4)
        limpiar_spacer = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        btn_limpiar_layout.addWidget(limpiar_spacer)
        btn_limpiar = QPushButton("Limpiar")
        btn_limpiar.setMinimumHeight(40)
        btn_limpiar.setMinimumWidth(100)
        btn_limpiar.setObjectName("tileButton")
        btn_limpiar.setProperty("tileColor", WindowsPhoneTheme.TILE_ORANGE)
        btn_limpiar.clicked.connect(self.limpiar_filtros)
        btn_limpiar_layout.addWidget(btn_limpiar)
        filters_layout.addWidget(btn_limpiar_container)
        
        parent_layout.addWidget(filters_panel)
        
    def create_history_table(self, parent_layout):
        """Crear tabla de historial"""
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Miembro", "Locker", "Tipo", 
            "Fecha Inicio", "Fecha Fin", "Cancelada", "Hora Cancelación"
        ])
        
        # Configurar para que no sea editable
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        
        parent_layout.addWidget(self.history_table)
    
    def create_info_buttons_panel(self, parent_layout):
        """Crear panel de información con paginación integrada"""
        info_panel = ContentPanel()
        info_layout = QHBoxLayout(info_panel)
        info_layout.setSpacing(8)
        
        # Etiqueta de información (con paginación integrada)
        self.info_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        info_layout.addWidget(self.info_label, stretch=1)
        
        # Botones de paginación
        self.btn_pagina_anterior = CompactNavButton(
            "Anterior",
            "fa5s.chevron-left",
            WindowsPhoneTheme.TILE_BLUE,
            icon_position="left"
        )
        self.btn_pagina_anterior.setToolTip("Página anterior")
        self.btn_pagina_anterior.clicked.connect(self.pagina_anterior)
        info_layout.addWidget(self.btn_pagina_anterior)
        
        self.btn_proxima_pagina = CompactNavButton(
            "Siguiente",
            "fa5s.chevron-right",
            WindowsPhoneTheme.TILE_BLUE,
            icon_position="right"
        )
        self.btn_proxima_pagina.setToolTip("Página siguiente")
        self.btn_proxima_pagina.clicked.connect(self.proxima_pagina)
        info_layout.addWidget(self.btn_proxima_pagina)
        
        parent_layout.addWidget(info_panel)
    
    def actualizar_pagination_buttons(self):
        """Actualizar estado de botones de paginación e info"""
        total_paginas = (len(self.lockers_filtrados) + self.items_por_pagina - 1) // self.items_por_pagina
        
        self.btn_pagina_anterior.setEnabled(self.pagina_actual > 0)
        self.btn_proxima_pagina.setEnabled(self.pagina_actual < total_paginas - 1)
        
        inicio = self.pagina_actual * self.items_por_pagina + 1
        fin = min((self.pagina_actual + 1) * self.items_por_pagina, len(self.lockers_filtrados))
        total_filtrados = len(self.lockers_filtrados)
        total_disponibles = len(self.lockers_data)
        
        # Actualizar label con información completa
        if total_filtrados > 0:
            if total_paginas > 1:
                self.info_label.setText(
                    f"Página {self.pagina_actual + 1}/{total_paginas} | Mostrando {inicio}-{fin} de {total_filtrados} | "
                    f"Disponibles: {total_disponibles}"
                )
            else:
                self.info_label.setText(
                    f"Total: {total_filtrados} asignaciones | Disponibles: {total_disponibles}"
                )
        else:
            self.info_label.setText("No hay registros")
    
    def pagina_anterior(self):
        """Ir a la página anterior"""
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.mostrar_pagina_actual()
    
    def proxima_pagina(self):
        """Ir a la siguiente página"""
        total_paginas = (len(self.lockers_filtrados) + self.items_por_pagina - 1) // self.items_por_pagina
        if self.pagina_actual < total_paginas - 1:
            self.pagina_actual += 1
            self.mostrar_pagina_actual()
    
    def mostrar_pagina_actual(self):
        """Mostrar la página actual de asignaciones"""
        inicio = self.pagina_actual * self.items_por_pagina
        fin = inicio + self.items_por_pagina
        lockers_pagina = self.lockers_filtrados[inicio:fin]
        self.actualizar_tabla(lockers_pagina, mostrar_paginacion=True)
    
    def on_search_changed(self):
        """Reiniciar timer cuando cambia el texto de búsqueda"""
        self.scanner_timer.start()
    
    def limpiar_filtros(self):
        """Limpiar todos los filtros"""
        self.search_bar.clear()
        self.tipo_combo.setCurrentIndex(0)
        self.fecha_desde.setDate(QDate.currentDate().addDays(-30))
        self.fecha_hasta.setDate(QDate.currentDate())
        self.cargar_historial_completo()
    
    def cargar_historial_completo(self):
        """Cargar historial completo de asignaciones de lockers desde la base de datos"""
        try:
            fecha_desde = self.fecha_desde.date().toPython()
            fecha_hasta = self.fecha_hasta.date().toPython()
            
            # Consultar asignaciones que se solapan con el rango de fechas seleccionado
            # fecha_inicio <= fecha_hasta AND fecha_fin >= fecha_desde
            response = self.pg_manager.client.table('asignaciones_activas').select(
                '''id_asignacion, 
                   id_miembro, 
                   id_locker, 
                   id_producto_digital,
                   fecha_inicio, 
                   fecha_fin, 
                   cancelada, 
                   fecha_cancelacion,
                   miembros(nombres, apellido_paterno, apellido_materno),
                   lockers(numero)
                '''
            ).in_('id_producto_digital', [9, 19]).lte(
                'fecha_inicio', f'{fecha_hasta}'
            ).gte(
                'fecha_fin', f'{fecha_desde}'
            ).order('fecha_inicio', desc=True).execute()
            
            self.lockers_data = response.data or []
            
            # Aplicar filtros
            self.aplicar_filtros()
            
        except Exception as e:
            logging.error(f"Error cargando historial de lockers: {e}")
            show_warning_dialog(self, "Error", f"Error al cargar historial: {e}")
            
            self.lockers_data = response.data or []
            
            # Aplicar filtros
            self.aplicar_filtros()
            
        except Exception as e:
            logging.error(f"Error cargando historial de lockers: {e}")
            show_warning_dialog(self, "Error", f"Error al cargar historial: {e}")
    
    def aplicar_filtros(self):
        """Aplicar filtros a los datos de asignaciones"""
        try:
            # Obtener texto de búsqueda
            search_text = self.search_bar.text().lower().strip()
            tipo_filtro = self.tipo_combo.currentText()
            
            # Filtrar datos
            self.lockers_filtrados = self.lockers_data
            
            # Filtro por tipo de locker
            if tipo_filtro and tipo_filtro != "Todos":
                if tipo_filtro == "Mensual":
                    self.lockers_filtrados = [
                        l for l in self.lockers_filtrados 
                        if l.get('id_producto_digital') == 9
                    ]
                elif tipo_filtro == "Diario":
                    self.lockers_filtrados = [
                        l for l in self.lockers_filtrados 
                        if l.get('id_producto_digital') == 19
                    ]
            
            # Filtro por búsqueda de texto
            if search_text:
                self.lockers_filtrados = [
                    l for l in self.lockers_filtrados
                    if (
                        search_text in str(l.get('id_asignacion', '')).lower() or
                        search_text in str(l.get('id_locker', '')).lower() or
                        (l.get('miembros') and search_text in f"{l['miembros'].get('nombres', '')} {l['miembros'].get('apellido_paterno', '')} {l['miembros'].get('apellido_materno', '')}".lower()) or
                        (l.get('lockers') and search_text in str(l['lockers'].get('numero', '')).lower())
                    )
                ]
            
            # Resetear paginación cuando se aplican filtros
            self.pagina_actual = 0
            self.mostrar_pagina_actual()
            
        except Exception as e:
            logging.error(f"Error aplicando filtros: {e}")
    
    def actualizar_tabla(self, asignaciones, mostrar_paginacion=False):
        """Actualizar tabla con las asignaciones filtradas"""
        try:
            self.history_table.setRowCount(len(asignaciones))
            
            for row, asignacion in enumerate(asignaciones):
                self.history_table.setRowHeight(row, 55)
                
                # Miembro
                miembro_nombres = ""
                if asignacion.get('miembros') and isinstance(asignacion['miembros'], dict):
                    miembro = asignacion['miembros']
                    miembro_nombres = f"{miembro.get('nombres', '')} {miembro.get('apellido_paterno', '')} {miembro.get('apellido_materno', '')}".strip()
                self.history_table.setItem(row, 0, QTableWidgetItem(miembro_nombres))
                
                # Locker
                locker_numero = "N/A"
                if asignacion.get('lockers') and isinstance(asignacion['lockers'], dict):
                    locker_numero = f"Locker {asignacion['lockers'].get('numero', 'N/A')}"
                self.history_table.setItem(row, 1, QTableWidgetItem(locker_numero))
                
                # Tipo de locker
                tipo = "Mensual" if asignacion.get('id_producto_digital') == 9 else "Diario"
                self.history_table.setItem(row, 2, QTableWidgetItem(tipo))
                
                # Fecha inicio
                fecha_inicio = asignacion.get('fecha_inicio', 'N/A')
                self.history_table.setItem(row, 3, QTableWidgetItem(str(fecha_inicio)))
                
                # Fecha fin
                fecha_fin = asignacion.get('fecha_fin', 'N/A')
                self.history_table.setItem(row, 4, QTableWidgetItem(str(fecha_fin)))
                
                # Cancelada (Sí/No)
                cancelada = "Sí" if asignacion.get('cancelada') else "No"
                self.history_table.setItem(row, 5, QTableWidgetItem(cancelada))
                
                # Hora de cancelación (dividiendo el timestamp)
                hora_cancelacion = "N/A"
                if asignacion.get('fecha_cancelacion'):
                    fecha_cancel_str = asignacion['fecha_cancelacion']
                    try:
                        # Parsear string ISO
                        if isinstance(fecha_cancel_str, str):
                            fecha_cancel_obj = datetime.fromisoformat(fecha_cancel_str.replace('Z', '+00:00'))
                            hora_cancelacion = fecha_cancel_obj.strftime("%d/%m/%Y %H:%M:%S")
                    except Exception as e:
                        logging.warning(f"Error parseando fecha cancelación: {e}")
                        hora_cancelacion = str(fecha_cancel_str)
                
                self.history_table.setItem(row, 6, QTableWidgetItem(hora_cancelacion))
            
            # Actualizar información y paginación
            self.actualizar_pagination_buttons()
            
        except Exception as e:
            logging.error(f"Error actualizando tabla: {e}")
            show_warning_dialog(self, "Error", f"Error al actualizar tabla: {e}")
    
    def exportar_datos(self):
        """Exportar datos a CSV (placeholder)"""
        try:
            show_info_dialog(self, "Exportar", "Funcionalidad de exportación en desarrollo")
        except Exception as e:
            logging.error(f"Error exportando datos: {e}")
            show_warning_dialog(self, "Error", f"Error al exportar: {e}")
