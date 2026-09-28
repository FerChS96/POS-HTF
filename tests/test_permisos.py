"""
Pruebas del sistema de permisos.

Cubren tres cosas distintas, y las tres importan:

  1. El contrato (database/permisos.py): que la lista blanca sea coherente y
     que ningun permiso reservado se haya colado a OTORGABLES por descuido.
  2. La capa de datos (PostgresManager): otorgar, revocar y calcular permisos
     efectivos contra un cliente Supabase falso.
  3. Las defensas: que `precios.actualizar` no se pueda otorgar desde el POS y
     que, si alguien mete una fila a mano en la base, TAMPOCO surta efecto.

Ninguna prueba toca la base real.
"""

import logging

import pytest

from conftest import FakeSupabaseClient

from database.permisos import (
    CAJA_ABRIR_TURNO,
    CATALOGO_ALTA_PRODUCTO,
    DESCRIPCIONES,
    INVENTARIO_ACTUALIZAR,
    INVENTARIO_VER,
    MIEMBROS_EDITAR,
    NO_OTORGABLES,
    OTORGABLES,
    PERMISOS_GESTIONAR,
    PERMISOS_POR_ROL,
    PRECIOS_ACTUALIZAR,
    TODOS,
    USUARIOS_GESTIONAR,
    VENTAS_CANCELAR,
    VENTAS_REGISTRAR,
)


# Ids fijos para que las aserciones se lean solas.
ID_ADMIN         = 2
ID_RECEPCION     = 3
ID_SISTEMAS      = 12
ID_INEXISTENTE   = 99

USUARIOS_EJEMPLO = [
    {"id_usuario": ID_ADMIN, "nombre_usuario": "admin",
     "nombre_completo": "Administrador Sistema", "rol": "administrador", "activo": True},
    {"id_usuario": ID_RECEPCION, "nombre_usuario": "balbina",
     "nombre_completo": "Balbina", "rol": "recepcionista", "activo": True},
    {"id_usuario": ID_SISTEMAS, "nombre_usuario": "sistemas",
     "nombre_completo": "Sistemas", "rol": "sistemas", "activo": True},
]


def _construir_gestor(cliente):
    """PostgresManager con la conexion reemplazada por un cliente falso."""
    from database.postgres_manager import PostgresManager

    gestor = PostgresManager.__new__(PostgresManager)
    gestor.client = cliente
    gestor.is_connected = True
    gestor.db_config = {}
    gestor.supabase_key = "llave-de-prueba"
    gestor._missing_suplementos_logged = False
    return gestor


@pytest.fixture
def cliente_permisos():
    """Cliente falso con el padron de usuarios y la tabla de permisos vacia."""
    return FakeSupabaseClient({
        "usuarios": USUARIOS_EJEMPLO,
        "permisos_usuario": [],
    })


@pytest.fixture
def gestor(cliente_permisos):
    return _construir_gestor(cliente_permisos)


# ---------------------------------------------------------------------------
# Cliente falso SIN la tabla permisos_usuario
# ---------------------------------------------------------------------------
# El doble de conftest crea cualquier tabla al vuelo, asi que para probar el
# caso "la migracion 003 no esta aplicada" hay que simular la respuesta real de
# PostgREST: PGRST205 con el texto "schema cache".

class _ConsultaTablaInexistente:
    """Consulta encadenable que siempre falla como PostgREST sin la tabla."""

    def __init__(self, tabla):
        self._tabla = tabla

    def __getattr__(self, _nombre):
        # select/eq/order/limit/insert/update... todo encadena y devuelve self.
        def _encadenar(*args, **kwargs):
            return self
        return _encadenar

    def execute(self):
        raise Exception(
            "{'message': \"Could not find the table 'public." + self._tabla +
            "' in the schema cache\", 'code': 'PGRST205'}"
        )


class ClienteSinTablaPermisos(FakeSupabaseClient):
    """Como el cliente falso normal, pero `permisos_usuario` no existe."""

    def table(self, nombre):
        if nombre == "permisos_usuario":
            return _ConsultaTablaInexistente(nombre)
        return super().table(nombre)


@pytest.fixture
def gestor_sin_tabla():
    return _construir_gestor(ClienteSinTablaPermisos({"usuarios": USUARIOS_EJEMPLO}))


# ---------------------------------------------------------------------------
# 1. Coherencia del contrato
# ---------------------------------------------------------------------------

def test_todo_lo_otorgable_tiene_descripcion():
    """Si la UI va a ofrecer un permiso, tiene que saber como llamarlo."""
    faltantes = sorted(OTORGABLES - set(DESCRIPCIONES))
    assert not faltantes, f"Sin descripcion en DESCRIPCIONES: {faltantes}"


def test_otorgables_y_no_otorgables_no_se_solapan():
    """Un permiso no puede estar en las dos listas: seria una contradiccion."""
    solapados = sorted(OTORGABLES & set(NO_OTORGABLES))
    assert not solapados, f"Estan en OTORGABLES y en NO_OTORGABLES: {solapados}"


def test_ningun_permiso_base_de_recepcion_es_prohibido():
    """
    Lo que recepcion ya trae por rol no puede figurar como prohibido: seria
    prohibir algo que de todas formas tienen.
    """
    contradiccion = sorted(PERMISOS_POR_ROL['recepcionista'] & set(NO_OTORGABLES))
    assert not contradiccion, f"Recepcion ya los trae y estan prohibidos: {contradiccion}"


def test_los_no_otorgables_traen_motivo_por_escrito():
    for permiso, motivo in NO_OTORGABLES.items():
        assert motivo.strip(), f"'{permiso}' esta prohibido sin explicar por que"


def test_no_otorgables_son_permisos_reales():
    desconocidos = sorted(set(NO_OTORGABLES) - set(TODOS))
    assert not desconocidos, f"NO_OTORGABLES nombra permisos que no existen: {desconocidos}"


# ---------------------------------------------------------------------------
# 2. Permisos base por rol
# ---------------------------------------------------------------------------

def test_recepcionista_no_puede_mover_inventario(gestor):
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is False


def test_recepcionista_no_puede_cambiar_precios(gestor):
    assert gestor.tiene_permiso(ID_RECEPCION, PRECIOS_ACTUALIZAR) is False


def test_recepcionista_si_trae_lo_suyo(gestor):
    efectivos = gestor.get_permisos_efectivos(ID_RECEPCION)
    assert VENTAS_REGISTRAR in efectivos
    assert CAJA_ABRIR_TURNO in efectivos
    assert INVENTARIO_VER in efectivos


def test_administrador_tiene_todo(gestor):
    assert gestor.get_permisos_efectivos(ID_ADMIN) == frozenset(TODOS)


def test_sistemas_tiene_todo(gestor):
    assert gestor.get_permisos_efectivos(ID_SISTEMAS) == frozenset(TODOS)


def test_usuario_inexistente_no_tiene_nada(gestor):
    assert gestor.get_permisos_efectivos(ID_INEXISTENTE) == frozenset()
    assert gestor.tiene_permiso(ID_INEXISTENTE, VENTAS_REGISTRAR) is False


def test_permisos_efectivos_son_dos_lecturas(gestor, cliente_permisos):
    """Una consulta a usuarios y una a permisos_usuario. Ni una mas."""
    gestor.get_permisos_efectivos(ID_RECEPCION)
    assert cliente_permisos.contar_llamadas("usuarios", "select") == 1
    assert cliente_permisos.contar_llamadas("permisos_usuario", "select") == 1


# ---------------------------------------------------------------------------
# 3. Otorgar
# ---------------------------------------------------------------------------

def test_otorgar_inventario_a_recepcion(gestor, cliente_permisos):
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is False

    ok = gestor.otorgar_permiso(
        ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN,
        notas="Cubre almacen los martes",
    )

    assert ok is True
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is True

    filas = cliente_permisos.filas("permisos_usuario")
    assert len(filas) == 1
    assert filas[0]["permiso"] == INVENTARIO_ACTUALIZAR
    assert filas[0]["otorgado_por"] == ID_ADMIN
    assert filas[0]["activo"] is True
    assert filas[0]["notas"] == "Cubre almacen los martes"


def test_otorgar_no_contamina_a_los_demas(gestor):
    """El permiso es de esa persona, no del rol entero."""
    gestor.otorgar_permiso(ID_RECEPCION, VENTAS_CANCELAR, otorgado_por=ID_ADMIN)

    otra = dict(USUARIOS_EJEMPLO[1], id_usuario=77, nombre_usuario="margarita")
    gestor.client.store["usuarios"].append(otra)

    assert gestor.tiene_permiso(ID_RECEPCION, VENTAS_CANCELAR) is True
    assert gestor.tiene_permiso(77, VENTAS_CANCELAR) is False


@pytest.mark.parametrize("permiso", sorted(OTORGABLES))
def test_todos_los_otorgables_se_pueden_otorgar(gestor, permiso):
    assert gestor.otorgar_permiso(ID_RECEPCION, permiso, otorgado_por=ID_ADMIN) is True
    assert gestor.tiene_permiso(ID_RECEPCION, permiso) is True


def test_get_permisos_otorgados_solo_devuelve_los_otorgados(gestor):
    gestor.otorgar_permiso(ID_RECEPCION, MIEMBROS_EDITAR, otorgado_por=ID_ADMIN)

    otorgados = gestor.get_permisos_otorgados(ID_RECEPCION)

    assert otorgados == [MIEMBROS_EDITAR]
    # Lo del rol NO aparece aqui: esta funcion solo lee las excepciones.
    assert VENTAS_REGISTRAR not in otorgados


# ---------------------------------------------------------------------------
# 4. La lista blanca: lo que NO se puede otorgar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("permiso", sorted(NO_OTORGABLES))
def test_otorgar_rechaza_los_prohibidos(gestor, cliente_permisos, caplog, permiso):
    """
    Ninguno de los permisos reservados se puede conceder de forma puntual.
    `precios.actualizar` es el caso que motivo todo esto.
    """
    with caplog.at_level(logging.ERROR):
        resultado = gestor.otorgar_permiso(ID_RECEPCION, permiso, otorgado_por=ID_ADMIN)

    assert resultado is False
    # No se escribio nada en la base.
    assert cliente_permisos.filas("permisos_usuario") == []
    assert cliente_permisos.contar_llamadas("permisos_usuario", "insert") == 0
    # Y quedo constancia clara en el log.
    assert any(permiso in r.message for r in caplog.records if r.levelno >= logging.ERROR)


def test_otorgar_precios_actualizar_no_da_el_permiso(gestor):
    """El caso concreto, escrito aparte para que no se pierda entre parametros."""
    assert gestor.otorgar_permiso(
        ID_RECEPCION, PRECIOS_ACTUALIZAR, otorgado_por=ID_ADMIN,
        notas="Me lo pidio el dueno",
    ) is False
    assert gestor.tiene_permiso(ID_RECEPCION, PRECIOS_ACTUALIZAR) is False


def test_otorgar_usuarios_gestionar_no_escala_privilegios(gestor):
    assert gestor.otorgar_permiso(ID_RECEPCION, USUARIOS_GESTIONAR, otorgado_por=ID_ADMIN) is False
    assert gestor.tiene_permiso(ID_RECEPCION, USUARIOS_GESTIONAR) is False


def test_otorgar_permisos_gestionar_no_escala_privilegios(gestor):
    assert gestor.otorgar_permiso(ID_RECEPCION, PERMISOS_GESTIONAR, otorgado_por=ID_ADMIN) is False
    assert gestor.tiene_permiso(ID_RECEPCION, PERMISOS_GESTIONAR) is False


def test_otorgar_permiso_inventado_se_rechaza(gestor, cliente_permisos):
    assert gestor.otorgar_permiso(ID_RECEPCION, "caja.vaciar", otorgado_por=ID_ADMIN) is False
    assert cliente_permisos.filas("permisos_usuario") == []


def test_fila_manipulada_en_la_base_no_concede_nada(gestor, cliente_permisos):
    """
    Segunda defensa: alguien escribe directo en la base (panel de Supabase,
    script suelto) una fila con un permiso reservado. `permisos_efectivos`
    filtra por OTORGABLES, asi que NO surte efecto.

    El CHECK de migrations/003_permisos.sql es la tercera defensa y evita que
    esta fila exista siquiera; aqui se prueba que aun existiendo, no sirve.
    """
    cliente_permisos.store["permisos_usuario"].append({
        "id_permiso": 500,
        "id_usuario": ID_RECEPCION,
        "permiso": PRECIOS_ACTUALIZAR,
        "otorgado_por": None,
        "activo": True,
        "notas": "insertado a mano",
    })

    # La lectura cruda si la ve: la fila esta ahi de verdad.
    assert PRECIOS_ACTUALIZAR in gestor.get_permisos_otorgados(ID_RECEPCION)

    # Pero no cuenta para nada.
    assert PRECIOS_ACTUALIZAR not in gestor.get_permisos_efectivos(ID_RECEPCION)
    assert gestor.tiene_permiso(ID_RECEPCION, PRECIOS_ACTUALIZAR) is False


def test_fila_manipulada_no_arrastra_a_las_validas(gestor, cliente_permisos):
    """Una fila basura no invalida los permisos legitimos de la misma persona."""
    cliente_permisos.store["permisos_usuario"].append({
        "id_usuario": ID_RECEPCION, "permiso": PRECIOS_ACTUALIZAR, "activo": True,
    })
    gestor.otorgar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN)

    efectivos = gestor.get_permisos_efectivos(ID_RECEPCION)

    assert INVENTARIO_ACTUALIZAR in efectivos
    assert PRECIOS_ACTUALIZAR not in efectivos


# ---------------------------------------------------------------------------
# 5. Revocar
# ---------------------------------------------------------------------------

def test_revocar_deja_rastro_y_quita_el_permiso(gestor, cliente_permisos):
    gestor.otorgar_permiso(
        ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN,
        notas="Cubre almacen los martes",
    )
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is True

    assert gestor.revocar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is True

    # El permiso deja de surtir efecto...
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is False
    assert gestor.get_permisos_otorgados(ID_RECEPCION) == []

    # ...pero la fila sigue ahi, con su historia completa.
    filas = cliente_permisos.filas("permisos_usuario")
    assert len(filas) == 1
    assert filas[0]["activo"] is False
    assert filas[0]["otorgado_por"] == ID_ADMIN
    assert filas[0]["notas"] == "Cubre almacen los martes"


def test_revocar_nunca_borra(gestor, cliente_permisos):
    gestor.otorgar_permiso(ID_RECEPCION, VENTAS_CANCELAR, otorgado_por=ID_ADMIN)
    gestor.revocar_permiso(ID_RECEPCION, VENTAS_CANCELAR)

    assert cliente_permisos.contar_llamadas("permisos_usuario", "delete") == 0
    assert len(cliente_permisos.filas("permisos_usuario")) == 1


def test_revocar_algo_que_no_tenia(gestor):
    assert gestor.revocar_permiso(ID_RECEPCION, MIEMBROS_EDITAR) is False


def test_revocar_no_toca_los_del_rol(gestor):
    """Los permisos base no se pueden quitar de uno en uno; vienen con el rol."""
    gestor.revocar_permiso(ID_RECEPCION, VENTAS_REGISTRAR)
    assert gestor.tiene_permiso(ID_RECEPCION, VENTAS_REGISTRAR) is True


# ---------------------------------------------------------------------------
# 6. Otorgar dos veces: reactivar, no duplicar
# ---------------------------------------------------------------------------

def test_otorgar_dos_veces_no_duplica(gestor, cliente_permisos):
    gestor.otorgar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN)
    gestor.otorgar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_SISTEMAS)

    filas = cliente_permisos.filas("permisos_usuario")
    assert len(filas) == 1
    assert filas[0]["otorgado_por"] == ID_SISTEMAS
    assert cliente_permisos.contar_llamadas("permisos_usuario", "insert") == 1


def test_otorgar_tras_revocar_reactiva_la_misma_fila(gestor, cliente_permisos):
    gestor.otorgar_permiso(
        ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN, notas="Primera vez",
    )
    gestor.revocar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR)

    assert gestor.otorgar_permiso(
        ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_SISTEMAS, notas="Otra vez",
    ) is True

    filas = cliente_permisos.filas("permisos_usuario")
    assert len(filas) == 1
    assert filas[0]["activo"] is True
    assert filas[0]["notas"] == "Otra vez"
    assert gestor.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is True


def test_reactivar_sin_notas_conserva_las_anteriores(gestor, cliente_permisos):
    gestor.otorgar_permiso(
        ID_RECEPCION, VENTAS_CANCELAR, otorgado_por=ID_ADMIN, notas="Autorizado por el dueno",
    )
    gestor.revocar_permiso(ID_RECEPCION, VENTAS_CANCELAR)
    gestor.otorgar_permiso(ID_RECEPCION, VENTAS_CANCELAR, otorgado_por=ID_ADMIN)

    assert cliente_permisos.filas("permisos_usuario")[0]["notas"] == "Autorizado por el dueno"


# ---------------------------------------------------------------------------
# 7. Padron para la pantalla de permisos
# ---------------------------------------------------------------------------

def test_get_usuarios_con_permisos(gestor):
    gestor.otorgar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN)

    padron = {u["id_usuario"]: u for u in gestor.get_usuarios_con_permisos()}

    assert set(padron) == {ID_ADMIN, ID_RECEPCION, ID_SISTEMAS}

    balbina = padron[ID_RECEPCION]
    assert balbina["rol"] == "recepcionista"
    assert balbina["permisos_otorgados"] == [INVENTARIO_ACTUALIZAR]
    assert INVENTARIO_ACTUALIZAR in balbina["permisos_efectivos"]
    assert VENTAS_REGISTRAR in balbina["permisos_efectivos"]

    assert padron[ID_ADMIN]["permisos_otorgados"] == []
    assert padron[ID_ADMIN]["permisos_efectivos"] == sorted(TODOS)


def test_get_usuarios_con_permisos_omite_los_revocados(gestor):
    gestor.otorgar_permiso(ID_RECEPCION, CATALOGO_ALTA_PRODUCTO, otorgado_por=ID_ADMIN)
    gestor.revocar_permiso(ID_RECEPCION, CATALOGO_ALTA_PRODUCTO)

    padron = {u["id_usuario"]: u for u in gestor.get_usuarios_con_permisos()}

    assert padron[ID_RECEPCION]["permisos_otorgados"] == []


def test_get_usuarios_con_permisos_no_hace_n_mas_1(gestor, cliente_permisos):
    """Dos consultas en total, sin importar cuantos usuarios haya."""
    gestor.otorgar_permiso(ID_RECEPCION, MIEMBROS_EDITAR, otorgado_por=ID_ADMIN)
    cliente_permisos.calls.clear()

    gestor.get_usuarios_con_permisos()

    assert len(cliente_permisos.calls) == 2


# ---------------------------------------------------------------------------
# 8. Sin la tabla permisos_usuario (migracion 003 sin aplicar)
# ---------------------------------------------------------------------------

def test_sin_tabla_los_permisos_del_rol_siguen_vivos(gestor_sin_tabla):
    """Lo importante: nadie se queda fuera del POS por una migracion pendiente."""
    efectivos = gestor_sin_tabla.get_permisos_efectivos(ID_RECEPCION)

    assert efectivos == PERMISOS_POR_ROL["recepcionista"]
    assert gestor_sin_tabla.tiene_permiso(ID_RECEPCION, VENTAS_REGISTRAR) is True
    assert gestor_sin_tabla.tiene_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is False


def test_sin_tabla_el_administrador_conserva_todo(gestor_sin_tabla):
    assert gestor_sin_tabla.get_permisos_efectivos(ID_ADMIN) == frozenset(TODOS)


def test_sin_tabla_get_permisos_otorgados_devuelve_vacio(gestor_sin_tabla):
    assert gestor_sin_tabla.get_permisos_otorgados(ID_RECEPCION) == []


def test_sin_tabla_otorgar_falla_sin_reventar(gestor_sin_tabla):
    assert gestor_sin_tabla.otorgar_permiso(
        ID_RECEPCION, INVENTARIO_ACTUALIZAR, otorgado_por=ID_ADMIN,
    ) is False


def test_sin_tabla_revocar_falla_sin_reventar(gestor_sin_tabla):
    assert gestor_sin_tabla.revocar_permiso(ID_RECEPCION, INVENTARIO_ACTUALIZAR) is False


def test_sin_tabla_el_padron_sigue_saliendo(gestor_sin_tabla):
    padron = {u["id_usuario"]: u for u in gestor_sin_tabla.get_usuarios_con_permisos()}

    assert len(padron) == 3
    assert padron[ID_RECEPCION]["permisos_otorgados"] == []
    assert padron[ID_RECEPCION]["permisos_efectivos"] == sorted(
        PERMISOS_POR_ROL["recepcionista"]
    )


def test_sin_tabla_el_aviso_se_registra_una_sola_vez(gestor_sin_tabla, caplog):
    """
    El POS consulta permisos todo el tiempo. Si el aviso saliera en cada
    consulta, el log quedaria inservible.
    """
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            gestor_sin_tabla.get_permisos_otorgados(ID_RECEPCION)
            gestor_sin_tabla.get_permisos_efectivos(ID_RECEPCION)

    avisos = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "permisos_usuario" in r.message
    ]
    assert len(avisos) == 1
