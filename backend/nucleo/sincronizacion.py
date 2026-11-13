"""Aplicación de eventos que llegan de la app del conductor.

Reglas:
- Un evento se aplica una sola vez aunque llegue repetido (idempotencia por id).
- Lo que el conductor hizo físicamente nunca se rechaza ni se descarta. Si ya no
  encaja (servicio cancelado, reasignado, salto de estado), se devuelve CONFLICTO:
  quien llama guarda el evento igual y abre una alerta para logística.
- Desde la app solo llegan los cuatro botones del conductor (DESTINOS_DESDE_LA_APP).
  Cualquier otro destino (cancelar, asignar) es de logística: también es CONFLICTO.
- El orden lo da la secuencia del dispositivo, no su reloj (puede estar mal puesto).
- Todo conflicto lleva su motivo (`Motivo`), con un texto legible (`DETALLE`) para el
  conductor y para la alerta de logística.
- Un id ya guardado que vuelve con otro contenido (otro servicio, destino, secuencia o
  conductor) no es un reenvío: no se aplica ni pisa al guardado (`es_reenvio`).
"""
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nucleo.estados import Estado, Servicio, puede_transicionar, transicionar

# Los cuatro botones de la app del conductor.
DESTINOS_DESDE_LA_APP = frozenset(
    {Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO, Estado.NOVEDAD}
)


class Resultado(StrEnum):
    APLICADO = "aplicado"
    DUPLICADO = "duplicado"
    CONFLICTO = "conflicto"
    # No se guardó porque no se puede guardar (no es un toque válido de la app): id reutilizado
    # con otro contenido, servicio que no existe o datos ilegibles. Se avisa a logística.
    RECHAZADO = "rechazado"
    # No se guardó por una falla del servidor: el celular lo conserva y lo reenvía.
    REINTENTAR = "reintentar"


class Motivo(StrEnum):
    """Por qué un evento no se aplicó."""

    # Conflictos: el evento se guarda y abre una alerta.
    DESTINO_NO_PERMITIDO = "destino_no_permitido"
    SERVICIO_NO_ASIGNADO = "servicio_no_asignado"
    SERVICIO_CANCELADO = "servicio_cancelado"
    SERVICIO_ENTREGADO = "servicio_entregado"
    NOVEDAD_ABIERTA = "novedad_abierta"
    SALTO_DE_ESTADO = "salto_de_estado"
    NOVEDAD_SIN_MOTIVO = "novedad_sin_motivo"
    IDENTIFICACION_INCOMPLETA = "identificacion_incompleta"
    # Rechazos: el evento no se puede guardar.
    ID_REUTILIZADO = "id_reutilizado"
    SERVICIO_DESCONOCIDO = "servicio_desconocido"
    DATOS_INVALIDOS = "datos_invalidos"
    # Reintentos: el evento no se guardó; el celular lo reenvía.
    ERROR_DEL_SERVIDOR = "error_del_servidor"
    ESPERA_EVENTO_ANTERIOR = "espera_evento_anterior"


MOTIVOS_DE_CONFLICTO = frozenset(
    {
        Motivo.DESTINO_NO_PERMITIDO,
        Motivo.SERVICIO_NO_ASIGNADO,
        Motivo.SERVICIO_CANCELADO,
        Motivo.SERVICIO_ENTREGADO,
        Motivo.NOVEDAD_ABIERTA,
        Motivo.SALTO_DE_ESTADO,
        Motivo.NOVEDAD_SIN_MOTIVO,
        Motivo.IDENTIFICACION_INCOMPLETA,
    }
)
MOTIVOS_DE_RECHAZO = frozenset(
    {Motivo.ID_REUTILIZADO, Motivo.SERVICIO_DESCONOCIDO, Motivo.DATOS_INVALIDOS}
)

DETALLE = {
    Motivo.DESTINO_NO_PERMITIDO: "Ese cambio de estado no se hace desde la app.",
    Motivo.SERVICIO_NO_ASIGNADO: "El servicio ya no está asignado a este conductor.",
    Motivo.SERVICIO_CANCELADO: "El servicio ya estaba cancelado.",
    Motivo.SERVICIO_ENTREGADO: "El servicio ya estaba entregado.",
    Motivo.NOVEDAD_ABIERTA: "El servicio tiene una novedad abierta que logística debe resolver.",
    Motivo.SALTO_DE_ESTADO: "El estado no es el que sigue al que tenía el servicio.",
    Motivo.NOVEDAD_SIN_MOTIVO: "La novedad llegó sin motivo.",
    Motivo.IDENTIFICACION_INCOMPLETA: "Al vehículo le falta la placa o el VIN para recogerlo.",
    Motivo.ID_REUTILIZADO: "Ese id ya se usó en un evento distinto.",
    Motivo.SERVICIO_DESCONOCIDO: "El servicio no existe.",
    Motivo.DATOS_INVALIDOS: "El evento llegó con datos que no se pueden leer.",
    Motivo.ERROR_DEL_SERVIDOR: "El servidor no pudo guardar el evento. Se enviará de nuevo.",
    Motivo.ESPERA_EVENTO_ANTERIOR: "Espera a un evento anterior del mismo servicio que no se "
    "pudo guardar. Se enviará de nuevo.",
}


@dataclass(frozen=True)
class Evento:
    id: str  # UUID generado en el celular
    servicio_id: str
    conductor_id: str
    destino: Estado
    secuencia: int  # contador creciente por dispositivo
    hora_dispositivo: datetime
    motivo: str | None = None


@dataclass(frozen=True)
class Decision:
    servicio: Servicio  # como queda; igual al recibido si el evento no se aplica
    resultado: Resultado
    motivo: Motivo | None = None  # solo en un conflicto


def motivo_de_conflicto(
    servicio: Servicio, conductor_asignado: str | None, evento: Evento
) -> Motivo | None:
    """Por qué el evento no encaja en el servicio, o None si se puede aplicar."""
    if evento.destino not in DESTINOS_DESDE_LA_APP:
        return Motivo.DESTINO_NO_PERMITIDO
    if evento.conductor_id != conductor_asignado:
        return Motivo.SERVICIO_NO_ASIGNADO
    if not puede_transicionar(servicio, evento.destino):
        if servicio.estado == Estado.CANCELADO:
            return Motivo.SERVICIO_CANCELADO
        if servicio.estado == Estado.ENTREGADO:
            return Motivo.SERVICIO_ENTREGADO
        if servicio.estado == Estado.NOVEDAD:
            return Motivo.NOVEDAD_ABIERTA
        return Motivo.SALTO_DE_ESTADO
    if evento.destino == Estado.NOVEDAD and not (evento.motivo or "").strip():
        return Motivo.NOVEDAD_SIN_MOTIVO
    return None


def decidir(
    servicio: Servicio,
    conductor_asignado: str | None,
    evento: Evento,
    ids_ya_aplicados: Collection[str],
) -> Decision:
    if evento.id in ids_ya_aplicados:
        return Decision(servicio, Resultado.DUPLICADO)
    motivo = motivo_de_conflicto(servicio, conductor_asignado, evento)
    if motivo is not None:
        return Decision(servicio, Resultado.CONFLICTO, motivo)
    nuevo = transicionar(servicio, evento.destino, motivo=evento.motivo)
    return Decision(nuevo, Resultado.APLICADO)


def aplicar_evento(
    servicio: Servicio,
    conductor_asignado: str | None,
    evento: Evento,
    ids_ya_aplicados: Collection[str],
) -> tuple[Servicio, Resultado]:
    """Como `decidir`, sin el motivo."""
    decision = decidir(servicio, conductor_asignado, evento, ids_ya_aplicados)
    return decision.servicio, decision.resultado


def es_reenvio(guardado: Evento, recibido: Evento) -> bool:
    """¿El evento que llega con un id ya guardado es el mismo toque, reenviado?

    Cuentan el servicio, el conductor, el destino y la secuencia. La hora del celular no (no es
    de fiar) ni los textos.
    """
    return (
        guardado.id == recibido.id
        and guardado.servicio_id == recibido.servicio_id
        and guardado.conductor_id == recibido.conductor_id
        and guardado.destino == recibido.destino
        and guardado.secuencia == recibido.secuencia
    )


def ordenar(eventos: Iterable[Evento]) -> list[Evento]:
    """Por secuencia del dispositivo; si se repite, en el orden en que llegaron."""
    return sorted(eventos, key=lambda e: (e.conductor_id, e.secuencia))
