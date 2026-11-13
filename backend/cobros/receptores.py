"""Receptores de las señales de otras apps. Se conectan en `CobrosConfig.ready()`."""
from . import operaciones


def crear_linea_del_servicio_entregado(sender, servicio, actor=None, **kwargs):
    """El servicio acaba de quedar Entregado: nace su línea de cobro en la misma transacción.

    No atrapa errores: si la línea no se puede crear, la transacción del cambio de estado se
    deshace entera.
    """
    operaciones.crear_linea_al_entregar(servicio, actor=actor)
