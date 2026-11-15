"""Receptores de las señales de `solicitudes`. Se conectan en `ApiConfig.ready()`.

A diferencia de los de `alertas` y `cobros`, este no deja que su falla deshaga la operación: un
aviso push es un aviso, y la asignación vale aunque no se pueda encolar. Corre en su propio punto
de restauración (savepoint): si algo falla, se deshace solo lo del aviso y queda en el registro.
"""
import logging

from django.db import transaction

from . import notificaciones

registro = logging.getLogger(__name__)


def encolar_avisos_push(sender, servicio, conductor_anterior=None, **kwargs):
    try:
        with transaction.atomic():
            notificaciones.encolar_avisos_de_asignacion(servicio, conductor_anterior)
    except Exception:  # noqa: BLE001
        registro.exception(
            "No se pudieron encolar los avisos push del servicio %s; la asignación sigue.",
            servicio.pk,
        )
