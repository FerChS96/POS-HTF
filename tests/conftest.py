"""
Andamiaje de pruebas para el POS HTF.

Provee un doble de prueba del cliente de Supabase (FakeSupabaseClient) que
imita la API encadenada de supabase-py v2 sobre un almacen en memoria, de modo
que la capa de datos se pueda probar SIN tocar la base de produccion.

Capacidades:
  - Almacen en memoria por tabla, con PK autoincremental.
  - Conteo de llamadas (.calls) para detectar consultas N+1.
  - Inyeccion de fallos (.fail_on) para simular cortes de red a media operacion.
  - Soporte de rpc() para probar el camino transaccional.
"""

import os
import sys
import copy
import pytest

# La raiz del proyecto (POS_HTF/) debe estar en el path para importar
# database.*, utils.*, services.*
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


# Llaves primarias reales, tomadas del esquema vivo de Supabase.
CLAVES_PRIMARIAS = {
    "ventas": "id_venta",
    "detalles_venta": "id_detalle",
    "inventario": "id_inventario",
    "movimientos_inventario": "id_movimiento",
    "ca_productos_varios": "id_producto",
    "ca_productos_digitales": "id_producto_digital",
    "ventas_digitales": "id_venta_digital",
    "usuarios": "id_usuario",
    "miembros": "id_miembro",
    "turnos_caja": "id_turno",
    "notificaciones_pos": "id_notificacion",
    "lockers": "id_locker",
}


class FallaSimulada(Exception):
    """Error inyectado a proposito para simular una caida de red o de la API."""


class RespuestaFake:
    """Equivalente de APIResponse de supabase-py."""

    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class ConsultaFake:
    """
    Constructor de consultas encadenable: replica .select().eq().limit().execute()
    de supabase-py sobre listas de diccionarios en memoria.
    """

    def __init__(self, cliente, tabla):
        self._cliente = cliente
        self._tabla = tabla
        self._operacion = None
        self._payload = None
        self._filtros = []       # lista de (columna, valor, tipo)
        self._limite = None
        self._orden = None
        self._contar = None
        self._single = False
        self._columnas = None    # columnas pedidas en select(), None = todas

    # --- operaciones ---
    def select(self, *columnas, **kwargs):
        self._operacion = "select"
        self._contar = kwargs.get("count")
        # PostgREST devuelve SOLO las columnas pedidas. Imitarlo importa: es lo
        # que hace que una consulta que no pide 'contrasenia' no la reciba.
        self._columnas = self._parsear_columnas(columnas)
        return self

    @staticmethod
    def _parsear_columnas(columnas):
        """
        Lista de columnas a devolver, o None para devolver la fila entera.

        Se devuelve None (sin recorte) con '*' o con sintaxis de relaciones
        anidadas tipo 'usuarios(nombre_completo)', que este doble no resuelve.
        """
        if not columnas:
            return None
        crudo = ",".join(str(c) for c in columnas)
        if "*" in crudo or "(" in crudo:
            return None
        nombres = [c.strip() for c in crudo.split(",") if c.strip()]
        return nombres or None

    def insert(self, datos, **kwargs):
        self._operacion = "insert"
        self._payload = datos
        return self

    def update(self, datos, **kwargs):
        self._operacion = "update"
        self._payload = datos
        return self

    def upsert(self, datos, **kwargs):
        self._operacion = "upsert"
        self._payload = datos
        return self

    def delete(self, **kwargs):
        self._operacion = "delete"
        return self

    # --- filtros ---
    def eq(self, columna, valor):
        self._filtros.append((columna, valor, "eq"))
        return self

    def neq(self, columna, valor):
        self._filtros.append((columna, valor, "neq"))
        return self

    def gt(self, columna, valor):
        self._filtros.append((columna, valor, "gt"))
        return self

    def gte(self, columna, valor):
        self._filtros.append((columna, valor, "gte"))
        return self

    def lt(self, columna, valor):
        self._filtros.append((columna, valor, "lt"))
        return self

    def lte(self, columna, valor):
        self._filtros.append((columna, valor, "lte"))
        return self

    def in_(self, columna, valores):
        self._filtros.append((columna, list(valores), "in"))
        return self

    def is_(self, columna, valor):
        self._filtros.append((columna, valor, "is"))
        return self

    def like(self, columna, patron):
        self._filtros.append((columna, patron, "like"))
        return self

    def ilike(self, columna, patron):
        self._filtros.append((columna, patron, "ilike"))
        return self

    # --- modificadores ---
    def order(self, columna, desc=False, **kwargs):
        self._orden = (columna, desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def range(self, desde, hasta):
        self._limite = (hasta - desde) + 1
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    # --- ejecucion ---
    def _coincide(self, fila):
        for columna, valor, tipo in self._filtros:
            actual = fila.get(columna)
            if tipo == "eq" and actual != valor:
                return False
            if tipo == "neq" and actual == valor:
                return False
            if tipo == "gt" and not (actual is not None and actual > valor):
                return False
            if tipo == "gte" and not (actual is not None and actual >= valor):
                return False
            if tipo == "lt" and not (actual is not None and actual < valor):
                return False
            if tipo == "lte" and not (actual is not None and actual <= valor):
                return False
            if tipo == "in" and actual not in valor:
                return False
            if tipo == "is" and actual is not valor:
                return False
            if tipo in ("like", "ilike"):
                aguja = str(valor).replace("%", "")
                heno = str(actual or "")
                if tipo == "ilike":
                    aguja, heno = aguja.lower(), heno.lower()
                if aguja not in heno:
                    return False
        return True

    def execute(self):
        cliente = self._cliente
        cliente.calls.append((self._tabla, self._operacion))
        cliente._quiza_fallar(self._tabla, self._operacion)

        filas = cliente.store.setdefault(self._tabla, [])

        if self._operacion in ("insert", "upsert"):
            nuevas = self._payload if isinstance(self._payload, list) else [self._payload]
            insertadas = []
            for cruda in nuevas:
                fila = copy.deepcopy(cruda)
                pk = CLAVES_PRIMARIAS.get(self._tabla, "id")
                if pk not in fila:
                    fila[pk] = cliente._siguiente_id(self._tabla)
                cliente._validar_restricciones(self._tabla, fila)
                filas.append(fila)
                insertadas.append(copy.deepcopy(fila))
            return RespuestaFake(insertadas)

        seleccionadas = [f for f in filas if self._coincide(f)]

        if self._operacion == "update":
            for fila in seleccionadas:
                fila.update(copy.deepcopy(self._payload))
                cliente._validar_restricciones(self._tabla, fila)
            return RespuestaFake([copy.deepcopy(f) for f in seleccionadas])

        if self._operacion == "delete":
            for fila in seleccionadas:
                filas.remove(fila)
            return RespuestaFake([copy.deepcopy(f) for f in seleccionadas])

        # select
        total = len(seleccionadas)
        if self._orden:
            columna, desc = self._orden
            seleccionadas = sorted(
                seleccionadas,
                key=lambda f: (f.get(columna) is None, f.get(columna)),
                reverse=desc,
            )
        if self._limite is not None:
            seleccionadas = seleccionadas[: self._limite]

        datos = [copy.deepcopy(f) for f in seleccionadas]
        if self._columnas is not None:
            datos = [
                {c: fila[c] for c in self._columnas if c in fila}
                for fila in datos
            ]
        if self._single:
            return RespuestaFake(datos[0] if datos else None, total)
        return RespuestaFake(datos, total if self._contar else None)


class FakeSupabaseClient:
    """
    Doble de prueba de supabase.Client.

    Uso tipico:
        cli = FakeSupabaseClient({"inventario": [{...}]})
        cli.fail_on = ("detalles_venta", "insert")   # simula corte de red
        cli.calls                                     # round-trips registrados
    """

    def __init__(self, datos_iniciales=None, funciones_rpc=None):
        self.store = {}
        for tabla, filas in (datos_iniciales or {}).items():
            self.store[tabla] = [copy.deepcopy(f) for f in filas]
        self.calls = []
        self.rpc_calls = []
        # (tabla, operacion) que debe lanzar FallaSimulada, o None
        self.fail_on = None
        # cuantas veces omitir el fallo antes de dispararlo
        self.fail_after = 0
        # nombre -> callable(params) para funciones RPC disponibles
        self.funciones_rpc = dict(funciones_rpc or {})
        self._contadores = {}

    # --- API publica que imita a supabase.Client ---
    def table(self, nombre):
        return ConsultaFake(self, nombre)

    def from_(self, nombre):
        return ConsultaFake(self, nombre)

    def rpc(self, nombre, params=None):
        self.rpc_calls.append((nombre, copy.deepcopy(params or {})))
        cliente = self

        class _EjecutorRPC:
            def execute(self_inner):
                cliente.calls.append(("rpc:" + nombre, "rpc"))
                if nombre not in cliente.funciones_rpc:
                    raise Exception(
                        "Could not find the function public." + nombre +
                        " in the schema cache"
                    )
                return RespuestaFake(cliente.funciones_rpc[nombre](params or {}))

        return _EjecutorRPC()

    # --- utilidades de prueba ---
    def _siguiente_id(self, tabla):
        self._contadores[tabla] = self._contadores.get(tabla, 0) + 1
        return self._contadores[tabla]

    def _quiza_fallar(self, tabla, operacion):
        if self.fail_on and self.fail_on == (tabla, operacion):
            if self.fail_after > 0:
                self.fail_after -= 1
                return
            raise FallaSimulada(
                "Fallo simulado en " + str(operacion) + " sobre " + str(tabla)
            )

    def _validar_restricciones(self, tabla, fila):
        """Replica los CHECK del esquema real que importan para las pruebas."""
        if tabla == "inventario" and fila.get("stock_actual", 0) < 0:
            raise Exception(
                'new row for relation "inventario" violates check constraint '
                '"inventario_stock_actual_check"'
            )
        if tabla == "detalles_venta" and fila.get("cantidad", 1) <= 0:
            raise Exception(
                'new row for relation "detalles_venta" violates check constraint '
                '"detalles_venta_cantidad_check"'
            )

    def contar_llamadas(self, tabla=None, operacion=None):
        """Cuenta round-trips, opcionalmente filtrando por tabla y/u operacion."""
        return sum(
            1
            for (t, o) in self.calls
            if (tabla is None or t == tabla) and (operacion is None or o == operacion)
        )

    def filas(self, tabla):
        """Lectura directa del almacen, para aserciones."""
        return [copy.deepcopy(f) for f in self.store.get(tabla, [])]


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

@pytest.fixture
def datos_catalogo():
    """Catalogo minimo coherente: 2 productos con su inventario."""
    return {
        "ca_productos_varios": [
            {
                "id_producto": 1,
                "codigo_interno": "PROT-001",
                "nombre": "Proteina Whey 1kg",
                "descripcion": "Sabor chocolate",
                "precio_venta": 650.0,
                "activo": True,
            },
            {
                "id_producto": 2,
                "codigo_interno": "AGUA-001",
                "nombre": "Agua 600ml",
                "descripcion": None,
                "precio_venta": 15.0,
                "activo": True,
            },
        ],
        "inventario": [
            {
                "id_inventario": 1,
                "codigo_interno": "PROT-001",
                "tipo_producto": "varios",
                "stock_actual": 10,
                "stock_minimo": 2,
                "activo": True,
            },
            {
                "id_inventario": 2,
                "codigo_interno": "AGUA-001",
                "tipo_producto": "varios",
                "stock_actual": 3,
                "stock_minimo": 5,
                "activo": True,
            },
        ],
        "usuarios": [
            {
                "id_usuario": 1,
                "nombre_usuario": "cajera",
                "nombre_completo": "Cajera de Prueba",
                "rol": "recepcionista",
                "activo": True,
            }
        ],
        "turnos_caja": [
            {"id_turno": 1, "id_usuario": 1, "cerrado": False, "monto_inicial": 500.0}
        ],
        "ventas": [],
        "detalles_venta": [],
        "movimientos_inventario": [],
    }


@pytest.fixture
def cliente_fake(datos_catalogo):
    """Cliente Supabase falso ya cargado con el catalogo minimo."""
    return FakeSupabaseClient(datos_catalogo)


@pytest.fixture
def pg_manager(cliente_fake):
    """
    PostgresManager con su conexion reemplazada por el cliente falso.
    Evita __init__ (que conectaria a Supabase de verdad) usando __new__.
    """
    from database.postgres_manager import PostgresManager

    gestor = PostgresManager.__new__(PostgresManager)
    gestor.client = cliente_fake
    gestor.is_connected = True
    gestor.db_config = {}
    gestor.supabase_key = "llave-de-prueba"
    gestor._missing_suplementos_logged = False
    return gestor


@pytest.fixture
def venta_dos_productos():
    """Carrito valido: 2 proteinas + 1 agua."""
    return {
        "id_usuario": 1,
        "id_miembro": None,
        "id_turno": 1,
        "total": 1315.0,
        "metodo_pago": "efectivo",
        "tipo_venta": "producto",
        "productos": [
            {"id_producto": 1, "cantidad": 2, "precio": 650.0, "subtotal": 1300.0},
            {"id_producto": 2, "cantidad": 1, "precio": 15.0, "subtotal": 15.0},
        ],
    }
