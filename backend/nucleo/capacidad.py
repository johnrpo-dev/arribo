"""Capacidad de la grúa: nunca más vehículos montados que puestos."""
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
