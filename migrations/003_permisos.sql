-- =============================================================================
-- 003 - Permisos otorgados de forma puntual
-- =============================================================================
-- PROBLEMA QUE RESUELVE
--   Hoy el acceso se decide solo por el rol: o eres recepcionista o eres
--   administrador. No hay manera de decir "Balbina si puede mover inventario,
--   pero nadie mas de recepcion". La unica salida era subirla a administrador,
--   lo que de paso le daba precios, usuarios y permisos. Demasiado.
--
-- COMO LO RESUELVE
--   Una tabla de excepciones por persona:
--       permisos efectivos = permisos base del rol + permisos otorgados
--   El catalogo de permisos vive en POS_HTF/database/permisos.py, que es el
--   contrato compartido entre la UI, la capa de datos y las pruebas.
--
-- LA LISTA BLANCA (lo importante de esta migracion)
--   Solo cuatro permisos pueden otorgarse de forma puntual. El CHECK de abajo
--   es copia literal de OTORGABLES en database/permisos.py y es la ULTIMA
--   defensa: aunque alguien escriba en la tabla desde el panel de Supabase o
--   desde un script suelto, Postgres rechaza 'precios.actualizar',
--   'usuarios.gestionar', 'permisos.gestionar' y 'caja.cerrar_fuera_horario'.
--   La aplicacion ya los filtra dos veces (al otorgar y al calcular los
--   permisos efectivos); esto lo cierra tambien a nivel de base.
--
--   Si algun dia se agrega un permiso otorgable en database/permisos.py, hay
--   que agregarlo TAMBIEN aqui con una migracion nueva. Son dos listas que
--   deben viajar juntas; la prueba tests/test_permisos.py lo recuerda.
--
-- REVOCAR NO BORRA
--   Quitar un permiso pone `activo = false`. La fila se queda para conservar
--   el rastro de quien lo otorgo, cuando y por que. Un DELETE borraria esa
--   historia justo cuando mas se necesita (una aclaracion, un faltante).
--
-- ALCANCE REAL
--   Esto es control de acceso a nivel de aplicacion. Mientras no haya RLS y la
--   llave viaje dentro del .exe, quien tenga el ejecutable puede hablarle
--   directo a Supabase y saltarse las comprobaciones del POS. Este CHECK
--   sobrevive a eso (Postgres lo aplica siempre), pero no impide que alguien
--   con la llave inserte una fila valida para si mismo. El cierre de verdad
--   sigue siendo RLS.
--
-- NO ejecutar automaticamente. Aplicar desde el SQL Editor de Supabase.
-- Ver migrations/README.md.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Tabla de permisos otorgados
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.permisos_usuario (
    id_permiso      bigserial    PRIMARY KEY,
    id_usuario      integer      NOT NULL REFERENCES public.usuarios(id_usuario),
    permiso         varchar(64)  NOT NULL,
    -- Quien lo concedio. Si esa cuenta se borrara, preferimos perder el nombre
    -- antes que perder la fila entera, por eso queda NULL-able y sin CASCADE.
    otorgado_por    integer      REFERENCES public.usuarios(id_usuario),
    fecha_otorgado  timestamp without time zone
                    DEFAULT (now() AT TIME ZONE 'America/Mexico_City'),
    -- Revocar = poner en false. NUNCA se borra la fila: es el rastro.
    activo          boolean      NOT NULL DEFAULT true,
    notas           text,

    -- Un permiso por persona. Volver a otorgar algo revocado REACTIVA la fila
    -- existente en vez de crear una segunda; asi no hay dos verdades.
    CONSTRAINT uq_permisos_usuario_persona_permiso UNIQUE (id_usuario, permiso),

    -- LISTA BLANCA. Copia literal de OTORGABLES en database/permisos.py.
    CONSTRAINT chk_permisos_usuario_otorgable CHECK (
        permiso IN (
            'inventario.actualizar',
            'ventas.cancelar',
            'miembros.editar',
            'catalogo.alta_producto'
        )
    )
);

COMMENT ON TABLE public.permisos_usuario IS
    'Permisos extra concedidos a una persona concreta, por encima de los de su rol. '
    'Revocar es activo=false, no DELETE. Catalogo en POS_HTF/database/permisos.py.';

COMMENT ON COLUMN public.permisos_usuario.permiso IS
    'Identificador <area>.<accion>. Restringido por CHECK a la lista OTORGABLES.';

COMMENT ON COLUMN public.permisos_usuario.activo IS
    'false = revocado. La fila se conserva para saber quien lo otorgo y por que.';

COMMENT ON COLUMN public.permisos_usuario.notas IS
    'Por que se otorgo. Texto libre para la aclaracion de despues.';


-- -----------------------------------------------------------------------------
-- 2. Indice
-- -----------------------------------------------------------------------------
-- La pregunta que hace el POS en cada arranque de sesion es siempre la misma:
-- "que permisos extra tiene ESTA persona". El UNIQUE de arriba ya sirve para
-- eso, pero este indice deja explicito el acceso por usuario y sobrevive si
-- algun dia cambia la llave unica.

CREATE INDEX IF NOT EXISTS idx_permisos_usuario_usuario
    ON public.permisos_usuario (id_usuario);


-- -----------------------------------------------------------------------------
-- 3. Permisos de acceso (PostgREST)
-- -----------------------------------------------------------------------------
-- El POS habla por REST con una sola llave. Sin estos GRANT, PostgREST
-- responde PGRST205 / "schema cache" y el POS cae al camino sin tabla: sigue
-- funcionando, pero solo con los permisos del rol.
--
-- No hay DELETE a proposito: revocar es un UPDATE. Cuando se active RLS habra
-- que apretar esto para que solo administracion pueda escribir.

GRANT SELECT, INSERT, UPDATE ON public.permisos_usuario
    TO anon, authenticated, service_role;

GRANT USAGE, SELECT ON SEQUENCE public.permisos_usuario_id_permiso_seq
    TO anon, authenticated, service_role;


-- PostgREST cachea el esquema: forzar recarga para que la tabla sea visible ya.
NOTIFY pgrst, 'reload schema';
