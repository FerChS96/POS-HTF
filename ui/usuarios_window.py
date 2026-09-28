"""
Ventana de Gestión de Usuarios para HTF POS

Permite dar de alta cuentas de acceso, cambiar contraseñas, editar nombre/rol
y activar o desactivar usuarios desde el propio sistema. Antes esto solo se
podía hacer ejecutando scripts sueltos desde una terminal.

OJO: esta ventana gestiona la tabla `usuarios` (cuentas para entrar al POS),
que es distinta de `personal` (fichas laborales, en Gestionar Personal).

No existe opción de borrar: los usuarios se desactivan, para no romper las
referencias desde ventas, turnos y movimientos de inventario.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QAbstractItemView, QDialog, QFormLayout, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import logging
from datetime import datetime

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    ContentPanel,
    StyledLabel,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog,
)

# Longitud mínima de contraseña. No es una política de seguridad seria, pero
# evita el caso de "1234" que es lo que pasa cuando no se valida nada.
LARGO_MINIMO_CONTRASENIA = 8
LARGO_MINIMO_USUARIO = 3

DESCRIPCION_ROLES = {
    'recepcionista': 'Cajero: vende, abre y cierra turno de caja.',
    'administrador': 'Administra el sistema. No vende ni abre turno.',
    'sistemas': 'Acceso técnico completo. No vende ni abre turno.',
}


class FormularioUsuarioDialog(QDialog):
    """Diálogo de alta y edición de un usuario."""

    def __init__(self, pg_manager, usuario=None, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.usuario = usuario          # None = alta; dict = edición
        self.es_alta = usuario is None
        self.setWindowTitle("Nuevo Usuario" if self.es_alta else "Editar Usuario")
        self.setMinimumWidth(460)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)

        formulario = QFormLayout()
        formulario.setSpacing(10)

        # --- Nombre de usuario ---
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Con el que inicia sesión (ej. yessica)")
        if not self.es_alta:
            # El nombre de usuario es la llave de acceso: cambiarlo dejaría
            # fuera a la persona sin avisarle. Se muestra pero no se edita.
            self.input_usuario.setText(self.usuario['nombre_usuario'])
            self.input_usuario.setReadOnly(True)
            self.input_usuario.setStyleSheet("background-color: #f3f4f6; color: #6b7280;")
        formulario.addRow(StyledLabel("Usuario:"), self.input_usuario)

        # --- Nombre completo ---
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Nombre y apellidos")
        if not self.es_alta:
            self.input_nombre.setText(self.usuario.get('nombre_completo') or "")
        formulario.addRow(StyledLabel("Nombre completo:"), self.input_nombre)

        # --- Rol ---
        self.combo_rol = QComboBox()
        for rol in self.pg_manager.ROLES_VALIDOS:
            self.combo_rol.addItem(rol.capitalize(), rol)
        if not self.es_alta:
            indice = self.combo_rol.findData(self.usuario.get('rol'))
            if indice >= 0:
                self.combo_rol.setCurrentIndex(indice)
        else:
            indice = self.combo_rol.findData('recepcionista')
            self.combo_rol.setCurrentIndex(max(0, indice))
        self.combo_rol.currentIndexChanged.connect(self._actualizar_ayuda_rol)
        formulario.addRow(StyledLabel("Rol:"), self.combo_rol)

        self.ayuda_rol = QLabel()
        self.ayuda_rol.setWordWrap(True)
        self.ayuda_rol.setStyleSheet("color: #6b7280; font-size: 12px;")
        formulario.addRow("", self.ayuda_rol)

        # --- Contraseña ---
        self.input_contrasenia = QLineEdit()
        self.input_contrasenia.setEchoMode(QLineEdit.Password)
        self.input_contrasenia.setPlaceholderText(
            f"Mínimo {LARGO_MINIMO_CONTRASENIA} caracteres"
            if self.es_alta else "Dejar vacío para no cambiarla"
        )
        formulario.addRow(StyledLabel("Contraseña:"), self.input_contrasenia)

        self.input_confirmacion = QLineEdit()
        self.input_confirmacion.setEchoMode(QLineEdit.Password)
        self.input_confirmacion.setPlaceholderText("Repetir contraseña")
        formulario.addRow(StyledLabel("Confirmar:"), self.input_confirmacion)

        self.check_ver = QCheckBox("Mostrar contraseña")
        self.check_ver.toggled.connect(self._alternar_visibilidad)
        formulario.addRow("", self.check_ver)

        # --- Activo (solo en edición) ---
        if not self.es_alta:
            self.check_activo = QCheckBox("Usuario activo (puede iniciar sesión)")
            self.check_activo.setChecked(bool(self.usuario.get('activo')))
            formulario.addRow("", self.check_activo)

        layout.addLayout(formulario)
        layout.addStretch()

        botones = QHBoxLayout()
        botones.setSpacing(WindowsPhoneTheme.TILE_SPACING)

        btn_guardar = TileButton("Guardar", "fa5s.save", WindowsPhoneTheme.TILE_GREEN)
        btn_guardar.clicked.connect(self.guardar)

        btn_cancelar = TileButton("Cancelar", "fa5s.times", WindowsPhoneTheme.TILE_RED)
        btn_cancelar.clicked.connect(self.reject)

        botones.addWidget(btn_guardar)
        botones.addWidget(btn_cancelar)
        layout.addLayout(botones)

        self._actualizar_ayuda_rol()

    def _alternar_visibilidad(self, visible):
        modo = QLineEdit.Normal if visible else QLineEdit.Password
        self.input_contrasenia.setEchoMode(modo)
        self.input_confirmacion.setEchoMode(modo)

    def _actualizar_ayuda_rol(self):
        rol = self.combo_rol.currentData()
        self.ayuda_rol.setText(DESCRIPCION_ROLES.get(rol, ""))

    def validar(self):
        """Devuelve un mensaje de error, o None si todo está bien."""
        usuario = self.input_usuario.text().strip()
        nombre = self.input_nombre.text().strip()
        contrasenia = self.input_contrasenia.text()
        confirmacion = self.input_confirmacion.text()

        if self.es_alta:
            if len(usuario) < LARGO_MINIMO_USUARIO:
                return f"El usuario debe tener al menos {LARGO_MINIMO_USUARIO} caracteres."
            if " " in usuario:
                return "El usuario no puede llevar espacios."

        if not nombre:
            return "El nombre completo es obligatorio."

        # En alta la contraseña es obligatoria; en edición, opcional.
        if self.es_alta or contrasenia:
            if len(contrasenia) < LARGO_MINIMO_CONTRASENIA:
                return f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENIA} caracteres."
            if contrasenia != confirmacion:
                return "Las contraseñas no coinciden."

        return None

    def guardar(self):
        error = self.validar()
        if error:
            show_warning_dialog(self, "Datos incompletos", error)
            return

        usuario = self.input_usuario.text().strip()
        nombre = self.input_nombre.text().strip()
        rol = self.combo_rol.currentData()
        contrasenia = self.input_contrasenia.text()

        try:
            if self.es_alta:
                nuevo_id = self.pg_manager.create_user(
                    username=usuario, password=contrasenia,
                    nombre_completo=nombre, rol=rol,
                )
                if not nuevo_id:
                    show_error_dialog(
                        self, "No se pudo crear",
                        f"No se pudo crear el usuario '{usuario}'.",
                        "Puede que ya exista otro usuario con ese nombre."
                    )
                    return
                logging.info(f"[OK] Usuario '{usuario}' creado con ID {nuevo_id}")
                show_success_dialog(
                    self, "Usuario creado",
                    f"'{usuario}' fue creado correctamente.",
                    f"Rol: {rol}\n\nYa puede iniciar sesión con la contraseña asignada."
                )
                self.accept()
                return

            # --- Edición ---
            id_usuario = self.usuario['id_usuario']
            activo = self.check_activo.isChecked()

            # No dejar el sistema sin nadie que pueda administrarlo.
            era_admin = self.usuario.get('rol') in self.pg_manager.ROLES_ADMINISTRATIVOS
            sigue_admin = rol in self.pg_manager.ROLES_ADMINISTRATIVOS and activo
            if era_admin and self.usuario.get('activo') and not sigue_admin:
                restantes = self.pg_manager.contar_administradores_activos(excluir_id=id_usuario)
                if restantes == 0:
                    show_error_dialog(
                        self, "Operación bloqueada",
                        "Es la única cuenta administrativa activa.",
                        "Si la desactivas o le cambias el rol, nadie podrá "
                        "administrar el sistema.\n\nCrea antes otro administrador."
                    )
                    return

            if not self.pg_manager.update_user(
                id_usuario, nombre_completo=nombre, rol=rol, activo=activo
            ):
                show_error_dialog(self, "Error", "No se pudieron guardar los cambios.")
                return

            if contrasenia:
                if not self.pg_manager.update_user_password_by_id(id_usuario, contrasenia):
                    show_error_dialog(
                        self, "Cambios parciales",
                        "Se guardaron los datos, pero no la contraseña.",
                        "Vuelve a intentar el cambio de contraseña."
                    )
                    return

            detalle = "Se actualizó también la contraseña." if contrasenia else None
            show_success_dialog(self, "Usuario actualizado",
                                f"'{usuario}' se guardó correctamente.", detalle)
            self.accept()

        except Exception as e:
            logging.error(f"[ERROR] Error guardando usuario: {e}")
            show_error_dialog(self, "Error", "Ocurrió un error al guardar.", str(e))


class UsuariosWindow(QWidget):
    """Listado y gestión de las cuentas de acceso al POS."""

    cerrar_solicitado = Signal()

    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data or {}
        self.usuarios = []
        self.setup_ui()
        self.cargar_usuarios()

    # ------------------------------------------------------------------ UI

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)

        aviso = QLabel(
            "Cuentas de acceso al POS. No confundir con Gestionar Personal, "
            "que son las fichas laborales y no permiten iniciar sesión."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 0;")
        layout.addWidget(aviso)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(6)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Usuario", "Nombre Completo", "Rol", "Estado", "Último acceso"]
        )
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self.editar_usuario)

        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(2, QHeaderView.Stretch)
        cabecera.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.tabla.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                border: none;
                gridline-color: #e5e7eb;
                font-family: {WindowsPhoneTheme.FONT_FAMILY};
                font-size: {WindowsPhoneTheme.FONT_SIZE_NORMAL}px;
            }}
            QTableWidget::item {{ padding: 8px; border-bottom: 1px solid #e5e7eb; }}
            QTableWidget::item:selected {{
                background-color: {WindowsPhoneTheme.TILE_BLUE}; color: white;
            }}
            QHeaderView::section {{
                background-color: {WindowsPhoneTheme.PRIMARY_BLUE};
                color: white; padding: 8px; border: none; font-weight: bold;
            }}
        """)
        layout.addWidget(self.tabla)

        botones = QHBoxLayout()
        botones.setSpacing(WindowsPhoneTheme.TILE_SPACING)

        btn_nuevo = TileButton("Nuevo\nUsuario", "fa5s.user-plus", WindowsPhoneTheme.TILE_GREEN)
        btn_nuevo.clicked.connect(self.nuevo_usuario)

        btn_editar = TileButton("Editar", "fa5s.user-edit", WindowsPhoneTheme.TILE_BLUE)
        btn_editar.clicked.connect(self.editar_usuario)

        btn_estado = TileButton("Activar /\nDesactivar", "fa5s.user-slash", WindowsPhoneTheme.TILE_ORANGE)
        btn_estado.clicked.connect(self.alternar_estado)

        btn_refrescar = TileButton("Refrescar", "fa5s.sync", WindowsPhoneTheme.TILE_TEAL)
        btn_refrescar.clicked.connect(self.cargar_usuarios)

        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_GRAY)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)

        for boton in (btn_nuevo, btn_editar, btn_estado, btn_refrescar, btn_volver):
            botones.addWidget(boton)
        layout.addLayout(botones)

    # ---------------------------------------------------------------- Datos

    def _formatear_fecha(self, valor):
        if not valor:
            return "nunca"
        try:
            if isinstance(valor, str):
                return datetime.fromisoformat(
                    valor.replace('Z', '+00:00')
                ).strftime('%d/%m/%Y %H:%M')
            return valor.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return str(valor)

    def cargar_usuarios(self):
        """Traer los usuarios y pintarlos en la tabla."""
        try:
            self.usuarios = self.pg_manager.get_users(incluir_inactivos=True)
            self.tabla.setRowCount(len(self.usuarios))

            for fila, usuario in enumerate(self.usuarios):
                activo = bool(usuario.get('activo'))
                celdas = [
                    str(usuario['id_usuario']),
                    usuario['nombre_usuario'],
                    usuario.get('nombre_completo') or "",
                    (usuario.get('rol') or "").capitalize(),
                    "Activo" if activo else "Inactivo",
                    self._formatear_fecha(usuario.get('ultimo_acceso')),
                ]
                for columna, texto in enumerate(celdas):
                    item = QTableWidgetItem(texto)
                    if columna in (0, 4):
                        item.setTextAlignment(Qt.AlignCenter)
                    if not activo:
                        item.setForeground(Qt.gray)
                    if columna == 3 and usuario.get('rol') in self.pg_manager.ROLES_ADMINISTRATIVOS:
                        fuente = QFont()
                        fuente.setBold(True)
                        item.setFont(fuente)
                    self.tabla.setItem(fila, columna, item)

            logging.info(f"[OK] {len(self.usuarios)} usuarios cargados")
        except Exception as e:
            logging.error(f"[ERROR] Error cargando usuarios: {e}")
            show_error_dialog(self, "Error", "No se pudieron cargar los usuarios.", str(e))

    def usuario_seleccionado(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self.usuarios):
            return None
        return self.usuarios[fila]

    # -------------------------------------------------------------- Acciones

    def nuevo_usuario(self):
        dialogo = FormularioUsuarioDialog(self.pg_manager, usuario=None, parent=self)
        if dialogo.exec():
            self.cargar_usuarios()

    def editar_usuario(self):
        usuario = self.usuario_seleccionado()
        if not usuario:
            show_warning_dialog(self, "Sin selección",
                                "Selecciona un usuario de la lista.")
            return
        dialogo = FormularioUsuarioDialog(self.pg_manager, usuario=usuario, parent=self)
        if dialogo.exec():
            self.cargar_usuarios()

    def alternar_estado(self):
        usuario = self.usuario_seleccionado()
        if not usuario:
            show_warning_dialog(self, "Sin selección",
                                "Selecciona un usuario de la lista.")
            return

        id_usuario = usuario['id_usuario']
        activo = bool(usuario.get('activo'))
        nombre = usuario['nombre_usuario']

        # No dejar que alguien se cierre la puerta a si mismo.
        if id_usuario == self.user_data.get('id_usuario') and activo:
            show_warning_dialog(
                self, "Operación no permitida",
                "No puedes desactivar tu propia cuenta.",
                "Pídeselo a otro administrador."
            )
            return

        # No dejar el sistema sin administradores.
        if activo and usuario.get('rol') in self.pg_manager.ROLES_ADMINISTRATIVOS:
            if self.pg_manager.contar_administradores_activos(excluir_id=id_usuario) == 0:
                show_error_dialog(
                    self, "Operación bloqueada",
                    "Es la única cuenta administrativa activa.",
                    "Si la desactivas, nadie podrá administrar el sistema.\n\n"
                    "Crea antes otro administrador."
                )
                return

        accion = "desactivar" if activo else "activar"
        if not show_confirmation_dialog(
            self, f"Confirmar {accion}",
            f"¿Seguro que quieres {accion} a '{nombre}'?",
            detail=("No podrá iniciar sesión, pero su historial de ventas y "
                    "turnos se conserva." if activo else
                    "Volverá a poder iniciar sesión con su contraseña actual."),
            confirm_text=f"Sí, {accion}",
            cancel_text="Cancelar",
        ):
            return

        if self.pg_manager.update_user(id_usuario, activo=not activo):
            logging.info(f"[OK] Usuario '{nombre}' {accion}do")
            show_success_dialog(self, "Listo", f"'{nombre}' quedó {accion}do.")
            self.cargar_usuarios()
        else:
            show_error_dialog(self, "Error", f"No se pudo {accion} a '{nombre}'.")
