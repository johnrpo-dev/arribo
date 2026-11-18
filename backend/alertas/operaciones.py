"""Abrir y resolver alertas. Quien necesita avisar a logística llama a `abrir_alerta`."""
import uuid
from dataclasses import dataclass

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


# Las alertas abiertas que se muestran en el tablero de inicio.
LIMITE_TABLERO = 50


@dataclass(frozen=True)
class AlertaEnTablero:
    alerta: Alerta
    solicitud_id: int | None = None  # a qué solicitud lleva (evento o servicio)
    documento: object | None = None  # el documento al que apunta (documento por vencer)


def alertas_para_tablero(limite: int = LIMITE_TABLERO) -> list[AlertaEnTablero]:
    """Alertas abiertas, la más reciente primero, con la solicitud o el documento a que llevan.

    Una alerta que apunta a un evento de estado o a un servicio lleva a su solicitud; una de
    documento, a ese documento; una que apunta a un conductor no lleva a ninguna parte. Una
    consulta por tipo de registro.
    """
    from documentos.models import Documento
    from solicitudes.models import EventoEstado, Servicio

    alertas = list(
        alertas_abiertas().select_related("tipo_registro").order_by("-creada_en", "-pk")[:limite]
    )

    def ids_de(modelo, convertir=str):
        tipo = ContentType.objects.get_for_model(modelo).pk
        ids = {a.pk: convertir(a.registro_id) for a in alertas if a.tipo_registro_id == tipo}
        return {k: v for k, v in ids.items() if v is not None}

    eventos = ids_de(EventoEstado, _uuid)
    servicios = ids_de(Servicio, _entero)
    documentos = ids_de(Documento, _entero)
    solicitud_de_evento = dict(
        EventoEstado.objects.filter(pk__in=eventos.values()).values_list(
            "pk", "servicio__solicitud_id"
        )
    ) if eventos else {}
    solicitud_de_servicio = dict(
        Servicio.objects.filter(pk__in=servicios.values()).values_list("pk", "solicitud_id")
    ) if servicios else {}
    documento = (
        Documento.objects.select_related("tipo", "grua", "conductor").in_bulk(documentos.values())
        if documentos
        else {}
    )
    return [
        AlertaEnTablero(
            a,
            solicitud_de_evento.get(eventos.get(a.pk))
            or solicitud_de_servicio.get(servicios.get(a.pk)),
            documento.get(documentos.get(a.pk)),
        )
        for a in alertas
    ]


def _entero(texto: str) -> int | None:
    return int(texto) if texto.isdigit() else None


def _uuid(texto: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(texto)
    except ValueError:
        return None
