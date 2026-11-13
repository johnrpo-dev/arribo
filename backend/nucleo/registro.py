"""Registro de una solicitud: qué le falta para dejar de ser borrador, cuándo lleva servicios de
regreso y cuándo se puede cerrar como no concretada.

Obligatorios (supuesto anunciado al dueño en QUESTIONS.md, pregunta de la 1a-04): solicitante,
tipo de servicio, origen y al menos un vehículo; el destino es obligatorio en traslado y evento, y
opcional en desvare. Si paga una aseguradora, cada vehículo lleva su referencia externa (el número
de caso). Un evento además debe responder si tiene regreso (la base lo exige a toda solicitud
abierta de evento). La placa o el VIN no se exigen aquí: se exigen al asignar o al recoger, según
la configuración (`identificacion.identificacion_exigida`).

Python puro: lo usan el registro del panel y la vista de detalle.
"""
from collections.abc import Iterable
from enum import StrEnum

from nucleo.estados import Estado
from nucleo.tipos import TipoServicio


class Faltante(StrEnum):
    SOLICITANTE = "solicitante"
    TIPO = "tipo"
    ORIGEN = "origen"
    DESTINO = "destino"
    VEHICULO = "vehiculo"
    REFERENCIA_EXTERNA = "referencia_externa"
    RESPUESTA_REGRESO = "respuesta_regreso"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS[self]


_ETIQUETAS = {
    Faltante.SOLICITANTE: "el solicitante",
    Faltante.TIPO: "el tipo de servicio",
    Faltante.ORIGEN: "el origen",
    Faltante.DESTINO: "el destino",
    Faltante.VEHICULO: "al menos un vehículo",
    Faltante.REFERENCIA_EXTERNA: "la referencia externa de la aseguradora en cada vehículo",
    Faltante.RESPUESTA_REGRESO: "la respuesta de si el evento tiene regreso",
}


def destino_obligatorio(tipo: TipoServicio | str | None) -> bool:
    """El destino se exige en traslado y evento; en un desvare puede faltar."""
    if not tipo:
        return True
    return TipoServicio(tipo) != TipoServicio.DESVARE


def faltantes_para_abrir(
    *,
    tiene_solicitante: bool,
    tipo: TipoServicio | str | None,
    origen: str | None,
    destino: str | None,
    vehiculos: int,
    tiene_regreso: bool | None = None,
    paga_aseguradora: bool = False,
    vehiculos_sin_referencia: int = 0,
) -> list[Faltante]:
    """Lo que falta, en el orden del formulario. Lista vacía = la solicitud puede quedar abierta.

    `vehiculos_sin_referencia`: cuántos de los vehículos no tienen referencia externa; solo
    cuenta si paga una aseguradora.
    """
    faltan = []
    if not tiene_solicitante:
        faltan.append(Faltante.SOLICITANTE)
    if not tipo:
        faltan.append(Faltante.TIPO)
    if not (origen or "").strip():
        faltan.append(Faltante.ORIGEN)
    if destino_obligatorio(tipo) and not (destino or "").strip():
        faltan.append(Faltante.DESTINO)
    if vehiculos < 1:
        faltan.append(Faltante.VEHICULO)
    if paga_aseguradora and vehiculos_sin_referencia > 0:
        faltan.append(Faltante.REFERENCIA_EXTERNA)
    if tipo and TipoServicio(tipo) == TipoServicio.EVENTO and tiene_regreso is None:
        faltan.append(Faltante.RESPUESTA_REGRESO)
    return faltan


def describir_faltantes(faltantes: list[Faltante]) -> str:
    """Frase para la pantalla, por ejemplo: el origen, el destino y al menos un vehículo.

    Vacía si no falta nada.
    """
    etiquetas = [f.etiqueta for f in faltantes]
    if len(etiquetas) <= 1:
        return "".join(etiquetas)
    return f"{', '.join(etiquetas[:-1])} y {etiquetas[-1]}"


def crea_regreso(tipo: TipoServicio | str | None, tiene_regreso: bool | None) -> bool:
    """Un evento con regreso lleva, por cada vehículo, un servicio de regreso (destino → origen)."""
    return bool(tipo) and TipoServicio(tipo) == TipoServicio.EVENTO and tiene_regreso is True


class CierreNoPermitido(ValueError):
    """La solicitud no se puede cerrar como no concretada."""


def verificar_cierre_no_concretada(
    *,
    ya_no_concretada: bool,
    estados: Iterable[Estado],
    alguno_fue_asignado: bool,
    motivo: str | None,
) -> None:
    """Una solicitud se cierra como no concretada (nunca se aceptó) solo si ningún servicio se
    asignó nunca: ni ahora ni antes (un servicio que se asignó y volvió a la cola o se canceló
    ya movió una grúa). Exige motivo. Lanza CierreNoPermitido si no se puede.
    """
    if ya_no_concretada:
        raise CierreNoPermitido("La solicitud ya está cerrada como no concretada.")
    nunca_asignados = {Estado.PENDIENTE_ASIGNAR, Estado.CANCELADO}
    if alguno_fue_asignado or any(Estado(e) not in nunca_asignados for e in estados):
        raise CierreNoPermitido(
            "Un servicio de esta solicitud ya fue asignado: no se cierra como no concretada; "
            "sus servicios se cancelan con motivo."
        )
    if not (motivo or "").strip():
        raise CierreNoPermitido("Elija el motivo por el que no se concretó.")
