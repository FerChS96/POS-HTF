"""
Distingue una lectura del escáner de código de barras de una captura a mano.

El escáner se comporta como un teclado, pero teclea cada carácter en unos
16 ms (medido en pos_htf.log); una persona tarda de 150 a 250 ms. Por eso la
diferencia se mide por velocidad y no por longitud: buscar al llegar a N
caracteres disparaba búsquedas a media captura cuando alguien escribía a mano.
"""

# Una tecla que llega antes de este tiempo desde la anterior es del escáner.
MAX_MS_ENTRE_TECLAS = 50
# Caracteres seguidos y rápidos que hacen falta para darlo por lectura.
MIN_CARACTERES_RAFAGA = 4


class DetectorEscaner:
    """Registra el tiempo de cada tecla y dice si la última ráfaga fue del escáner."""

    def __init__(self, max_ms=MAX_MS_ENTRE_TECLAS, min_caracteres=MIN_CARACTERES_RAFAGA):
        self.max_ms = max_ms
        self.min_caracteres = min_caracteres
        self.reiniciar()

    def reiniciar(self):
        self._ultima_ms = None
        self._rafaga = 0
        self._inicio_rafaga = 0

    def tecla(self, ahora_ms, largo_texto_antes):
        """Anota una tecla imprimible; largo_texto_antes es el texto previo a ella."""
        if self._ultima_ms is not None and ahora_ms - self._ultima_ms <= self.max_ms:
            self._rafaga += 1
        else:
            self._rafaga = 1
            self._inicio_rafaga = largo_texto_antes
        self._ultima_ms = ahora_ms

    def es_lectura(self):
        return self._rafaga >= self.min_caracteres

    def codigo_leido(self, texto):
        """
        El código que trajo la ráfaga. Si el campo ya tenía algo escrito a
        mano, el escáner lo agregó al final: se descarta lo anterior.
        """
        return texto[self._inicio_rafaga:].strip()
