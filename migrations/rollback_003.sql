-- =============================================================================
-- ROLLBACK de 003_permisos.sql
-- =============================================================================
-- CUIDADO: al borrar `permisos_usuario` se pierde el rastro de quien otorgo
-- que permiso, cuando y por que, incluido el de los ya revocados.
--
-- El POS NO se rompe al revertir: todos los metodos de permisos detectan
-- PGRST205 / "schema cache" y siguen devolviendo los permisos del rol. Lo que
-- se pierde es la posibilidad de conceder extras a una persona concreta.
-- =============================================================================

-- --- SECCION 1: revocar en bloque (reversible, no pierde datos) -------------
-- Si solo quieres desactivar los permisos especiales sin perder el historial,
-- ejecuta esto y detente aqui.

UPDATE public.permisos_usuario SET activo = false WHERE activo;


-- --- SECCION 2: borrar la tabla (DESTRUCTIVO) -------------------------------
-- Descomenta solo si quieres revertir la migracion por completo.

-- DROP INDEX IF EXISTS public.idx_permisos_usuario_usuario;
-- DROP TABLE IF EXISTS public.permisos_usuario;   -- <-- se pierde el historial

NOTIFY pgrst, 'reload schema';
