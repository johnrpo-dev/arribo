"""Fotos de evidencia que sube la app del conductor.

Reglas:
- Solo JPEG (la app comprime la foto antes de subirla) y con un tope de tamaño. El tope es un
  límite técnico del servidor, no una opción del cliente.
- La foto de recogida acompaña al evento Recogido y la de entrega al Entregado. Se enlaza al
  evento solo si es de su mismo servicio y lo tocó el mismo conductor que la subió.
- El id lo genera el celular: subir otra vez la misma foto no la duplica. El mismo id con otro
  contenido u otros datos no es la misma foto: no reemplaza a la guardada.
"""
from dataclasses import dataclass

from nucleo.estados import Estado

TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024  # bytes; una foto comprimida en el celular pesa menos de 1 MB
MARCA_JPEG = b"\xff\xd8\xff"

# Tipo de foto → evento al que acompaña. "soporte" no llega desde la app en la fase 1a.
EVENTO_QUE_ACOMPANA = {"recogida": Estado.RECOGIDO, "entrega": Estado.ENTREGADO}
TIPOS_DESDE_LA_APP = frozenset(EVENTO_QUE_ACOMPANA)


@dataclass(frozen=True)
class Foto:
    servicio_id: str
    conductor_id: str | None  # quien la subió
    evento_id: str  # el evento que el celular dijo que acompaña
    tipo: str
    sha256: str  # huella del contenido, en hexadecimal


def es_jpeg(primeros_bytes: bytes) -> bool:
    """Se mira el contenido, no el nombre ni el tipo que declara el celular."""
    return primeros_bytes[: len(MARCA_JPEG)] == MARCA_JPEG


def excede_el_tamano(tamano: int) -> bool:
    return tamano > TAMANO_MAXIMO_FOTO


def acompana(tipo: str, destino: Estado) -> bool:
    return EVENTO_QUE_ACOMPANA.get(tipo) == destino


def se_enlaza(
    foto: Foto, *, servicio_del_evento: str, conductor_del_evento: str | None, destino: Estado
) -> bool:
    return (
        foto.servicio_id == servicio_del_evento
        and foto.conductor_id is not None
        and foto.conductor_id == conductor_del_evento
        and acompana(foto.tipo, destino)
    )


def misma_foto(guardada: Foto, recibida: Foto) -> bool:
    """¿La que llega con un id ya guardado es un reenvío de la misma foto?"""
    return bool(guardada.sha256) and guardada == recibida
