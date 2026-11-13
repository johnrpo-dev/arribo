"""Abrir y resolver alertas. Quien necesita avisar a logística llama a `abrir_alerta`."""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import Alerta, TipoAlerta


def abrir_alerta(tipo, registro, mensaje: str) -> Alerta:
    """Abre una alerta del tipo dado que apunta a `registro` (una instancia ya guardada).

    Es idempotente por (tipo, registro) mientras siga abierta: si ya hay una, devuelve esa, sin
    cambiarle el mensaje. Una alerta resuelta no cuenta: lo mismo puede volver a alertar. La
    unicidad la garantiza la base (`alerta_una_abierta_por_registro`), también si dos peticiones
    la abren a la vez.
    """
    if registro.pk is None:
        raise ValueError("La alerta apunta a un registro ya guardado.")
    alerta, _ = Alerta.objects.get_or_create(
        tipo=TipoAlerta(tipo).value,
        tipo_registro=ContentType.objects.get_for_model(registro),
        registro_id=str(registro.pk),
        resuelta_en__isnull=True,
        defaults={"mensaje": mensaje},
    )
    return alerta


def resolver_alerta(alerta, *, por) -> Alerta:
    """Marca la alerta como resuelta, con quién y cuándo. Resolverla dos veces no cambia nada:
    queda quien la resolvió primero."""
    with transaction.atomic():
        guardada = Alerta.objects.select_for_update().get(pk=getattr(alerta, "pk", alerta))
        if guardada.abierta:
            guardada.resuelta_en = timezone.now()
            guardada.resuelta_por = por
            guardada.save(update_fields=["resuelta_en", "resuelta_por"])
    return guardada


def alertas_abiertas(registro=None, tipo=None):
    """Las alertas sin resolver, opcionalmente solo las de un registro o las de un tipo."""
    alertas = Alerta.objects.filter(resuelta_en__isnull=True)
    if registro is not None:
        alertas = alertas.filter(
            tipo_registro=ContentType.objects.get_for_model(registro), registro_id=str(registro.pk)
        )
    if tipo is not None:
        alertas = alertas.filter(tipo=TipoAlerta(tipo).value)
    return alertas
