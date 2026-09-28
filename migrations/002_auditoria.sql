-- =============================================================================
-- 002 - Auditoria de cambios en precios e inventario
-- =============================================================================
-- PROBLEMA QUE RESUELVE
--   Hoy no hay forma de saber quien cambio un precio. `ca_productos_varios`
--   tiene `precio_venta` pero no guarda usuario, ni fecha, ni valor anterior:
--   la UI hace un UPDATE directo y no queda rastro de ningun tipo.
--   Con `inventario.stock_actual` pasa lo mismo; solo hay trazabilidad si el
--   codigo se acuerda de escribir tambien en `movimientos_inventario`, en una
--   segunda operacion que puede fallar por separado.
--
-- COMO LO RESUELVE
--   1. Columnas de atribucion en los catalogos y en inventario.
--   2. Tabla `auditoria` con el historial completo (valor anterior y nuevo).
--   3. TRIGGERS que llenan la tabla solos. Esto es lo importante: la auditoria
--      no depende de que la aplicacion se acuerde de registrarla. Cualquier
--      cambio queda grabado, venga del POS, del panel de Supabase o de un
--      script suelto.
--
-- NO ejecutar automaticamente. Aplicar desde el SQL Editor de Supabase.
-- Ver migrations/README.md.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Quien es el usuario que esta operando
-- -----------------------------------------------------------------------------
-- El POS se conecta con una sola llave de servicio, asi que Postgres no sabe
-- por si mismo que cajero esta detras. La aplicacion lo declara por sesion con:
--     SELECT set_config('app.id_usuario', '3', false);
-- y los triggers lo leen de ahi. Si no se declara, queda NULL y el registro
-- igual se guarda (preferimos una auditoria incompleta a ninguna).

CREATE OR REPLACE FUNCTION public.app_id_usuario()
RETURNS integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_valor text;
BEGIN
    v_valor := current_setting('app.id_usuario', true);
    IF v_valor IS NULL OR v_valor = '' THEN
        RETURN NULL;
    END IF;
    RETURN v_valor::integer;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.app_id_usuario() IS
    'Usuario del POS declarado por la sesion via set_config(''app.id_usuario'', ...).';


-- -----------------------------------------------------------------------------
-- 2. Columnas de atribucion
-- -----------------------------------------------------------------------------
-- Responden "quien y cuando" de un vistazo, sin consultar el historial.

ALTER TABLE public.ca_productos_varios
    ADD COLUMN IF NOT EXISTS actualizado_por      integer REFERENCES public.usuarios(id_usuario),
    ADD COLUMN IF NOT EXISTS fecha_actualizacion  timestamp without time zone;

ALTER TABLE public.ca_productos_digitales
    ADD COLUMN IF NOT EXISTS actualizado_por      integer REFERENCES public.usuarios(id_usuario),
    ADD COLUMN IF NOT EXISTS fecha_actualizacion  timestamp without time zone;

ALTER TABLE public.inventario
    ADD COLUMN IF NOT EXISTS actualizado_por      integer REFERENCES public.usuarios(id_usuario),
    ADD COLUMN IF NOT EXISTS fecha_actualizacion  timestamp without time zone;

COMMENT ON COLUMN public.ca_productos_varios.actualizado_por IS
    'Ultimo usuario que modifico el producto. El historial esta en public.auditoria.';


-- -----------------------------------------------------------------------------
-- 3. Tabla de auditoria
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.auditoria (
    id_auditoria    bigserial    PRIMARY KEY,
    tabla           varchar(64)  NOT NULL,
    id_registro     varchar(64)  NOT NULL,   -- PK del registro tocado, como texto
    campo           varchar(64)  NOT NULL,   -- columna que cambio
    valor_anterior  text,
    valor_nuevo     text,
    operacion       varchar(16)  NOT NULL,   -- INSERT | UPDATE | DELETE
    id_usuario      integer      REFERENCES public.usuarios(id_usuario),
    fecha           timestamp without time zone NOT NULL DEFAULT (now() AT TIME ZONE 'America/Mexico_City'),
    -- Rastro tecnico, util cuando id_usuario viene NULL (cambio hecho fuera del POS)
    db_usuario      varchar(64)  NOT NULL DEFAULT current_user,
    aplicacion      varchar(128)
);

COMMENT ON TABLE public.auditoria IS
    'Historial de cambios en precios e inventario. Lo llenan triggers, no la aplicacion.';

-- Indices para las tres preguntas que se haran de verdad:
--   "que le paso a ESTE producto", "que cambio Fulano", "que paso ayer"
CREATE INDEX IF NOT EXISTS idx_auditoria_registro ON public.auditoria (tabla, id_registro, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario  ON public.auditoria (id_usuario, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_fecha    ON public.auditoria (fecha DESC);


-- -----------------------------------------------------------------------------
-- 4. Trigger generico
-- -----------------------------------------------------------------------------
-- Se configura por tabla con TG_ARGV:
--   TG_ARGV[0] = nombre de la columna que es la PK
--   TG_ARGV[1..] = columnas a vigilar
-- Solo escribe cuando el valor cambio de verdad (IS DISTINCT FROM), para no
-- llenar la tabla de ruido cuando se guarda un formulario sin tocar nada.

CREATE OR REPLACE FUNCTION public.fn_auditar_cambios()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_pk          text;
    v_campo       text;
    v_anterior    text;
    v_nuevo       text;
    v_fila_ant    jsonb;
    v_fila_nue    jsonb;
    v_usuario     integer;
    v_aplicacion  text    := current_setting('application_name', true);
    i             integer;
BEGIN
    v_fila_ant := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
    v_fila_nue := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;

    -- Quien hizo el cambio. Se busca en dos lugares, por este orden:
    --   1. La variable de sesion app.id_usuario, util para scripts y psql.
    --   2. La columna actualizado_por de la propia fila, que es la via que
    --      funciona desde el POS: la aplicacion habla por la API REST, cuyo
    --      pool de conexiones NO conserva variables de sesion. Sin este
    --      respaldo, todo cambio hecho desde el POS quedaba con usuario vacio,
    --      que es justo lo que la auditoria tenia que responder.
    v_usuario := COALESCE(
        public.app_id_usuario(),
        NULLIF(v_fila_nue ->> 'actualizado_por', '')::integer,
        NULLIF(v_fila_ant ->> 'actualizado_por', '')::integer
    );

    v_pk := COALESCE(v_fila_nue ->> TG_ARGV[0], v_fila_ant ->> TG_ARGV[0]);

    -- Un renglon de auditoria por cada columna vigilada que haya cambiado.
    FOR i IN 1 .. (TG_NARGS - 1) LOOP
        v_campo    := TG_ARGV[i];
        v_anterior := v_fila_ant ->> v_campo;
        v_nuevo    := v_fila_nue ->> v_campo;

        IF TG_OP = 'UPDATE' AND v_anterior IS NOT DISTINCT FROM v_nuevo THEN
            CONTINUE;   -- no cambio: no se registra
        END IF;

        INSERT INTO public.auditoria (
            tabla, id_registro, campo, valor_anterior, valor_nuevo,
            operacion, id_usuario, aplicacion
        ) VALUES (
            TG_TABLE_NAME, v_pk, v_campo, v_anterior, v_nuevo,
            TG_OP, v_usuario, v_aplicacion
        );
    END LOOP;

    RETURN NULL;   -- AFTER trigger: el valor de retorno se ignora
END;
$$;


-- -----------------------------------------------------------------------------
-- 5. Trigger que rellena actualizado_por / fecha_actualizacion
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.fn_marcar_actualizacion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- COALESCE en este orden a proposito: la variable de sesion manda, pero si
    -- no existe se respeta el valor que haya enviado la aplicacion, y solo si
    -- tampoco lo hay se conserva el anterior.
    NEW.actualizado_por     := COALESCE(
        public.app_id_usuario(), NEW.actualizado_por, OLD.actualizado_por
    );
    NEW.fecha_actualizacion := (now() AT TIME ZONE 'America/Mexico_City');
    RETURN NEW;
END;
$$;


-- -----------------------------------------------------------------------------
-- 6. Conectar los triggers
-- -----------------------------------------------------------------------------

-- --- Productos varios: precio y datos comerciales ---
DROP TRIGGER IF EXISTS trg_marcar_productos_varios ON public.ca_productos_varios;
CREATE TRIGGER trg_marcar_productos_varios
    BEFORE UPDATE ON public.ca_productos_varios
    FOR EACH ROW EXECUTE FUNCTION public.fn_marcar_actualizacion();

DROP TRIGGER IF EXISTS trg_auditar_productos_varios ON public.ca_productos_varios;
CREATE TRIGGER trg_auditar_productos_varios
    AFTER INSERT OR UPDATE OR DELETE ON public.ca_productos_varios
    FOR EACH ROW EXECUTE FUNCTION public.fn_auditar_cambios(
        'id_producto', 'precio_venta', 'nombre', 'codigo_barras', 'activo', 'categoria'
    );

-- --- Productos digitales (membresias): precio y vigencia ---
DROP TRIGGER IF EXISTS trg_marcar_productos_digitales ON public.ca_productos_digitales;
CREATE TRIGGER trg_marcar_productos_digitales
    BEFORE UPDATE ON public.ca_productos_digitales
    FOR EACH ROW EXECUTE FUNCTION public.fn_marcar_actualizacion();

DROP TRIGGER IF EXISTS trg_auditar_productos_digitales ON public.ca_productos_digitales;
CREATE TRIGGER trg_auditar_productos_digitales
    AFTER INSERT OR UPDATE OR DELETE ON public.ca_productos_digitales
    FOR EACH ROW EXECUTE FUNCTION public.fn_auditar_cambios(
        'id_producto_digital', 'precio_venta', 'nombre', 'duracion_dias', 'activo'
    );

-- --- Inventario: stock ---
-- Nota: las ventas mueven stock constantemente y ya quedan registradas en
-- `movimientos_inventario` y en `ventas`. Aqui se vigila igualmente porque el
-- ajuste manual de stock es justo lo que hoy no deja rastro.
DROP TRIGGER IF EXISTS trg_marcar_inventario ON public.inventario;
CREATE TRIGGER trg_marcar_inventario
    BEFORE UPDATE ON public.inventario
    FOR EACH ROW EXECUTE FUNCTION public.fn_marcar_actualizacion();

DROP TRIGGER IF EXISTS trg_auditar_inventario ON public.inventario;
CREATE TRIGGER trg_auditar_inventario
    AFTER INSERT OR UPDATE OR DELETE ON public.inventario
    FOR EACH ROW EXECUTE FUNCTION public.fn_auditar_cambios(
        'id_inventario', 'stock_actual', 'stock_minimo', 'stock_maximo', 'activo'
    );


-- -----------------------------------------------------------------------------
-- 7. Vista de consulta
-- -----------------------------------------------------------------------------
-- Para no tener que unir con usuarios cada vez que se quiera revisar algo.

CREATE OR REPLACE VIEW public.v_auditoria AS
SELECT
    a.id_auditoria,
    a.fecha,
    a.tabla,
    a.id_registro,
    a.campo,
    a.valor_anterior,
    a.valor_nuevo,
    a.operacion,
    a.id_usuario,
    COALESCE(u.nombre_completo, '(fuera del POS: ' || a.db_usuario || ')') AS usuario,
    u.rol,
    a.aplicacion
FROM public.auditoria a
LEFT JOIN public.usuarios u ON u.id_usuario = a.id_usuario
ORDER BY a.fecha DESC;

COMMENT ON VIEW public.v_auditoria IS
    'Auditoria legible. Ejemplo: SELECT * FROM v_auditoria WHERE campo = ''precio_venta'';';


-- -----------------------------------------------------------------------------
-- 8. Permisos
-- -----------------------------------------------------------------------------
-- La auditoria no se edita ni se borra: solo se consulta. Ni siquiera el POS
-- debe poder alterarla; quien escribe es el trigger, que corre como definer.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.auditoria FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.auditoria FROM anon, authenticated;
GRANT SELECT ON public.auditoria  TO authenticated, service_role;
GRANT SELECT ON public.v_auditoria TO authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE public.auditoria_id_auditoria_seq TO service_role;

-- Refrescar el cache de esquema de PostgREST para que la API vea lo nuevo.
NOTIFY pgrst, 'reload schema';
