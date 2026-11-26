"""Capacidad de la grúa.

- Al recoger: nunca más vehículos montados que puestos (`verificar_recogida`).
- Al marcar En camino: los servicios que el conductor tiene iniciados y sin finalizar
  (`nucleo.estados.en_curso`) no pasan de los puestos de la grúa (`verificar_inicio`). Se le
  pueden asignar más servicios que puestos; los toma uno tras otro, terminando antes.
"""
from collections.abc import Sequence


class CapacidadExcedida(Exception):
    def __init__(self, capacidad: int, pendientes_de_entregar: Sequence[str]):
        self.capacidad = capacidad
        # Lo que la app le muestra al conductor: qué le falta marcar como Entregado.
        self.pendientes_de_entregar = list(pendientes_de_entregar)
        super().__init__(
            f"La grúa lleva {len(self.pendientes_de_entregar)} de {capacidad} vehículos"
        )


def verificar_recogida(capacidad: int, servicios_a_bordo: Sequence[str]) -> None:
    """Se llama antes de marcar Recogido. `servicios_a_bordo` son los que cumplen a_bordo()."""
    if capacidad < 1:
        raise ValueError("La capacidad de una grúa es al menos 1")
    if len(servicios_a_bordo) >= capacidad:
        raise CapacidadExcedida(capacidad, servicios_a_bordo)


class InicioExcedido(Exception):
    """El conductor ya tiene tantos servicios iniciados sin finalizar como puestos tiene la grúa.
    `sin_finalizar` es lo que se le muestra: los servicios que debe terminar primero."""

    def __init__(self, capacidad: int, sin_finalizar: Sequence[str]):
        self.capacidad = capacidad
        self.sin_finalizar = list(sin_finalizar)
        super().__init__(mensaje_de_inicio_excedido(capacidad, self.sin_finalizar))


def verificar_inicio(capacidad: int, en_curso: Sequence[str]) -> None:
    """Se llama antes de marcar En camino. `en_curso` son los OTROS servicios del mismo conductor
    que cumplen en_curso(); `capacidad`, la de la grúa del servicio que se inicia."""
    if capacidad < 1:
        raise ValueError("La capacidad de una grúa es al menos 1")
    if len(en_curso) >= capacidad:
        raise InicioExcedido(capacidad, en_curso)


def mensaje_de_inicio_excedido(capacidad: int, sin_finalizar: Sequence[str]) -> str:
    """El bloqueo en palabras del dueño, con los servicios que faltan por terminar."""
    cuales = ", ".join(sin_finalizar)
    cuantos = len(sin_finalizar)
    if capacidad == 1 and cuantos == 1:
        return (
            f"Tiene un servicio iniciado y no se ha finalizado: {cuales}. Debe terminarlo para "
            "tomar el siguiente."
        )
    puestos = "1 puesto" if capacidad == 1 else f"{capacidad} puestos"
    sobran = cuantos - capacidad + 1
    termine = "Termine uno" if sobran == 1 else f"Termine {sobran}"
    return (
        f"La grúa tiene {puestos} y ya tiene {cuantos} servicios iniciados sin finalizar: "
        f"{cuales}. {termine} para tomar el siguiente."
    )
