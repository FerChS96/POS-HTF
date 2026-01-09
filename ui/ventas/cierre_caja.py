"""
Ventana de Cierre de Caja para HTF POS
Usando componentes reutilizables del sistema de diseño
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QGridLayout,
    QTextEdit, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QDoubleValidator
import logging
from datetime import date, datetime, time, timedelta

# Importar componentes del sistema de diseño
from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    InfoTile,
    SectionTitle,
    ContentPanel,
    StyledLabel,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog
)
from database.postgres_manager import PostgresManager


class CierreCajaWindow(QWidget):
    """Widget para cierre de caja"""
    
    cerrar_solicitado = Signal()
    
    def __init__(self, pg_manager, supabase_service, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.supabase_service = supabase_service
        self.user_data = user_data
        self.turno_abierto = None
        
        # Configurar política de tamaño
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Verificar si hay turno abierto antes de mostrar UI
        if not self.verificar_turno_abierto():
            self.mostrar_sin_turno()
        else:
            self.setup_ui()
    
    def verificar_turno_abierto(self):
        """Verificar si el usuario tiene un turno abierto"""
        try:
            response = self.pg_manager.client.table('turnos_caja').select(
                'id_turno, monto_inicial, fecha_apertura'
            ).eq('id_usuario', self.user_data['id_usuario']).eq(
                'cerrado', False
            ).order('fecha_apertura', desc=True).limit(1).execute()
            
            if response.data and len(response.data) > 0:
                self.turno_abierto = response.data[0]
                return True
            return False
                
        except Exception as e:
            logging.error(f"Error verificando turno abierto: {e}")
            return False
    
    def mostrar_sin_turno(self):
        """Mostrar mensaje cuando no hay turno abierto"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE,
                                 WindowsPhoneTheme.MARGIN_LARGE)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_MEDIUM)
        
        # Panel de información
        info_panel = ContentPanel()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(40, 40, 40, 40)
        info_layout.setSpacing(20)
        
        # Icono y título
        title = StyledLabel(
            "NO HAY TURNO ABIERTO",
            bold=True,
            size=WindowsPhoneTheme.FONT_SIZE_TITLE
        )
        title.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(title)
        
        # Mensaje
        mensaje = StyledLabel(
            "No tienes un turno abierto actualmente.\n\n"
            "Para cerrar caja primero debes tener un turno activo.\n"
            "Contacta al administrador para que te asigne un turno.",
            size=WindowsPhoneTheme.FONT_SIZE_NORMAL
        )
        mensaje.setAlignment(Qt.AlignCenter)
        mensaje.setWordWrap(True)
        info_layout.addWidget(mensaje)
        
        layout.addWidget(info_panel)
        layout.addStretch()
        
        # Botón volver
        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_BLUE)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        layout.addWidget(btn_volver)
        
    def setup_ui(self):
        """Configurar interfaz de cierre de caja"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM,
                                 WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        
        # 1. Sección de conteo de efectivo primero
        self.create_cash_count_section(layout)
        
        # 2. Resumen en una fila (esperado, transacciones, contado)
        self.create_summary_section(layout)
        
        # 3. Espaciador flexible antes de los botones
        layout.addStretch()
        
        # 4. Botones al final
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        btn_cerrar_caja = TileButton("Cerrar Caja", "fa5s.lock", WindowsPhoneTheme.TILE_GREEN)
        btn_cerrar_caja.clicked.connect(self.procesar_cierre)
        
        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.cerrar_solicitado.emit)
        
        buttons_layout.addWidget(btn_cerrar_caja)
        buttons_layout.addWidget(btn_cancelar)
        
        layout.addLayout(buttons_layout)
        
        # Cargar datos iniciales
        self.cargar_resumen()
        
    def create_cash_count_section(self, parent_layout):
        """Crear sección de conteo de efectivo simplificada"""
        cash_panel = ContentPanel()
        cash_layout = QVBoxLayout(cash_panel)
        cash_layout.setContentsMargins(20, 20, 20, 20)
        cash_layout.setSpacing(15)
        
        # Título
        #title = SectionTitle("")
        #cash_layout.addWidget(title)
        
        # Grid simplificado
        form_layout = QGridLayout()
        form_layout.setSpacing(15)
        form_layout.setColumnStretch(1, 1)
        
        # Efectivo en caja
        label_efectivo = StyledLabel("Efectivo en caja:", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        form_layout.addWidget(label_efectivo, 0, 0, Qt.AlignTop)
        
        self.efectivo_input = QLineEdit()
        self.efectivo_input.setPlaceholderText("0.00")
        
        # Limitar a 8 caracteres máximo (99999.99)
        self.efectivo_input.setMaxLength(8)
        
        # Validador para limitar a 99,999.99 máximo con 2 decimales
        validator = QDoubleValidator(0.0, 99999.99, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.efectivo_input.setValidator(validator)
        
        self.efectivo_input.textChanged.connect(self.calcular_diferencia)
        self.efectivo_input.setMinimumHeight(45)
        self.efectivo_input.setMaximumHeight(50)
        form_layout.addWidget(self.efectivo_input, 0, 1)
        
        # Notas
        label_notas = StyledLabel("Notas:", bold=True, size=WindowsPhoneTheme.FONT_SIZE_NORMAL)
        form_layout.addWidget(label_notas, 1, 0, Qt.AlignTop)
        
        self.notas_input = QTextEdit()
        self.notas_input.setPlaceholderText("Observaciones del cierre de caja...")
        self.notas_input.setMinimumHeight(80)
        self.notas_input.setMaximumHeight(100)
        form_layout.addWidget(self.notas_input, 1, 1)
        
        cash_layout.addLayout(form_layout)
        
        parent_layout.addWidget(cash_panel)
        
    def create_summary_section(self, parent_layout):
        """Crear sección de resumen en una fila"""
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(WindowsPhoneTheme.TILE_SPACING)
        
        # Total esperado
        self.esperado_tile = InfoTile("TOTAL ESPERADO", "fa5s.dollar-sign", WindowsPhoneTheme.TILE_BLUE)
        self.esperado_tile.setMinimumHeight(140)
        self.esperado_value = self.esperado_tile.add_main_value("$0.00")
        self.esperado_tile.add_secondary_value("según ventas")
        summary_layout.addWidget(self.esperado_tile)
        
        # Número de ventas
        self.ventas_tile = InfoTile("TRANSACCIONES", "fa5s.shopping-cart", WindowsPhoneTheme.TILE_GREEN)
        self.ventas_tile.setMinimumHeight(140)
        self.ventas_value = self.ventas_tile.add_main_value("0")
        self.ventas_tile.add_secondary_value("ventas realizadas")
        summary_layout.addWidget(self.ventas_tile)
        
        # Total contado
        self.total_tile = InfoTile("TOTAL CONTADO", "fa5s.money-bill", WindowsPhoneTheme.TILE_ORANGE)
        self.total_tile.setMinimumHeight(140)
        self.total_contado = self.total_tile.add_main_value("$0.00")
        self.diferencia_label = self.total_tile.add_secondary_value("Diferencia: $0.00")
        summary_layout.addWidget(self.total_tile)
        
        parent_layout.addLayout(summary_layout)
        
    def cargar_resumen(self):
        """Cargar resumen del turno actual"""
        try:
            if not self.turno_abierto:
                logging.warning("No hay turno abierto para cargar resumen")
                self.total_esperado_valor = 0.0
                return
            
            # Obtener monto inicial del turno
            monto_inicial = float(self.turno_abierto.get('monto_inicial', 0))
            
            # Obtener ventas del turno actual usando Supabase
            response = self.pg_manager.client.table('ventas').select(
                'id_venta, fecha, total, usuarios(nombre_completo)'
            ).eq('id_turno', self.turno_abierto['id_turno']).order('fecha', desc=True).execute()
            
            ventas = response.data or []
            total_ventas_turno = sum(float(v.get('total', 0)) for v in ventas)
            num_ventas = len(ventas)
            
            # Total esperado = monto inicial + ventas del turno
            total_esperado = monto_inicial + total_ventas_turno
            
            # Actualizar widgets
            self.esperado_value.setText(f"${total_esperado:.2f}")
            self.ventas_value.setText(str(num_ventas))
            
            # Guardar valores para cálculos
            self.total_esperado_valor = total_esperado
            
            logging.info(f"Resumen del turno: Inicial=${monto_inicial:.2f}, Ventas=${total_ventas_turno:.2f}, Esperado=${total_esperado:.2f}")
            
        except Exception as e:
            logging.error(f"Error cargando resumen: {e}")
            self.total_esperado_valor = 0.0
            
    def calcular_diferencia(self):
        """Calcular diferencia entre esperado y contado"""
        try:
            # Solo efectivo
            efectivo_texto = self.efectivo_input.text()
            
            # Validar que no esté vacío
            if not efectivo_texto:
                efectivo = 0.0
            else:
                efectivo = float(efectivo_texto)
                
                # Validación adicional de límite
                if efectivo > 99999.99:
                    efectivo = 99999.99
                    self.efectivo_input.setText(f"{efectivo:.2f}")
                elif efectivo < 0:
                    efectivo = 0.0
                    self.efectivo_input.setText("0.00")
            
            # Calcular total
            total = efectivo
            
            # Actualizar total contado
            self.total_contado.setText(f"${total:.2f}")
            self.total_contado_valor = total
            
            # Calcular diferencia
            diferencia = total - self.total_esperado_valor
            signo = "+" if diferencia >= 0 else ""
            self.diferencia_label.setText(f"Diferencia: {signo}${diferencia:.2f}")
            
        except ValueError:
            # Si hay un error de conversión, resetear a 0
            self.efectivo_input.setText("0.00")
            self.total_contado.setText("$0.00")
            self.total_contado_valor = 0.0
            self.diferencia_label.setText("Diferencia: $0.00")
    
    def verificar_horario_turno(self):
        """Verificar si el cierre está dentro del horario esperado del turno
        
        Returns:
            tuple: (requiere_autorizacion: bool, motivo: str)
        """
        try:
            if not self.turno_abierto:
                return False, ""
            
            # Obtener hora de apertura del turno
            fecha_apertura = self.turno_abierto['fecha_apertura']
            hora_apertura = fecha_apertura.time()
            
            # Calcular hora esperada de cierre según el turno
            # Turno matutino: 06:00 - 14:00
            # Turno vespertino: 14:00 - 22:00
            
            hora_actual = datetime.now().time()
            
            # Determinar tipo de turno basado en hora de apertura
            if time(5, 0) <= hora_apertura < time(13, 0):
                # Turno matutino
                hora_inicio_esperada = time(6, 0)
                hora_fin_esperada = time(14, 0)
                nombre_turno = "Matutino (06:00 - 14:00)"
            elif time(13, 0) <= hora_apertura < time(21, 0):
                # Turno vespertino
                hora_inicio_esperada = time(14, 0)
                hora_fin_esperada = time(22, 0)
                nombre_turno = "Vespertino (14:00 - 22:00)"
            else:
                # Turno fuera de horario estándar, requiere autorización siempre
                return True, f"Cierre de turno fuera de horario estándar\n\nTurno iniciado a las {hora_apertura.strftime('%H:%M')}"
            
            # Margen de tolerancia: 30 minutos antes o después
            margen = timedelta(minutes=30)
            
            # Convertir a datetime para comparar
            ahora = datetime.now()
            fecha_hoy = ahora.date()
            
            hora_fin_datetime = datetime.combine(fecha_hoy, hora_fin_esperada)
            hora_cierre_min = hora_fin_datetime - margen
            hora_cierre_max = hora_fin_datetime + margen
            
            # Verificar si está fuera del rango
            if ahora < hora_cierre_min:
                # Cerrando muy temprano
                diferencia = hora_cierre_min - ahora
                minutos = int(diferencia.total_seconds() / 60)
                return True, (
                    f"Cierre anticipado de turno {nombre_turno}\n\n"
                    f"Hora esperada de cierre: {hora_fin_esperada.strftime('%H:%M')}\n"
                    f"Hora actual: {hora_actual.strftime('%H:%M')}\n"
                    f"Se está cerrando {minutos} minutos antes de lo esperado"
                )
            elif ahora > hora_cierre_max:
                # Cerrando muy tarde
                diferencia = ahora - hora_cierre_max
                minutos = int(diferencia.total_seconds() / 60)
                
                # Mostrar advertencia pero no requiere autorización si es menos de 2 horas
                if minutos < 120:
                    show_warning_dialog(
                        self,
                        "Recordatorio",
                        f"⚠️ El turno {nombre_turno} debía cerrar a las {hora_fin_esperada.strftime('%H:%M')}\n\n"
                        f"Recuerda cerrar el turno puntualmente al finalizar tu horario."
                    )
                    return False, ""
                else:
                    # Más de 2 horas de retraso requiere autorización
                    return True, (
                        f"Cierre tardío de turno {nombre_turno}\n\n"
                        f"Hora esperada de cierre: {hora_fin_esperada.strftime('%H:%M')}\n"
                        f"Hora actual: {hora_actual.strftime('%H:%M')}\n"
                        f"Se está cerrando {minutos} minutos después de lo esperado"
                    )
            
            # Está dentro del rango aceptable
            return False, ""
            
        except Exception as e:
            logging.error(f"Error verificando horario de turno: {e}")
            # En caso de error, permitir el cierre sin autorización
            return False, ""
        
    def procesar_cierre(self):
        """Procesar cierre de caja"""
        if not hasattr(self, 'total_contado_valor'):
            show_warning_dialog(self, "Cierre de Caja", "Debe contar el efectivo antes de cerrar la caja.")
            return
        
        # Validar que el campo de efectivo tenga un valor válido
        try:
            efectivo = float(self.efectivo_input.text() or 0)
            
            # Validar rango
            if efectivo < 0 or efectivo > 99999.99:
                show_warning_dialog(
                    self, 
                    "Valor Inválido", 
                    "El efectivo debe estar entre $0.00 y $99,999.99"
                )
                return
        except ValueError:
            show_warning_dialog(
                self, 
                "Valor Inválido", 
                "Por favor ingrese un valor numérico válido para el efectivo."
            )
            return
        
        # Verificar si está dentro del horario del turno
        autorizacion_requerida, motivo = self.verificar_horario_turno()
        
        if autorizacion_requerida:
            # Solicitar autorización de administrador
            from ui.admin_auth_dialog import AdminAuthDialog
            dialog = AdminAuthDialog(self.pg_manager, motivo, self)
            
            if dialog.exec() != dialog.Accepted:
                # Autorización cancelada o denegada
                return
            
            # Obtener datos de autorización
            auth_data = dialog.get_autorizacion()
            if not auth_data['autorizado']:
                return
            
            # Guardar datos de autorización para el registro
            self.autorizacion = auth_data
        else:
            self.autorizacion = None
        
        diferencia = float(self.total_contado_valor) - float(self.total_esperado_valor)
        
        # Confirmar cierre
        resumen = (
            f"Total esperado: ${self.total_esperado_valor:.2f}\n\n"
            f"Efectivo en caja: ${efectivo:.2f}\n"
            "─────────────────────\n"
            f"Total contado: ${self.total_contado_valor:.2f}\n"
            f"Diferencia: ${diferencia:.2f}"
        )

        if show_confirmation_dialog(
            self,
            "Confirmar Cierre",
            "Revise el resumen antes de confirmar.",
            detail=resumen,
            confirm_text="Sí, cerrar",
            cancel_text="Volver"
        ):
            try:
                # Obtener valores
                efectivo = float(self.efectivo_input.text() or 0)
                notas = self.notas_input.toPlainText()
                
                # Registrar cierre en la base de datos
                cierre_data = {
                    'fecha': date.today(),
                    'total_esperado': self.total_esperado_valor,
                    'total_contado': self.total_contado_valor,
                    'diferencia': diferencia,
                    'id_usuario': self.user_data['id_usuario'],
                    'efectivo': efectivo,
                    'notas': notas
                }
                
                self.registrar_cierre(cierre_data)
                
                show_success_dialog(self, "Cierre Completado", "Cierre de caja registrado exitosamente.")
                self.cerrar_solicitado.emit()
                
            except Exception as e:
                logging.error(f"Error procesando cierre: {e}")
                show_error_dialog(self, "Error", f"Error al procesar cierre: {e}")
                
    def registrar_cierre(self, cierre_data):
        try:
            # Usar el turno que ya verificamos que está abierto
            if not self.turno_abierto:
                raise Exception("No hay turno abierto para cerrar")
            
            # Preparar notas incluyendo autorización si existe
            notas_cierre = cierre_data.get('notas', '')
            if self.autorizacion:
                auth_info = (
                    f"\n\n--- AUTORIZACIÓN ADMINISTRADOR ---\n"
                    f"Autorizado por: {self.autorizacion['nombre_admin']}\n"
                    f"Justificación: {self.autorizacion['justificacion']}"
                )
                notas_cierre = (notas_cierre + auth_info) if notas_cierre else auth_info.strip()
            
            # Actualizar turno existente
            self.pg_manager.client.table('turnos_caja').update({
                'fecha_cierre': datetime.now().isoformat(),
                'total_ventas_efectivo': cierre_data['total_esperado'],
                'monto_esperado': float(self.turno_abierto['monto_inicial']) + cierre_data['total_esperado'],
                'monto_real_cierre': cierre_data['total_contado'],
                'diferencia': cierre_data['diferencia'],
                'cerrado': True,
                'notas_apertura': (self.turno_abierto.get('notas_apertura', '') or '') + ('\n' + notas_cierre if self.turno_abierto.get('notas_apertura') else notas_cierre)
            }).eq('id_turno', self.turno_abierto['id_turno']).execute()
            
            logging.info("Cierre de caja registrado correctamente")
                
        except Exception as e:
            logging.error(f"Error registrando cierre de caja: {e}")
            raise