"""Trayecto de un servicio: de dónde sale el vehículo, a dónde llega y para cuándo.

Un servicio no tiene origen ni destino propios: usa los de su solicitud. El regreso de un evento
(el servicio enlazado a su ida) va al revés, del destino al origen de la solicitud, y su hora es la
fecha de regreso de la solicitud, no la hora programada de la ida (`QUESTIONS.md`, 1a-07).
"""
from datetime import datetime


def puntos_del_servicio[T](es_regreso: bool, origen: T, destino: T) -> tuple[T, T]:
    """(dónde se recoge, dónde se entrega). Sirve para direcciones, ubicaciones y contactos."""
    return (destino, origen) if es_regreso else (origen, destino)


def hora_programada(
    es_regreso: bool, programada_para: datetime | None, fecha_regreso: datetime | None
) -> datetime | None:
    """Para cuándo es el servicio; None es inmediato."""
    return fecha_regreso if es_regreso else programada_para
