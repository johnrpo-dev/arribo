"""Aplicación de eventos que llegan de la app del conductor.

Reglas:
- Un evento se aplica una sola vez aunque llegue repetido (idempotencia por id).
- Lo que el conductor hizo físicamente nunca se rechaza ni se descarta. Si ya no
  encaja (servicio cancelado, reasignado, salto de estado), se devuelve CONFLICTO:
  quien llama guarda el evento igual y abre una alerta para logística.
- Desde la app solo llegan los cuatro botones del conductor (DESTINOS_DESDE_LA_APP).
  Cualquier otro destino (cancelar, asignar) es de logística: también es CONFLICTO.
- El orden lo da la secuencia del dispositivo, no su reloj (puede estar mal puesto).
"""
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nucleo.estados import Estado, Servicio, puede_transicionar, transicionar


DESTINOS_DESDE_LA_APP = frozenset(
    {Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO, Estado.NOVEDAD}
)


class Resultado(StrEnum):
    APLICADO = "aplicado"
    DUPLICADO = "duplicado"
    CONFLICTO = "conflicto"


@dataclass(frozen=True)
class Evento:
    id: str  # UUID generado en el celular
    servicio_id: str
    conductor_id: str
    destino: Estado
    secuencia: int  # contador creciente por dispositivo
    hora_dispositivo: datetime
    motivo: str | None = None


def aplicar_evento(
    servicio: Servicio,
    conductor_asignado: str | None,
    evento: Evento,
    ids_ya_aplicados: Collection[str],
) -> tuple[Servicio, Resultado]:
    if evento.id in ids_ya_aplicados:
        return servicio, Resultado.DUPLICADO
    if evento.destino not in DESTINOS_DESDE_LA_APP:
        return servicio, Resultado.CONFLICTO
    if evento.conductor_id != conductor_asignado:
        return servicio, Resultado.CONFLICTO
    if not puede_transicionar(servicio, evento.destino):
        return servicio, Resultado.CONFLICTO
    if evento.destino == Estado.NOVEDAD and not (evento.motivo or "").strip():
        return servicio, Resultado.CONFLICTO
    return transicionar(servicio, evento.destino, motivo=evento.motivo), Resultado.APLICADO


def ordenar(eventos: Iterable[Evento]) -> list[Evento]:
    return sorted(eventos, key=lambda e: (e.conductor_id, e.secuencia))
