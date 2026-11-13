"""Qué le falta a una solicitud para dejar de ser borrador y quedar abierta.

Obligatorios (supuesto anunciado al dueño en QUESTIONS.md, pregunta de la 1a-04): solicitante,
tipo de servicio, origen y al menos un vehículo; el destino es obligatorio en traslado y evento, y
opcional en desvare. Un evento además debe responder si tiene regreso (la base lo exige a toda
solicitud abierta de evento). La placa o el VIN no se exigen aquí: se exigen al recoger
(`validar_identificacion`), y el momento configurable es de la tarea 1a-07.

Python puro: lo usan el formulario del panel y la vista de detalle.
"""
from enum import StrEnum

from nucleo.tipos import TipoServicio


class Faltante(StrEnum):
    SOLICITANTE = "solicitante"
    TIPO = "tipo"
    ORIGEN = "origen"
    DESTINO = "destino"
    VEHICULO = "vehiculo"
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
) -> list[Faltante]:
    """Lo que falta, en el orden del formulario. Lista vacía = la solicitud puede quedar abierta."""
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
