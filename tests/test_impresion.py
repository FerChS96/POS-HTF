"""
Pruebas de la capa de impresion de tickets.

Cubren los tres problemas reportados desde el gimnasio:
  - "a veces no encuentra la impresora"  -> resolucion del nombre
  - "se congela al imprimir"             -> enumeracion nativa, sin PowerShell
  - "imprime cortado y descuadrado"      -> ancho unico y nombres sin truncar

Ninguna prueba abre la impresora real ni manda nada a imprimir.
"""

import pytest

from services.printing.windows_printer_manager import (
    WindowsPrinterManager,
    TicketPrinterWindows,
    generar_ticket_venta,
    generar_ticket_corte,
    obtener_ancho_ticket,
    _envolver,
    ANCHO_TICKET_POR_DEFECTO,
    VAR_ANCHO_TICKET,
    VAR_IMPRESORA,
)


# Lo que Windows reporta en el POS del gimnasio: la impresora de tickets
# tiene un emoticono en el nombre.
INSTALADAS_REALES = [
    "OneNote for Windows 10",
    "Microsoft XPS Document Writer",
    "Microsoft Print to PDF",
    "Generic / Text Only :)",
    "Fax",
]


@pytest.fixture
def entorno_impresion(monkeypatch):
    """Entorno limpio: sin variables de impresion heredadas del .env real."""
    monkeypatch.delenv(VAR_IMPRESORA, raising=False)
    monkeypatch.delenv(VAR_ANCHO_TICKET, raising=False)
    yield monkeypatch


@pytest.fixture
def impresoras_simuladas(entorno_impresion):
    """Sustituye la enumeracion real por una lista fija."""
    def _instalar(lista):
        entorno_impresion.setattr(
            WindowsPrinterManager,
            "obtener_impresoras_instaladas",
            staticmethod(lambda force_refresh=False: list(lista)),
        )
        return lista
    return _instalar


@pytest.fixture
def venta_ejemplo():
    return {
        "numero_ticket": 503,
        "fecha_hora": "22/09/2026 19:45",
        "cajero": "Alexa",
        "productos": [
            {"nombre": "ALEGRIA GRANDE MIEL PILONCILLO",
             "cantidad": 2, "precio": 35.0, "subtotal": 70.0},
            {"nombre": "AGUA", "cantidad": 1, "precio": 18.5, "subtotal": 18.5},
        ],
        "total": 88.5,
        "metodo_pago": "EFECTIVO",
    }


@pytest.fixture
def corte_ejemplo():
    return {
        "turno": 12,
        "cajero": "Alexa",
        "fecha_apertura": "22/09/2026 08:00",
        "fecha_hora": "22/09/2026 22:15",
        "num_ventas": 40,
        "total_efectivo": 4250.0,
        "total_transferencia": 1100.0,
        "total_ventas": 5350.0,
        "monto_inicial": 500.0,
        "total_esperado": 4750.0,
    }


# ---------------------------------------------------------------------------
# Resolucion del nombre de la impresora
# ---------------------------------------------------------------------------

def test_resuelve_nombre_con_emoticono(impresoras_simuladas):
    """Regresion: el codigo buscaba 'Generic / Text Only' exacto y fallaba."""
    impresoras_simuladas(INSTALADAS_REALES)
    assert WindowsPrinterManager.resolver_impresora() == "Generic / Text Only :)"


def test_nombre_configurado_exacto_gana(impresoras_simuladas, entorno_impresion):
    impresoras_simuladas(INSTALADAS_REALES)
    entorno_impresion.setenv(VAR_IMPRESORA, "Microsoft Print to PDF")
    assert WindowsPrinterManager.resolver_impresora() == "Microsoft Print to PDF"


def test_nombre_configurado_se_normaliza(impresoras_simuladas, entorno_impresion):
    """Configurar el nombre 'limpio' debe encontrar el que tiene emoticono."""
    impresoras_simuladas(INSTALADAS_REALES)
    entorno_impresion.setenv(VAR_IMPRESORA, "Generic / Text Only")
    assert WindowsPrinterManager.resolver_impresora() == "Generic / Text Only :)"


def test_nombre_configurado_inexistente_devuelve_none(impresoras_simuladas, entorno_impresion):
    """No debe imprimir en otra impresora por su cuenta: mejor avisar."""
    impresoras_simuladas(INSTALADAS_REALES)
    entorno_impresion.setenv(VAR_IMPRESORA, "Impresora Que No Existe")
    assert WindowsPrinterManager.resolver_impresora() is None


def test_no_elige_impresoras_virtuales(impresoras_simuladas):
    """Sin impresora fisica no debe caer en PDF, XPS, OneNote ni Fax."""
    impresoras_simuladas([
        "Microsoft Print to PDF", "Microsoft XPS Document Writer",
        "OneNote for Windows 10", "Fax",
    ])
    assert WindowsPrinterManager.resolver_impresora() is None


def test_prefiere_text_only_sobre_otra_generic(impresoras_simuladas):
    """Regresion: antes tomaba la PRIMERA coincidencia de 'generic'."""
    impresoras_simuladas(["Generic Laser Office", "Generic / Text Only :)"])
    assert WindowsPrinterManager.resolver_impresora() == "Generic / Text Only :)"


def test_sin_impresoras_devuelve_none(impresoras_simuladas):
    impresoras_simuladas([])
    assert WindowsPrinterManager.resolver_impresora() is None


def test_normalizacion_ignora_signos_y_espacios():
    n = WindowsPrinterManager._normalizar_nombre
    assert n("Generic / Text Only :)") == n("generic text only")


# ---------------------------------------------------------------------------
# Enumeracion rapida (el congelamiento de la interfaz)
# ---------------------------------------------------------------------------

def test_enumeracion_no_usa_powershell(entorno_impresion):
    """
    Regresion del congelamiento: cada impresion lanzaba PowerShell (~3.4 s).
    Si la via nativa responde, PowerShell no debe ejecutarse.
    """
    llamadas = []
    entorno_impresion.setattr(
        WindowsPrinterManager, "_enumerar_impresoras_nativo",
        staticmethod(lambda: list(INSTALADAS_REALES)),
    )
    entorno_impresion.setattr(
        WindowsPrinterManager, "_ejecutar_powershell",
        staticmethod(lambda cmd, timeout=12: llamadas.append(cmd) or ""),
    )

    assert WindowsPrinterManager.obtener_impresoras_instaladas(force_refresh=True) == INSTALADAS_REALES
    assert llamadas == [], "No debe lanzarse PowerShell si la via nativa funciona"


def test_powershell_es_el_respaldo(entorno_impresion):
    """Si la via nativa falla, se debe recurrir a PowerShell."""
    entorno_impresion.setattr(
        WindowsPrinterManager, "_enumerar_impresoras_nativo",
        staticmethod(lambda: None),
    )
    entorno_impresion.setattr(
        WindowsPrinterManager, "_ejecutar_powershell",
        staticmethod(lambda cmd, timeout=12: "Generic / Text Only :)\nFax"),
    )

    resultado = WindowsPrinterManager.obtener_impresoras_instaladas(force_refresh=True)
    assert "Generic / Text Only :)" in resultado


# ---------------------------------------------------------------------------
# Ancho del ticket y nombres largos
# ---------------------------------------------------------------------------

def test_ancho_por_defecto(entorno_impresion):
    assert obtener_ancho_ticket() == ANCHO_TICKET_POR_DEFECTO == 32


def test_ancho_configurable(entorno_impresion):
    entorno_impresion.setenv(VAR_ANCHO_TICKET, "48")
    assert obtener_ancho_ticket() == 48


@pytest.mark.parametrize("valor", ["0", "5", "200", "ancho", ""])
def test_ancho_invalido_cae_al_por_defecto(entorno_impresion, valor):
    entorno_impresion.setenv(VAR_ANCHO_TICKET, valor)
    assert obtener_ancho_ticket() == ANCHO_TICKET_POR_DEFECTO


def test_vista_previa_y_impresion_usan_el_mismo_ancho(entorno_impresion, venta_ejemplo):
    """
    Regresion del descuadre: la vista previa se dibujaba a 42 columnas y el
    papel salia a 30, asi que nunca coincidian.
    """
    texto = generar_ticket_venta(venta_ejemplo)
    impresora = TicketPrinterWindows("cualquiera")
    assert impresora.ancho_linea == obtener_ancho_ticket()
    assert texto == impresora._generar_ticket(venta_ejemplo)


def test_ninguna_linea_excede_el_ancho(entorno_impresion, venta_ejemplo):
    ancho = obtener_ancho_ticket()
    for linea in generar_ticket_venta(venta_ejemplo).splitlines():
        assert len(linea) <= ancho, f"linea de {len(linea)} columnas: {linea!r}"


def test_nombre_largo_no_se_trunca(entorno_impresion, venta_ejemplo):
    """
    Regresion: se cortaba a 22 caracteres y 63 de 244 productos del catalogo
    salian ilegibles ('ALEGRIA GRANDE MIEL PI').
    """
    texto = generar_ticket_venta(venta_ejemplo)
    assert "ALEGRIA GRANDE MIEL PILONCILLO" in texto.replace("\n", " ")
    assert "ALEGRIA GRANDE MIEL PI\n" not in texto


def test_envolver_corta_por_palabras():
    assert _envolver("ALEGRIA GRANDE MIEL PILONCILLO", 16) == [
        "ALEGRIA GRANDE", "MIEL PILONCILLO",
    ]


def test_envolver_parte_palabra_mas_larga_que_el_renglon():
    assert _envolver("SUPERCALIFRAGILISTICO", 10) == ["SUPERCALIF", "RAGILISTIC", "O"]


def test_envolver_texto_vacio():
    assert _envolver("", 32) == [""]


def test_ticket_venta_lleva_total_y_metodo_de_pago(entorno_impresion, venta_ejemplo):
    texto = generar_ticket_venta(venta_ejemplo)
    assert "$88.50" in texto
    assert "EFECTIVO" in texto
    assert "#000503" in texto


def test_texto_del_ticket_es_imprimible_en_cp850(entorno_impresion, venta_ejemplo):
    """La impresion RAW codifica en cp850; nada debe volverse '?'."""
    texto = generar_ticket_venta(venta_ejemplo)
    assert "?" not in texto.encode("cp850", errors="replace").decode("cp850")


# ---------------------------------------------------------------------------
# Ticket de corte de caja (funcion nueva)
# ---------------------------------------------------------------------------

def test_corte_trae_el_resumen_de_ventas(entorno_impresion, corte_ejemplo):
    texto = generar_ticket_corte(corte_ejemplo)
    assert "CORTE DE CAJA" in texto
    assert "#12" in texto
    assert "40" in texto
    assert "$4250.00" in texto
    assert "$1100.00" in texto
    assert "$5350.00" in texto


def test_corte_sin_conteo_omite_el_arqueo(entorno_impresion, corte_ejemplo):
    """Si el cajero aun no conto la caja, solo se imprime el resumen."""
    texto = generar_ticket_corte(corte_ejemplo)
    assert "ARQUEO DE EFECTIVO" not in texto
    assert "RESUMEN DE VENTAS" in texto


def test_corte_con_conteo_incluye_el_arqueo(entorno_impresion, corte_ejemplo):
    corte_ejemplo.update({"total_contado": 4730.0, "diferencia": -20.0})
    texto = generar_ticket_corte(corte_ejemplo)
    assert "ARQUEO DE EFECTIVO" in texto
    assert "FALTANTE:" in texto
    assert "$20.00" in texto


def test_corte_marca_sobrante(entorno_impresion, corte_ejemplo):
    corte_ejemplo.update({"total_contado": 4800.0, "diferencia": 50.0})
    assert "SOBRANTE:" in generar_ticket_corte(corte_ejemplo)


def test_corte_caja_exacta(entorno_impresion, corte_ejemplo):
    corte_ejemplo.update({"total_contado": 4750.0, "diferencia": 0.0})
    texto = generar_ticket_corte(corte_ejemplo)
    assert "DIFERENCIA:" in texto
    assert "FALTANTE:" not in texto and "SOBRANTE:" not in texto


def test_corte_ninguna_linea_excede_el_ancho(entorno_impresion, corte_ejemplo):
    corte_ejemplo.update({"total_contado": 4730.0, "diferencia": -20.0})
    ancho = obtener_ancho_ticket()
    for linea in generar_ticket_corte(corte_ejemplo).splitlines():
        assert len(linea) <= ancho, f"linea de {len(linea)} columnas: {linea!r}"


def test_corte_respeta_ancho_de_80mm(entorno_impresion, corte_ejemplo):
    entorno_impresion.setenv(VAR_ANCHO_TICKET, "48")
    for linea in generar_ticket_corte(corte_ejemplo).splitlines():
        assert len(linea) <= 48


def test_corte_tolera_datos_faltantes(entorno_impresion):
    """No debe reventar si el turno todavia no tiene ventas."""
    texto = generar_ticket_corte({})
    assert "CORTE DE CAJA" in texto
    assert "$0.00" in texto


def test_imprimir_corte_sin_conexion_no_envia(entorno_impresion, corte_ejemplo):
    impresora = TicketPrinterWindows("cualquiera")
    impresora.conectado = False
    assert impresora.imprimir_corte(corte_ejemplo) is False


def test_imprimir_corte_envia_el_texto_generado(entorno_impresion, corte_ejemplo):
    enviados = []
    impresora = TicketPrinterWindows("cualquiera")
    impresora.conectado = True
    impresora.enviar_texto = lambda contenido: enviados.append(contenido) or True

    assert impresora.imprimir_corte(corte_ejemplo) is True
    assert len(enviados) == 1
    assert "CORTE DE CAJA" in enviados[0]
    assert "$5350.00" in enviados[0]


# ---------------------------------------------------------------------------
# Integracion con la ventana de Cierre de Caja
# ---------------------------------------------------------------------------

def _ventana_cierre(**valores):
    """
    CierreCajaWindow sin construir la interfaz Qt: se evita __init__ con
    __new__ y se ponen a mano solo los atributos que usa el resumen.
    """
    from ui.ventas.cierre_caja import CierreCajaWindow

    ventana = CierreCajaWindow.__new__(CierreCajaWindow)
    ventana.user_data = {"id_usuario": 1, "nombre_completo": "Alexa Ramirez"}
    ventana.turno_abierto = {
        "id_turno": 12,
        "monto_inicial": 500.0,
        "fecha_apertura": "2026-09-22T08:00:00",
    }
    ventana.total_ventas_efectivo_valor = 4250.0
    ventana.total_ventas_transferencia_valor = 1100.0
    ventana.total_esperado_valor = 4750.0
    ventana.num_ventas_valor = 40
    for clave, valor in valores.items():
        setattr(ventana, clave, valor)
    return ventana


def test_datos_corte_suma_los_dos_metodos_de_pago():
    datos = _ventana_cierre().construir_datos_corte()
    assert datos["num_ventas"] == 40
    assert datos["total_efectivo"] == 4250.0
    assert datos["total_transferencia"] == 1100.0
    assert datos["total_ventas"] == 5350.0
    assert datos["turno"] == 12
    assert datos["cajero"] == "Alexa Ramirez"


def test_datos_corte_sin_conteo_no_trae_arqueo():
    datos = _ventana_cierre().construir_datos_corte()
    assert "total_contado" not in datos
    assert "diferencia" not in datos


def test_datos_corte_con_conteo_calcula_la_diferencia():
    datos = _ventana_cierre(total_contado_valor=4730.0).construir_datos_corte()
    assert datos["total_contado"] == 4730.0
    assert datos["diferencia"] == pytest.approx(-20.0)


def test_datos_corte_formatea_la_fecha_iso_de_supabase():
    """Supabase devuelve texto ISO, no datetime."""
    assert _ventana_cierre().construir_datos_corte()["fecha_apertura"] == "22/09/2026 08:00"


def test_datos_corte_tolera_turno_sin_ventas():
    ventana = _ventana_cierre(
        total_ventas_efectivo_valor=0.0,
        total_ventas_transferencia_valor=0.0,
        total_esperado_valor=500.0,
        num_ventas_valor=0,
    )
    datos = ventana.construir_datos_corte()
    assert datos["total_ventas"] == 0.0
    assert "CORTE DE CAJA" in generar_ticket_corte(datos)


def test_ticket_de_corte_de_la_ventana_cabe_en_el_papel(entorno_impresion):
    datos = _ventana_cierre(total_contado_valor=4730.0).construir_datos_corte()
    ancho = obtener_ancho_ticket()
    for linea in generar_ticket_corte(datos).splitlines():
        assert len(linea) <= ancho
