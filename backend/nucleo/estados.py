"""Máquina de estados operativa de un servicio (vehículo-en-solicitud)."""
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum


class Estado(StrEnum):
    PENDIENTE_ASIGNAR = "pendiente_asignar"
    ASIGNADO = "asignado"
    EN_CAMINO = "en_camino"
    RECOGIDO = "recogido"
    ENTREGADO = "entregado"
    NOVEDAD = "novedad"
    CANCELADO = "cancelado"


class EstadoSolicitud(StrEnum):
    ABIERTA = "abierta"
    EN_CURSO = "en_curso"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"


class Resolucion(StrEnum):
    REANUDAR = "reanudar"
    REASIGNAR = "reasignar"
    CANCELAR = "cancelar"


TERMINALES = frozenset({Estado.ENTREGADO, Estado.CANCELADO})
AVANCE = {
    Estado.PENDIENTE_ASIGNAR: Estado.ASIGNADO,
    Estado.ASIGNADO: Estado.EN_CAMINO,
    Estado.EN_CAMINO: Estado.RECOGIDO,
    Estado.RECOGIDO: Estado.ENTREGADO,
}
NOVEDAD_DESDE = frozenset({Estado.ASIGNADO, Estado.EN_CAMINO, Estado.RECOGIDO})
REASIGNABLE_DESDE = frozenset({Estado.ASIGNADO, Estado.EN_CAMINO})


class TransicionInvalida(Exception):
    pass


@dataclass(frozen=True)
class Servicio:
    estado: Estado = Estado.PENDIENTE_ASIGNAR
    # Solo tiene valor mientras el servicio está en NOVEDAD.
    estado_previo: Estado | None = None


def puede_transicionar(servicio: Servicio, destino: Estado) -> bool:
    actual = servicio.estado
    if actual in TERMINALES:
        return False
    if destino == Estado.CANCELADO:
        return True
    if destino == Estado.NOVEDAD:
        return actual in NOVEDAD_DESDE
    # De una novedad solo se sale con resolver_novedad.
    return AVANCE.get(actual) == destino


def transicionar(servicio: Servicio, destino: Estado, *, motivo: str | None = None) -> Servicio:
    if not puede_transicionar(servicio, destino):
        raise TransicionInvalida(f"No se puede pasar de {servicio.estado} a {destino}")
    if destino in (Estado.CANCELADO, Estado.NOVEDAD) and not (motivo or "").strip():
        raise TransicionInvalida(f"{destino} exige motivo")
    if destino == Estado.NOVEDAD:
        return Servicio(estado=Estado.NOVEDAD, estado_previo=servicio.estado)
    return Servicio(estado=destino)


def reasignar(servicio: Servicio) -> Servicio:
    """Pasar el servicio a otro conductor antes de que el vehículo esté montado."""
    if servicio.estado not in REASIGNABLE_DESDE:
        raise TransicionInvalida(f"No se puede reasignar un servicio en {servicio.estado}")
    return Servicio(estado=Estado.ASIGNADO)


def resolver_novedad(
    servicio: Servicio, resolucion: Resolucion, *, motivo: str | None = None
) -> Servicio:
    if servicio.estado != Estado.NOVEDAD:
        raise TransicionInvalida("El servicio no tiene una novedad abierta")
    if resolucion == Resolucion.REANUDAR:
        return Servicio(estado=servicio.estado_previo)
    if resolucion == Resolucion.REASIGNAR:
        if servicio.estado_previo == Estado.RECOGIDO:
            raise TransicionInvalida("El vehículo está montado: se reanuda o se cancela")
        return Servicio(estado=Estado.PENDIENTE_ASIGNAR)
    if not (motivo or "").strip():
        raise TransicionInvalida("Cancelar exige motivo")
    return replace(servicio, estado=Estado.CANCELADO, estado_previo=None)


def a_bordo(servicio: Servicio) -> bool:
    """El vehículo ocupa un puesto en la grúa (cuenta para la capacidad)."""
    if servicio.estado == Estado.RECOGIDO:
        return True
    return servicio.estado == Estado.NOVEDAD and servicio.estado_previo == Estado.RECOGIDO


def estado_solicitud(estados: Iterable[Estado]) -> EstadoSolicitud:
    """El estado de una solicitud se deriva de sus servicios; nunca se guarda a mano."""
    estados = list(estados)
    if estados and all(e == Estado.CANCELADO for e in estados):
        return EstadoSolicitud.CANCELADA
    if estados and all(e in TERMINALES for e in estados):
        return EstadoSolicitud.COMPLETADA
    en_movimiento = {Estado.EN_CAMINO, Estado.RECOGIDO, Estado.NOVEDAD, Estado.ENTREGADO}
    if any(e in en_movimiento for e in estados):
        return EstadoSolicitud.EN_CURSO
    return EstadoSolicitud.ABIERTA
