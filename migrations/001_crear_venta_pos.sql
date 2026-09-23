-- =============================================================================
-- 001_crear_venta_pos.sql
-- -----------------------------------------------------------------------------
-- Crea la funcion transaccional `crear_venta_pos`, que registra en UNA SOLA
-- transaccion: la venta, sus detalles, el descuento de stock y los movimientos
-- de inventario.
--
-- Problemas que resuelve (ver POS_HTF/database/postgres_manager.py::create_sale):
--   Bug A: la venta se insertaba primero y, si un producto no tenia stock, el
--          `continue` saltaba el detalle/stock/movimiento pero la venta ya
--          estaba cobrada. Aqui, cualquier RAISE revierte TODO.
--   Bug B: patron leer-restar-escribir entre dos cajas. Aqui el descuento es un
--          UPDATE atomico (`stock_actual = stock_actual - X`), que toma el
--          candado de la fila; dos cajas simultaneas se serializan.
--   Bug C: N+1 (5 round-trips por linea). Aqui todo es una sola llamada RPC.
--
-- NO ejecutar automaticamente. Aplicar desde el SQL Editor de Supabase.
-- Ver migrations/README.md.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.crear_venta_pos(
    p_id_usuario      integer,
    p_items           jsonb,
    p_total           numeric,
    p_subtotal        numeric     DEFAULT NULL,
    p_descuento       numeric     DEFAULT 0,
    p_impuestos       numeric     DEFAULT 0,
    p_id_miembro      integer     DEFAULT NULL,
    p_id_turno        integer     DEFAULT NULL,
    p_metodo_pago     text        DEFAULT 'efectivo',
    p_tipo_venta      text        DEFAULT 'producto',
    p_referencia_pago text        DEFAULT NULL,
    p_notas           text        DEFAULT NULL,
    p_fecha           timestamptz DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_id_venta        integer;
    v_item            jsonb;
    v_id_producto     integer;
    v_codigo          text;
    v_tipo            text;
    v_cantidad        integer;
    v_precio          numeric;
    v_subtotal_linea  numeric;
    v_desc_linea      numeric;
    v_nombre          text;
    v_descripcion     text;
    v_stock_anterior  integer;
    v_stock_nuevo     integer;
BEGIN
    -- ---------------------------------------------------------------------
    -- 0) Validaciones de entrada
    -- ---------------------------------------------------------------------
    IF p_items IS NULL
       OR jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'La venta no tiene productos: no hay nada que cobrar.'
            USING ERRCODE = '22023';
    END IF;

    IF p_id_usuario IS NULL THEN
        RAISE EXCEPTION 'La venta requiere un id_usuario (cajero).'
            USING ERRCODE = '22023';
    END IF;

    -- ---------------------------------------------------------------------
    -- 1) Cabecera de la venta
    --    Si cualquier paso posterior lanza excepcion, este INSERT se revierte
    --    junto con todo lo demas: NUNCA queda una venta cobrada sin detalle.
    -- ---------------------------------------------------------------------
    INSERT INTO ventas (
        id_usuario, id_miembro, id_turno, fecha,
        subtotal, descuento, impuestos, total,
        metodo_pago, referencia_pago, tipo_venta, estado, notas
    ) VALUES (
        p_id_usuario,
        p_id_miembro,
        p_id_turno,
        COALESCE(p_fecha, now()),
        COALESCE(p_subtotal, p_total),
        COALESCE(p_descuento, 0),
        COALESCE(p_impuestos, 0),
        p_total,
        COALESCE(p_metodo_pago, 'efectivo'),
        p_referencia_pago,
        COALESCE(p_tipo_venta, 'producto'),
        'completada',
        p_notas
    )
    RETURNING id_venta INTO v_id_venta;

    -- ---------------------------------------------------------------------
    -- 2) Una pasada por cada linea del carrito
    -- ---------------------------------------------------------------------
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_id_producto    := NULLIF(v_item->>'id_producto', '')::integer;
        v_codigo         := NULLIF(v_item->>'codigo_interno', '');
        v_tipo           := COALESCE(NULLIF(v_item->>'tipo_producto', ''), 'varios');
        v_cantidad       := COALESCE(NULLIF(v_item->>'cantidad', '')::integer, 0);
        v_precio         := COALESCE(NULLIF(v_item->>'precio_unitario', '')::numeric, 0);
        v_subtotal_linea := COALESCE(NULLIF(v_item->>'subtotal_linea', '')::numeric,
                                     v_precio * v_cantidad);
        v_desc_linea     := COALESCE(NULLIF(v_item->>'descuento_linea', '')::numeric, 0);

        IF v_cantidad <= 0 THEN
            RAISE EXCEPTION 'Cantidad invalida (%) en la linea del producto %.',
                v_cantidad, COALESCE(v_codigo, v_id_producto::text)
                USING ERRCODE = '22023';
        END IF;

        -- 2.a) Resolver el producto (nombre y descripcion para el ticket).
        --      Se acepta codigo_interno directo o id_producto del catalogo.
        v_nombre      := NULL;
        v_descripcion := NULL;

        IF v_tipo = 'varios' THEN
            SELECT p.codigo_interno, p.nombre, p.descripcion
              INTO v_codigo, v_nombre, v_descripcion
              FROM ca_productos_varios p
             WHERE (v_codigo IS NOT NULL AND p.codigo_interno = v_codigo)
                OR (v_codigo IS NULL AND p.id_producto = v_id_producto)
             LIMIT 1;
        END IF;

        IF v_codigo IS NULL THEN
            RAISE EXCEPTION 'Producto no encontrado en el catalogo (id_producto=%, tipo=%).',
                v_id_producto, v_tipo
                USING ERRCODE = '23503';
        END IF;

        v_nombre := COALESCE(v_nombre, v_codigo);

        -- 2.b) DESCUENTO ATOMICO DE STOCK  (arregla el Bug B)
        --      Un solo UPDATE: se lee y se escribe dentro de la misma
        --      sentencia, bajo el candado de fila de Postgres. NUNCA se hace
        --      "leer stock -> restar en Python -> escribir".
        --      El filtro `stock_actual >= v_cantidad` evita chocar contra el
        --      CHECK (stock_actual >= 0) y nos deja dar un mensaje legible.
        UPDATE inventario
           SET stock_actual        = stock_actual - v_cantidad,
               fecha_ultima_salida = now()
         WHERE codigo_interno = v_codigo
           AND tipo_producto  = v_tipo
           AND stock_actual  >= v_cantidad
        RETURNING stock_actual INTO v_stock_nuevo;

        IF NOT FOUND THEN
            -- Solo en el camino de error volvemos a leer, para poder decirle al
            -- cajero cuanto habia. La transaccion se revierte de todos modos.
            SELECT i.stock_actual
              INTO v_stock_anterior
              FROM inventario i
             WHERE i.codigo_interno = v_codigo
               AND i.tipo_producto  = v_tipo
             LIMIT 1;

            IF v_stock_anterior IS NULL THEN
                RAISE EXCEPTION 'No existe registro de inventario para "%" (%).',
                    v_nombre, v_codigo
                    USING ERRCODE = '23503';
            END IF;

            RAISE EXCEPTION 'Stock insuficiente para "%": se pidieron % y solo hay %.',
                v_nombre, v_cantidad, v_stock_anterior
                USING ERRCODE = '23514';
        END IF;

        -- Red de seguridad: si por cualquier motivo el stock quedara negativo,
        -- se aborta la venta completa con un mensaje que nombra el producto.
        IF v_stock_nuevo < 0 THEN
            RAISE EXCEPTION 'Stock insuficiente para "%": se pidieron % y solo hay %.',
                v_nombre, v_cantidad, v_stock_nuevo + v_cantidad
                USING ERRCODE = '23514';
        END IF;

        v_stock_anterior := v_stock_nuevo + v_cantidad;

        -- 2.c) Detalle de la venta
        INSERT INTO detalles_venta (
            id_venta, codigo_interno, tipo_producto, cantidad,
            precio_unitario, subtotal_linea, descuento_linea,
            nombre_producto, descripcion_producto
        ) VALUES (
            v_id_venta, v_codigo, v_tipo, v_cantidad,
            v_precio, v_subtotal_linea, v_desc_linea,
            v_nombre, v_descripcion
        );

        -- 2.d) Movimiento de inventario (kardex)
        INSERT INTO movimientos_inventario (
            codigo_interno, tipo_producto, tipo_movimiento, cantidad,
            stock_anterior, stock_nuevo, id_usuario, id_venta, fecha, motivo
        ) VALUES (
            v_codigo, v_tipo, 'venta', -v_cantidad,
            v_stock_anterior, v_stock_nuevo, p_id_usuario, v_id_venta,
            COALESCE(p_fecha, now()),
            'Venta POS #' || v_id_venta
        );
    END LOOP;

    RETURN v_id_venta;
END;
$$;

COMMENT ON FUNCTION public.crear_venta_pos(
    integer, jsonb, numeric, numeric, numeric, numeric, integer, integer,
    text, text, text, text, timestamptz
) IS
'POS HTF: registra venta + detalles + descuento atomico de stock + movimientos '
'en una sola transaccion. Lanza excepcion (y revierte todo) si falta stock.';

-- El POS se conecta via PostgREST con la llave anon/service. Sin estos GRANT,
-- PostgREST responde PGRST202 y el cliente Python cae al camino de respaldo.
GRANT EXECUTE ON FUNCTION public.crear_venta_pos(
    integer, jsonb, numeric, numeric, numeric, numeric, integer, integer,
    text, text, text, text, timestamptz
) TO anon, authenticated, service_role;

-- PostgREST cachea el esquema: forzar recarga para que la funcion sea visible ya.
NOTIFY pgrst, 'reload schema';
