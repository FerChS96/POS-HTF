"""
Pruebas del manejo de notificaciones de entrada.

Cubren la causa del cuelgue reportado desde el gimnasio: los avisos de entrada
se acumulaban sin tope, no se destruian al cerrarse y cada uno mantenia un
temporizador repintando un reloj cada segundo.

Medido antes del arreglo:
    50 notificaciones = 50 ventanas abiertas, ~113 MB, 50 repintados/segundo
    cerrarlas no liberaba nada (seguian vivas como hijas de la ventana)

No se construyen widgets Qt: se usan dobles, para que la suite siga sin
necesitar pantalla.
"""

import pytest


class NotificacionFalsa:
    """Doble de NotificacionEntradaWidget con lo justo para estas pruebas."""

    def __init__(self, id_entrada):
        self.miembro_data = {'id_entrada': id_entrada}
        self.cerrada = False
        self.destruida = False

    def close(self):
        self.cerrada = True
        # El widget real emite 'cerrado', que la ventana conecta a
        # remover_notificacion. Aqui lo hace el llamador.

    def deleteLater(self):
        self.destruida = True

    def isVisible(self):
        return not self.cerrada


@pytest.fixture
def ventana():
    """
    MainPOSWindow sin construir la interfaz: solo el estado que usa la
    gestion de notificaciones.
    """
    from ui.main_pos_window import MainPOSWindow

    v = MainPOSWindow.__new__(MainPOSWindow)
    v.notificaciones_activas = []
    return v


# ---------------------------------------------------------------------------
# Destruccion al cerrar
# ---------------------------------------------------------------------------

def test_al_remover_se_destruye_el_widget(ventana):
    """
    Regresion: antes solo se quitaba de la lista. Como se crean con
    parent=self, Qt los mantenia vivos toda la sesion y cerrar una
    notificacion no liberaba ni un byte.
    """
    n = NotificacionFalsa(1)
    ventana.notificaciones_activas.append(n)

    ventana.remover_notificacion(n)

    assert n.destruida is True
    assert ventana.notificaciones_activas == []


def test_remover_dos_veces_no_revienta(ventana):
    """Un doble cierre no debe tumbar la aplicacion."""
    n = NotificacionFalsa(1)
    ventana.notificaciones_activas.append(n)

    ventana.remover_notificacion(n)
    ventana.remover_notificacion(n)   # no debe lanzar

    assert ventana.notificaciones_activas == []


def test_destruye_aunque_no_estuviera_en_la_lista(ventana):
    """Si llega una notificacion huerfana, igual hay que liberarla."""
    n = NotificacionFalsa(99)
    ventana.remover_notificacion(n)
    assert n.destruida is True


def test_widget_ya_destruido_no_propaga_error(ventana):
    """deleteLater sobre un widget ya destruido lanza RuntimeError en Qt."""
    class YaDestruida(NotificacionFalsa):
        def deleteLater(self):
            raise RuntimeError("Internal C++ object already deleted")

    n = YaDestruida(1)
    ventana.notificaciones_activas.append(n)
    ventana.remover_notificacion(n)   # no debe lanzar
    assert ventana.notificaciones_activas == []


# ---------------------------------------------------------------------------
# Tope de notificaciones simultaneas
# ---------------------------------------------------------------------------

def _llenar(ventana, cantidad):
    """Simular `cantidad` entradas seguidas, como en hora punta."""
    from ui.main_pos_window import MainPOSWindow

    creadas = []
    for i in range(cantidad):
        n = NotificacionFalsa(i)
        # El widget real emite 'cerrado' al cerrarse; aqui se replica.
        n.close = lambda n=n: (
            setattr(n, 'cerrada', True),
            ventana.remover_notificacion(n),
        )
        ventana.notificaciones_activas.append(n)
        creadas.append(n)
        ventana._limitar_notificaciones_abiertas()
    return creadas


def test_no_se_pasa_del_limite(ventana):
    """Regresion del cuelgue: antes se apilaban sin tope."""
    from ui.main_pos_window import MAX_NOTIFICACIONES_VISIBLES

    _llenar(ventana, 50)
    assert len(ventana.notificaciones_activas) == MAX_NOTIFICACIONES_VISIBLES


def test_las_que_sobran_se_destruyen(ventana):
    """No basta con ocultarlas: hay que liberar la memoria."""
    from ui.main_pos_window import MAX_NOTIFICACIONES_VISIBLES

    creadas = _llenar(ventana, 30)
    sobrantes = creadas[:30 - MAX_NOTIFICACIONES_VISIBLES]
    assert all(n.destruida for n in sobrantes)


def test_se_conservan_las_mas_recientes(ventana):
    """Se cierran las viejas: son las que ya nadie iba a leer."""
    from ui.main_pos_window import MAX_NOTIFICACIONES_VISIBLES

    _llenar(ventana, 20)
    ids = [n.miembro_data['id_entrada'] for n in ventana.notificaciones_activas]
    assert ids == list(range(20 - MAX_NOTIFICACIONES_VISIBLES, 20))


def test_por_debajo_del_limite_no_cierra_nada(ventana):
    creadas = _llenar(ventana, 3)
    assert len(ventana.notificaciones_activas) == 3
    assert not any(n.destruida for n in creadas)


def test_el_limite_esta_en_un_rango_razonable():
    from ui.main_pos_window import MAX_NOTIFICACIONES_VISIBLES

    assert 1 <= MAX_NOTIFICACIONES_VISIBLES <= 50


@pytest.mark.parametrize("valor,esperado", [
    ("5", 5), ("20", 20), ("1", 1), ("50", 50),
    ("0", 8), ("51", 8), ("-3", 8), ("muchas", 8), ("", 8),
])
def test_limite_configurable_por_entorno(monkeypatch, valor, esperado):
    """Fuera de rango o mal escrito debe caer al valor por defecto."""
    import importlib
    import ui.main_pos_window as modulo

    monkeypatch.setenv('NOTIFICACIONES_MAX_VISIBLES', valor)
    assert modulo._limite_notificaciones() == esperado


def test_sin_variable_usa_el_valor_por_defecto(monkeypatch):
    import ui.main_pos_window as modulo

    monkeypatch.delenv('NOTIFICACIONES_MAX_VISIBLES', raising=False)
    assert modulo._limite_notificaciones() == 8


# ---------------------------------------------------------------------------
# La hora mostrada
# ---------------------------------------------------------------------------

def _widget_sin_qt(datos):
    """NotificacionEntradaWidget sin construir la interfaz."""
    from ui.notificacion_entrada_widget import NotificacionEntradaWidget

    w = NotificacionEntradaWidget.__new__(NotificacionEntradaWidget)
    w.miembro_data = datos
    return w


def test_muestra_la_hora_de_entrada_no_la_actual():
    """
    Regresion: la etiqueta nacia con la hora de entrada y un temporizador la
    sobrescribia cada segundo con el reloj, perdiendo el dato util.
    """
    w = _widget_sin_qt({'hora_entrada': '2026-09-28T10:14:32'})
    assert w._hora_de_entrada() == '10:14:32'


def test_acepta_hora_ya_formateada():
    w = _widget_sin_qt({'hora_entrada': '08:45:10'})
    assert w._hora_de_entrada() == '08:45:10'


def test_acepta_fecha_entrada_como_alternativa():
    w = _widget_sin_qt({'fecha_entrada': '2026-09-28T19:05:00'})
    assert w._hora_de_entrada() == '19:05:00'


def test_sin_hora_no_revienta():
    w = _widget_sin_qt({})
    valor = w._hora_de_entrada()
    assert len(valor) == 8 and valor.count(':') == 2


def test_hora_ilegible_no_revienta():
    w = _widget_sin_qt({'hora_entrada': 'no es una hora'})
    valor = w._hora_de_entrada()
    assert len(valor) == 8 and valor.count(':') == 2


def test_actualizar_tiempo_ya_no_hace_nada():
    """
    Se conserva el método por compatibilidad, pero no debe repintar: era la
    fuente del consumo de CPU cuando habia muchas notificaciones abiertas.
    """
    w = _widget_sin_qt({'hora_entrada': '10:00:00'})
    assert w.actualizar_tiempo() is None   # no toca hora_label (no existe aqui)
