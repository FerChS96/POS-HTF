"""
Ventana de Permisos Especiales para HTF POS.

Permite que un administrador conceda permisos puntuales a una recepcionista
concreta sin cambiarle el rol. El caso que motivó esto: Balbina y Yessica
necesitan registrar entradas y salidas de inventario, pero los precios siguen
siendo cosa de administración.

REGLAS (todas salen de database/permisos.py, aquí no se escribe ni un
identificador de permiso a mano):

    permisos efectivos = permisos base del rol + permisos otorgados

    - Solo se ofrecen los permisos de OTORGABLES.
    - Los de NO_OTORGABLES se muestran deshabilitados y CON el motivo a la
      vista. Es a propósito: que se vea que `precios.actualizar` existe y por
      qué no se delega, en vez de que parezca un descuido.
    - Los permisos que ya trae el rol de base se muestran marcados y
      deshabilitados: no son un otorgamiento y nunca se envían como tal.

OJO: esto es control de acceso a nivel de aplicación, igual que el resto del
POS. Evita que el personal haga de más por error; no detiene a quien se
proponga saltárselo hablando directo con la base (eso lo cierra RLS).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QCheckBox, QScrollArea, QFrame,
    QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import logging

from database.permisos import (
    DESCRIPCIONES,
    OTORGABLES,
    NO_OTORGABLES,
    permisos_base_de,
    es_otorgable,
    motivo_no_otorgable,
)

from ui.components import (
    WindowsPhoneTheme,
    TileButton,
    StyledLabel,
    show_success_dialog,
    show_warning_dialog,
    show_error_dialog,
    show_confirmation_dialog,
)

# Roles que pueden ENTRAR a este módulo. No se toman de permisos.py porque
# `permisos.gestionar` es un permiso de rol y no es otorgable: quien lo tiene
# es exactamente quien tiene uno de estos roles.
ROLES_GESTORES = ('administrador', 'sistemas')

NOTA_VIENE_DEL_ROL = "Incluido en su rol. No se otorga ni se revoca desde aquí."


# --- Ayudas puras (sin Qt, para que las pruebas no abran ventanas) ---------

def permisos_otorgables_ordenados():
    """Los permisos que la pantalla puede ofrecer, en orden estable."""
    return sorted(OTORGABLES)


def permisos_no_otorgables_ordenados():
    """Los permisos que se muestran solo como explicación, en orden estable."""
    return sorted(NO_OTORGABLES)


def rol_puede_gestionar_permisos(rol) -> bool:
    """Si un rol puede abrir este módulo."""
    return (rol or '').strip().lower() in ROLES_GESTORES


def puede_recibir_permisos(rol) -> bool:
    """
    Si a alguien con ese rol le falta algún permiso otorgable.

    Se calcula contra el catálogo en vez de comparar con 'recepcionista', para
    que al agregar un rol nuevo esta pantalla no se quede desactualizada.
    """
    return bool(OTORGABLES - permisos_base_de(rol))


def filtrar_candidatos(usuarios):
    """
    Cuentas a las que tiene sentido otorgarles algo: activas y con permisos
    otorgables que su rol no les dé ya.
    """
    return [
        u for u in (usuarios or [])
        if u.get('activo') and puede_recibir_permisos(u.get('rol'))
    ]


def extraer_permisos_otorgados(fila):
    """
    Lista de permisos otorgados dentro de una fila de `get_usuarios_con_permisos`.

    Se aceptan varias formas ('permisos' o 'permisos_otorgados', cadenas o
    diccionarios con la clave 'permiso') porque esa consulta la arma la capa
    de datos y no queremos que un cambio de nombre deje la tabla en blanco.
    Cualquier cosa que no sea otorgable se descarta: un registro manipulado en
    la base no debe pintarse como un permiso válido.
    """
    crudo = fila.get('permisos')
    if crudo is None:
        crudo = fila.get('permisos_otorgados')
    if not crudo:
        return []

    permisos = []
    for elemento in crudo:
        if isinstance(elemento, dict):
            elemento = elemento.get('permiso')
        if isinstance(elemento, str) and es_otorgable(elemento):
            permisos.append(elemento)
    return sorted(set(permisos))


# Estilo propio del dialogo. Se define el indicador de las casillas de forma
# explicita porque el tema de la aplicacion no toca QCheckBox: al dejarlo al
# estilo nativo dentro de un QScrollArea, algunas filas se dibujaban sin su
# recuadro. Con medidas y colores fijos el resultado es siempre el mismo.
# Estilo de los dos botones del dialogo. Se aplica a cada boton por separado,
# nunca al dialogo: una hoja puesta en el dialogo se hereda a sus hijos.
ESTILO_BOTON_PRINCIPAL = (
    "background: #0078d7; color: white; border: none; border-radius: 2px; "
    "font-size: 14px; font-weight: bold; padding: 8px 18px;"
)
ESTILO_BOTON_SECUNDARIO = (
    "background: #ffffff; color: #1f2937; border: 2px solid #d1d5db; "
    "border-radius: 2px; font-size: 14px; padding: 8px 18px;"
)

ESTILO_CASILLAS = """
    QCheckBox {
        spacing: 8px;
        padding: 3px 0;
        font-size: 13px;
        color: #111827;
    }
    QCheckBox:disabled {
        color: #9ca3af;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 2px solid #6b7280;
        border-radius: 3px;
        background: #ffffff;
    }
    QCheckBox::indicator:hover {
        border-color: #0078d7;
    }
    QCheckBox::indicator:checked {
        background: #0078d7;
        border-color: #0078d7;
        image: none;
    }
    QCheckBox::indicator:checked:disabled {
        background: #9ca3af;
        border-color: #9ca3af;
    }
    QCheckBox::indicator:unchecked:disabled {
        border-color: #d1d5db;
        background: #f3f4f6;
    }
"""


class PermisosDialog(QDialog):
    """Casillas de permisos especiales de UNA persona."""

    def __init__(self, pg_manager, usuario, id_administrador, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.usuario = usuario
        self.id_administrador = id_administrador

        self.permisos_base = permisos_base_de(usuario.get('rol'))
        self.otorgados = set(self._cargar_otorgados())
        self.casillas = {}

        self.setWindowTitle(
            f"Permisos de {usuario.get('nombre_usuario', '')}"
        )
        self.setMinimumWidth(720)
        # Alto suficiente para que se vean las ocho filas sin recortar la
        # ultima nota: antes el dialogo nacia corto y el texto del motivo de
        # 'precios.actualizar' quedaba cortado a media linea.
        self.setMinimumHeight(560)
        self.setup_ui()

    # ---------------------------------------------------------------- Datos

    def _cargar_otorgados(self):
        try:
            otorgados = self.pg_manager.get_permisos_otorgados(
                self.usuario['id_usuario']
            ) or []
        except Exception as e:
            logging.error(f"[ERROR] No se pudieron leer los permisos otorgados: {e}")
            show_error_dialog(self, "Error",
                              "No se pudieron leer los permisos actuales.", str(e))
            return []
        # Solo lo que el catálogo considera otorgable.
        return [p for p in otorgados if es_otorgable(p)]

    # ------------------------------------------------------------------ UI

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)

        encabezado = StyledLabel(
            f"{self.usuario.get('nombre_completo') or self.usuario.get('nombre_usuario')}"
            f"  ·  {(self.usuario.get('rol') or '').capitalize()}"
        )
        fuente = QFont()
        fuente.setBold(True)
        encabezado.setFont(fuente)
        layout.addWidget(encabezado)

        aviso = QLabel(
            "Marca los permisos extra que quieras darle. Los que ya trae su "
            "rol aparecen marcados y no se pueden quitar desde aquí."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 0;")
        layout.addWidget(aviso)

        contenedor = QWidget()
        interior = QVBoxLayout(contenedor)
        interior.setContentsMargins(0, 0, 0, 0)
        interior.setSpacing(8)

        interior.addWidget(self._titulo_seccion("Permisos que se pueden otorgar"))
        for permiso in permisos_otorgables_ordenados():
            interior.addWidget(self._fila_otorgable(permiso))

        interior.addWidget(self._titulo_seccion("No se pueden delegar"))
        for permiso in permisos_no_otorgables_ordenados():
            interior.addWidget(self._fila_no_otorgable(permiso))

        interior.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # La barra vertical siempre presente: si aparece y desaparece segun el
        # contenido, el ancho del area cambia y las filas se redibujan a medias,
        # que es lo que dejaba casillas sin su recuadro.
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # AsNeeded, no AlwaysOff: si por tipografia o traduccion el contenido
        # llegara a ser mas ancho que el area, preferimos que aparezca la barra
        # a que el texto se recorte sin que nadie se entere.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # El estilo se aplica al CONTENEDOR, no al diálogo. Las hojas de estilo
        # de Qt se heredan a los diálogos hijos, y ponerla en `self` hacía que
        # el diálogo de confirmación heredara la regla de QPushButton: su botón
        # secundario quedaba con texto azul sobre fondo azul, es decir, en
        # blanco. Acotándola al contenedor no sale de esta pantalla.
        contenedor.setStyleSheet(ESTILO_CASILLAS)

        scroll.setWidget(contenedor)
        layout.addWidget(scroll, 1)   # se lleva el espacio sobrante


        botones = QHBoxLayout()
        botones.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        botones.addStretch()

        # Botones de dialogo, no mosaicos: TileButton esta pensado para la
        # rejilla principal y aqui se comia un tercio de la ventana.
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setMinimumSize(130, 40)
        btn_cancelar.setStyleSheet(ESTILO_BOTON_SECUNDARIO)
        btn_cancelar.clicked.connect(self.reject)

        btn_guardar = QPushButton("Guardar")
        btn_guardar.setMinimumSize(130, 40)
        btn_guardar.setStyleSheet(ESTILO_BOTON_PRINCIPAL)
        btn_guardar.setDefault(True)
        btn_guardar.clicked.connect(self.guardar)

        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _titulo_seccion(self, texto):
        etiqueta = QLabel(texto.upper())
        etiqueta.setStyleSheet(
            f"color: {WindowsPhoneTheme.PRIMARY_BLUE}; font-size: 12px; "
            f"font-weight: bold; padding-top: 8px;"
        )
        return etiqueta

    def _bloque(self, casilla, nota, color_nota):
        marco = QWidget()
        caja = QVBoxLayout(marco)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(0)
        caja.addWidget(casilla)
        if nota:
            etiqueta = QLabel(nota)
            etiqueta.setWordWrap(True)
            etiqueta.setStyleSheet(
                f"color: {color_nota}; font-size: 11px; padding-left: 22px;"
            )
            caja.addWidget(etiqueta)
        return marco

    def estado_inicial(self, permiso):
        """
        (marcado, editable, nota) con que arranca la casilla de un otorgable.

        Se deja aparte de la construcción de widgets para poder probarla sin
        abrir ventanas.
        """
        if permiso in self.permisos_base:
            # Ya lo trae el rol: se muestra marcado para que no parezca que
            # falta, pero no es un otorgamiento y no se puede tocar.
            return True, False, NOTA_VIENE_DEL_ROL
        return permiso in self.otorgados, True, None

    def _fila_otorgable(self, permiso):
        # Solo la descripción en la casilla. El identificador técnico va en la
        # nota de abajo: junto en una misma línea el texto se salía del diálogo
        # y quedaba cortado por la derecha.
        casilla = QCheckBox(DESCRIPCIONES.get(permiso, permiso))
        marcado, editable, nota = self.estado_inicial(permiso)
        casilla.setChecked(marcado)
        casilla.setEnabled(editable)
        self.casillas[permiso] = casilla

        pie = f"{permiso}" if not nota else f"{permiso} — {nota}"
        return self._bloque(casilla, pie, "#6b7280")

    def _fila_no_otorgable(self, permiso):
        casilla = QCheckBox(DESCRIPCIONES.get(permiso, permiso))
        casilla.setChecked(permiso in self.permisos_base)
        casilla.setEnabled(False)
        # A propósito NO se guarda en self.casillas: lo que no es otorgable no
        # entra jamás en el cálculo de cambios.
        return self._bloque(
            casilla, f"{permiso} — {motivo_no_otorgable(permiso)}", "#b45309"
        )

    # -------------------------------------------------------------- Lógica

    def calcular_cambios(self):
        """
        Qué hay que otorgar y qué hay que revocar, según las casillas.

        Los permisos base del rol quedan fuera de ambas listas: no se mandan
        como otorgamiento aunque estén marcados.
        """
        otorgar, revocar = [], []
        for permiso in permisos_otorgables_ordenados():
            if permiso in self.permisos_base:
                continue
            casilla = self.casillas.get(permiso)
            if casilla is None:
                continue
            marcado = bool(casilla.isChecked())
            if marcado and permiso not in self.otorgados:
                otorgar.append(permiso)
            elif not marcado and permiso in self.otorgados:
                revocar.append(permiso)
        return otorgar, revocar

    def resumen_cambios(self, otorgar, revocar):
        """Texto del diálogo de confirmación."""
        lineas = []
        if otorgar:
            lineas.append("Se van a OTORGAR:")
            lineas += [f"  • {DESCRIPCIONES.get(p, p)}" for p in otorgar]
        if revocar:
            if lineas:
                lineas.append("")
            lineas.append("Se van a REVOCAR:")
            lineas += [f"  • {DESCRIPCIONES.get(p, p)}" for p in revocar]
        return "\n".join(lineas)

    def aplicar_cambios(self, otorgar, revocar):
        """
        Manda los cambios a la capa de datos.

        Devuelve la lista de permisos que fallaron; vacía si todo salió bien.
        No se corta al primer fallo: es mejor aplicar lo que se pueda y decir
        con nombre y apellido qué quedó pendiente.
        """
        id_usuario = self.usuario['id_usuario']
        fallidos = []

        for permiso in otorgar:
            try:
                if self.pg_manager.otorgar_permiso(
                    id_usuario, permiso, self.id_administrador
                ):
                    logging.info(
                        f"[OK] Permiso '{permiso}' otorgado a "
                        f"'{self.usuario.get('nombre_usuario')}' por "
                        f"id {self.id_administrador}"
                    )
                else:
                    fallidos.append(permiso)
            except Exception as e:
                logging.error(f"[ERROR] Otorgando '{permiso}': {e}")
                fallidos.append(permiso)

        for permiso in revocar:
            try:
                if self.pg_manager.revocar_permiso(id_usuario, permiso):
                    logging.info(
                        f"[OK] Permiso '{permiso}' revocado a "
                        f"'{self.usuario.get('nombre_usuario')}'"
                    )
                else:
                    fallidos.append(permiso)
            except Exception as e:
                logging.error(f"[ERROR] Revocando '{permiso}': {e}")
                fallidos.append(permiso)

        return fallidos

    def guardar(self):
        otorgar, revocar = self.calcular_cambios()

        if not otorgar and not revocar:
            show_warning_dialog(self, "Sin cambios",
                                "No cambiaste ningún permiso.")
            return

        nombre = self.usuario.get('nombre_usuario', '')
        if not show_confirmation_dialog(
            self, "Confirmar cambios",
            f"¿Aplicar estos cambios de permisos a '{nombre}'?",
            detail=self.resumen_cambios(otorgar, revocar),
            confirm_text="Sí, aplicar",
            cancel_text="Cancelar",
        ):
            return

        fallidos = self.aplicar_cambios(otorgar, revocar)

        if fallidos:
            show_error_dialog(
                self, "Cambios parciales",
                f"Algunos permisos de '{nombre}' no se pudieron guardar.",
                "Quedaron pendientes:\n" +
                "\n".join(f"  • {DESCRIPCIONES.get(p, p)}" for p in fallidos)
            )
        else:
            show_success_dialog(
                self, "Permisos actualizados",
                f"Los permisos de '{nombre}' quedaron guardados.",
                self.resumen_cambios(otorgar, revocar)
            )
        self.accept()


class PermisosWindow(QWidget):
    """Listado de cuentas que pueden recibir permisos especiales."""

    cerrar_solicitado = Signal()

    @staticmethod
    def verificar_acceso(user_data) -> bool:
        """
        Si esa persona puede abrir la pantalla. Deja rastro si no.

        Defensa en profundidad: el botón ya está oculto para otros roles y
        main_pos_window vuelve a comprobar, pero si se llegara por otra vía
        la pantalla no se arma ni consulta nada.
        """
        datos = user_data or {}
        if rol_puede_gestionar_permisos(datos.get('rol')):
            return True
        logging.warning(
            f"[SEGURIDAD] Intento de abrir Permisos Especiales con rol "
            f"'{(datos.get('rol') or '?')}' (usuario "
            f"{datos.get('username', '?')})"
        )
        return False

    def __init__(self, pg_manager, user_data, parent=None):
        super().__init__(parent)
        self.pg_manager = pg_manager
        self.user_data = user_data or {}
        self.usuarios = []
        self.acceso_denegado = not self.verificar_acceso(self.user_data)

        if self.acceso_denegado:
            self.setup_ui_denegado()
            show_warning_dialog(
                self, "Acceso denegado",
                "Solo un administrador puede otorgar permisos especiales."
            )
            return

        self.setup_ui()
        self.cargar_usuarios()

    # ------------------------------------------------------------------ UI

    def _layout_base(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM,
                                  WindowsPhoneTheme.MARGIN_MEDIUM)
        layout.setSpacing(WindowsPhoneTheme.MARGIN_SMALL)
        return layout

    def setup_ui_denegado(self):
        layout = self._layout_base()
        mensaje = StyledLabel(
            "No tienes permiso para ver esta pantalla.\n"
            "Pídeselo a un administrador."
        )
        mensaje.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(mensaje)
        layout.addStretch()

        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_GRAY)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)
        layout.addWidget(btn_volver)

    def setup_ui(self):
        layout = self._layout_base()

        aviso = QLabel(
            "Permisos extra para cuentas de recepción. Se suman a los de su "
            "rol, sin cambiárselo. Los precios no se delegan: son de "
            "administración."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #6b7280; font-size: 12px; padding: 2px 0;")
        layout.addWidget(aviso)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Usuario", "Nombre Completo", "Rol", "Permisos especiales"]
        )
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self.editar_permisos)

        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        cabecera.setSectionResizeMode(4, QHeaderView.Stretch)

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

        btn_editar = TileButton("Editar\nPermisos", "fa5s.key", WindowsPhoneTheme.TILE_PURPLE)
        btn_editar.clicked.connect(self.editar_permisos)

        btn_refrescar = TileButton("Refrescar", "fa5s.sync", WindowsPhoneTheme.TILE_TEAL)
        btn_refrescar.clicked.connect(self.cargar_usuarios)

        btn_volver = TileButton("Volver", "fa5s.arrow-left", WindowsPhoneTheme.TILE_GRAY)
        btn_volver.clicked.connect(self.cerrar_solicitado.emit)

        for boton in (btn_editar, btn_refrescar, btn_volver):
            botones.addWidget(boton)
        layout.addLayout(botones)

    # ---------------------------------------------------------------- Datos

    def _permisos_de(self, id_usuario):
        try:
            otorgados = self.pg_manager.get_permisos_otorgados(id_usuario) or []
        except Exception as e:
            logging.error(f"[ERROR] Permisos de {id_usuario}: {e}")
            return []
        return sorted({p for p in otorgados if es_otorgable(p)})

    def cuentas_candidatas(self):
        """
        Cuentas a listar, con sus permisos otorgados ya resueltos.

        Se pide primero `get_usuarios_con_permisos`, que trae padrón y
        permisos en el mismo viaje. Si esa consulta falla o no trae las
        columnas esperadas se rehace con `get_users` más una consulta por
        persona: más lenta, pero la pantalla no se queda en blanco ni dice
        que nadie tiene permisos cuando lo que hubo fue un error de lectura.
        """
        try:
            filas = self.pg_manager.get_usuarios_con_permisos() or []
        except Exception as e:
            logging.error(f"[ERROR] No se pudo leer el resumen de permisos: {e}")
            filas = []

        candidatos = filtrar_candidatos(filas)
        if candidatos:
            for usuario in candidatos:
                usuario['permisos_otorgados'] = extraer_permisos_otorgados(usuario)
            return candidatos

        todos = self.pg_manager.get_users(incluir_inactivos=False) or []
        candidatos = filtrar_candidatos(todos)
        for usuario in candidatos:
            usuario['permisos_otorgados'] = self._permisos_de(usuario['id_usuario'])
        return candidatos

    def cargar_usuarios(self):
        """Traer las cuentas activas que pueden recibir permisos."""
        try:
            self.usuarios = self.cuentas_candidatas()
            self.tabla.setRowCount(len(self.usuarios))

            for fila, usuario in enumerate(self.usuarios):
                otorgados = usuario.get('permisos_otorgados') or []
                texto_permisos = ", ".join(
                    DESCRIPCIONES.get(p, p) for p in otorgados
                ) or "sin permisos extra"

                celdas = [
                    str(usuario['id_usuario']),
                    usuario.get('nombre_usuario') or "",
                    usuario.get('nombre_completo') or "",
                    (usuario.get('rol') or "").capitalize(),
                    texto_permisos,
                ]
                for columna, texto in enumerate(celdas):
                    item = QTableWidgetItem(texto)
                    if columna == 0:
                        item.setTextAlignment(Qt.AlignCenter)
                    if columna == 4 and not otorgados:
                        item.setForeground(Qt.gray)
                    self.tabla.setItem(fila, columna, item)

            logging.info(
                f"[OK] {len(self.usuarios)} cuentas cargadas en permisos especiales"
            )
        except Exception as e:
            logging.error(f"[ERROR] Error cargando permisos: {e}")
            show_error_dialog(self, "Error",
                              "No se pudieron cargar las cuentas.", str(e))

    def usuario_seleccionado(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self.usuarios):
            return None
        return self.usuarios[fila]

    # -------------------------------------------------------------- Acciones

    def validar_seleccion(self, usuario):
        """
        Mensaje de error si no se puede editar a esa persona, o None.

        Nadie edita sus propios permisos, ni siquiera un administrador: es la
        puerta por la que se cuela cualquier escalada.
        """
        if not usuario:
            return "Selecciona una cuenta de la lista."

        if usuario.get('id_usuario') == self.user_data.get('id_usuario'):
            return "No puedes modificar tus propios permisos."

        if not puede_recibir_permisos(usuario.get('rol')):
            return (f"Un {(usuario.get('rol') or '').lower()} ya tiene todos "
                    f"estos permisos por su rol.")

        return None

    def editar_permisos(self):
        usuario = self.usuario_seleccionado()
        error = self.validar_seleccion(usuario)
        if error:
            if usuario and usuario.get('id_usuario') == self.user_data.get('id_usuario'):
                logging.warning(
                    f"[SEGURIDAD] '{self.user_data.get('username', '?')}' intentó "
                    f"editar sus propios permisos"
                )
                show_warning_dialog(
                    self, "Operación no permitida", error,
                    "Pídeselo a otro administrador."
                )
            else:
                show_warning_dialog(self, "No se puede editar", error)
            return

        dialogo = PermisosDialog(
            self.pg_manager, usuario,
            self.user_data.get('id_usuario'), parent=self
        )
        if dialogo.exec():
            self.cargar_usuarios()
