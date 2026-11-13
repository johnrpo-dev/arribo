"""Guardar una foto de evidencia que sube la app del conductor. Reglas en `nucleo/evidencia.py`.

- El id lo genera el celular y es la llave primaria: la misma foto subida otra vez no se duplica
  ni reemplaza a la guardada. El mismo id con otro contenido u otros datos es un error.
- La foto puede llegar antes que su evento. Se guarda igual, sin evento y con el id que el celular
  anunció; `solicitudes/operaciones.py` la enlaza cuando el evento llega. Las dos operaciones
  bloquean la fila del servicio, así que no se cruzan: o la foto ve el evento, o el evento ve la foto.
- Solo la sube un conductor que tiene o tuvo el servicio (está asignado a él o hay un evento suyo
  en su historial). La foto de un conductor al que le reasignaron el servicio mientras estaba sin
  señal se guarda: es evidencia de lo que hizo.
- El archivo llega ya en disco (un temporal que escribió la vista por partes) y aquí solo se mueve
  a `MEDIA_ROOT`, con el nombre que pone el servidor.
"""
import uuid
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from nucleo.estados import Estado
from nucleo.evidencia import Foto, misma_foto, se_enlaza

from .models import EventoEstado, Evidencia, Servicio


class ServicioAjeno(Exception):
    """El servicio no existe o nunca fue de este conductor."""


class EvidenciaDistinta(Exception):
    """Ya hay una evidencia con ese id y no es esta foto (otro contenido u otros datos)."""


@dataclass(frozen=True)
class Subida:
    evidencia: Evidencia
    nueva: bool  # False: ya estaba guardada y no se tocó


def guardar_foto(*, id, servicio_id, conductor, evento_id, tipo, archivo, sha256, tamano) -> Subida:
    """Guarda la foto una sola vez. `archivo` es un archivo subido de Django que ya está en disco."""
    evidencia_id = uuid.UUID(str(id))
    evento_id = uuid.UUID(str(evento_id))
    recibida = Foto(
        servicio_id=str(servicio_id),
        conductor_id=str(conductor.pk),
        evento_id=str(evento_id),
        tipo=tipo,
        sha256=sha256,
    )
    with transaction.atomic():
        servicio = (
            Servicio.objects.select_for_update(of=("self",)).filter(pk=servicio_id).first()
        )
        if servicio is None or not _tiene_o_tuvo(servicio, conductor):
            raise ServicioAjeno()
        guardada = Evidencia.objects.filter(pk=evidencia_id).first()
        if guardada is not None:
            return _repetida(guardada, recibida)
        evento = EventoEstado.objects.filter(pk=evento_id).first()
        evidencia = Evidencia(
            id=evidencia_id,
            servicio=servicio,
            evento=evento if evento is not None and _le_corresponde(recibida, evento) else None,
            evento_esperado=evento_id,
            tipo=tipo,
            archivo=archivo,
            sha256=sha256,
            tamano=tamano,
            subida_por=conductor,
        )
        try:
            with transaction.atomic():
                evidencia.save(force_insert=True)
        except IntegrityError:
            # Otra petición guardó el mismo id a la vez (con otro servicio, o no habría pasado el
            # bloqueo): el archivo que esta alcanzó a mover sobra.
            if evidencia.archivo.name:
                evidencia.archivo.storage.delete(evidencia.archivo.name)
            guardada = Evidencia.objects.filter(pk=evidencia_id).first()
            if guardada is None:
                raise
            return _repetida(guardada, recibida)
    return Subida(evidencia, nueva=True)


def _tiene_o_tuvo(servicio: Servicio, conductor) -> bool:
    if servicio.conductor_id == conductor.pk:
        return True
    return EventoEstado.objects.filter(servicio=servicio, conductor=conductor).exists()


def _le_corresponde(foto: Foto, evento: EventoEstado) -> bool:
    return se_enlaza(
        foto,
        servicio_del_evento=str(evento.servicio_id),
        conductor_del_evento=None if evento.conductor_id is None else str(evento.conductor_id),
        destino=Estado(evento.destino),
    )


def _repetida(guardada: Evidencia, recibida: Foto) -> Subida:
    if not misma_foto(guardada.como_nucleo(), recibida):
        raise EvidenciaDistinta()
    return Subida(guardada, nueva=False)
