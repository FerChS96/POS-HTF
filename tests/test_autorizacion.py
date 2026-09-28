"""
Pruebas de autorizacion del POS HTF.

Cubren dos cosas distintas:

  1. El dialogo de autorizacion de administrador (AdminAuthDialog). Contiene la
     REGRESION del bug por el que la verificacion de contrasenia quedo indentada
     dentro del 'if' de rechazo, despues del 'return': el bloque era inalcanzable
     y NINGUN administrador podia autorizar nunca. Con el codigo viejo,
     test_administrador_con_contrasenia_correcta_autoriza falla.

  2. Los permisos donde de verdad importan: precios en el catalogo editable
     (permiso NO otorgable) y movimientos de inventario (permiso SI otorgable).

Ninguna prueba abre ventanas Qt ni toca la base real. Los dialogos se instancian
con __new__ y se les sustituyen los campos por objetos minimos, igual que en
tests/test_usuarios.py. 'tiene_permiso' de la capa de datos se simula con un
doble.
"""

import datetime

import bcrypt
import pytest

from conftest import FakeSupabaseClient
from database.permisos import INVENTARIO_ACTUALIZAR, PRECIOS_ACTUALIZAR


# Rondas bajas a proposito: aqui se prueba el flujo, no la fortaleza del hash.
def _hash(clave):
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


CLAVE_ADMIN = "ClaveAdmin123"
CLAVE_RECEPCION = "ClaveRecepcion123"

USUARIOS = [
    {"id_usuario": 2, "nombre_usuario": "admin", "nombre_completo": "Administrador Sistema",
     "rol": "administrador", "activo": True, "contrasenia": _hash(CLAVE_ADMIN)},
    {"id_usuario": 3, "nombre_usuario": "balbina", "nombre_completo": "Balbina",
     "rol": "recepcionista", "activo": True, "contrasenia": _hash(CLAVE_RECEPCION)},
    {"id_usuario": 5, "nombre_usuario": "margarita", "nombre_completo": "Margarita",
     "rol": "administrador", "activo": False, "contrasenia": _hash(CLAVE_ADMIN)},
]


# ---------------------------------------------------------------------------
# Dobles minimos
# ---------------------------------------------------------------------------

class GestorFake:
    """
    Doble de PostgresManager: solo expone lo que la UI usa de verdad.

    'tiene_permiso' se simula con un mapa {id_usuario: {permisos}}; asi las
    pruebas no dependen de la implementacion que otro agente esta escribiendo.
    """

    def __init__(self, client=None, permisos=None, fallar_permiso=False):
        self.client = client
        self._permisos = permisos or {}
        self._fallar_permiso = fallar_permiso
        self.consultas_permiso = []
        self.stock_actualizado = []
        self.movimientos = []

    def tiene_permiso(self, id_usuario, permiso):
        self.consultas_permiso.append((id_usuario, permiso))
        if self._fallar_permiso:
            raise Exception("Fallo simulado consultando permisos")
        return permiso in self._permisos.get(id_usuario, frozenset())

    # --- inventario ---
    def actualizar_stock(self, codigo, tipo_producto, nuevo_stock, **kwargs):
        self.stock_actualizado.append((codigo, tipo_producto, nuevo_stock))
        return True

    def registrar_movimiento_inventario(self, datos):
        self.movimientos.append(dict(datos))
        return True


class CampoTexto:
    """QLineEdit / QTextEdit minimo."""

    def __init__(self, valor=""):
        self._valor = valor
        self.limpiado = False
        self.enfocado = False

    def text(self):
        return self._valor

    def toPlainText(self):
        return self._valor

    def clear(self):
        self._valor = ""
        self.limpiado = True

    def setFocus(self):
        self.enfocado = True


class SenalFake:
    """Signal de Qt minima: solo registra lo emitido."""

    def __init__(self):
        self.emitido = []

    def emit(self, *args):
        self.emitido.append(args)


class ValorFijo:
    """Sirve de QSpinBox, QComboBox y QTextEdit de una sola lectura."""

    def __init__(self, valor):
        self._valor = valor

    def value(self):
        return self._valor

    def currentText(self):
        return self._valor

    def toPlainText(self):
        return str(self._valor)


class FechaFake:
    """QDateEdit minimo: .date().toPython() devuelve una fecha real."""

    def date(self):
        return self

    def toPython(self):
        return datetime.date(2026, 9, 28)


@pytest.fixture
def dialogos(monkeypatch):
    """
    Captura los dialogos que mostraria la UI.

    Se parchea tanto ui.components (el dialogo de autorizacion importa dentro
    de la funcion) como el espacio de nombres de los modulos que importaron los
    helpers al cargarse.
    """
    import ui.components
    import ui.editable_catalog_grid
    import ui.movimiento_inventario_window

    registro = []

    def _capturador(tipo):
        def _mostrar(parent, titulo, mensaje, detail=None, **kwargs):
            registro.append({
                "tipo": tipo,
                "titulo": titulo,
                "mensaje": mensaje,
                "detalle": detail,
            })
        return _mostrar

    nombres = {
        "show_error_dialog": "error",
        "show_warning_dialog": "advertencia",
        "show_info_dialog": "info",
        "show_success_dialog": "exito",
    }
    modulos = (ui.components, ui.editable_catalog_grid, ui.movimiento_inventario_window)
    for modulo in modulos:
        for nombre, tipo in nombres.items():
            if hasattr(modulo, nombre):
                monkeypatch.setattr(modulo, nombre, _capturador(tipo))

    return registro


# ---------------------------------------------------------------------------
# AdminAuthDialog
# ---------------------------------------------------------------------------

def _dialogo_auth(usuario="", password="", justificacion="Cliente esperando"):
    """AdminAuthDialog sin construir la interfaz Qt."""
    from ui.admin_auth_dialog import AdminAuthDialog

    cliente = FakeSupabaseClient({"usuarios": USUARIOS})
    dialogo = AdminAuthDialog.__new__(AdminAuthDialog)
    dialogo.pg_manager = GestorFake(client=cliente)
    dialogo.motivo = "Cierre de caja fuera de horario"
    dialogo.autorizado = False
    dialogo.id_admin_autorizador = None
    dialogo.nombre_admin = None
    dialogo.justificacion = ""
    dialogo.usuario_input = CampoTexto(usuario)
    dialogo.password_input = CampoTexto(password)
    dialogo.justificacion_input = CampoTexto(justificacion)

    # accept() abriria el dialogo real: se sustituye por un contador.
    dialogo.accept_llamadas = []
    dialogo.accept = lambda: dialogo.accept_llamadas.append(True)
    return dialogo


def test_administrador_con_contrasenia_correcta_autoriza(dialogos):
    """
    REGRESION del bug: con el codigo viejo la verificacion de contrasenia
    estaba dentro del 'if' de rechazo, despues del 'return', asi que para un
    administrador nunca se ejecutaba y accept() jamas se llamaba.
    """
    dialogo = _dialogo_auth(usuario="admin", password=CLAVE_ADMIN)
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is True
    assert dialogo.accept_llamadas == [True]
    assert dialogo.id_admin_autorizador == 2
    assert dialogo.nombre_admin == "Administrador Sistema"
    assert dialogo.justificacion == "Cliente esperando"


def test_autorizacion_exitosa_devuelve_los_datos(dialogos):
    dialogo = _dialogo_auth(usuario="admin", password=CLAVE_ADMIN)
    dialogo.verificar_credenciales()

    datos = dialogo.get_autorizacion()
    assert datos["autorizado"] is True
    assert datos["id_admin"] == 2
    assert datos["nombre_admin"] == "Administrador Sistema"
    assert datos["justificacion"] == "Cliente esperando"


def test_administrador_con_contrasenia_incorrecta_no_autoriza(dialogos):
    dialogo = _dialogo_auth(usuario="admin", password="EstaNoEs")
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []
    assert dialogo.get_autorizacion() == {"autorizado": False}


def test_recepcionista_con_contrasenia_correcta_no_autoriza(dialogos):
    """El rol manda: aunque la clave sea buena, una recepcionista no autoriza."""
    dialogo = _dialogo_auth(usuario="balbina", password=CLAVE_RECEPCION)
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []
    assert dialogos[-1]["titulo"] == "Acceso Denegado"


def test_usuario_inexistente_no_autoriza(dialogos):
    dialogo = _dialogo_auth(usuario="nadie", password=CLAVE_ADMIN)
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []


def test_administrador_inactivo_no_autoriza(dialogos):
    """Una cuenta desactivada no debe poder autorizar nada."""
    dialogo = _dialogo_auth(usuario="margarita", password=CLAVE_ADMIN)
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []


def test_no_revela_si_el_usuario_existe(dialogos):
    """
    Un usuario inexistente y una contrasenia incorrecta deben producir
    exactamente el mismo mensaje: si difieren, el dialogo confirma que cuentas
    existen.
    """
    inexistente = _dialogo_auth(usuario="nadie", password="LoQueSea")
    inexistente.verificar_credenciales()
    mensaje_inexistente = dialogos[-1]

    clave_mala = _dialogo_auth(usuario="admin", password="EstaNoEs")
    clave_mala.verificar_credenciales()
    mensaje_clave_mala = dialogos[-1]

    assert mensaje_inexistente["titulo"] == mensaje_clave_mala["titulo"]
    assert mensaje_inexistente["mensaje"] == mensaje_clave_mala["mensaje"]
    assert "no encontrado" not in mensaje_inexistente["mensaje"].lower()


def test_registra_en_el_log_los_intentos_fallidos(dialogos, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        dialogo = _dialogo_auth(usuario="admin", password="EstaNoEs")
        dialogo.verificar_credenciales()

    registros = [r.getMessage() for r in caplog.records]
    assert any("[SEGURIDAD]" in m and "admin" in m for m in registros)


def test_exige_justificacion_no_vacia(dialogos):
    dialogo = _dialogo_auth(usuario="admin", password=CLAVE_ADMIN, justificacion="   ")
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []
    assert dialogos[-1]["titulo"] == "Campo Requerido"


@pytest.mark.parametrize("usuario,password", [("", CLAVE_ADMIN), ("admin", "")])
def test_exige_usuario_y_contrasenia(dialogos, usuario, password):
    dialogo = _dialogo_auth(usuario=usuario, password=password)
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []


def test_un_error_de_la_base_no_autoriza(dialogos):
    """Si la consulta revienta, se falla cerrado."""
    dialogo = _dialogo_auth(usuario="admin", password=CLAVE_ADMIN)
    dialogo.pg_manager.client.fail_on = ("usuarios", "select")
    dialogo.verificar_credenciales()

    assert dialogo.autorizado is False
    assert dialogo.accept_llamadas == []


# ---------------------------------------------------------------------------
# Precios: EditableCatalogGrid (permiso NO otorgable)
# ---------------------------------------------------------------------------

PRODUCTOS = [
    {"id_producto": 1, "codigo_interno": "PROT-001", "nombre": "Proteina Whey 1kg",
     "descripcion": "Sabor chocolate", "precio_venta": 650.0, "activo": True},
]


def _grid(user_data, cambios, permisos=None):
    """EditableCatalogGrid sin construir la interfaz Qt."""
    from ui.editable_catalog_grid import EditableCatalogGrid

    cliente = FakeSupabaseClient({"ca_productos_varios": PRODUCTOS})
    grid = EditableCatalogGrid.__new__(EditableCatalogGrid)
    grid.pg_manager = GestorFake(client=cliente, permisos=permisos)
    grid.user_data = user_data
    grid.productos_varios = [dict(p) for p in PRODUCTOS]
    grid.suplementos = []
    grid.cambios_pendientes = cambios
    grid.puede_editar_precios = False
    grid.actualizar_label_cambios = lambda: None
    grid.cargar_datos = lambda: None
    grid.catalogo_actualizado = SenalFake()
    return grid


def _precio_guardado(grid):
    fila = grid.pg_manager.client.filas("ca_productos_varios")[0]
    return fila["precio_venta"]


def _nombre_guardado(grid):
    fila = grid.pg_manager.client.filas("ca_productos_varios")[0]
    return fila["nombre"]


def test_recepcionista_no_puede_guardar_precios(dialogos):
    grid = _grid(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        cambios={"PROT-001": {"precio_venta": "1.00"}},
        permisos={3: frozenset()},
    )
    grid.guardar_cambios()

    assert _precio_guardado(grid) == 650.0
    assert grid.pg_manager.consultas_permiso == [(3, PRECIOS_ACTUALIZAR)]


def test_administrador_si_puede_guardar_precios(dialogos):
    grid = _grid(
        user_data={"id_usuario": 2, "rol": "administrador"},
        cambios={"PROT-001": {"precio_venta": "700.00"}},
        permisos={2: frozenset({PRECIOS_ACTUALIZAR})},
    )
    grid.guardar_cambios()

    assert _precio_guardado(grid) == 700.0


def test_se_guardan_los_demas_campos_y_solo_se_omite_el_precio(dialogos):
    """Sin permiso de precios no se descarta todo el guardado en silencio."""
    grid = _grid(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        cambios={"PROT-001": {"nombre": "Proteina Whey 1kg Chocolate",
                              "precio_venta": "1.00"}},
        permisos={3: frozenset()},
    )
    grid.guardar_cambios()

    assert _nombre_guardado(grid) == "Proteina Whey 1kg Chocolate"
    assert _precio_guardado(grid) == 650.0


def test_avisa_de_los_precios_no_aplicados(dialogos):
    grid = _grid(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        cambios={"PROT-001": {"nombre": "Otro nombre", "precio_venta": "1.00"}},
        permisos={3: frozenset()},
    )
    grid.guardar_cambios()

    avisos = [d for d in dialogos if d["tipo"] == "advertencia"]
    assert avisos, "debe avisarse que el precio no se aplico"
    assert "PROT-001" in avisos[-1]["mensaje"]
    assert "precio" in avisos[-1]["mensaje"].lower()


def test_el_precio_rechazado_queda_en_el_log(dialogos, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        grid = _grid(
            user_data={"id_usuario": 3, "rol": "recepcionista"},
            cambios={"PROT-001": {"precio_venta": "1.00"}},
            permisos={3: frozenset()},
        )
        grid.guardar_cambios()

    registros = [r.getMessage() for r in caplog.records]
    assert any("[SEGURIDAD]" in m and "PROT-001" in m for m in registros)


def test_sin_user_data_no_se_guardan_precios(dialogos):
    """Fallar cerrado: sin datos de usuario no hay permiso de precios."""
    grid = _grid(
        user_data=None,
        cambios={"PROT-001": {"precio_venta": "1.00"}},
        permisos={2: frozenset({PRECIOS_ACTUALIZAR})},
    )
    grid.guardar_cambios()

    assert _precio_guardado(grid) == 650.0
    assert grid.pg_manager.consultas_permiso == []


def test_si_falla_la_consulta_de_permisos_no_se_guardan_precios(dialogos):
    from ui.editable_catalog_grid import EditableCatalogGrid

    cliente = FakeSupabaseClient({"ca_productos_varios": PRODUCTOS})
    grid = EditableCatalogGrid.__new__(EditableCatalogGrid)
    grid.pg_manager = GestorFake(client=cliente, fallar_permiso=True)
    grid.user_data = {"id_usuario": 2, "rol": "administrador"}
    grid.productos_varios = [dict(p) for p in PRODUCTOS]
    grid.suplementos = []
    grid.cambios_pendientes = {"PROT-001": {"precio_venta": "1.00"}}
    grid.puede_editar_precios = True
    grid.actualizar_label_cambios = lambda: None
    grid.cargar_datos = lambda: None
    grid.catalogo_actualizado = SenalFake()

    grid.guardar_cambios()

    assert _precio_guardado(grid) == 650.0


def test_precios_actualizar_no_es_otorgable():
    """El contrato lo dice; aqui se verifica en vez de confiar en la memoria."""
    from database.permisos import OTORGABLES

    assert PRECIOS_ACTUALIZAR not in OTORGABLES


# ---------------------------------------------------------------------------
# Inventario: MovimientoInventarioWindow (permiso SI otorgable)
# ---------------------------------------------------------------------------

PRODUCTO_INVENTARIO = {
    "codigo_interno": "PROT-001",
    "tipo_producto": "varios",
    "nombre": "Proteina Whey 1kg",
    "stock_actual": 10,
}


def _ventana_movimiento(user_data, permisos=None, cantidad=3):
    """MovimientoInventarioWindow sin construir la interfaz Qt."""
    from ui.movimiento_inventario_window import MovimientoInventarioWindow

    ventana = MovimientoInventarioWindow.__new__(MovimientoInventarioWindow)
    ventana.tipo_movimiento = "entrada"
    ventana.pg_manager = GestorFake(permisos=permisos)
    ventana.supabase_service = None
    ventana.user_data = user_data
    ventana.producto_seleccionado = dict(PRODUCTO_INVENTARIO)
    ventana.cantidad_spin = ValorFijo(cantidad)
    ventana.tipo_combo = ValorFijo("Compra")
    ventana.fecha_input = FechaFake()
    ventana.observaciones_input = ValorFijo("")
    ventana.search_bar = None
    ventana.movimiento_registrado = SenalFake()
    ventana.limpiar_formulario = lambda: None
    return ventana


def test_recepcionista_con_permiso_otorgado_si_mueve_inventario(dialogos):
    """El caso real: a Balbina le otorgaron 'inventario.actualizar'."""
    ventana = _ventana_movimiento(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        permisos={3: frozenset({INVENTARIO_ACTUALIZAR})},
    )
    ventana.registrar_movimiento()

    assert ventana.pg_manager.stock_actualizado == [("PROT-001", "varios", 13)]
    assert len(ventana.pg_manager.movimientos) == 1
    assert ventana.pg_manager.movimientos[0]["id_usuario"] == 3
    assert ventana.movimiento_registrado.emitido


def test_recepcionista_sin_permiso_no_mueve_inventario(dialogos):
    ventana = _ventana_movimiento(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        permisos={3: frozenset()},
    )
    ventana.registrar_movimiento()

    assert ventana.pg_manager.stock_actualizado == []
    assert ventana.pg_manager.movimientos == []
    assert ventana.movimiento_registrado.emitido == []


def test_sin_permiso_se_avisa_con_un_dialogo(dialogos):
    ventana = _ventana_movimiento(
        user_data={"id_usuario": 3, "rol": "recepcionista"},
        permisos={3: frozenset()},
    )
    ventana.registrar_movimiento()

    errores = [d for d in dialogos if d["tipo"] == "error"]
    assert errores, "debe avisarse que falta el permiso"
    assert "permiso" in errores[-1]["titulo"].lower()


def test_sin_user_data_no_mueve_inventario(dialogos):
    """Fallar cerrado: sin datos de usuario no se ejecuta el movimiento."""
    ventana = _ventana_movimiento(user_data=None, permisos={3: frozenset({INVENTARIO_ACTUALIZAR})})
    ventana.registrar_movimiento()

    assert ventana.pg_manager.stock_actualizado == []
    assert ventana.pg_manager.movimientos == []
    assert ventana.pg_manager.consultas_permiso == []


def test_si_falla_la_consulta_de_permisos_no_mueve_inventario(dialogos):
    from ui.movimiento_inventario_window import MovimientoInventarioWindow

    ventana = _ventana_movimiento(user_data={"id_usuario": 3, "rol": "recepcionista"})
    ventana.pg_manager = GestorFake(fallar_permiso=True)
    ventana.registrar_movimiento()

    assert ventana.pg_manager.stock_actualizado == []
    assert ventana.pg_manager.movimientos == []


def test_el_movimiento_rechazado_queda_en_el_log(dialogos, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        ventana = _ventana_movimiento(
            user_data={"id_usuario": 3, "rol": "recepcionista"},
            permisos={3: frozenset()},
        )
        ventana.registrar_movimiento()

    registros = [r.getMessage() for r in caplog.records]
    assert any("[SEGURIDAD]" in m and INVENTARIO_ACTUALIZAR in m for m in registros)


def test_administrador_mueve_inventario_sin_otorgamiento(dialogos):
    """Al administrador le viene de su rol, no de un otorgamiento puntual."""
    ventana = _ventana_movimiento(
        user_data={"id_usuario": 2, "rol": "administrador"},
        permisos={2: frozenset({INVENTARIO_ACTUALIZAR})},
    )
    ventana.registrar_movimiento()

    assert ventana.pg_manager.stock_actualizado == [("PROT-001", "varios", 13)]


def test_inventario_actualizar_si_es_otorgable():
    from database.permisos import OTORGABLES

    assert INVENTARIO_ACTUALIZAR in OTORGABLES
