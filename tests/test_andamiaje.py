"""
Pruebas del propio andamiaje (FakeSupabaseClient).

Si estas fallan, no confies en ninguna otra prueba: el doble de Supabase
no esta imitando correctamente a la API real.
"""

import pytest

from conftest import FakeSupabaseClient, FallaSimulada


def test_insert_asigna_pk_autoincremental(cliente_fake):
    r = cliente_fake.table("ventas").insert({"id_usuario": 1, "total": 100.0}).execute()
    assert r.data[0]["id_venta"] == 1

    r2 = cliente_fake.table("ventas").insert({"id_usuario": 1, "total": 50.0}).execute()
    assert r2.data[0]["id_venta"] == 2


def test_select_con_filtros_encadenados(cliente_fake):
    r = (
        cliente_fake.table("inventario")
        .select("stock_actual")
        .eq("codigo_interno", "PROT-001")
        .eq("tipo_producto", "varios")
        .execute()
    )
    assert len(r.data) == 1
    assert r.data[0]["stock_actual"] == 10


def test_update_persiste_en_el_almacen(cliente_fake):
    cliente_fake.table("inventario").update({"stock_actual": 7}).eq(
        "codigo_interno", "PROT-001"
    ).execute()

    r = cliente_fake.table("inventario").select("*").eq(
        "codigo_interno", "PROT-001"
    ).execute()
    assert r.data[0]["stock_actual"] == 7


def test_delete_quita_filas(cliente_fake):
    cliente_fake.table("ventas").insert({"id_usuario": 1, "total": 10.0}).execute()
    cliente_fake.table("ventas").delete().eq("id_venta", 1).execute()
    assert cliente_fake.filas("ventas") == []


def test_check_de_stock_negativo_se_respeta(cliente_fake):
    with pytest.raises(Exception, match="inventario_stock_actual_check"):
        cliente_fake.table("inventario").update({"stock_actual": -1}).eq(
            "codigo_interno", "AGUA-001"
        ).execute()


def test_inyeccion_de_fallo(cliente_fake):
    cliente_fake.fail_on = ("detalles_venta", "insert")
    with pytest.raises(FallaSimulada):
        cliente_fake.table("detalles_venta").insert({"id_venta": 1}).execute()


def test_fail_after_permite_fallar_en_la_segunda_llamada(cliente_fake):
    cliente_fake.fail_on = ("detalles_venta", "insert")
    cliente_fake.fail_after = 1

    cliente_fake.table("detalles_venta").insert({"id_venta": 1}).execute()  # pasa
    with pytest.raises(FallaSimulada):
        cliente_fake.table("detalles_venta").insert({"id_venta": 1}).execute()


def test_conteo_de_llamadas(cliente_fake):
    cliente_fake.table("inventario").select("*").execute()
    cliente_fake.table("inventario").select("*").execute()
    cliente_fake.table("ventas").insert({"id_usuario": 1, "total": 1.0}).execute()

    assert cliente_fake.contar_llamadas("inventario", "select") == 2
    assert cliente_fake.contar_llamadas("ventas", "insert") == 1
    assert cliente_fake.contar_llamadas() == 3


def test_rpc_ausente_imita_el_error_de_postgrest(cliente_fake):
    with pytest.raises(Exception, match="schema cache"):
        cliente_fake.rpc("crear_venta_pos", {"p_total": 1}).execute()


def test_rpc_presente_devuelve_su_resultado():
    cli = FakeSupabaseClient(funciones_rpc={"crear_venta_pos": lambda p: 42})
    assert cli.rpc("crear_venta_pos", {}).execute().data == 42
