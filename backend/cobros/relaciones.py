"""Operaciones de la relación de cobro (1a-17): armarla, facturarla, marcarla pagada o descartarla,
y los datos para exportarla. Reglas en `nucleo/relacion.py`; el estado de cada línea lo siguen
cambiando las operaciones de `cobros/operaciones.py`, que dejan su historial.

- La fecha del servicio es la hora en que se marcó Entregado (la del celular si la mandó), en hora
  de Colombia; si no hay Entregado (un cancelado que se marcó cobrable), la de la línea.
- Mientras la relación está armada, sus líneas quedan reservadas: no entran en otra relación ni se
  facturan sueltas. PostgreSQL garantiza que una línea esté reservada en una sola relación.
- Facturar la relación factura cada línea con el mismo número; marcarla pagada marca pagadas las
  líneas que siguen con esa factura (si a una le anularon la factura, se deja y se avisa).
"""
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from nucleo import relacion as reglas
from nucleo.cobro import CobroInvalido, EstadoCobro
from nucleo.estados import Estado
from nucleo.exportacion import DatosRelacion, FilaRelacion
from nucleo.trayecto import puntos_del_servicio
from solicitudes.models import EventoEstado

from . import operaciones
from .models import LineaCobro, LineaEnRelacion, RelacionCobro


def con_fecha_de_servicio(lineas):
    """Anota `fecha_servicio` (fecha en Colombia de la última entrega, o de la línea)."""
    entrega = (
        EventoEstado.objects.filter(
            servicio=OuterRef("servicio"), destino=Estado.ENTREGADO.value
        )
        .order_by("-hora_sincronizacion")
        .annotate(momento=Coalesce("hora_dispositivo", "hora_sincronizacion"))
        .values("momento")[:1]
    )
    return lineas.annotate(
        momento_servicio=Coalesce(Subquery(entrega), "creada_en"),
        fecha_servicio=TruncDate("momento_servicio", tzinfo=timezone.get_current_timezone()),
    )


def _del_rango(pagador, desde, hasta, estado: EstadoCobro):
    return con_fecha_de_servicio(
        LineaCobro.objects.filter(pagador=pagador, estado=estado.value)
    ).filter(fecha_servicio__range=(desde, hasta))


def candidatas(pagador, desde, hasta):
    """Líneas que entrarían hoy: por facturar, del pagador, en el rango y sin otra relación armada."""
    return (
        _del_rango(pagador, desde, hasta, EstadoCobro.POR_FACTURAR)
        .exclude(inclusiones__reservada=True)
        .select_related("servicio__vehiculo", "servicio__solicitud")
        .order_by("fecha_servicio", "servicio_id")
    )


def sin_valor(pagador, desde, hasta):
    """Las del rango que quedan por fuera porque todavía no tienen valor."""
    return _del_rango(pagador, desde, hasta, EstadoCobro.SIN_VALOR).order_by("servicio_id")


class RelacionOcupada(CobroInvalido):
    """Otra persona armó una relación con alguna de estas líneas al mismo tiempo."""


def armar(pagador, desde, hasta, *, actor) -> RelacionCobro:
    reglas.validar_rango(desde, hasta)
    with transaction.atomic():
        lineas = list(candidatas(pagador, desde, hasta).select_for_update(of=("self",)))
        nueva = reglas.armar(len(lineas))
        relacion = RelacionCobro.objects.create(
            pagador=pagador, desde=desde, hasta=hasta, estado=nueva.estado.value, creada_por=actor
        )
        try:
            with transaction.atomic():
                LineaEnRelacion.objects.bulk_create(
                    LineaEnRelacion(relacion=relacion, linea=linea) for linea in lineas
                )
        except IntegrityError as error:
            raise RelacionOcupada(
                "Alguna de esas líneas acaba de entrar en otra relación; vuelva a intentarlo"
            ) from error
    return relacion


def facturar(relacion, numero_factura, *, actor) -> RelacionCobro:
    with transaction.atomic():
        bloqueada = _bloquear(relacion)
        nueva = reglas.facturar(bloqueada.como_nucleo(), numero_factura)
        lineas = list(_reservadas(bloqueada))
        no_listas = [linea.servicio_id for linea in lineas if linea.estado != EstadoCobro.POR_FACTURAR]
        if no_listas:
            raise CobroInvalido(
                "Estas líneas ya no están por facturar: servicio "
                + ", ".join(f"N.º {n}" for n in no_listas)
            )
        for linea in lineas:
            operaciones.facturar(linea, nueva.numero_factura, actor=actor, desde_relacion=True)
        _cerrar(bloqueada, nueva, actor)
    return _refrescado(relacion)


@dataclass(frozen=True)
class Pago:
    relacion: RelacionCobro
    sin_marcar: list[int]  # servicios cuya línea ya no tenía esa factura


def pagar(relacion, *, actor) -> Pago:
    with transaction.atomic():
        bloqueada = _bloquear(relacion)
        nueva = reglas.pagar(bloqueada.como_nucleo())
        sin_marcar = []
        for linea in bloqueada.lineas.order_by("servicio_id"):
            if (
                linea.estado == EstadoCobro.FACTURADO
                and linea.numero_factura == bloqueada.numero_factura
            ):
                operaciones.pagar(linea, actor=actor)
            elif linea.estado != EstadoCobro.PAGADO:
                sin_marcar.append(linea.servicio_id)
        _cerrar(bloqueada, nueva, actor)
    return Pago(_refrescado(relacion), sin_marcar)


def descartar(relacion, motivo, *, actor) -> RelacionCobro:
    with transaction.atomic():
        bloqueada = _bloquear(relacion)
        nueva = reglas.descartar(bloqueada.como_nucleo(), motivo)
        _cerrar(bloqueada, nueva, actor)
    return _refrescado(relacion)


def lineas_de(relacion):
    """Todas las líneas que entraron en la relación, con su fecha de servicio."""
    return (
        con_fecha_de_servicio(LineaCobro.objects.filter(inclusiones__relacion=relacion))
        .select_related("servicio__vehiculo", "servicio__solicitud")
        .order_by("fecha_servicio", "servicio_id")
    )


def datos_para_exportar(relacion) -> DatosRelacion:
    filas = []
    for linea in lineas_de(relacion):
        servicio, solicitud = linea.servicio, linea.servicio.solicitud
        vehiculo = servicio.vehiculo
        recoger, entregar = puntos_del_servicio(
            servicio.regreso_de_id is not None, solicitud.origen, solicitud.destino
        )
        filas.append(
            FilaRelacion(
                servicio=servicio.pk,
                solicitud=solicitud.pk,
                numero_caso=servicio.referencia_externa,
                fecha_servicio=linea.fecha_servicio,
                tipo_servicio=solicitud.get_tipo_display(),
                placa=vehiculo.placa,
                vin=vehiculo.vin,
                vehiculo=" ".join(p for p in (vehiculo.marca, vehiculo.linea) if p),
                origen=recoger,
                destino=entregar,
                valor=linea.valor,
            )
        )
    return DatosRelacion(
        numero=relacion.pk,
        pagador=relacion.pagador.nombre,
        documento_pagador=relacion.pagador.documento,
        desde=relacion.desde,
        hasta=relacion.hasta,
        numero_factura=relacion.numero_factura,
        filas=tuple(filas),
    )


def _bloquear(relacion) -> RelacionCobro:
    return RelacionCobro.objects.select_for_update().get(pk=getattr(relacion, "pk", relacion))


def _reservadas(relacion):
    return LineaCobro.objects.filter(
        inclusiones__relacion=relacion, inclusiones__reservada=True
    ).order_by("servicio_id")


def _cerrar(relacion: RelacionCobro, nueva: reglas.Relacion, actor):
    relacion.estado = nueva.estado.value
    relacion.numero_factura = nueva.numero_factura or ""
    relacion.motivo_descarte = nueva.motivo_descarte or ""
    relacion.cerrada_en = timezone.now()
    relacion.cerrada_por = actor
    relacion.save(
        update_fields=["estado", "numero_factura", "motivo_descarte", "cerrada_en", "cerrada_por"]
    )
    LineaEnRelacion.objects.filter(relacion=relacion, reservada=True).update(reservada=False)


def _refrescado(relacion):
    if isinstance(relacion, RelacionCobro):
        relacion.refresh_from_db()
        return relacion
    return RelacionCobro.objects.get(pk=relacion)
