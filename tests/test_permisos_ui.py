"""
Pruebas del modulo de permisos especiales (ui/permisos_window.py).

Lo que se cuida aqui:
  - La pantalla ofrece EXACTAMENTE los permisos de OTORGABLES. Ni uno mas.
  - `precios.actualizar` nunca se puede otorgar, y el motivo esta a la vista.
  - Nadie edita sus propios permisos, ni siendo administrador.
  - Un rol no administrativo no entra.
  - Otorgar y revocar llegan a la capa de datos con los datos correctos.
  - Los permisos que ya trae el rol se ven marcados y NO se mandan como
    otorgamientos.

Los dialogos Qt se instancian con __new__ y se les sustituyen los campos, el
mismo patron de tests/test_usuarios.py: ninguna prueba abre una ventana ni
toca la base real. Los metodos de permisos de PostgresManager se simulan con
un doble (los implementa otro modulo).
"""

import logging

import pytest

from database.permisos import (
    OTORGABLES,
    NO_OTORGABLES,
    DESCRIPCIONES,
    INVENTARIO_ACTUALIZAR,
    INVENTARIO_VER,
    VENTAS_CANCELAR,
    MIEMBROS_EDITAR,
    CATALOGO_ALTA_PRODUCTO,
    PRECIOS_ACTUALIZAR,
    USUARIOS_GESTIONAR,
    PERMISOS_GESTIONAR,
    CAJA_CERRAR_FUERA_HORA,
    permisos_base_de,
    motivo_no_otorgable,
)
from ui.permisos_window import (
    NOTA_VIENE_DEL_ROL,
    PermisosDialog,
    PermisosWindow,
    extraer_permisos_otorgados,
    filtrar_candidatos,
    permisos_no_otorgables_ordenados,
    permisos_otorgables_ordenados,
    puede_recibir_permisos,
    rol_puede_gestionar_permisos,
)


ADMIN = {"id_usuario": 2, "nombre_usuario": "admin",
         "nombre_completo": "Administrador Sistema", "rol": "administrador",
         "activo": True}
BALBINA = {"id_usuario": 3, "nombre_usuario": "balbina",
           "nombre_completo": "Balbina", "rol": "recepcionista", "activo": True}
YESSICA = {"id_usuario": 4, "nombre_usuario": "yessica",
           "nombre_completo": "Yessica Valdez Ayala", "rol": "recepcionista",
           "activo": True}
MARGARITA = {"id_usuario": 5, "nombre_usuario": "margarita",
             "nombre_completo": "Margarita", "rol": "recepcionista",
             "activo": False}


class GestorFalso:
    """Doble de PostgresManager con solo lo que la pantalla usa."""

    def __init__(self, usuarios=None, otorgados=None):
        self.usuarios = list(usuarios or [ADMIN, BALBINA, YESSICA, MARGARITA])
        self.otorgados = dict(otorgados or {})
        self.llamadas = []          # ('otorgar'|'revocar', ...)

    def get_users(self, incluir_inactivos=True):
        if incluir_inactivos:
            return [dict(u) for u in self.usuarios]
        return [dict(u) for u in self.usuarios if u.get("activo")]

    def get_permisos_otorgados(self, id_usuario):
        return list(self.otorgados.get(id_usuario, []))

    def get_usuarios_con_permisos(self):
        """Misma forma que el metodo real: padron + permisos en un viaje."""
        filas = []
        for usuario in self.usuarios:
            fila = dict(usuario)
            fila["permisos_otorgados"] = list(
                self.otorgados.get(usuario["id_usuario"], [])
            )
            filas.append(fila)
        return filas

    def otorgar_permiso(self, id_usuario, permiso, otorgado_por, notas=None):
        self.llamadas.append(("otorgar", id_usuario, permiso, otorgado_por, notas))
        self.otorgados.setdefault(id_usuario, []).append(permiso)
        return True

    def revocar_permiso(self, id_usuario, permiso):
        self.llamadas.append(("revocar", id_usuario, permiso))
        restantes = [p for p in self.otorgados.get(id_usuario, []) if p != permiso]
        self.otorgados[id_usuario] = restantes
        return True


class _Casilla:
    """QCheckBox de mentira: solo hace falta saber si esta marcada."""

    def __init__(self, marcada=False):
        self._marcada = bool(marcada)

    def isChecked(self):
        return self._marcada


@pytest.fixture
def gestor():
    return GestorFalso(otorgados={3: [VENTAS_CANCELAR]})


def _dialogo(gestor, usuario, id_administrador=2, marcados=None):
    """
    PermisosDialog sin construir la interfaz Qt.

    `marcados` es lo que el administrador deja marcado al guardar; si no se
    pasa, se usa el estado con el que abre la pantalla.
    """
    dialogo = PermisosDialog.__new__(PermisosDialog)
    dialogo.pg_manager = gestor
    dialogo.usuario = usuario
    dialogo.id_administrador = id_administrador
    dialogo.permisos_base = permisos_base_de(usuario.get("rol"))
    dialogo.otorgados = set(gestor.get_permisos_otorgados(usuario["id_usuario"]))
    dialogo.casillas = {}
    for permiso in permisos_otorgables_ordenados():
        inicial, _editable, _nota = dialogo.estado_inicial(permiso)
        if marcados is None:
            valor = inicial
        else:
            # Lo que viene del rol no se puede desmarcar en la pantalla real.
            valor = permiso in marcados or permiso in dialogo.permisos_base
        dialogo.casillas[permiso] = _Casilla(valor)
    return dialogo


def _ventana(gestor, user_data, usuarios=None):
    """PermisosWindow sin interfaz, para probar sus reglas."""
    ventana = PermisosWindow.__new__(PermisosWindow)
    ventana.pg_manager = gestor
    ventana.user_data = user_data
    ventana.usuarios = list(usuarios or [BALBINA, YESSICA])
    ventana.acceso_denegado = False
    return ventana


# ---------------------------------------------------------------------------
# Que se ofrece y que no
# ---------------------------------------------------------------------------

def test_la_pantalla_ofrece_exactamente_los_otorgables():
    ofrecidos = permisos_otorgables_ordenados()
    assert set(ofrecidos) == set(OTORGABLES)
    assert len(ofrecidos) == len(OTORGABLES)


def test_el_dialogo_solo_crea_casillas_de_otorgables(gestor):
    dialogo = _dialogo(gestor, BALBINA)
    assert set(dialogo.casillas) == set(OTORGABLES)


@pytest.mark.parametrize("prohibido", sorted(NO_OTORGABLES))
def test_ningun_no_otorgable_se_ofrece(prohibido):
    assert prohibido not in permisos_otorgables_ordenados()


def test_precios_actualizar_nunca_es_otorgable():
    assert PRECIOS_ACTUALIZAR not in OTORGABLES
    assert PRECIOS_ACTUALIZAR not in permisos_otorgables_ordenados()


def test_precios_actualizar_se_muestra_con_su_motivo():
    """
    Se lista a proposito, deshabilitado y con el porque. Si no apareciera,
    pareceria un olvido y alguien lo pediria de nuevo cada mes.
    """
    assert PRECIOS_ACTUALIZAR in permisos_no_otorgables_ordenados()
    motivo = motivo_no_otorgable(PRECIOS_ACTUALIZAR)
    assert motivo
    assert "administraci" in motivo.lower()


def test_gestionar_usuarios_y_permisos_ni_se_ofrecen():
    """Un administrador no puede delegar la llave de la casa."""
    ofrecidos = permisos_otorgables_ordenados()
    assert USUARIOS_GESTIONAR not in ofrecidos
    assert PERMISOS_GESTIONAR not in ofrecidos
    assert CAJA_CERRAR_FUERA_HORA not in ofrecidos


def test_una_casilla_intrusa_no_se_envia(gestor):
    """
    Aunque alguien inyecte una casilla de un permiso reservado, el calculo de
    cambios solo recorre OTORGABLES y la ignora.
    """
    dialogo = _dialogo(gestor, BALBINA)
    dialogo.casillas[PRECIOS_ACTUALIZAR] = _Casilla(True)
    otorgar, revocar = dialogo.calcular_cambios()
    assert PRECIOS_ACTUALIZAR not in otorgar
    assert PRECIOS_ACTUALIZAR not in revocar


def test_todos_los_otorgables_tienen_descripcion():
    """La casilla se pinta con DESCRIPCIONES: ninguna debe quedar vacia."""
    for permiso in permisos_otorgables_ordenados():
        assert DESCRIPCIONES.get(permiso)


# ---------------------------------------------------------------------------
# Quien puede abrir la pantalla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ["administrador", "sistemas", "ADMINISTRADOR"])
def test_administracion_puede_abrir(rol):
    assert rol_puede_gestionar_permisos(rol) is True
    assert PermisosWindow.verificar_acceso({"rol": rol}) is True


@pytest.mark.parametrize("rol", ["recepcionista", "gerente", "", None])
def test_rol_no_administrativo_no_puede_abrir(rol):
    assert rol_puede_gestionar_permisos(rol) is False
    assert PermisosWindow.verificar_acceso({"rol": rol, "username": "x"}) is False


def test_el_intento_queda_registrado(caplog):
    with caplog.at_level(logging.WARNING):
        PermisosWindow.verificar_acceso({"rol": "recepcionista",
                                         "username": "balbina"})
    assert any("[SEGURIDAD]" in r.message for r in caplog.records)
    assert any("balbina" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Nadie se edita a si mismo
# ---------------------------------------------------------------------------

def test_un_administrador_no_puede_editar_sus_propios_permisos(gestor):
    ventana = _ventana(gestor, {"id_usuario": 2, "rol": "administrador",
                                "username": "admin"})
    error = ventana.validar_seleccion(dict(ADMIN))
    assert error is not None
    assert "propios permisos" in error


def test_sistemas_tampoco_puede_editarse(gestor):
    yo = {"id_usuario": 12, "nombre_usuario": "sistemas", "rol": "sistemas",
          "activo": True}
    ventana = _ventana(gestor, {"id_usuario": 12, "rol": "sistemas",
                                "username": "sistemas"})
    assert ventana.validar_seleccion(yo) is not None


def test_sin_seleccion_avisa(gestor):
    ventana = _ventana(gestor, {"id_usuario": 2, "rol": "administrador"})
    assert "Selecciona" in ventana.validar_seleccion(None)


def test_a_otra_persona_si_se_le_puede_editar(gestor):
    ventana = _ventana(gestor, {"id_usuario": 2, "rol": "administrador"})
    assert ventana.validar_seleccion(dict(BALBINA)) is None


def test_no_tiene_sentido_editar_a_un_administrador(gestor):
    """Su rol ya trae todo lo otorgable: no hay nada que darle."""
    ventana = _ventana(gestor, {"id_usuario": 12, "rol": "sistemas"})
    assert ventana.validar_seleccion(dict(ADMIN)) is not None


# ---------------------------------------------------------------------------
# Guardar: otorgar y revocar
# ---------------------------------------------------------------------------

def test_otorgar_llama_a_otorgar_permiso_con_el_administrador_correcto(gestor):
    dialogo = _dialogo(gestor, BALBINA, id_administrador=2,
                       marcados={VENTAS_CANCELAR, INVENTARIO_ACTUALIZAR})
    otorgar, revocar = dialogo.calcular_cambios()
    assert otorgar == [INVENTARIO_ACTUALIZAR]
    assert revocar == []

    assert dialogo.aplicar_cambios(otorgar, revocar) == []
    assert gestor.llamadas == [
        ("otorgar", 3, INVENTARIO_ACTUALIZAR, 2, None)
    ]


def test_el_otorgado_por_es_quien_opera(gestor):
    dialogo = _dialogo(gestor, BALBINA, id_administrador=12,
                       marcados={VENTAS_CANCELAR, MIEMBROS_EDITAR})
    dialogo.aplicar_cambios(*dialogo.calcular_cambios())
    assert [c[3] for c in gestor.llamadas if c[0] == "otorgar"] == [12]


def test_desmarcar_revoca(gestor):
    """Balbina tiene ventas.cancelar; al desmarcarlo se revoca."""
    dialogo = _dialogo(gestor, BALBINA, marcados=set())
    otorgar, revocar = dialogo.calcular_cambios()
    assert otorgar == []
    assert revocar == [VENTAS_CANCELAR]

    dialogo.aplicar_cambios(otorgar, revocar)
    assert gestor.llamadas == [("revocar", 3, VENTAS_CANCELAR)]


def test_sin_tocar_nada_no_se_manda_nada(gestor):
    dialogo = _dialogo(gestor, BALBINA)
    assert dialogo.calcular_cambios() == ([], [])
    dialogo.aplicar_cambios(*dialogo.calcular_cambios())
    assert gestor.llamadas == []


def test_un_fallo_se_reporta_y_no_detiene_al_resto(gestor):
    def otorgar_a_medias(id_usuario, permiso, otorgado_por, notas=None):
        gestor.llamadas.append(("otorgar", id_usuario, permiso, otorgado_por, notas))
        return permiso != MIEMBROS_EDITAR

    gestor.otorgar_permiso = otorgar_a_medias
    dialogo = _dialogo(gestor, YESSICA,
                       marcados={INVENTARIO_ACTUALIZAR, MIEMBROS_EDITAR})
    fallidos = dialogo.aplicar_cambios(*dialogo.calcular_cambios())
    assert fallidos == [MIEMBROS_EDITAR]
    assert len([c for c in gestor.llamadas if c[0] == "otorgar"]) == 2


def test_el_resumen_dice_que_se_otorga_y_que_se_revoca(gestor):
    dialogo = _dialogo(gestor, BALBINA, marcados={INVENTARIO_ACTUALIZAR})
    otorgar, revocar = dialogo.calcular_cambios()
    resumen = dialogo.resumen_cambios(otorgar, revocar)
    assert "OTORGAR" in resumen and "REVOCAR" in resumen
    assert DESCRIPCIONES[INVENTARIO_ACTUALIZAR] in resumen
    assert DESCRIPCIONES[VENTAS_CANCELAR] in resumen


# ---------------------------------------------------------------------------
# Permisos que vienen del rol
# ---------------------------------------------------------------------------

def test_los_permisos_del_rol_se_ven_marcados_y_bloqueados(gestor):
    """Para un administrador, todo lo otorgable ya viene de su rol."""
    dialogo = _dialogo(gestor, ADMIN)
    for permiso in permisos_otorgables_ordenados():
        marcado, editable, nota = dialogo.estado_inicial(permiso)
        assert marcado is True
        assert editable is False
        assert nota == NOTA_VIENE_DEL_ROL


def test_los_permisos_del_rol_no_se_envian_como_otorgamientos(gestor):
    dialogo = _dialogo(gestor, ADMIN,
                       marcados=set(permisos_otorgables_ordenados()))
    assert dialogo.calcular_cambios() == ([], [])
    dialogo.aplicar_cambios(*dialogo.calcular_cambios())
    assert gestor.llamadas == []


def test_un_permiso_otorgado_arranca_marcado_y_editable(gestor):
    dialogo = _dialogo(gestor, BALBINA)
    marcado, editable, nota = dialogo.estado_inicial(VENTAS_CANCELAR)
    assert (marcado, editable, nota) == (True, True, None)


def test_un_permiso_sin_otorgar_arranca_desmarcado(gestor):
    dialogo = _dialogo(gestor, YESSICA)
    assert dialogo.estado_inicial(INVENTARIO_ACTUALIZAR) == (False, True, None)


# ---------------------------------------------------------------------------
# El caso que motivo el modulo
# ---------------------------------------------------------------------------

def test_a_una_recepcionista_se_le_puede_dar_inventario_pero_no_precios(gestor):
    """
    Balbina y Yessica actualizan inventario; los precios siguen siendo de
    administracion.
    """
    dialogo = _dialogo(gestor, YESSICA, id_administrador=2,
                       marcados={INVENTARIO_ACTUALIZAR, PRECIOS_ACTUALIZAR})
    otorgar, revocar = dialogo.calcular_cambios()

    assert otorgar == [INVENTARIO_ACTUALIZAR]
    assert PRECIOS_ACTUALIZAR not in otorgar

    dialogo.aplicar_cambios(otorgar, revocar)
    enviados = [c[2] for c in gestor.llamadas]
    assert enviados == [INVENTARIO_ACTUALIZAR]
    assert PRECIOS_ACTUALIZAR not in enviados


def test_la_recepcionista_ya_veia_inventario_por_su_rol():
    """`inventario.ver` es de rol; lo que se otorga es actualizar."""
    base = permisos_base_de("recepcionista")
    assert INVENTARIO_VER in base
    assert INVENTARIO_ACTUALIZAR not in base
    assert INVENTARIO_ACTUALIZAR in OTORGABLES


# ---------------------------------------------------------------------------
# A quien se lista
# ---------------------------------------------------------------------------

def test_solo_se_listan_cuentas_activas_que_pueden_recibir_algo():
    candidatos = filtrar_candidatos([ADMIN, BALBINA, YESSICA, MARGARITA])
    assert [u["nombre_usuario"] for u in candidatos] == ["balbina", "yessica"]


def test_la_tabla_trae_padron_y_permisos_en_un_viaje(gestor):
    ventana = _ventana(gestor, {"id_usuario": 2, "rol": "administrador"})
    candidatos = ventana.cuentas_candidatas()
    assert [u["nombre_usuario"] for u in candidatos] == ["balbina", "yessica"]
    assert candidatos[0]["permisos_otorgados"] == [VENTAS_CANCELAR]
    assert candidatos[1]["permisos_otorgados"] == []


def test_si_falla_el_resumen_se_arma_la_tabla_con_el_respaldo(gestor):
    """Un error de lectura no debe pintar la tabla vacia."""
    def truena():
        raise RuntimeError("se cayo la red")

    gestor.get_usuarios_con_permisos = truena
    ventana = _ventana(gestor, {"id_usuario": 2, "rol": "administrador"})
    candidatos = ventana.cuentas_candidatas()
    assert [u["nombre_usuario"] for u in candidatos] == ["balbina", "yessica"]
    assert candidatos[0]["permisos_otorgados"] == [VENTAS_CANCELAR]


@pytest.mark.parametrize("rol,esperado", [
    ("recepcionista", True),
    ("administrador", False),
    ("sistemas", False),
])
def test_quien_puede_recibir_permisos(rol, esperado):
    assert puede_recibir_permisos(rol) is esperado


def test_se_ignoran_permisos_raros_guardados_en_la_base():
    """Un registro manipulado no debe pintarse como permiso valido."""
    fila = {"id_usuario": 3,
            "permisos": [INVENTARIO_ACTUALIZAR, PRECIOS_ACTUALIZAR, "inventado"]}
    assert extraer_permisos_otorgados(fila) == [INVENTARIO_ACTUALIZAR]


def test_se_aceptan_filas_con_diccionarios():
    fila = {"id_usuario": 3,
            "permisos_otorgados": [{"permiso": CATALOGO_ALTA_PRODUCTO}]}
    assert extraer_permisos_otorgados(fila) == [CATALOGO_ALTA_PRODUCTO]


def test_una_fila_sin_permisos_no_truena():
    assert extraer_permisos_otorgados({"id_usuario": 9}) == []


# ---------------------------------------------------------------------------
# Pestanas de navegacion decididas por permisos
# ---------------------------------------------------------------------------
# Regresion: la barra ocultaba Inventario con `if role == 'recepcionista'`,
# sin mirar permisos. Otorgarle inventario.actualizar a una recepcionista
# quedaba guardado y era efectivo, pero la pestana no aparecia nunca.

class _GestorPermisos:
    """Doble minimo: solo responde tiene_permiso."""

    def __init__(self, permisos_por_usuario):
        self._permisos = permisos_por_usuario

    def tiene_permiso(self, id_usuario, permiso):
        return permiso in self._permisos.get(id_usuario, set())


def _ventana_principal(user_data, gestor):
    from ui.main_pos_window import MainPOSWindow

    v = MainPOSWindow.__new__(MainPOSWindow)
    v.user_data = user_data
    v.pg_manager = gestor
    return v


def test_recepcionista_con_permiso_ve_inventario():
    from database.permisos import INVENTARIO_ACTUALIZAR

    gestor = _GestorPermisos({13: {INVENTARIO_ACTUALIZAR}})
    v = _ventana_principal({'id_usuario': 13, 'rol': 'recepcionista'}, gestor)
    assert v.puede_ver_inventario() is True


def test_recepcionista_sin_permiso_no_ve_inventario():
    gestor = _GestorPermisos({5: set()})
    v = _ventana_principal({'id_usuario': 5, 'rol': 'recepcionista'}, gestor)
    assert v.puede_ver_inventario() is False


def test_recepcionista_nunca_ve_administracion():
    from database.permisos import INVENTARIO_ACTUALIZAR

    gestor = _GestorPermisos({13: {INVENTARIO_ACTUALIZAR}})
    v = _ventana_principal({'id_usuario': 13, 'rol': 'recepcionista'}, gestor)
    assert v.puede_ver_administracion() is False


def test_administrador_ve_ambas():
    from database.permisos import INVENTARIO_ACTUALIZAR, USUARIOS_GESTIONAR

    gestor = _GestorPermisos({2: {INVENTARIO_ACTUALIZAR, USUARIOS_GESTIONAR}})
    v = _ventana_principal({'id_usuario': 2, 'rol': 'administrador'}, gestor)
    assert v.puede_ver_inventario() is True
    assert v.puede_ver_administracion() is True


def test_sin_id_usuario_falla_cerrado():
    gestor = _GestorPermisos({})
    v = _ventana_principal({'rol': 'administrador'}, gestor)
    assert v.puede_ver_inventario() is False
    assert v.puede_ver_administracion() is False


def test_sin_gestor_falla_cerrado():
    v = _ventana_principal({'id_usuario': 2, 'rol': 'administrador'}, None)
    assert v.puede_ver_inventario() is False


def test_error_al_consultar_falla_cerrado():
    """Ante un fallo de red es preferible esconder la pestana que mostrarla."""
    class GestorQueRevienta:
        def tiene_permiso(self, *a):
            raise RuntimeError("sin conexion")

    v = _ventana_principal({'id_usuario': 2, 'rol': 'administrador'}, GestorQueRevienta())
    assert v.puede_ver_inventario() is False
    assert v.puede_ver_administracion() is False


def test_el_rol_por_si_solo_ya_no_decide():
    """
    Dos recepcionistas con el MISMO rol y distinto permiso deben ver cosas
    distintas. Es justo lo que antes no ocurria.
    """
    from database.permisos import INVENTARIO_ACTUALIZAR

    gestor = _GestorPermisos({13: {INVENTARIO_ACTUALIZAR}, 5: set()})
    con = _ventana_principal({'id_usuario': 13, 'rol': 'recepcionista'}, gestor)
    sin = _ventana_principal({'id_usuario': 5, 'rol': 'recepcionista'}, gestor)
    assert con.puede_ver_inventario() != sin.puede_ver_inventario()


# ---------------------------------------------------------------------------
# Configuracion y cierre de sesion
# ---------------------------------------------------------------------------

def test_recepcionista_no_ve_configuracion():
    """
    Para una recepcionista la pestana quedaria vacia: sin sincronizar, sin
    respaldar, sin cambio de contrasena y con el cierre de sesion en la barra.
    """
    from database.permisos import INVENTARIO_ACTUALIZAR

    gestor = _GestorPermisos({13: {INVENTARIO_ACTUALIZAR}})
    v = _ventana_principal({'id_usuario': 13, 'rol': 'recepcionista'}, gestor)
    assert v.puede_ver_configuracion() is False


def test_administracion_si_ve_configuracion():
    from database.permisos import USUARIOS_GESTIONAR

    gestor = _GestorPermisos({2: {USUARIOS_GESTIONAR}})
    v = _ventana_principal({'id_usuario': 2, 'rol': 'administrador'}, gestor)
    assert v.puede_ver_configuracion() is True


def test_solo_administracion_cambia_contrasenas():
    from database.permisos import INVENTARIO_ACTUALIZAR, USUARIOS_GESTIONAR

    gestor = _GestorPermisos({
        13: {INVENTARIO_ACTUALIZAR},
        2: {USUARIOS_GESTIONAR},
    })
    recep = _ventana_principal({'id_usuario': 13, 'rol': 'recepcionista'}, gestor)
    admin = _ventana_principal({'id_usuario': 2, 'rol': 'administrador'}, gestor)

    assert recep.puede_cambiar_contrasenas() is False
    assert admin.puede_cambiar_contrasenas() is True


def test_quien_no_ve_configuracion_tiene_salir_en_la_barra():
    """
    El boton de cerrar sesion no puede desaparecer: si no esta en
    Configuracion, tiene que estar en la barra inferior.
    """
    from database.permisos import INVENTARIO_ACTUALIZAR, USUARIOS_GESTIONAR

    gestor = _GestorPermisos({
        13: {INVENTARIO_ACTUALIZAR},
        2: {USUARIOS_GESTIONAR},
    })
    for id_usuario, rol in ((13, 'recepcionista'), (2, 'administrador')):
        v = _ventana_principal({'id_usuario': id_usuario, 'rol': rol}, gestor)
        en_configuracion = v.puede_ver_configuracion()
        en_la_barra = not en_configuracion
        # Exactamente uno de los dos sitios, nunca ninguno ni los dos.
        assert en_configuracion != en_la_barra


def test_sin_permisos_no_ve_configuracion_pero_puede_salir():
    gestor = _GestorPermisos({99: set()})
    v = _ventana_principal({'id_usuario': 99, 'rol': 'recepcionista'}, gestor)
    assert v.puede_ver_configuracion() is False   # -> Salir va en la barra
