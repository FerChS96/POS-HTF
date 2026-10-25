"""
Búsqueda de producto en Registrar Entrada / Registrar Salida.

El escáner busca solo; lo escrito a mano solo se busca con el botón o Enter,
por código exacto o por nombre.
"""

from utils.detector_escaner import DetectorEscaner


# ---------------------------------------------------------------------------
# DetectorEscaner
# ---------------------------------------------------------------------------

def _teclear(detector, texto, intervalo_ms, inicio_ms=0, previo=""):
    t = inicio_ms
    for i, _ in enumerate(texto):
        detector.tecla(t, len(previo) + i)
        t += intervalo_ms
    return previo + texto


def test_lectura_del_escaner_a_16_ms_por_caracter():
    d = DetectorEscaner()
    texto = _teclear(d, "7898024390107", 16)
    assert d.es_lectura()
    assert d.codigo_leido(texto) == "7898024390107"


def test_captura_a_mano_no_es_lectura():
    """El caso del log del 23/10: el Ferrero tecleado a mano."""
    d = DetectorEscaner()
    _teclear(d, "7898024390107", 200)
    assert not d.es_lectura()


def test_nombre_escrito_rapido_a_mano_no_es_lectura():
    d = DetectorEscaner()
    _teclear(d, "gatorade", 90)
    assert not d.es_lectura()


def test_codigo_corto_del_escaner_tambien_cuenta():
    """Los códigos internos como 10004 son de 5 caracteres."""
    d = DetectorEscaner()
    texto = _teclear(d, "10004", 16)
    assert d.es_lectura()
    assert d.codigo_leido(texto) == "10004"


def test_escaneo_sobre_texto_escrito_a_mano_se_queda_solo_con_el_codigo():
    d = DetectorEscaner()
    previo = _teclear(d, "gato", 200)
    texto = _teclear(d, "7501022015162", 16, inicio_ms=5000, previo=previo)
    assert d.es_lectura()
    assert d.codigo_leido(texto) == "7501022015162"


def test_reiniciar_olvida_la_rafaga():
    d = DetectorEscaner()
    _teclear(d, "7501022015162", 16)
    d.reiniciar()
    assert not d.es_lectura()


# ---------------------------------------------------------------------------
# MovimientoInventarioWindow.buscar_manual / buscar_lectura
# ---------------------------------------------------------------------------

CATALOGO = {
    "10086": {"codigo_interno": "10086", "codigo_barras": "10086", "nombre": "TOALLA GRANDE", "stock_actual": 64, "tipo_producto": "varios"},
    "10089": {"codigo_interno": "10089", "codigo_barras": "10089", "nombre": "TOALLA CHICA", "stock_actual": 80, "tipo_producto": "varios"},
    "7501": {"codigo_interno": "7501", "codigo_barras": "7501022015162", "nombre": "GATORLYTE UVA", "stock_actual": 4, "tipo_producto": "varios"},
}


class GestorFake:
    def __init__(self):
        self.busquedas = []

    def get_product_with_stock(self, codigo):
        p = CATALOGO.get(codigo)
        return dict(p) if p else None

    def get_product_by_barcode(self, barcode):
        return next((dict(p) for p in CATALOGO.values() if p["codigo_barras"] == barcode), None)

    def search_products(self, texto):
        self.busquedas.append(texto)
        t = texto.lower()
        return [dict(p) for p in CATALOGO.values()
                if t in p["nombre"].lower() or t in p["codigo_barras"] or t in p["codigo_interno"]]


class Visible:
    def __init__(self):
        self.visible = False
        self.texto = ""
        self.items = []

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def setText(self, t):
        self.texto = t

    def text(self):
        return self.texto

    def setStyleSheet(self, _):
        pass

    def setFocus(self):
        pass

    def clear(self):
        self.items = []

    def addItem(self, item):
        self.items.append(item)


class BarraFake:
    def __init__(self, texto):
        self.search_input = Visible()
        self.search_input.texto = texto


def _ventana(texto):
    from ui.movimiento_inventario_window import MovimientoInventarioWindow

    v = MovimientoInventarioWindow.__new__(MovimientoInventarioWindow)
    v.pg_manager = GestorFake()
    v.search_bar = BarraFake(texto)
    v.detector = DetectorEscaner()
    v.producto_seleccionado = None
    v.producto_info_label = Visible()
    v.busqueda_aviso_label = Visible()
    v.resultados_list = Visible()
    v.cantidad_spin = Visible()
    return v


def test_buscar_por_nombre_con_un_resultado_lo_selecciona():
    v = _ventana("toalla chica")
    v.buscar_manual()
    assert v.producto_seleccionado["codigo_interno"] == "10089"
    assert not v.resultados_list.visible


def test_buscar_por_nombre_con_varios_resultados_muestra_la_lista():
    v = _ventana("toalla")
    v.buscar_manual()
    assert v.producto_seleccionado is None
    assert v.resultados_list.visible
    assert len(v.resultados_list.items) == 2


def test_buscar_codigo_de_barras_exacto_a_mano():
    v = _ventana("7501022015162")
    v.buscar_manual()
    assert v.producto_seleccionado["nombre"] == "GATORLYTE UVA"
    assert v.pg_manager.busquedas == []


def test_sin_resultados_avisa_en_linea_sin_ventana():
    v = _ventana("ferrero")
    v.buscar_manual()
    assert v.producto_seleccionado is None
    assert v.busqueda_aviso_label.visible
    assert "ferrero" in v.busqueda_aviso_label.texto


def test_campo_vacio_avisa_en_linea():
    v = _ventana("   ")
    v.buscar_manual()
    assert v.busqueda_aviso_label.visible
    assert v.pg_manager.busquedas == []


def test_comas_y_parentesis_no_llegan_al_filtro():
    v = _ventana("toalla, (chica)")
    v.buscar_manual()
    assert all("," not in b and "(" not in b and ")" not in b for b in v.pg_manager.busquedas)


def test_lectura_del_escaner_busca_solo_el_codigo_leido():
    v = _ventana("")
    previo = _teclear(v.detector, "abc", 200)
    v.search_bar.search_input.texto = _teclear(v.detector, "10086", 16, inicio_ms=5000, previo=previo)
    v.buscar_lectura()
    assert v.producto_seleccionado["nombre"] == "TOALLA GRANDE"
    assert v.search_bar.search_input.texto == "10086"
    assert not v.detector.es_lectura()
