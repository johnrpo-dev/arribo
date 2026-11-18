"""Datos del panel del dueño (1a-19): cómo va la operación y la plata, en una pantalla.

- Servicios del periodo por estado: los de solicitudes abiertas (no borradores ni no concretadas)
  cuya fecha cae en el periodo, en hora de Colombia. La fecha es la hora para la que se programó
  (en un regreso, la fecha de regreso) o, si es inmediato, el día en que se registró la solicitud.
- No concretadas del periodo por motivo: por el día en que se registró la solicitud.
- Por cobrar por pagador: lo pendiente hoy, sin importar el periodo (`nucleo.resumen.por_cobrar`).
- Documentos por vencer o vencidos hoy, de grúas y conductores activos.

Los totales los calcula `nucleo/resumen.py`; aquí solo se buscan los datos. Vive en `panel`
porque junta solicitudes, cobros y documentos, como el tablero.
"""
from datetime import date

from django.db.models import Case, F, When
from django.db.models.functions import TruncDate
from django.utils import timezone

from cobros.models import LineaCobro
from documentos.consultas import por_vencer_o_vencidos
from nucleo.cobro import EstadoCobro, formato_pesos
from nucleo.estados import Estado
from nucleo.resumen import LineaPendiente, contar, por_cobrar, total_por_cobrar
from solicitudes.models import (
    ETIQUETAS_ESTADO,
    EstadoRegistro,
    MotivoNoConcretada,
    Servicio,
    Solicitud,
)

ESTADOS_PENDIENTES_DE_COBRO = (
    EstadoCobro.SIN_VALOR.value,
    EstadoCobro.POR_FACTURAR.value,
    EstadoCobro.FACTURADO.value,
)


def servicios_por_estado(desde: date, hasta: date) -> list[tuple[str, str, int]]:
    """[(estado, etiqueta, cuántos)] de los servicios del periodo, con todos los estados."""
    zona = timezone.get_current_timezone()
    servicios = (
        Servicio.objects.filter(solicitud__estado_registro=EstadoRegistro.ABIERTA)
        .annotate(
            momento=Case(
                When(regreso_de__isnull=False, solicitud__fecha_regreso__isnull=False,
                     then=F("solicitud__fecha_regreso")),
                When(regreso_de__isnull=True, solicitud__programada_para__isnull=False,
                     then=F("solicitud__programada_para")),
                default=F("solicitud__creada_en"),
            ),
            dia=TruncDate("momento", tzinfo=zona),
        )
        .filter(dia__range=(desde, hasta))
    )
    estados = [e.value for e in Estado]
    conteo = contar(servicios.values_list("estado", flat=True), estados)
    return [(e, ETIQUETAS_ESTADO[Estado(e)], n) for e, n in conteo]


def no_concretadas_por_motivo(desde: date, hasta: date) -> list[tuple[str, int]]:
    """[(motivo, cuántas)] de las solicitudes no concretadas registradas en el periodo."""
    zona = timezone.get_current_timezone()
    motivos = (
        Solicitud.objects.filter(estado_registro=EstadoRegistro.NO_CONCRETADA)
        .annotate(dia=TruncDate("creada_en", tzinfo=zona))
        .filter(dia__range=(desde, hasta))
        .values_list("motivo_no_concretada", flat=True)
    )
    conteo = contar(motivos, MotivoNoConcretada.values)
    return [(MotivoNoConcretada(m).label, n) for m, n in conteo]


def cobros_por_pagador():
    """(filas, total) de lo pendiente de cobro por pagador, con los valores ya formateados."""
    lineas = LineaCobro.objects.filter(estado__in=ESTADOS_PENDIENTES_DE_COBRO).values_list(
        "pagador_id", "pagador__nombre", "estado", "valor"
    )
    filas = por_cobrar(LineaPendiente(*fila) for fila in lineas)
    return filas, total_por_cobrar(filas)


def _con_pesos(fila):
    """(fila, por facturar, facturado, total) con los valores como se leen: "$ 180.000"."""
    return (
        fila,
        formato_pesos(fila.valor_por_facturar),
        formato_pesos(fila.valor_facturado),
        formato_pesos(fila.total),
    )


def datos_del_panel(desde: date, hasta: date, hoy: date | None = None) -> dict:
    hoy = hoy or timezone.localdate()
    estados = servicios_por_estado(desde, hasta)
    motivos = no_concretadas_por_motivo(desde, hasta)
    filas, total = cobros_por_pagador()
    return {
        "desde": desde,
        "hasta": hasta,
        "servicios": estados,
        "total_servicios": sum(n for _, _, n in estados),
        "no_concretadas": motivos,
        "total_no_concretadas": sum(n for _, n in motivos),
        "por_cobrar": [_con_pesos(f) for f in filas],
        "total_por_cobrar": _con_pesos(total),
        "documentos": por_vencer_o_vencidos(hoy),
    }
