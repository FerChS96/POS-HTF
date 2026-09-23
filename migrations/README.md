# Migraciones SQL del POS HTF

Estos archivos **no se aplican solos**. El POS habla con Supabase por REST y no
ejecuta DDL. Aplícalos tú desde el **SQL Editor de Supabase**.

| Archivo | Qué hace |
|---|---|
| `001_crear_venta_pos.sql` | Crea la función `public.crear_venta_pos(...)`: venta + detalles + descuento atómico de stock + movimientos, todo en UNA transacción. |
| `rollback_001.sql` | `DROP FUNCTION` de lo anterior. |

## Por qué existe

`create_sale` insertaba la venta primero y luego, producto por producto, hacía
`continue` si faltaba stock: la venta quedaba **cobrada y sin detalle**, con el
stock intacto. Además descontaba stock con `leer → restar → escribir`, lo que
permite que dos cajas vendan la misma pieza. La función `plpgsql` elimina ambos
problemas porque todo ocurre en una transacción y el descuento es un solo
`UPDATE inventario SET stock_actual = stock_actual - X ... RETURNING`.

## Cómo aplicarla

1. Entra a <https://supabase.com/dashboard> → tu proyecto → **SQL Editor** →
   **New query**.
2. Pega el contenido completo de `001_crear_venta_pos.sql`.
3. **Run**. Debe responder `Success. No rows returned`.
4. No hace falta reiniciar nada: el archivo termina con
   `NOTIFY pgrst, 'reload schema';`, que refresca el caché de PostgREST. Si aun
   así el POS no la ve, espera ~30 s o usa
   *Settings → API → Restart server*.

> La migración es idempotente (`CREATE OR REPLACE`). Se puede volver a correr
> sin riesgo.

## Cómo verificar

**1) Que la función existe y PostgREST la ve:**

```sql
SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS firma
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.proname = 'crear_venta_pos';
```

**2) Prueba en vivo, sin ensuciar la base** (todo dentro de un `ROLLBACK`):

```sql
BEGIN;

-- Caso feliz: usa un codigo_interno real de tu catálogo.
SELECT public.crear_venta_pos(
    p_id_usuario := 1,
    p_items      := '[{"codigo_interno":"PROT-001","tipo_producto":"varios",
                       "cantidad":1,"precio_unitario":650,"subtotal_linea":650}]'::jsonb,
    p_total      := 650
);

-- Revisa que quedaron venta, detalle, movimiento y stock descontado.
SELECT * FROM ventas ORDER BY id_venta DESC LIMIT 1;
SELECT * FROM detalles_venta ORDER BY id_detalle DESC LIMIT 1;
SELECT * FROM movimientos_inventario ORDER BY id_movimiento DESC LIMIT 1;

ROLLBACK;  -- IMPORTANTE: no deja nada escrito
```

**3) Que el stock insuficiente aborta TODO (regresión del Bug A):**

```sql
BEGIN;
SELECT count(*) AS ventas_antes FROM ventas;

-- Pide una cantidad absurda: debe fallar con un mensaje que nombra el producto.
SELECT public.crear_venta_pos(
    p_id_usuario := 1,
    p_items      := '[{"codigo_interno":"PROT-001","tipo_producto":"varios",
                       "cantidad":999999,"precio_unitario":650,"subtotal_linea":649999350}]'::jsonb,
    p_total      := 649999350
);
-- ERROR: Stock insuficiente para "Proteina Whey 1kg": se pidieron 999999 y solo hay 10.

ROLLBACK;
SELECT count(*) AS ventas_despues FROM ventas;  -- debe ser igual a ventas_antes
```

**4) Desde el POS**, en la consola de Python:

```python
from database.postgres_manager import PostgresManager
# create_sale intenta primero el RPC; si el log dice
#   "[OK] Venta creada por RPC transaccional"  -> la migración está activa
#   "RPC crear_venta_pos no disponible..."      -> aún no se aplicó
```

## Camino de respaldo

`create_sale` **no depende** de esta migración: si la función no existe,
PostgREST devuelve `PGRST202` / `schema cache` y el POS cae a un camino Python
endurecido (valida todo el stock antes de insertar nada, y hace rollback
compensatorio si algo falla a medias). Ese camino es seguro contra el Bug A,
pero solo *mitiga* el Bug B (update condicionado + reintentos). **La garantía
real de atomicidad la da esta migración.**

## Revertir

Pega `rollback_001.sql` en el SQL Editor y ejecútalo. El POS vuelve solo al
camino Python, sin necesidad de reiniciarlo.
