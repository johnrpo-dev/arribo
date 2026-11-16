"""Trayecto de un servicio: de dónde sale el vehículo, a dónde llega y para cuándo.

Un servicio no tiene origen ni destino propios: usa los de su solicitud. El regreso de un evento
(el servicio enlazado a su ida) va al revés, del destino al origen de la solicitud, y su hora es la
fecha de regreso de la solicitud, no la hora programada de la ida (`QUESTIONS.md`, 1a-07). Y no
empieza hasta que la ida esté entregada (`regreso_bloqueado`).
"""
from datetime import datetime

from nucleo.estados import Estado

# Pasos del regreso que esperan a que la ida esté entregada (`regreso_bloqueado`).
PASOS_QUE_ESPERAN_LA_IDA = frozenset({Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO})


def puntos_del_servicio[T](es_regreso: bool, origen: T, destino: T) -> tuple[T, T]:
    """(dónde se recoge, dónde se entrega). Sirve para direcciones, ubicaciones y contactos."""
    return (destino, origen) if es_regreso else (origen, destino)


def hora_programada(
    es_regreso: bool, programada_para: datetime | None, fecha_regreso: datetime | None
) -> datetime | None:
    """Para cuándo es el servicio; None es inmediato."""
    return fecha_regreso if es_regreso else programada_para


def regreso_bloqueado(es_regreso: bool, ida_entregada: bool, destino: Estado | str) -> bool:
    """¿El regreso todavía no puede avanzar a `destino`?

    Un regreso no empieza hasta que su ida esté entregada: no se recoge en el destino un vehículo
    que todavía no ha llegado allá (decisión del dueño, 2026-11-15). Bloquea los pasos que lo hacen
    avanzar (En camino, Recogido, Entregado). La Novedad no: es un aviso de lo que pasa y se puede
    reportar siempre. Si la ida se cancela, el regreso queda bloqueado hasta que logística lo
    cancele (`QUESTIONS.md`).
    """
    return es_regreso and not ida_entregada and Estado(destino) in PASOS_QUE_ESPERAN_LA_IDA
