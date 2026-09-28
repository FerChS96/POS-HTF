"""
Pruebas de la gestion de usuarios.

Cubren la capa de datos nueva (listar, actualizar, contar administradores) y
las validaciones del formulario, incluidos los dos bloqueos que evitan dejar
el sistema sin acceso.

Ninguna prueba toca la base real.
"""

import pytest

from conftest import FakeSupabaseClient


USUARIOS_EJEMPLO = [
    {"id_usuario": 2,  "nombre_usuario": "admin",     "nombre_completo": "Administrador Sistema",
     "rol": "administrador", "activo": True,  "contrasenia": "$2b$12$hashfalso",
     "ultimo_acceso": "2026-08-20T21:15:00", "fecha_creacion": "2025-10-01T00:00:00"},
    {"id_usuario": 3,  "nombre_usuario": "balbina",   "nombre_completo": "Balbina",
     "rol": "recepcionista", "activo": True,  "contrasenia": "$2b$12$hashfalso",
     "ultimo_acceso": "2026-09-28T10:31:00", "fecha_creacion": "2025-10-01T00:00:00"},
    {"id_usuario": 5,  "nombre_usuario": "margarita", "nombre_completo": "Margarita",
     "rol": "recepcionista", "activo": False, "contrasenia": "$2b$12$hashfalso",
     "ultimo_acceso": None, "fecha_creacion": "2025-10-01T00:00:00"},
    {"id_usuario": 12, "nombre_usuario": "sistemas",  "nombre_completo": "Sistemas",
     "rol": "sistemas", "activo": True, "contrasenia": "$2b$12$hashfalso",
     "ultimo_acceso": None, "fecha_creacion": "2025-10-01T00:00:00"},
]


@pytest.fixture
def gestor_usuarios():
    """PostgresManager con un padron de usuarios en memoria."""
    from database.postgres_manager import PostgresManager

    cliente = FakeSupabaseClient({"usuarios": USUARIOS_EJEMPLO})
    gestor = PostgresManager.__new__(PostgresManager)
    gestor.client = cliente
    gestor.is_connected = True
    gestor.db_config = {}
    gestor.supabase_key = "llave-de-prueba"
    gestor._missing_suplementos_logged = False
    return gestor


# ---------------------------------------------------------------------------
# get_users
# ---------------------------------------------------------------------------

def test_get_users_devuelve_todos(gestor_usuarios):
    assert len(gestor_usuarios.get_users()) == 4


def test_get_users_puede_filtrar_inactivos(gestor_usuarios):
    activos = gestor_usuarios.get_users(incluir_inactivos=False)
    assert len(activos) == 3
    assert all(u["activo"] for u in activos)


def test_get_users_nunca_expone_el_hash(gestor_usuarios):
    """La UI no necesita el hash y no debe tenerlo a mano."""
    for usuario in gestor_usuarios.get_users():
        assert "contrasenia" not in usuario


def test_get_users_viene_ordenado_por_id(gestor_usuarios):
    ids = [u["id_usuario"] for u in gestor_usuarios.get_users()]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# contar_administradores_activos
# ---------------------------------------------------------------------------

def test_cuenta_administradores_activos(gestor_usuarios):
    """admin y sistemas: dos cuentas administrativas activas."""
    assert gestor_usuarios.contar_administradores_activos() == 2


def test_cuenta_administradores_excluyendo_uno(gestor_usuarios):
    assert gestor_usuarios.contar_administradores_activos(excluir_id=2) == 1


def test_no_cuenta_recepcionistas(gestor_usuarios):
    gestor_usuarios.client.store["usuarios"] = [
        u for u in USUARIOS_EJEMPLO if u["rol"] == "recepcionista"
    ]
    assert gestor_usuarios.contar_administradores_activos() == 0


def test_no_cuenta_administradores_inactivos(gestor_usuarios):
    for fila in gestor_usuarios.client.store["usuarios"]:
        if fila["rol"] in ("administrador", "sistemas"):
            fila["activo"] = False
    assert gestor_usuarios.contar_administradores_activos() == 0


def test_ante_un_error_responde_cero(gestor_usuarios):
    """
    Si la consulta falla debe devolver 0, para que el llamador BLOQUEE el
    cambio. Responder un numero alto por optimismo permitiria desactivar al
    ultimo administrador.
    """
    gestor_usuarios.client.fail_on = ("usuarios", "select")
    assert gestor_usuarios.contar_administradores_activos() == 0


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------

def test_actualiza_nombre(gestor_usuarios):
    assert gestor_usuarios.update_user(3, nombre_completo="Balbina Perez") is True
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert fila["nombre_completo"] == "Balbina Perez"


def test_actualiza_rol(gestor_usuarios):
    assert gestor_usuarios.update_user(3, rol="administrador") is True
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert fila["rol"] == "administrador"


def test_desactiva_usuario(gestor_usuarios):
    assert gestor_usuarios.update_user(3, activo=False) is True
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert fila["activo"] is False


@pytest.mark.parametrize("rol_invalido", ["gerente", "ADMIN", "root", ""])
def test_rechaza_roles_inventados(gestor_usuarios, rol_invalido):
    assert gestor_usuarios.update_user(3, rol=rol_invalido) is False


def test_no_cambia_nada_sin_argumentos(gestor_usuarios):
    assert gestor_usuarios.update_user(3) is False


def test_update_user_no_toca_la_contrasenia(gestor_usuarios):
    antes = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    gestor_usuarios.update_user(3, nombre_completo="Otro Nombre")
    despues = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert despues["contrasenia"] == antes["contrasenia"]


def test_update_user_no_permite_cambiar_el_nombre_de_usuario(gestor_usuarios):
    """El nombre de usuario es la llave de acceso: no se toca desde aqui."""
    gestor_usuarios.update_user(3, nombre_completo="X", rol="recepcionista", activo=True)
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert fila["nombre_usuario"] == "balbina"


# ---------------------------------------------------------------------------
# Contrasenia
# ---------------------------------------------------------------------------

def test_cambia_contrasenia_por_id(gestor_usuarios):
    import bcrypt

    assert gestor_usuarios.update_user_password_by_id(3, "NuevaClave123") is True
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert fila["contrasenia"] != "$2b$12$hashfalso"
    assert bcrypt.checkpw(b"NuevaClave123", fila["contrasenia"].encode("utf-8"))


def test_la_contrasenia_no_se_guarda_en_claro(gestor_usuarios):
    gestor_usuarios.update_user_password_by_id(3, "TextoPlano123")
    fila = [u for u in gestor_usuarios.client.filas("usuarios") if u["id_usuario"] == 3][0]
    assert "TextoPlano123" not in fila["contrasenia"]
    assert fila["contrasenia"].startswith("$2")


def test_cambiar_contrasenia_de_usuario_inexistente(gestor_usuarios):
    assert gestor_usuarios.update_user_password_by_id(999, "LoQueSea123") is False


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

def test_crea_usuario_con_hash(gestor_usuarios):
    import bcrypt

    nuevo = gestor_usuarios.create_user("yessica", "HTF-141824", "Yessica Valdez Ayala")
    assert nuevo is not None
    fila = [u for u in gestor_usuarios.client.filas("usuarios")
            if u["nombre_usuario"] == "yessica"][0]
    assert fila["rol"] == "recepcionista"
    assert fila["activo"] is True
    assert bcrypt.checkpw(b"HTF-141824", fila["contrasenia"].encode("utf-8"))


def test_no_crea_usuario_duplicado(gestor_usuarios):
    assert gestor_usuarios.create_user("admin", "OtraClave123", "Impostor") is None


def test_no_crea_usuario_con_nombre_corto(gestor_usuarios):
    assert gestor_usuarios.create_user("ab", "OtraClave123", "Muy Corto") is None


# ---------------------------------------------------------------------------
# Validaciones del formulario
# ---------------------------------------------------------------------------

def _formulario(gestor, editando=None, **campos):
    """
    FormularioUsuarioDialog sin construir la interfaz Qt: se evita __init__
    con __new__ y se sustituyen los campos por objetos minimos.
    """
    from ui.usuarios_window import FormularioUsuarioDialog

    class _Campo:
        def __init__(self, valor=""):
            self._v = valor

        def text(self):
            return self._v

    dialogo = FormularioUsuarioDialog.__new__(FormularioUsuarioDialog)
    dialogo.pg_manager = gestor
    dialogo.usuario = editando
    dialogo.es_alta = editando is None
    dialogo.input_usuario = _Campo(campos.get("usuario", ""))
    dialogo.input_nombre = _Campo(campos.get("nombre", ""))
    dialogo.input_contrasenia = _Campo(campos.get("contrasenia", ""))
    dialogo.input_confirmacion = _Campo(campos.get("confirmacion", ""))
    return dialogo


def test_alta_valida_pasa(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="yessica", nombre="Yessica Valdez Ayala",
                       contrasenia="HTF-141824", confirmacion="HTF-141824")
    assert form.validar() is None


def test_alta_rechaza_usuario_corto(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="ab", nombre="Alguien",
                       contrasenia="HTF-141824", confirmacion="HTF-141824")
    assert "al menos" in form.validar()


def test_alta_rechaza_usuario_con_espacios(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="yessica valdez", nombre="Alguien",
                       contrasenia="HTF-141824", confirmacion="HTF-141824")
    assert "espacios" in form.validar()


def test_alta_exige_nombre_completo(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="yessica", nombre="   ",
                       contrasenia="HTF-141824", confirmacion="HTF-141824")
    assert "nombre completo" in form.validar().lower()


def test_alta_rechaza_contrasenia_corta(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="yessica", nombre="Yessica",
                       contrasenia="corta", confirmacion="corta")
    assert "contraseña" in form.validar().lower()


def test_alta_rechaza_contrasenias_distintas(gestor_usuarios):
    form = _formulario(gestor_usuarios, usuario="yessica", nombre="Yessica",
                       contrasenia="HTF-141824", confirmacion="HTF-999999")
    assert "no coinciden" in form.validar()


def test_edicion_permite_dejar_la_contrasenia_vacia(gestor_usuarios):
    """En edicion, vacio significa 'no la cambies'."""
    form = _formulario(gestor_usuarios, editando=USUARIOS_EJEMPLO[1],
                       nombre="Balbina Perez", contrasenia="", confirmacion="")
    assert form.validar() is None


def test_edicion_valida_la_contrasenia_si_se_escribe(gestor_usuarios):
    form = _formulario(gestor_usuarios, editando=USUARIOS_EJEMPLO[1],
                       nombre="Balbina", contrasenia="123", confirmacion="123")
    assert form.validar() is not None
