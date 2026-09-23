"""
Ventana de Cancelación de Pagos para HTF POS
Basada en el grid de historial de ventas
"""

from PySide6.QtWidgets import (
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QInputDialog, QLineEdit
)
from PySide6.QtCore import Qt, QDate
from datetime import datetime
import logging
import qtawesome as qta

from ui.components import (
    WindowsPhoneTheme,
    show_success_dialog,
    show_warning_dialog,
    show_confirmation_dialog
)
from .historial import HistorialVentasWindow


class CancelarPagosWindow(HistorialVentasWindow):
    """Widget para cancelar pagos usando el grid de historial."""

    def create_history_table(self, parent_layout):
        """Crear tabla de historial con acción de cancelación."""
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(10)
        self.history_table.setHorizontalHeaderLabels([
            "ID", "Turno", "Fecha", "Hora", "Método", "Estado", "Total", "Usuario", "Detalles", "Cancelar"
        ])

        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)

        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)

        parent_layout.addWidget(self.history_table)

    def cargar_usuarios_filtro(self):
        """Cargar combos y dejar por defecto ventas completadas."""
        super().cargar_usuarios_filtro()

        index_completadas = self.estado_combo.findText("Completadas")
        if index_completadas >= 0:
            self.estado_combo.blockSignals(True)
            self.estado_combo.setCurrentIndex(index_completadas)
            self.estado_combo.blockSignals(False)

    def limpiar_filtros(self):
        """Limpiar filtros dejando estado por defecto en completadas."""
        self.search_bar.clear()
        self.usuario_combo.setCurrentIndex(0)
        self.turno_combo.setCurrentIndex(0)
        index_completadas = self.estado_combo.findText("Completadas")
        if index_completadas >= 0:
            self.estado_combo.setCurrentIndex(index_completadas)
        self.metodo_combo.setCurrentIndex(0)
        self.fecha_desde.setDate(QDate.currentDate().addDays(-30))
        self.fecha_hasta.setDate(QDate.currentDate())
        self.cargar_historial_completo()

    def actualizar_tabla(self, ventas, mostrar_paginacion=False):
        """Actualizar tabla con acción de cancelación por fila."""
        try:
            self.history_table.setRowCount(len(ventas))

            for row, venta in enumerate(ventas):
                self.history_table.setRowHeight(row, 55)

                self.history_table.setItem(row, 0, QTableWidgetItem(str(venta['id_venta'])))

                turno_text = str(venta.get('id_turno') or 'N/A')
                turno_item = QTableWidgetItem(turno_text)
                turno_item.setTextAlignment(Qt.AlignCenter)
                self.history_table.setItem(row, 1, turno_item)

                fecha_obj = venta['fecha']
                if isinstance(fecha_obj, str):
                    try:
                        fecha_obj = datetime.fromisoformat(fecha_obj.replace('Z', '+00:00'))
                    except Exception:
                        fecha_obj = None

                if isinstance(fecha_obj, datetime):
                    fecha = fecha_obj.strftime("%d/%m/%Y")
                    hora = fecha_obj.strftime("%H:%M")
                else:
                    fecha = str(venta['fecha']) if venta['fecha'] else "N/A"
                    hora = "N/A"

                self.history_table.setItem(row, 2, QTableWidgetItem(fecha))
                self.history_table.setItem(row, 3, QTableWidgetItem(hora))

                metodo = str(venta.get('metodo_pago') or 'N/A').replace('_', ' ').title()
                self.history_table.setItem(row, 4, QTableWidgetItem(metodo))

                estado_raw = str(venta.get('estado') or 'N/A')
                estado_item = QTableWidgetItem(estado_raw.title())
                estado_item.setTextAlignment(Qt.AlignCenter)
                self.history_table.setItem(row, 5, estado_item)

                total_item = QTableWidgetItem(f"${venta['total']:.2f}")
                total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.history_table.setItem(row, 6, total_item)

                usuario_name = venta.get('usuarios', {}).get('nombre_completo', 'N/A') if isinstance(venta.get('usuarios'), dict) else venta.get('usuario', 'N/A')
                self.history_table.setItem(row, 7, QTableWidgetItem(usuario_name))

                btn_detalles = QPushButton()
                btn_detalles.setIcon(qta.icon('fa5s.eye', color='white'))
                btn_detalles.setToolTip("Ver detalle de la venta")
                btn_detalles.setFixedWidth(40)
                btn_detalles.setMinimumHeight(35)
                btn_detalles.setStyleSheet(f"""
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
                btn_detalles.clicked.connect(lambda checked=False, vid=venta['id_venta']: self.ver_detalles(vid))
                self.history_table.setCellWidget(row, 8, btn_detalles)

                btn_cancelar = QPushButton()
                estado_completada = estado_raw.lower() == 'completada'

                if estado_completada:
                    btn_cancelar.setIcon(qta.icon('fa5s.ban', color='white'))
                    btn_cancelar.setToolTip("Cancelar pago")
                    btn_cancelar.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {WindowsPhoneTheme.TILE_RED};
                            color: white;
                            border: none;
                            border-radius: 3px;
                        }}
                        QPushButton:hover {{
                            background-color: #d32f2f;
                        }}
                    """)
                    btn_cancelar.clicked.connect(lambda checked=False, vid=venta['id_venta']: self.cancelar_pago(vid))
                else:
                    btn_cancelar.setIcon(qta.icon('fa5s.lock', color='white'))
                    btn_cancelar.setToolTip("Solo se pueden cancelar ventas completadas")
                    btn_cancelar.setEnabled(False)
                    btn_cancelar.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {WindowsPhoneTheme.TILE_GRAY};
                            color: white;
                            border: none;
                            border-radius: 3px;
                        }}
                    """)

                btn_cancelar.setFixedWidth(40)
                btn_cancelar.setMinimumHeight(35)
                self.history_table.setCellWidget(row, 9, btn_cancelar)

            if mostrar_paginacion:
                self.actualizar_pagination_buttons()

        except Exception as e:
            logging.error(f"Error cargando tabla de cancelación de pagos: {e}")
            show_warning_dialog(self, "Error", f"No se pudo cargar la tabla: {e}")

    def cancelar_pago(self, venta_id: int):
        """Cancelar una venta completada desde el grid."""
        try:
            venta = next((item for item in self.ventas_data if item.get('id_venta') == venta_id), None)
            if not venta:
                show_warning_dialog(self, "Venta no encontrada", f"No se encontró la venta #{venta_id}.")
                return

            estado_actual = str(venta.get('estado') or '').lower()
            if estado_actual != 'completada':
                show_warning_dialog(
                    self,
                    "Operación no permitida",
                    f"La venta #{venta_id} no está completada. Estado actual: {estado_actual or 'N/A'}"
                )
                return

            confirmar = show_confirmation_dialog(
                self,
                "Confirmar cancelación",
                f"¿Deseas cancelar el pago de la venta #{venta_id}?",
                detail="Esta acción regresará el inventario y marcará la venta como cancelada.",
                confirm_text="Cancelar Pago",
                cancel_text="Volver"
            )
            if not confirmar:
                return

            motivo, accepted = QInputDialog.getText(
                self,
                "Motivo de cancelación",
                "Escribe el motivo de la cancelación:",
                QLineEdit.Normal,
                ""
            )
            if not accepted:
                return

            if not motivo or not motivo.strip():
                show_warning_dialog(
                    self,
                    "Motivo requerido",
                    "Debes escribir el motivo de la cancelación para continuar."
                )
                return

            motivo_limpio = motivo.strip()
            id_usuario = self.user_data.get('id_usuario')

            if not id_usuario:
                show_warning_dialog(self, "Error de sesión", "No se pudo identificar al usuario que cancela.")
                return

            cancelada = self.pg_manager.cancelar_venta_pos(
                id_venta=venta_id,
                id_usuario_cancelacion=id_usuario,
                motivo=motivo_limpio
            )

            if not cancelada:
                show_warning_dialog(
                    self,
                    "No se pudo cancelar",
                    f"No fue posible cancelar la venta #{venta_id}."
                )
                return

            show_success_dialog(
                self,
                "Pago cancelado",
                f"La venta #{venta_id} fue cancelada correctamente."
            )
            self.cargar_historial_completo()

        except Exception as e:
            logging.error(f"Error cancelando pago de venta {venta_id}: {e}")
            show_warning_dialog(self, "Error", f"Ocurrió un error al cancelar el pago: {e}")
