-- =============================================================================
-- ROLLBACK de 002_auditoria.sql
-- =============================================================================
-- CUIDADO: al borrar la tabla `auditoria` se pierde TODO el historial de
-- cambios registrado hasta ahora. Si solo quieres desactivar la auditoria sin
-- perder lo acumulado, aplica unicamente la SECCION 1 y detente ahi.
-- =============================================================================

-- --- SECCION 1: desactivar los triggers (reversible, no pierde datos) --------

DROP TRIGGER IF EXISTS trg_auditar_productos_varios     ON public.ca_productos_varios;
DROP TRIGGER IF EXISTS trg_marcar_productos_varios      ON public.ca_productos_varios;
DROP TRIGGER IF EXISTS trg_auditar_productos_digitales  ON public.ca_productos_digitales;
DROP TRIGGER IF EXISTS trg_marcar_productos_digitales   ON public.ca_productos_digitales;
DROP TRIGGER IF EXISTS trg_auditar_inventario           ON public.inventario;
DROP TRIGGER IF EXISTS trg_marcar_inventario            ON public.inventario;


-- --- SECCION 2: borrar todo lo demas (DESTRUCTIVO) --------------------------
-- Descomenta solo si quieres revertir la migracion por completo.

-- DROP VIEW IF EXISTS public.v_auditoria;
-- DROP TABLE IF EXISTS public.auditoria;          -- <-- se pierde el historial
-- DROP FUNCTION IF EXISTS public.fn_auditar_cambios();
-- DROP FUNCTION IF EXISTS public.fn_marcar_actualizacion();
-- DROP FUNCTION IF EXISTS public.app_id_usuario();
--
-- ALTER TABLE public.ca_productos_varios
--     DROP COLUMN IF EXISTS actualizado_por,
--     DROP COLUMN IF EXISTS fecha_actualizacion;
-- ALTER TABLE public.ca_productos_digitales
--     DROP COLUMN IF EXISTS actualizado_por,
--     DROP COLUMN IF EXISTS fecha_actualizacion;
-- ALTER TABLE public.inventario
--     DROP COLUMN IF EXISTS actualizado_por,
--     DROP COLUMN IF EXISTS fecha_actualizacion;

NOTIFY pgrst, 'reload schema';
