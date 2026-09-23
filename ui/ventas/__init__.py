"""
Módulo de ventanas de ventas para HTF POS
"""

from .nueva_venta import NuevaVentaWindow
from .ventas_dia import VentasDiaWindow
from .historial import HistorialVentasWindow
from .cancelar_pagos import CancelarPagosWindow
from .cierre_caja import CierreCajaWindow

__all__ = [
    'NuevaVentaWindow',
    'VentasDiaWindow',
    'HistorialVentasWindow',
    'CancelarPagosWindow',
    'CierreCajaWindow'
]
