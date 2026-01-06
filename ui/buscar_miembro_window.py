"""
Ventana de Búsqueda de Miembros para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QSizePolicy, QFrame,
    QLabel, QDialog, QGridLayout, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QDate, QThread  # Eliminado pyqtSignal
from PySide6.QtGui import QFont
from datetime import datetime, date, timedelta
import logging

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
    show_error_dialog
)


class DetalleMiembroDialog(QDialog):
    """Diálogo para mostrar información detallada de un miembro"""
    
    def __init__(self, miembro_data, parent=None):
        super().__init__(parent)
        self.miembro_data = miembro_data
        self.setWindowTitle("Detalle de Miembro")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz del diálogo"""
        layout = QVBoxLayout(self)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Título
        nombre_completo = f"{self.miembro_data.get('nombres', '')} {self.miembro_data.get('apellido_paterno', '')} {self.miembro_data.get('apellido_materno', '')}".strip()
        titulo = StyledLabel(
            nombre_completo,
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_TITLE
        )
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)
        
        # Panel de información
        info_panel = ContentPanel()
        info_layout = QGridLayout(info_panel)
        info_layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        info_layout.setColumnStretch(1, 1)
        
        row = 0
        
        # Información básica
        self._add_info_row(info_layout, row, "Código:", self.miembro_data.get('codigo_miembro', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Fecha de Nacimiento:", self.miembro_data.get('fecha_nacimiento', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Teléfono:", self.miembro_data.get('telefono', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Email:", self.miembro_data.get('email', 'N/A'))
        row += 1
        
        # Separador
        separador = QFrame()
        separador.setFrameShape(QFrame.HLine)
        separador.setStyleSheet(f"background-color: {WindowsPhoneTheme.BORDER_COLOR};")
        info_layout.addWidget(separador, row, 0, 1, 2)
        row += 1
        
        # Contacto de emergencia
        self._add_info_row(info_layout, row, "Contacto Emergencia:", self.miembro_data.get('contacto_emergencia', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Tel. Emergencia:", self.miembro_data.get('telefono_emergencia', 'N/A'))
        row += 1
        
        # Separador
        separador2 = QFrame()
        separador2.setFrameShape(QFrame.HLine)
        separador2.setStyleSheet(f"background-color: {WindowsPhoneTheme.BORDER_COLOR};")
        info_layout.addWidget(separador2, row, 0, 1, 2)
        row += 1
        
        # Estado y membresía
        estado = "ACTIVO" if self.miembro_data.get('activo', False) else "INACTIVO"
        estado_color = WindowsPhoneTheme.TILE_GREEN if self.miembro_data.get('activo', False) else WindowsPhoneTheme.TILE_RED
        estado_label = StyledLabel(estado, bold=True, size=WindowsPhoneTheme.FONT_SIZE_SUBTITLE)
        estado_label.setStyleSheet(f"color: {estado_color};")
        self._add_info_row(info_layout, row, "Estado:", estado_label)
        row += 1
        
        self._add_info_row(info_layout, row, "Membresía:", self.miembro_data.get('membresia', 'Sin membresía'))
        row += 1
        self._add_info_row(info_layout, row, "Vencimiento:", self.miembro_data.get('fecha_fin_membresia', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Locker:", self.miembro_data.get('locker', 'Sin locker'))
        row += 1
        
        # Separador
        separador3 = QFrame()
        separador3.setFrameShape(QFrame.HLine)
        separador3.setStyleSheet(f"background-color: {WindowsPhoneTheme.BORDER_COLOR};")
        info_layout.addWidget(separador3, row, 0, 1, 2)
        row += 1
        
        # Fechas de registro
        self._add_info_row(info_layout, row, "Fecha de Registro:", self.miembro_data.get('fecha_registro', 'N/A'))
        row += 1
        self._add_info_row(info_layout, row, "Código QR:", self.miembro_data.get('codigo_qr', 'N/A'))
        
        layout.addWidget(info_panel)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        btn_registrar_acceso = TileButton("Registrar Acceso", "fa5s.sign-in-alt", WindowsPhoneTheme.TILE_GREEN)
        btn_ver_historial = TileButton("Ver Historial", "fa5s.history", WindowsPhoneTheme.TILE_BLUE)
        btn_cerrar = TileButton("Cerrar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cerrar.clicked.connect(self.accept)
        
        buttons_layout.addWidget(btn_registrar_acceso)
        buttons_layout.addWidget(btn_ver_historial)
        buttons_layout.addWidget(btn_cerrar)
        
        layout.addLayout(buttons_layout)
    
    def _add_info_row(self, layout, row, label_text, value_widget_or_text):
        """Agregar una fila de información al grid"""
        label = StyledLabel(label_text, bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(label, row, 0)
        
        if isinstance(value_widget_or_text, QWidget):
            layout.addWidget(value_widget_or_text, row, 1)
        else:
            value_label = StyledLabel(str(value_widget_or_text), size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
            layout.addWidget(value_label, row, 1)


class MiembrosLoaderThread(QThread):
    """Hilo para cargar miembros de forma asíncrona"""
    
    miembros_loaded = Signal(list)  # Cambiado de pyqtSignal a Signal
    error_occurred = Signal(str)   # Cambiado de pyqtSignal a Signal
    
    def __init__(self, supabase_service):
        super().__init__()
        self.supabase_service = supabase_service
    
    def run(self):
        """Cargar miembros desde Supabase en un hilo separado"""
        try:
            if self.supabase_service and self.supabase_service.is_connected:
                response = self.supabase_service.client.table('miembros')\
                    .select('''
                        *,
                        asignaciones_activas(
                            fecha_inicio,
                            fecha_fin,
                            activa,
                            cancelada,
                            id_producto_digital,
                            ca_productos_digitales(nombre, tipo)
                        )
                    ''')\
                    .order('nombres')\
                    .execute()
                
                rows = response.data if response.data else []
                self.miembros_loaded.emit(rows)
            else:
                self.error_occurred.emit("No hay conexión a Supabase")
        except Exception as e:
            self.error_occurred.emit(str(e))


class BuscarMiembroWindow(QWidget):
    """Widget para buscar y gestionar miembros"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, db_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.miembros_data = []
        self.miembros_filtrados = []
        self.loader_thread = None
        
        self.setup_ui()
        self.cargar_miembros()
    
    def setup_ui(self):
        """Configurar interfaz de búsqueda"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Contenido
        content = QWidget()
        content_layout = create_page_layout("BUSCAR MIEMBRO")
        content.setLayout(content_layout)
        
        # Panel de búsqueda y filtros
        search_panel = ContentPanel()
        search_layout = QHBoxLayout(search_panel)
        search_layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Buscador
        self.search_bar = SearchBar("Buscar por nombre, código o teléfono...")
        self.search_bar.connect_search(self.aplicar_filtros)
        search_layout.addWidget(self.search_bar, stretch=3)
        
        # Checkbox solo activos
        self.check_solo_activos = QCheckBox("Solo activos")
        self.check_solo_activos.setChecked(True)
        self.check_solo_activos.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.check_solo_activos.stateChanged.connect(self.aplicar_filtros)
        search_layout.addWidget(self.check_solo_activos)
        
        # Checkbox con membresía vigente
        self.check_membresia_vigente = QCheckBox("Con membresía vigente")
        self.check_membresia_vigente.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL))
        self.check_membresia_vigente.stateChanged.connect(self.aplicar_filtros)
        search_layout.addWidget(self.check_membresia_vigente)
        
        content_layout.addWidget(search_panel)
        
        # Panel para la tabla
        table_panel = ContentPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        
        # Tabla de miembros
        self.miembros_table = QTableWidget()
        self.miembros_table.setColumnCount(8)
        self.miembros_table.setHorizontalHeaderLabels([
            "Código", "Nombre Completo", "Teléfono", "Email", 
            "Membresía", "Vencimiento", "Locker", "Estado Membresía"
        ])
        
        # Configurar header
        header = self.miembros_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        
        # Estilo de la tabla
        self.miembros_table.setAlternatingRowColors(True)
        self.miembros_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.miembros_table.setSelectionMode(QTableWidget.SingleSelection)
        self.miembros_table.verticalHeader().setVisible(False)
        self.miembros_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.miembros_table.doubleClicked.connect(self.mostrar_detalle_miembro)
        
        table_layout.addWidget(self.miembros_table)
        content_layout.addWidget(table_panel)
        
        # Panel de información y botones
        info_buttons_panel = ContentPanel()
        info_buttons_layout = QHBoxLayout(info_buttons_panel)
        
        # Etiqueta de información
        self.info_label = StyledLabel("", size=WindowsPhoneTheme.FONT_SIZE_SMALL)
        info_buttons_layout.addWidget(self.info_label, stretch=1)
        
        # Botones de acción
        btn_ver_detalle = TileButton("Ver Detalle", "fa5s.info-circle", WindowsPhoneTheme.TILE_BLUE)
        btn_ver_detalle.clicked.connect(self.mostrar_detalle_miembro)
        btn_ver_detalle.setMaximumWidth(200)
        info_buttons_layout.addWidget(btn_ver_detalle)
        
        btn_actualizar = TileButton("Actualizar", "fa5s.sync", WindowsPhoneTheme.TILE_GREEN)
        btn_actualizar.clicked.connect(self.cargar_miembros)
        btn_actualizar.setMaximumWidth(200)
        info_buttons_layout.addWidget(btn_actualizar)
        
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_RED)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        btn_volver.setMaximumWidth(200)
        info_buttons_layout.addWidget(btn_volver)
        
        content_layout.addWidget(info_buttons_panel)
        layout.addWidget(content)
    
    def cargar_miembros(self):
        """Cargar todos los miembros desde Supabase de forma asíncrona"""
        try:
            # Mostrar indicador de carga
            self.info_label.setText("Cargando miembros...")
            self.miembros_table.setRowCount(0)
            
            # Detener hilo anterior si existe
            if self.loader_thread and self.loader_thread.isRunning():
                self.loader_thread.terminate()
                self.loader_thread.wait()
            
            # Crear y ejecutar hilo de carga
            self.loader_thread = MiembrosLoaderThread(self.supabase_service)
            self.loader_thread.miembros_loaded.connect(self.procesar_datos_miembros)
            self.loader_thread.error_occurred.connect(self.mostrar_error_carga)
            self.loader_thread.start()
            
        except Exception as e:
            logging.error(f"Error iniciando carga de miembros: {e}")
            show_error_dialog(
                self,
                "Error al cargar",
                "No se pudieron cargar los miembros",
                detail=str(e)
            )
    
    def procesar_datos_miembros(self, rows):
        """Procesar los datos de miembros cargados desde Supabase"""
        try:
            self.miembros_data = []
            hoy = datetime.now().date()
            
            for row in rows:
                # Procesar fecha de nacimiento
                fecha_nacimiento = row.get('fecha_nacimiento')
                fecha_nacimiento_str = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').strftime('%d/%m/%Y') if fecha_nacimiento else "N/A"
                
                # Procesar fecha de registro
                fecha_registro = row.get('fecha_registro')
                fecha_registro_str = datetime.strptime(fecha_registro, '%Y-%m-%d').strftime('%d/%m/%Y') if fecha_registro else "N/A"
                
                # Obtener información de asignaciones activas (membresías y lockers)
                asignaciones = row.get('asignaciones_activas', [])
                membresia = None
                fecha_fin_membresia = None
                fecha_fin_membresia_str = "N/A"
                estado_vigencia = None
                estado_membresia = None
                
                # Separar asignaciones de membresías y lockers
                asignacion_membresia = None
                asignacion_locker = None  # Solo necesitamos saber si existe, no el número
                
                if asignaciones and len(asignaciones) > 0:
                    # Primera pasada: buscar lockers (id_producto_digital = 9)
                    for a in asignaciones:
                        if not a.get('activa') or a.get('cancelada'):
                            continue
                        
                        # Solo procesar asignaciones de locker mensual (id_producto_digital = 9)
                        id_producto = a.get('id_producto_digital')
                        if id_producto != 9:
                            continue
                        
                        # Verificar que las fechas estén dentro del rango
                        fecha_inicio_str = a.get('fecha_inicio')
                        fecha_fin_str_temp = a.get('fecha_fin')
                        
                        if not fecha_inicio_str or not fecha_fin_str_temp:
                            continue
                            
                        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                        fecha_fin_temp = datetime.strptime(fecha_fin_str_temp, '%Y-%m-%d').date()
                        
                        # La asignación es válida si hoy está entre fecha_inicio y fecha_fin
                        if fecha_inicio <= hoy <= fecha_fin_temp:
                            # Guardar solo si no tenemos uno o si este vence después
                            if not asignacion_locker or fecha_fin_temp > datetime.strptime(asignacion_locker['fecha_fin'], '%Y-%m-%d').date():
                                asignacion_locker = a
                    
                    # Segunda pasada: buscar membresías (id_producto_digital = 10 o 11)
                    for a in asignaciones:
                        if not a.get('activa') or a.get('cancelada'):
                            continue
                        
                        # Solo procesar asignaciones de membresía (id_producto_digital = 10 u 11)
                        id_producto = a.get('id_producto_digital')
                        if id_producto not in [10, 11]:
                            continue
                        
                        # Verificar que las fechas estén dentro del rango
                        fecha_inicio_str = a.get('fecha_inicio')
                        fecha_fin_str_temp = a.get('fecha_fin')
                        
                        if not fecha_inicio_str or not fecha_fin_str_temp:
                            continue
                            
                        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                        fecha_fin_temp = datetime.strptime(fecha_fin_str_temp, '%Y-%m-%d').date()
                        
                        # La asignación es válida si hoy está entre fecha_inicio y fecha_fin
                        if fecha_inicio <= hoy <= fecha_fin_temp:
                            # Guardar solo si no tenemos una o si esta vence después
                            if not asignacion_membresia or fecha_fin_temp > datetime.strptime(asignacion_membresia['fecha_fin'], '%Y-%m-%d').date():
                                asignacion_membresia = a
                    
                    # Procesar la asignación de membresía encontrada
                    if asignacion_membresia:
                        if asignacion_membresia.get('ca_productos_digitales'):
                            membresia = asignacion_membresia['ca_productos_digitales'].get('nombre')
                        
                        if asignacion_membresia.get('fecha_fin'):
                            fecha_fin_membresia = datetime.strptime(asignacion_membresia['fecha_fin'], '%Y-%m-%d').date()
                            fecha_fin_membresia_str = fecha_fin_membresia.strftime('%d/%m/%Y')
                            
                            # Calcular estado de vigencia basado en fecha_fin de la membresía
                            if fecha_fin_membresia < hoy:
                                estado_vigencia = 'vencida'
                                estado_membresia = 'Vencida'
                            elif fecha_fin_membresia <= (hoy + timedelta(days=7)):
                                estado_vigencia = 'por_vencer'
                                estado_membresia = 'Por vencer'
                            else:
                                estado_vigencia = 'vigente'
                                estado_membresia = 'Vigente'
                    
                    # Construir objeto de miembro
                self.miembros_data.append({
                    'id_miembro': row.get('id_miembro'),
                    'nombres': row.get('nombres', ''),
                    'apellidos': f"{row.get('apellido_paterno', '')} {row.get('apellido_materno', '')}".strip(),
                    'nombre_completo': f"{row.get('nombres', '')} {row.get('apellido_paterno', '')} {row.get('apellido_materno', '')}".strip(),
                    'telefono': row.get('telefono') or 'N/A',
                    'email': row.get('email') or 'N/A',
                    'contacto_emergencia': row.get('contacto_emergencia') or 'N/A',
                    'telefono_emergencia': row.get('telefono_emergencia') or 'N/A',
                    'codigo_qr': row.get('codigo_qr', ''),
                    'codigo_miembro': f"M-{row.get('id_miembro', 0):05d}",
                    'activo': row.get('activo', False),
                    'fecha_registro': fecha_registro_str,
                    'fecha_nacimiento': fecha_nacimiento_str,
                    'membresia': membresia or 'Sin membresía',
                    'fecha_fin_membresia': fecha_fin_membresia_str,
                    'estado_membresia': estado_membresia,
                    'locker': 'Locker asignado' if asignacion_locker else 'Sin locker',
                    'estado_vigencia': estado_vigencia
                })
            
            self.aplicar_filtros()
            logging.info(f"Miembros cargados desde Supabase: {len(self.miembros_data)}")
            
        except Exception as e:
            logging.error(f"Error procesando datos de miembros: {e}")
            show_error_dialog(
                self,
                "Error al procesar datos",
                "No se pudieron procesar los datos de los miembros",
                detail=str(e)
            )
    
    def mostrar_error_carga(self, error_msg):
        """Mostrar mensaje de error al cargar miembros"""
        logging.error(f"Error cargando miembros: {error_msg}")
        show_error_dialog(
            self,
            "Error al cargar",
            "No se pudieron cargar los miembros",
            detail=error_msg
        )
        self.info_label.setText("Error al cargar miembros")
    
    def aplicar_filtros(self):
        """Aplicar todos los filtros activos"""
        try:
            # Obtener criterios de filtro
            texto_busqueda = self.search_bar.text().strip().lower()
            solo_activos = self.check_solo_activos.isChecked()
            membresia_vigente = self.check_membresia_vigente.isChecked()
            
            # Filtrar datos
            self.miembros_filtrados = []
            for miembro in self.miembros_data:
                # Filtro de texto
                if texto_busqueda:
                    if not any([
                        texto_busqueda in miembro['nombre_completo'].lower(),
                        texto_busqueda in miembro['codigo_miembro'].lower(),
                        texto_busqueda in (miembro['telefono'] or '').lower(),
                        texto_busqueda in (miembro['email'] or '').lower()
                    ]):
                        continue
                
                # Filtro solo activos
                if solo_activos and not miembro['activo']:
                    continue
                
                # Filtro membresía vigente
                if membresia_vigente and miembro['estado_vigencia'] not in ['vigente', 'por_vencer']:
                    continue
                
                self.miembros_filtrados.append(miembro)
            
            self.mostrar_miembros(self.miembros_filtrados)
            
        except Exception as e:
            logging.error(f"Error aplicando filtros: {e}")
            self.mostrar_miembros(self.miembros_data)
    
    def mostrar_miembros(self, miembros):
        """Mostrar miembros en la tabla"""
        try:
            self.miembros_table.setRowCount(0)
            
            for miembro in miembros:
                row = self.miembros_table.rowCount()
                self.miembros_table.insertRow(row)
                
                # Código
                item_codigo = QTableWidgetItem(miembro['codigo_miembro'])
                item_codigo.setTextAlignment(Qt.AlignCenter)
                self.miembros_table.setItem(row, 0, item_codigo)
                
                # Nombre completo
                self.miembros_table.setItem(row, 1, QTableWidgetItem(miembro['nombre_completo']))
                
                # Teléfono
                item_telefono = QTableWidgetItem(miembro['telefono'])
                item_telefono.setTextAlignment(Qt.AlignCenter)
                self.miembros_table.setItem(row, 2, item_telefono)
                
                # Email
                self.miembros_table.setItem(row, 3, QTableWidgetItem(miembro['email']))
                
                # Membresía
                item_membresia = QTableWidgetItem(miembro['membresia'])
                item_membresia.setTextAlignment(Qt.AlignCenter)
                self.miembros_table.setItem(row, 4, item_membresia)
                
                # Vencimiento
                item_vencimiento = QTableWidgetItem(miembro['fecha_fin_membresia'])
                item_vencimiento.setTextAlignment(Qt.AlignCenter)
                
                # Color según estado de vigencia
                if miembro['estado_vigencia'] == 'vencida':
                    item_vencimiento.setForeground(Qt.darkRed)
                elif miembro['estado_vigencia'] == 'por_vencer':
                    item_vencimiento.setForeground(Qt.darkYellow)
                elif miembro['estado_vigencia'] == 'vigente':
                    item_vencimiento.setForeground(Qt.darkGreen)
                
                self.miembros_table.setItem(row, 5, item_vencimiento)
                
                # Locker
                item_locker = QTableWidgetItem(miembro['locker'])
                item_locker.setTextAlignment(Qt.AlignCenter)
                self.miembros_table.setItem(row, 6, item_locker)
                
                # Estado de Membresía (basado en asignación activa, no en estado del miembro)
                estado_membresia_texto = miembro.get('estado_membresia') or 'Sin membresía'
                item_estado = QTableWidgetItem(estado_membresia_texto)
                item_estado.setTextAlignment(Qt.AlignCenter)
                item_estado.setFont(QFont(WindowsPhoneTheme.FONT_FAMILY, WindowsPhoneTheme.FONT_SIZE_NORMAL, QFont.Bold))
                
                # Color según estado de la asignación
                if miembro['estado_vigencia'] == 'vigente':
                    item_estado.setForeground(Qt.darkGreen)
                elif miembro['estado_vigencia'] == 'por_vencer':
                    item_estado.setForeground(Qt.darkYellow)
                elif miembro['estado_vigencia'] == 'vencida':
                    item_estado.setForeground(Qt.darkRed)
                else:
                    # Sin membresía
                    item_estado.setForeground(Qt.gray)
                
                self.miembros_table.setItem(row, 7, item_estado)
            
            # Actualizar información
            total_miembros = len(miembros)
            total_general = len(self.miembros_data)
            activos = sum(1 for m in miembros if m['activo'])
            con_membresia = sum(1 for m in miembros if m['estado_vigencia'] in ['vigente', 'por_vencer'])
            
            if total_miembros == total_general:
                self.info_label.setText(
                    f"Total: {total_miembros} | Activos: {activos} | Con membresía: {con_membresia}"
                )
            else:
                self.info_label.setText(
                    f"Mostrando {total_miembros} de {total_general} | Activos: {activos} | Con membresía: {con_membresia}"
                )
            
            logging.info(f"Mostrando {total_miembros} miembros en tabla")
            
        except Exception as e:
            logging.error(f"Error mostrando miembros: {e}")
            show_error_dialog(
                self,
                "Error de visualización",
                "No se pudieron mostrar los miembros",
                detail=str(e)
            )
    
    def mostrar_detalle_miembro(self):
        """Mostrar diálogo con detalle completo del miembro seleccionado"""
        try:
            selected_rows = self.miembros_table.selectedItems()
            if not selected_rows:
                show_warning_dialog(
                    self,
                    "Sin selección",
                    "Por favor selecciona un miembro de la tabla"
                )
                return
            
            # Obtener el índice de la fila seleccionada
            row = self.miembros_table.currentRow()
            codigo_miembro = self.miembros_table.item(row, 0).text()
            
            # Buscar el miembro en los datos filtrados
            miembro_seleccionado = None
            for miembro in self.miembros_filtrados:
                if miembro['codigo_miembro'] == codigo_miembro:
                    miembro_seleccionado = miembro
                    break
            
            if miembro_seleccionado:
                dialog = DetalleMiembroDialog(miembro_seleccionado, self)
                dialog.exec()
            
        except Exception as e:
            logging.error(f"Error mostrando detalle: {e}")
            show_error_dialog(
                self,
                "Error",
                "No se pudo mostrar el detalle del miembro",
                detail=str(e)
            )
    
    def closeEvent(self, event):
        """Evento al cerrar la ventana"""
        # Detener hilo de carga si está activo
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.terminate()
            self.loader_thread.wait()
            
        super().closeEvent(event)