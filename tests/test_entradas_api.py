"""
Pruebas de seguridad del servidor FastAPI de entradas del torniquete.

Cubren la regresión del agujero original: POST /entrada era anónimo y
cualquier dispositivo de la red podía inyectar entradas falsas.

Todo corre en memoria con fastapi.testclient.TestClient: NO se abre ningún
puerto real ni se toca Supabase.
"""

import os
import queue

import pytest
from fastapi.testclient import TestClient

from utils.fastapi_server_entradas import (
    app,
    entrada_queue,
    CABECERA_TOKEN,
    VAR_TOKEN,
    VAR_IPS_PERMITIDAS,
    VAR_LISTEN_HOST,
    resolver_listen_host,
)


TOKEN_VALIDO = "token-de-prueba-muy-largo-123456"
IP_TORNIQUETE = "192.168.1.50"
IP_INTRUSA = "192.168.1.99"


# ----------------------------------------------------------------------------
# Fixtures locales (no se toca tests/conftest.py)
# ----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cola_limpia():
    """Vacía la cola compartida antes y después de cada prueba."""
    _drenar(entrada_queue)
    yield
    _drenar(entrada_queue)


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Parte siempre de un entorno sin variables del torniquete."""
    monkeypatch.delenv(VAR_TOKEN, raising=False)
    monkeypatch.delenv(VAR_IPS_PERMITIDAS, raising=False)
    monkeypatch.delenv(VAR_LISTEN_HOST, raising=False)


@pytest.fixture
def con_token(monkeypatch):
    """Configura el token compartido como lo haría el archivo .env."""
    monkeypatch.setenv(VAR_TOKEN, TOKEN_VALIDO)
    return TOKEN_VALIDO


def _drenar(cola):
    """Saca todo lo pendiente de una cola sin bloquear."""
    while True:
        try:
            cola.get_nowait()
        except queue.Empty:
            return


def _cliente(ip=IP_TORNIQUETE):
    """TestClient simulando una petición desde la IP indicada."""
    return TestClient(app, client=(ip, 51000))


# ----------------------------------------------------------------------------
# POST /entrada: token
# ----------------------------------------------------------------------------

def test_entrada_sin_token_es_rechazada_y_no_encola(con_token):
    """Regresión del agujero: sin token no entra nada a la cola."""
    with _cliente() as cliente:
        respuesta = cliente.post("/entrada", json={"id_entrada": 777})

    assert respuesta.status_code == 401
    assert entrada_queue.qsize() == 0
    # El cuerpo es genérico: no revela si el token existe o no
    assert respuesta.json() == {"detail": "No autorizado"}


def test_entrada_con_token_incorrecto_es_rechazada(con_token):
    with _cliente() as cliente:
        respuesta = cliente.post(
            "/entrada",
            json={"id_entrada": 778},
            headers={CABECERA_TOKEN: "token-equivocado"},
        )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "No autorizado"}
    assert entrada_queue.qsize() == 0


def test_entrada_con_token_correcto_llega_a_la_cola(con_token):
    with _cliente() as cliente:
        respuesta = cliente.post(
            "/entrada",
            json={
                "id_entrada": 4321,
                "dispositivo": "torniquete_principal",
                "timestamp": "2026-01-01T08:00:00",
            },
            headers={CABECERA_TOKEN: con_token},
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["id_entrada"] == 4321

    assert entrada_queue.qsize() == 1
    encolada = entrada_queue.get_nowait()
    assert encolada == {
        "id_entrada": 4321,
        "dispositivo": "torniquete_principal",
        "timestamp": "2026-01-01T08:00:00",
    }


def test_entrada_sin_token_configurado_rechaza_peticiones_de_red():
    """Modo degradado: sin TORNIQUETE_API_TOKEN la red no puede inyectar nada."""
    with _cliente(IP_INTRUSA) as cliente:
        respuesta = cliente.post("/entrada", json={"id_entrada": 1})

    assert respuesta.status_code == 401
    assert entrada_queue.qsize() == 0


def test_entrada_sin_token_configurado_acepta_solo_localhost():
    """Modo degradado: la propia máquina del POS sigue funcionando."""
    with _cliente("127.0.0.1") as cliente:
        respuesta = cliente.post("/entrada", json={"id_entrada": 55})

    assert respuesta.status_code == 200
    assert entrada_queue.qsize() == 1


# ----------------------------------------------------------------------------
# POST /entrada: lista blanca de IPs
# ----------------------------------------------------------------------------

def test_ip_fuera_de_lista_blanca_es_rechazada_aunque_el_token_sea_valido(
    con_token, monkeypatch
):
    monkeypatch.setenv(VAR_IPS_PERMITIDAS, IP_TORNIQUETE)

    with _cliente(IP_INTRUSA) as cliente:
        respuesta = cliente.post(
            "/entrada",
            json={"id_entrada": 9},
            headers={CABECERA_TOKEN: con_token},
        )

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Acceso denegado"}
    assert entrada_queue.qsize() == 0


def test_ip_en_lista_blanca_con_token_valido_es_aceptada(con_token, monkeypatch):
    monkeypatch.setenv(
        VAR_IPS_PERMITIDAS, f" 10.0.0.7 , {IP_TORNIQUETE} ,"
    )

    with _cliente(IP_TORNIQUETE) as cliente:
        respuesta = cliente.post(
            "/entrada",
            json={"id_entrada": 10},
            headers={CABECERA_TOKEN: con_token},
        )

    assert respuesta.status_code == 200
    assert entrada_queue.qsize() == 1
    assert entrada_queue.get_nowait()["id_entrada"] == 10


def test_ip_en_lista_blanca_sin_token_sigue_rechazada(con_token, monkeypatch):
    """La lista blanca se aplica JUNTO al token, no en su lugar."""
    monkeypatch.setenv(VAR_IPS_PERMITIDAS, IP_TORNIQUETE)

    with _cliente(IP_TORNIQUETE) as cliente:
        respuesta = cliente.post("/entrada", json={"id_entrada": 11})

    assert respuesta.status_code == 401
    assert entrada_queue.qsize() == 0


# ----------------------------------------------------------------------------
# POST /test-entrada
# ----------------------------------------------------------------------------

def test_test_entrada_exige_token(con_token):
    with _cliente() as cliente:
        respuesta = cliente.post("/test-entrada?id_entrada=5")

    assert respuesta.status_code == 401
    assert entrada_queue.qsize() == 0


def test_test_entrada_con_token_valido_encola(con_token):
    with _cliente() as cliente:
        respuesta = cliente.post(
            "/test-entrada?id_entrada=5",
            headers={CABECERA_TOKEN: con_token},
        )

    assert respuesta.status_code == 200
    assert entrada_queue.qsize() == 1
    encolada = entrada_queue.get_nowait()
    assert encolada["id_entrada"] == 5
    assert encolada["dispositivo"] == "test"


# ----------------------------------------------------------------------------
# Endpoints de diagnóstico
# ----------------------------------------------------------------------------

def test_health_responde_sin_token(con_token):
    with _cliente() as cliente:
        respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "healthy"
    # Sin token no se expone información operativa
    assert "queue_size" not in cuerpo


def test_health_expone_queue_size_solo_con_token(con_token):
    with _cliente() as cliente:
        cliente.post(
            "/entrada",
            json={"id_entrada": 1},
            headers={CABECERA_TOKEN: con_token},
        )
        respuesta = cliente.get("/health", headers={CABECERA_TOKEN: con_token})

    assert respuesta.status_code == 200
    assert respuesta.json()["queue_size"] == 1


def test_root_responde_sin_token_y_no_filtra_configuracion(con_token):
    with _cliente() as cliente:
        respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "active"
    texto = respuesta.text
    assert TOKEN_VALIDO not in texto
    assert "queue_size" not in cuerpo


def test_no_hay_cabeceras_cors_permisivas(con_token):
    """CORS con allow_origins=* se eliminó: el torniquete no es un navegador."""
    with _cliente() as cliente:
        respuesta = cliente.get("/health", headers={"Origin": "http://evil.local"})

    assert "access-control-allow-origin" not in respuesta.headers


# ----------------------------------------------------------------------------
# Cuerpos malformados
# ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cuerpo",
    [
        {"dispositivo": "torniquete"},            # falta id_entrada
        {"id_entrada": "no-es-un-numero"},        # tipo incorrecto
        {"id_entrada": None},
    ],
)
def test_cuerpo_malformado_devuelve_422(con_token, cuerpo):
    with _cliente() as cliente:
        respuesta = cliente.post(
            "/entrada", json=cuerpo, headers={CABECERA_TOKEN: con_token}
        )

    assert respuesta.status_code == 422
    assert entrada_queue.qsize() == 0


def test_cuerpo_de_texto_plano_devuelve_422_y_el_servidor_sigue_vivo(con_token):
    with _cliente() as cliente:
        respuesta = cliente.post(
            "/entrada",
            content="esto no es json",
            headers={
                CABECERA_TOKEN: con_token,
                "Content-Type": "text/plain",
            },
        )
        assert respuesta.status_code == 422
        assert entrada_queue.qsize() == 0

        # El servidor sigue aceptando peticiones válidas después del error
        ok = cliente.post(
            "/entrada",
            json={"id_entrada": 99},
            headers={CABECERA_TOKEN: con_token},
        )

    assert ok.status_code == 200
    assert entrada_queue.get_nowait()["id_entrada"] == 99


# ----------------------------------------------------------------------------
# Resolución de la interfaz de escucha
# ----------------------------------------------------------------------------

def test_listen_host_es_localhost_sin_token():
    assert resolver_listen_host() == "127.0.0.1"


def test_listen_host_es_red_con_token(con_token):
    assert resolver_listen_host() == "0.0.0.0"


def test_listen_host_respeta_variable_explicita(con_token, monkeypatch):
    monkeypatch.setenv(VAR_LISTEN_HOST, "192.168.1.10")
    assert resolver_listen_host() == "192.168.1.10"


def test_el_reexportador_de_la_raiz_usa_la_misma_app():
    """No debe haber dos formas de levantar el servidor."""
    import fastapi_server_entradas as raiz
    import utils.fastapi_server_entradas as modulo_real

    assert raiz.app is modulo_real.app
    assert raiz.entrada_queue is modulo_real.entrada_queue
    assert raiz.ejecutar_servidor is modulo_real.ejecutar_servidor
