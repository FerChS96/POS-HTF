"""
Catálogo de permisos del POS HTF.

CONTRATO COMPARTIDO. Este módulo es la única fuente de verdad sobre qué
permisos existen, cuáles trae cada rol de base y cuáles se pueden otorgar de
forma puntual a una persona concreta. La UI, la capa de datos y las pruebas
leen de aquí; nadie escribe cadenas de permiso a mano.

MODELO
    permisos efectivos = permisos base del rol + permisos otorgados a esa persona

    - Los permisos base vienen del rol y no se pueden quitar individualmente.
    - Los permisos otorgados son extras que un administrador concede a una
      recepcionista concreta (por ejemplo, que Balbina pueda mover inventario).
    - Los permisos marcados como NO otorgables jamás salen de su rol base.
      `precios.actualizar` es el caso principal: solo administración.

ALCANCE REAL
    Esto es control de acceso a nivel de aplicación. Mientras la base no tenga
    RLS activo y la llave de servicio viaje dentro del ejecutable, alguien con
    el .exe puede saltarse estas comprobaciones hablando directo con Supabase.
    Sirve para que el personal no haga de más por error o por descuido, no
    para detener a quien quiera saltárselo a propósito. El cierre de verdad es
    RLS (ver migrations/).
"""

# --- Identificadores de permiso -------------------------------------------
# Formato: '<area>.<accion>'. Se usan como constantes, nunca como literales.

VENTAS_REGISTRAR        = 'ventas.registrar'
VENTAS_CANCELAR         = 'ventas.cancelar'
CAJA_ABRIR_TURNO        = 'caja.abrir_turno'
CAJA_CERRAR_TURNO       = 'caja.cerrar_turno'
CAJA_CERRAR_FUERA_HORA  = 'caja.cerrar_fuera_horario'

INVENTARIO_VER          = 'inventario.ver'
INVENTARIO_ACTUALIZAR   = 'inventario.actualizar'

PRECIOS_ACTUALIZAR      = 'precios.actualizar'
CATALOGO_ALTA_PRODUCTO  = 'catalogo.alta_producto'

MIEMBROS_VER            = 'miembros.ver'
MIEMBROS_EDITAR         = 'miembros.editar'

USUARIOS_GESTIONAR      = 'usuarios.gestionar'
PERMISOS_GESTIONAR      = 'permisos.gestionar'


# --- Descripciones legibles (las muestra la UI) ----------------------------

DESCRIPCIONES = {
    VENTAS_REGISTRAR:       'Registrar ventas en el punto de venta',
    VENTAS_CANCELAR:        'Cancelar ventas ya registradas',
    CAJA_ABRIR_TURNO:       'Abrir turno de caja',
    CAJA_CERRAR_TURNO:      'Cerrar turno de caja',
    CAJA_CERRAR_FUERA_HORA: 'Cerrar caja fuera del horario del turno',
    INVENTARIO_VER:         'Consultar el inventario',
    INVENTARIO_ACTUALIZAR:  'Registrar entradas y salidas de inventario',
    PRECIOS_ACTUALIZAR:     'Modificar precios de venta',
    CATALOGO_ALTA_PRODUCTO: 'Dar de alta productos nuevos',
    MIEMBROS_VER:           'Consultar miembros',
    MIEMBROS_EDITAR:        'Editar datos de miembros',
    USUARIOS_GESTIONAR:     'Crear y administrar cuentas de acceso',
    PERMISOS_GESTIONAR:     'Otorgar permisos especiales',
}

TODOS = tuple(DESCRIPCIONES.keys())


# --- Permisos base por rol -------------------------------------------------

PERMISOS_POR_ROL = {
    'recepcionista': frozenset({
        VENTAS_REGISTRAR,
        CAJA_ABRIR_TURNO,
        CAJA_CERRAR_TURNO,
        INVENTARIO_VER,
        MIEMBROS_VER,
    }),
    'administrador': frozenset(TODOS),
    'sistemas': frozenset(TODOS),
}


# --- Qué se puede otorgar de forma puntual ---------------------------------
# Solo estos permisos pueden concederse a una recepcionista concreta desde el
# módulo de permisos especiales. El resto queda atado al rol.

OTORGABLES = frozenset({
    INVENTARIO_ACTUALIZAR,
    VENTAS_CANCELAR,
    MIEMBROS_EDITAR,
    CATALOGO_ALTA_PRODUCTO,
})

# Nunca otorgables. Se listan de forma explícita para que quede por escrito el
# porqué, y para que una prueba lo verifique en vez de confiar en la memoria.
NO_OTORGABLES = {
    PRECIOS_ACTUALIZAR:
        'Cambiar precios afecta directamente los ingresos del negocio. '
        'Queda reservado a administración.',
    USUARIOS_GESTIONAR:
        'Quien crea cuentas puede crearse uno con más permisos.',
    PERMISOS_GESTIONAR:
        'Quien otorga permisos podría otorgarse cualquiera a sí mismo.',
    CAJA_CERRAR_FUERA_HORA:
        'Requiere autorización explícita de un administrador en el momento.',
}


# --- Utilidades ------------------------------------------------------------

def permisos_base_de(rol) -> frozenset:
    """Permisos que trae un rol por sí mismo."""
    return PERMISOS_POR_ROL.get((rol or '').strip().lower(), frozenset())


def es_otorgable(permiso) -> bool:
    """Si un permiso puede concederse de forma puntual a una persona."""
    return permiso in OTORGABLES


def motivo_no_otorgable(permiso) -> str:
    """Por qué un permiso no es otorgable (cadena vacía si sí lo es)."""
    return NO_OTORGABLES.get(permiso, '')


def permisos_efectivos(rol, otorgados=None) -> frozenset:
    """
    Permisos reales de una persona: los de su rol más los que le otorgaron.

    Los otorgados que no estén en OTORGABLES se ignoran, de modo que un
    registro manipulado en la base no pueda conceder algo reservado.
    """
    extras = {p for p in (otorgados or ()) if p in OTORGABLES}
    return permisos_base_de(rol) | extras
