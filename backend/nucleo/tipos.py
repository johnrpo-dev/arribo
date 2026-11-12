"""Tipos compartidos por varias apps (tarifas ahora, solicitudes después)."""
from enum import StrEnum


class TipoServicio(StrEnum):
    TRASLADO = "traslado"
    EVENTO = "evento"  # evento o muestra de concesionario
    DESVARE = "desvare"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS[self]


_ETIQUETAS = {
    TipoServicio.TRASLADO: "Traslado",
    TipoServicio.EVENTO: "Evento o muestra de concesionario",
    TipoServicio.DESVARE: "Desvare",
}
