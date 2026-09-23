"""
Pruebas de `utils.config.Config` y del cableado de credenciales de Supabase.

Ninguna prueba lee el `.env` real ni se conecta a Supabase: la fixture
`entorno_limpio` neutraliza `load_dotenv` y borra las variables SUPABASE_*
del entorno antes de construir cualquier `Config`.
"""

import os
import re
import logging

import pytest

from utils.config import Config
import utils.config as modulo_config


_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Variables que hay que aislar para que el `.env` real no contamine nada.
_VARS_SUPABASE = ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ROLE_KEY")


@pytest.fixture
def entorno_limpio(monkeypatch):
    """
    Aisla el entorno: `load_dotenv` no hace nada y no queda ninguna
    credencial de Supabase heredada del sistema o del `.env` real.
    """
    monkeypatch.setattr(modulo_config, "load_dotenv", lambda *a, **k: None)
    for var in _VARS_SUPABASE:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# get_supabase_config()
# ---------------------------------------------------------------------------

def test_get_supabase_config_devuelve_url_y_key(entorno_limpio):
    """El dict expone exactamente las llaves que PostgresManager lee."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")

    config = Config()
    supabase_config = config.get_supabase_config()

    assert supabase_config["url"] == "https://demo.supabase.co"
    assert supabase_config["key"] == "llave-anon"
    assert set(supabase_config) == {"url", "key"}


def test_prefiere_role_key_sobre_key(entorno_limpio):
    """Con ambas presentes gana SUPABASE_ROLE_KEY (bypasea RLS)."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")
    entorno_limpio.setenv("SUPABASE_ROLE_KEY", "llave-service-role")

    supabase_config = Config().get_supabase_config()

    assert supabase_config["key"] == "llave-service-role"


def test_cae_a_supabase_key_si_falta_role_key(entorno_limpio):
    """Regresión del Bug A: sin ROLE_KEY se usa SUPABASE_KEY, no cadena vacía."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")

    supabase_config = Config().get_supabase_config()

    assert supabase_config["key"] == "llave-anon"


def test_get_postgres_config_no_trae_credenciales_supabase(entorno_limpio):
    """
    Documenta el Bug A: el dict obsoleto NUNCA tuvo 'url' ni 'key', así que
    PostgresManager acababa dependiendo de os.environ por efecto colateral.
    """
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")

    postgres_config = Config().get_postgres_config()

    assert "url" not in postgres_config
    assert "key" not in postgres_config
    assert sorted(postgres_config) == ["database", "host", "password", "port", "user"]


def test_get_postgres_config_marcado_como_obsoleto():
    """El docstring debe avisar que está obsoleto."""
    docstring = (Config.get_postgres_config.__doc__ or "").upper()
    assert "OBSOLET" in docstring


# ---------------------------------------------------------------------------
# validate_config()
# ---------------------------------------------------------------------------

def test_validate_config_detecta_url_faltante(entorno_limpio, caplog):
    """Sin SUPABASE_URL falla y reporta la variable por nombre."""
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")

    config = Config()
    with caplog.at_level(logging.ERROR):
        assert config.validate_config() is False

    faltantes = config.get_missing_credentials()
    assert "SUPABASE_URL" in faltantes
    assert "SUPABASE_URL" in caplog.text


def test_validate_config_detecta_llave_faltante(entorno_limpio, caplog):
    """Sin ninguna llave falla y nombra SUPABASE_ROLE_KEY / SUPABASE_KEY."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")

    config = Config()
    with caplog.at_level(logging.ERROR):
        assert config.validate_config() is False

    faltantes = config.get_missing_credentials()
    assert any("SUPABASE_ROLE_KEY" in f for f in faltantes)
    assert "SUPABASE_ROLE_KEY" in caplog.text


def test_validate_config_reporta_todas_las_faltantes(entorno_limpio):
    """Sin nada configurado se reportan ambas credenciales."""
    config = Config()

    assert config.validate_config() is False
    faltantes = config.get_missing_credentials()
    assert len(faltantes) == 2
    assert "SUPABASE_URL" in faltantes


def test_validate_config_ok_con_credenciales_completas(entorno_limpio):
    """Con URL + ROLE_KEY la validación pasa y no queda en modo offline."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_ROLE_KEY", "llave-service-role")

    config = Config()

    assert config.validate_config() is True
    assert config.get_missing_credentials() == []
    assert config.OFFLINE_MODE is False


def test_validate_config_ok_solo_con_supabase_key(entorno_limpio):
    """SUPABASE_KEY sola es suficiente para validar (ROLE_KEY es opcional)."""
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_KEY", "llave-anon")

    assert Config().validate_config() is True


# ---------------------------------------------------------------------------
# Cableado real en main.py (Bug A)
# ---------------------------------------------------------------------------

def test_dict_pasado_a_postgres_manager_tiene_url_y_key(entorno_limpio):
    """
    El dict que main.py entrega a PostgresManager debe traer 'url' y 'key'
    sin depender del efecto colateral de load_dotenv sobre os.environ.
    """
    entorno_limpio.setenv("SUPABASE_URL", "https://demo.supabase.co")
    entorno_limpio.setenv("SUPABASE_ROLE_KEY", "llave-service-role")

    db_config = Config().get_supabase_config()

    # Mismo acceso que hace PostgresManager.connect()
    assert db_config.get("url") == "https://demo.supabase.co"
    assert db_config.get("key") == "llave-service-role"

    # Y sin nada en os.environ el dict sigue completo: no hay dependencia oculta.
    for var in _VARS_SUPABASE:
        entorno_limpio.delenv(var, raising=False)
    assert db_config.get("url") and db_config.get("key")


def test_main_usa_get_supabase_config():
    """main.py ya no debe cablear PostgresManager con get_postgres_config()."""
    ruta_main = os.path.join(_RAIZ, "main.py")
    with open(ruta_main, encoding="utf-8") as archivo:
        codigo = archivo.read()

    assert "self.config.get_supabase_config()" in codigo
    assert "db_config = self.config.get_postgres_config()" not in codigo


def test_main_valida_configuracion_al_arrancar():
    """Bug B: validate_config() debe invocarse desde main.py con aviso visible."""
    ruta_main = os.path.join(_RAIZ, "main.py")
    with open(ruta_main, encoding="utf-8") as archivo:
        codigo = archivo.read()

    assert "validate_config()" in codigo
    assert "QMessageBox.critical" in codigo


# ---------------------------------------------------------------------------
# requirements.txt (Bug C)
# ---------------------------------------------------------------------------

def _leer_requirements():
    ruta = os.path.join(_RAIZ, "requirements.txt")
    with open(ruta, encoding="utf-8") as archivo:
        lineas = [l.strip() for l in archivo]
    # Descartar comentarios y líneas vacías
    return [l for l in lineas if l and not l.startswith("#")]


@pytest.mark.parametrize("paquete", ["fastapi", "uvicorn", "pydantic", "bcrypt"])
def test_requirements_incluye_dependencias_de_arranque(paquete):
    """
    Regresión del Bug C: una instalación limpia con requirements.txt debe
    abrir la app; main.py importa utils.fastapi_server_entradas dentro de un
    try cuyo except ImportError hace sys.exit(1).
    """
    requisitos = _leer_requirements()
    nombres = [re.split(r"[\[<>=!;# ]", l, 1)[0].lower() for l in requisitos]

    assert paquete in nombres, f"Falta {paquete} en requirements.txt"
