"""
Pruebas de PostgresManager.create_sale.

Cubren los tres bugs reportados:
  Bug A - venta cobrada sin detalle (el mas grave).
  Bug B - carrera de stock entre cajas.
  Bug C - N+1 (5 round-trips por linea de venta).

El andamiaje (FakeSupabaseClient, fixtures) vive en tests/conftest.py.
"""

import pytest

from conftest import FakeSupabaseClient
from database.postgres_manager import PostgresManager, StockInsuficienteError


# ---------------------------------------------------------------------------
# Helpers locales (las fixtures compartidas estan en conftest.py)
# ---------------------------------------------------------------------------

def _manager_con(cliente):
    """PostgresManager sin __init__ real, apuntando al cliente falso."""
    gestor = PostgresManager.__new__(PostgresManager)
    gestor.client = cliente
    gestor.is_connected = True
    gestor.db_config = {}
    gestor.supabase_key = "llave-de-prueba"
    gestor._missing_suplementos_logged = False
    return gestor


def _stock_de(cliente, codigo):
    filas = [f for f in cliente.filas("inventario") if f["codigo_interno"] == codigo]
    assert filas, f"no hay inventario para {codigo}"
    return filas[0]["stock_actual"]


@pytest.fixture
def venta_sin_stock():
    """Carrito imposible: 10 aguas cuando solo hay 3 (el caso reportado)."""
    return {
        "id_usuario": 1,
        "id_turno": 1,
        "total": 150.0,
        "metodo_pago": "efectivo",
        "tipo_venta": "producto",
        "productos": [
            {"id_producto": 2, "cantidad": 10, "precio": 15.0, "subtotal": 150.0},
        ],
    }


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------

def test_venta_feliz_crea_venta_detalles_movimientos_y_descuenta_stock(
    pg_manager, cliente_fake, venta_dos_productos
):
    venta_id = pg_manager.create_sale(venta_dos_productos)

    assert venta_id, "create_sale debe devolver el id de la venta"

    ventas = cliente_fake.filas("ventas")
    assert len(ventas) == 1
    assert ventas[0]["id_venta"] == venta_id
    assert ventas[0]["total"] == 1315.0
    assert ventas[0]["estado"] == "completada"
    assert ventas[0]["id_turno"] == 1

    detalles = cliente_fake.filas("detalles_venta")
    assert len(detalles) == 2, "un detalle por linea del carrito"
    assert {d["codigo_interno"] for d in detalles} == {"PROT-001", "AGUA-001"}
    assert all(d["id_venta"] == venta_id for d in detalles)

    proteina = next(d for d in detalles if d["codigo_interno"] == "PROT-001")
    assert proteina["cantidad"] == 2
    assert proteina["precio_unitario"] == 650.0
    assert proteina["subtotal_linea"] == 1300.0
    assert proteina["nombre_producto"] == "Proteina Whey 1kg"
    assert proteina["descripcion_producto"] == "Sabor chocolate"

    movimientos = cliente_fake.filas("movimientos_inventario")
    assert len(movimientos) == 2
    assert all(m["tipo_movimiento"] == "venta" for m in movimientos)
    assert all(m["id_venta"] == venta_id for m in movimientos)
    mov_prot = next(m for m in movimientos if m["codigo_interno"] == "PROT-001")
    assert mov_prot["cantidad"] == -2
    assert mov_prot["stock_anterior"] == 10
    assert mov_prot["stock_nuevo"] == 8

    # El stock baja exactamente lo vendido.
    assert _stock_de(cliente_fake, "PROT-001") == 8    # 10 - 2
    assert _stock_de(cliente_fake, "AGUA-001") == 2    # 3 - 1


def test_venta_con_el_mismo_producto_en_dos_lineas_agrupa_el_descuento(
    pg_manager, cliente_fake
):
    venta = {
        "id_usuario": 1,
        "id_turno": 1,
        "total": 1300.0,
        "productos": [
            {"id_producto": 1, "cantidad": 2, "precio": 650.0, "subtotal": 1300.0},
            {"id_producto": 1, "cantidad": 1, "precio": 650.0, "subtotal": 650.0},
        ],
    }
    pg_manager.create_sale(venta)

    assert len(cliente_fake.filas("detalles_venta")) == 2
    assert _stock_de(cliente_fake, "PROT-001") == 7    # 10 - 3


# ---------------------------------------------------------------------------
# Bug A: venta cobrada sin detalle  (REGRESION - falla con el codigo viejo)
# ---------------------------------------------------------------------------

def test_stock_insuficiente_no_registra_ninguna_venta(
    pg_manager, cliente_fake, venta_sin_stock
):
    """
    Regresion del Bug A: con el codigo viejo esto devolvia el id 1, dejaba una
    venta de $150 en `ventas`, `detalles_venta` vacia y el stock intacto.
    """
    with pytest.raises(StockInsuficienteError) as info:
        pg_manager.create_sale(venta_sin_stock)

    error = info.value
    assert error.producto == "Agua 600ml"
    assert error.solicitado == 10
    assert error.disponible == 3
    assert "Agua 600ml" in str(error)

    # Nada quedo escrito: el cajero NO cobro.
    assert cliente_fake.filas("ventas") == []
    assert cliente_fake.filas("detalles_venta") == []
    assert cliente_fake.filas("movimientos_inventario") == []
    assert _stock_de(cliente_fake, "AGUA-001") == 3


def test_stock_insuficiente_en_la_segunda_linea_tampoco_cobra_la_primera(
    pg_manager, cliente_fake
):
    """Todo el carrito se valida antes de insertar la cabecera de la venta."""
    venta = {
        "id_usuario": 1,
        "id_turno": 1,
        "total": 1375.0,
        "productos": [
            {"id_producto": 1, "cantidad": 2, "precio": 650.0, "subtotal": 1300.0},
            {"id_producto": 2, "cantidad": 5, "precio": 15.0, "subtotal": 75.0},
        ],
    }

    with pytest.raises(StockInsuficienteError):
        pg_manager.create_sale(venta)

    assert cliente_fake.filas("ventas") == []
    assert cliente_fake.filas("detalles_venta") == []
    assert _stock_de(cliente_fake, "PROT-001") == 10, "no se toco el primer producto"
    assert _stock_de(cliente_fake, "AGUA-001") == 3


# ---------------------------------------------------------------------------
# Fallos de red a media venta -> rollback compensatorio
# ---------------------------------------------------------------------------

def test_fallo_al_insertar_detalles_no_deja_venta_huerfana(
    pg_manager, cliente_fake, venta_dos_productos
):
    cliente_fake.fail_on = ("detalles_venta", "insert")

    with pytest.raises(Exception):
        pg_manager.create_sale(venta_dos_productos)

    assert cliente_fake.filas("ventas") == [], "la venta no debe sobrevivir"
    assert cliente_fake.filas("detalles_venta") == []
    assert cliente_fake.filas("movimientos_inventario") == []
    assert _stock_de(cliente_fake, "PROT-001") == 10
    assert _stock_de(cliente_fake, "AGUA-001") == 3


def test_fallo_al_insertar_movimientos_revierte_venta_detalles_y_stock(
    pg_manager, cliente_fake, venta_dos_productos
):
    cliente_fake.fail_on = ("movimientos_inventario", "insert")

    with pytest.raises(Exception):
        pg_manager.create_sale(venta_dos_productos)

    assert cliente_fake.filas("ventas") == []
    assert cliente_fake.filas("detalles_venta") == []
    assert cliente_fake.filas("movimientos_inventario") == []
    # El stock ya descontado se devolvio.
    assert _stock_de(cliente_fake, "PROT-001") == 10
    assert _stock_de(cliente_fake, "AGUA-001") == 3


def test_fallo_al_insertar_la_cabecera_no_escribe_nada(
    pg_manager, cliente_fake, venta_dos_productos
):
    cliente_fake.fail_on = ("ventas", "insert")

    with pytest.raises(Exception):
        pg_manager.create_sale(venta_dos_productos)

    assert cliente_fake.filas("ventas") == []
    assert cliente_fake.filas("detalles_venta") == []
    assert _stock_de(cliente_fake, "PROT-001") == 10


# ---------------------------------------------------------------------------
# Bug C: N+1
# ---------------------------------------------------------------------------

def test_venta_de_dos_productos_hace_pocos_round_trips(
    pg_manager, cliente_fake, venta_dos_productos
):
    """
    Antes: 1 insert de venta + 5 llamadas por linea = 11 round-trips.
    Ahora: 1 intento de RPC + 2 precargas (.in_) + insert venta +
           insert de detalles en lote + 1 update por producto +
           insert de movimientos en lote = 8.
    """
    pg_manager.create_sale(venta_dos_productos)

    total = cliente_fake.contar_llamadas()
    assert total <= 8, f"demasiados round-trips: {total} -> {cliente_fake.calls}"

    # Las precargas son UNA consulta por tabla, no una por producto.
    assert cliente_fake.contar_llamadas("ca_productos_varios", "select") == 1
    assert cliente_fake.contar_llamadas("inventario", "select") == 1
    # Detalles y movimientos van en lote.
    assert cliente_fake.contar_llamadas("detalles_venta", "insert") == 1
    assert cliente_fake.contar_llamadas("movimientos_inventario", "insert") == 1


def test_el_costo_no_crece_linealmente_con_el_carrito(cliente_fake, datos_catalogo):
    """Cinco lineas no deben costar 25 llamadas."""
    gestor = _manager_con(cliente_fake)
    venta = {
        "id_usuario": 1,
        "id_turno": 1,
        "total": 75.0,
        "productos": [
            {"id_producto": 2, "cantidad": 1, "precio": 15.0, "subtotal": 15.0}
            for _ in range(3)
        ],
    }
    gestor.create_sale(venta)

    assert cliente_fake.contar_llamadas() <= 8
    assert _stock_de(cliente_fake, "AGUA-001") == 0    # 3 - 3


# ---------------------------------------------------------------------------
# Bug B: descuento condicionado + reintento (mitigacion en el camino Python)
# ---------------------------------------------------------------------------

def test_el_update_de_stock_va_condicionado_por_el_valor_leido(
    pg_manager, cliente_fake, venta_dos_productos
):
    """
    Si otra caja cambio el stock entre la lectura y la escritura, el update
    condicionado no afecta filas y NO se pisa su descuento.
    """
    llamadas_update = []
    original = cliente_fake.table

    def espia(nombre):
        consulta = original(nombre)
        if nombre == "inventario":
            eq_original = consulta.eq

            def eq(columna, valor):
                if columna == "stock_actual":
                    llamadas_update.append(valor)
                return eq_original(columna, valor)

            consulta.eq = eq
        return consulta

    cliente_fake.table = espia
    try:
        pg_manager.create_sale(venta_dos_productos)
    finally:
        cliente_fake.table = original

    assert sorted(llamadas_update) == [3, 10], (
        "el update debe filtrar por el stock leido (optimistic locking)"
    )


def test_reintenta_cuando_otra_caja_movio_el_stock(cliente_fake):
    """
    Se simula la carrera: justo antes del primer update, otra caja baja el
    stock de 10 a 9. El update condicionado falla, se relee y se reintenta,
    quedando 9 - 2 = 7 (y NO 8, que seria haber pisado la otra venta).
    """
    gestor = _manager_con(cliente_fake)
    original = cliente_fake.table
    estado = {"interferido": False}
    llamadas = {"n": 0}

    venta = {
        "id_usuario": 1,
        "id_turno": 1,
        "total": 1300.0,
        "productos": [
            {"id_producto": 1, "cantidad": 2, "precio": 650.0, "subtotal": 1300.0},
        ],
    }

    # La precarga lee 10; a partir de ahi interferimos como si otra caja
    # hubiera vendido 1 proteina justo antes de nuestro update.
    def espia_tardio(nombre):
        llamadas["n"] += 1
        if nombre == "inventario" and llamadas["n"] > 1 and not estado["interferido"]:
            estado["interferido"] = True
            for fila in cliente_fake.store["inventario"]:
                if fila["codigo_interno"] == "PROT-001":
                    fila["stock_actual"] = 9
        return original(nombre)

    cliente_fake.table = espia_tardio
    try:
        gestor.create_sale(venta)
    finally:
        cliente_fake.table = original

    assert estado["interferido"], "la prueba debia simular la carrera"
    assert _stock_de(cliente_fake, "PROT-001") == 7, (
        "debio reintentar sobre el valor nuevo, no pisar el descuento ajeno"
    )


# ---------------------------------------------------------------------------
# Camino RPC (funcion transaccional aplicada en la base)
# ---------------------------------------------------------------------------

def _rpc_disponible(datos_catalogo, retorno=77, error=None):
    """Cliente falso con la funcion crear_venta_pos ya presente en la base."""
    registro = {"params": None}

    def crear_venta_pos(params):
        registro["params"] = params
        if error is not None:
            raise error
        return retorno

    cliente = FakeSupabaseClient(
        datos_catalogo, funciones_rpc={"crear_venta_pos": crear_venta_pos}
    )
    return cliente, registro


def test_con_rpc_disponible_se_usa_la_transaccion_y_no_se_tocan_las_tablas(
    datos_catalogo, venta_dos_productos
):
    cliente, registro = _rpc_disponible(datos_catalogo, retorno=77)
    gestor = _manager_con(cliente)

    venta_id = gestor.create_sale(venta_dos_productos)

    assert venta_id == 77
    assert len(cliente.rpc_calls) == 1, "el RPC se llama exactamente una vez"
    assert cliente.rpc_calls[0][0] == "crear_venta_pos"
    # Ningun acceso directo a tablas: la transaccion hace todo del lado de Postgres.
    assert cliente.calls == [("rpc:crear_venta_pos", "rpc")]
    assert cliente.filas("ventas") == []
    assert cliente.filas("detalles_venta") == []
    assert _stock_de(cliente, "PROT-001") == 10

    # Los parametros llegan con la forma que espera la funcion plpgsql.
    params = registro["params"]
    assert params["p_id_usuario"] == 1
    assert params["p_total"] == 1315.0
    assert params["p_id_turno"] == 1
    assert params["p_metodo_pago"] == "efectivo"
    assert len(params["p_items"]) == 2
    assert params["p_items"][0] == {
        "id_producto": 1,
        "codigo_interno": None,
        "tipo_producto": "varios",
        "cantidad": 2,
        "precio_unitario": 650.0,
        "subtotal_linea": 1300.0,
        "descuento_linea": 0.0,
    }


def test_rpc_con_stock_insuficiente_se_traduce_a_stock_insuficiente_error(
    datos_catalogo, venta_sin_stock
):
    """La excepcion de plpgsql llega como error de PostgREST; hay que mapearla."""
    falla = Exception(
        'Stock insuficiente para "Agua 600ml": se pidieron 10 y solo hay 3.'
    )
    cliente, _ = _rpc_disponible(datos_catalogo, error=falla)
    gestor = _manager_con(cliente)

    with pytest.raises(StockInsuficienteError) as info:
        gestor.create_sale(venta_sin_stock)

    assert info.value.producto == "Agua 600ml"
    assert info.value.solicitado == 10
    assert info.value.disponible == 3
    # La transaccion de Postgres ya revirtio: nada escrito por el cliente.
    assert cliente.filas("ventas") == []


def test_sin_rpc_cae_al_camino_python_y_la_venta_se_completa(
    pg_manager, cliente_fake, venta_dos_productos
):
    """El cliente falso sin funciones_rpc imita el PGRST202 / 'schema cache'."""
    assert cliente_fake.funciones_rpc == {}

    venta_id = pg_manager.create_sale(venta_dos_productos)

    # Se intento el RPC primero...
    assert [n for n, _ in cliente_fake.rpc_calls] == ["crear_venta_pos"]
    # ...y al no existir, la venta se completo por el camino de respaldo.
    assert venta_id
    assert len(cliente_fake.filas("ventas")) == 1
    assert len(cliente_fake.filas("detalles_venta")) == 2
    assert len(cliente_fake.filas("movimientos_inventario")) == 2
    assert _stock_de(cliente_fake, "PROT-001") == 8


def test_error_de_rpc_no_relacionado_no_cae_al_respaldo(
    datos_catalogo, venta_dos_productos
):
    """Un fallo real del RPC debe propagarse, no reintentarse por otro camino."""
    cliente, _ = _rpc_disponible(datos_catalogo, error=Exception("timeout de red"))
    gestor = _manager_con(cliente)

    with pytest.raises(Exception, match="timeout de red"):
        gestor.create_sale(venta_dos_productos)

    assert cliente.filas("ventas") == [], "no debe duplicarse por el respaldo"


# ---------------------------------------------------------------------------
# Validaciones de entrada
# ---------------------------------------------------------------------------

def test_carrito_vacio_no_registra_venta(pg_manager, cliente_fake):
    with pytest.raises(ValueError):
        pg_manager.create_sale({"id_usuario": 1, "total": 0.0, "productos": []})

    assert cliente_fake.filas("ventas") == []


def test_cantidad_invalida_no_registra_venta(pg_manager, cliente_fake):
    venta = {
        "id_usuario": 1,
        "total": 0.0,
        "productos": [{"id_producto": 1, "cantidad": 0, "precio": 650.0, "subtotal": 0.0}],
    }
    with pytest.raises(ValueError):
        pg_manager.create_sale(venta)

    assert cliente_fake.filas("ventas") == []
