"""Servicios asignados a un conductor, como los lee la API.

Una sola consulta para toda la lista: el serializador lee vehículo, grúa, solicitud y sus contactos,
y todo viene ya cargado (`select_related`), tenga el conductor 1 o 20 servicios.
"""
from solicitudes.operaciones import consulta_ronda


def asignaciones_de(conductor):
    """Sus servicios no terminales (asignado, en camino, recogido y novedad) en orden de ronda."""
    return consulta_ronda(conductor).select_related(
        "vehiculo",
        "grua",
        "solicitud",
        "solicitud__contacto_origen",
        "solicitud__contacto_destino",
    )
