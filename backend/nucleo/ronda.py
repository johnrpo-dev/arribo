"""Orden de ronda: en qué orden atiende un conductor los servicios que tiene asignados.

Regla: entre los servicios no terminales de un conductor, el orden es único (lo garantiza la base).
Un servicio asignado o reasignado entra al final de la ronda de su conductor. El operador lo sube o
lo baja un puesto; al moverlo, la ronda se numera de nuevo 1, 2, 3... Cuando un servicio termina o
vuelve a la cola, su puesto queda libre: la ronda puede tener huecos hasta el siguiente movimiento,
pero el orden relativo no cambia.
"""
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class Direccion(StrEnum):
    SUBIR = "subir"
    BAJAR = "bajar"


class MovimientoInvalido(ValueError):
    pass


def siguiente_orden(ordenes: Iterable[int | None]) -> int:
    """El puesto para un servicio que entra a la ronda: después del último."""
    return max((o for o in ordenes if o is not None), default=0) + 1


def mover(ronda: Sequence[T], elemento: T, direccion: Direccion) -> list[T]:
    """La ronda con `elemento` un puesto antes (subir) o después (bajar)."""
    direccion = Direccion(direccion)
    ronda = list(ronda)
    if elemento not in ronda:
        raise MovimientoInvalido("El servicio no está en la ronda de ese conductor.")
    posicion = ronda.index(elemento)
    destino = posicion - 1 if direccion == Direccion.SUBIR else posicion + 1
    if destino < 0:
        raise MovimientoInvalido("El servicio ya es el primero de la ronda.")
    if destino >= len(ronda):
        raise MovimientoInvalido("El servicio ya es el último de la ronda.")
    ronda[posicion], ronda[destino] = ronda[destino], ronda[posicion]
    return ronda


def numerar(ronda: Sequence[T]) -> dict[T, int]:
    """Puesto de cada elemento, desde 1 y sin huecos."""
    return {elemento: puesto for puesto, elemento in enumerate(ronda, start=1)}
