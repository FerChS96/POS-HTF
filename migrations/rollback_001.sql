-- =============================================================================
-- rollback_001.sql
-- Revierte migrations/001_crear_venta_pos.sql.
--
-- Al eliminar la funcion, el POS deja de encontrarla (PostgREST devuelve
-- PGRST202 / "schema cache") y `create_sale` cae automaticamente al camino
-- Python endurecido. El POS sigue vendiendo; solo se pierde la garantia
-- transaccional real.
-- =============================================================================

DROP FUNCTION IF EXISTS public.crear_venta_pos(
    integer, jsonb, numeric, numeric, numeric, numeric, integer, integer,
    text, text, text, text, timestamptz
);

NOTIFY pgrst, 'reload schema';
