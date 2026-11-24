"""Orden de facturación (1a-19b): el total con IVA y la verificación al registrar la factura.

La orden de facturación es la relación de cobro armada (o una línea suelta): Arribo calcula el
subtotal, el IVA de la configuración (si lo lleva: se pregunta) y el total. Al registrar la factura, el facturador digita el
número y el total que le dio su programa de facturación; aquí se comprueba, con las reglas de
`nucleo/facturacion.py`, que el total sea el de la orden y que el número no esté ya registrado, y
solo entonces se factura con las operaciones de siempre (que dejan el historial).

Dos facturaciones al mismo tiempo con el mismo número se ordenan con un bloqueo de PostgreSQL
por número: la segunda ya ve el número usado.
"""
from decimal import Decimal

from django.db import connection, transaction

from configuracion.models import configuracion_vigente
from nucleo import facturacion as reglas
from nucleo.cobro import CobroInvalido, EstadoCobro
from nucleo.relacion import EstadoRelacion

from . import operaciones, relaciones
from .models import LineaCobro, RelacionCobro


def porcentaje_iva() -> Decimal:
    return configuracion_vigente().porcentaje_iva


def liquidar_lineas(lineas, porcentaje=None) -> reglas.Liquidacion:
    porcentaje = porcentaje_iva() if porcentaje is None else porcentaje
    return reglas.liquidar((linea.valor or Decimal(0) for linea in lineas), porcentaje)


def liquidar_relacion(relacion, lineas) -> reglas.Liquidacion:
    return liquidar_lineas(lineas, relaciones.porcentaje_iva_de(relacion))


def donde_esta_la_factura(numero: str, *, excepto=()) -> str | None:
    """Dónde está ya registrado ese número de factura (en una línea facturada o pagada)."""
    linea = (
        LineaCobro.objects.filter(
            numero_factura__iexact=numero.strip(),
            estado__in=(EstadoCobro.FACTURADO.value, EstadoCobro.PAGADO.value),
        )
        .exclude(pk__in=list(excepto))
        .order_by("pk")
        .first()
    )
    return None if linea is None else f"la línea de cobro del servicio N.º {linea.servicio_id}"


def _bloquear_numero(numero: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [f"factura:{reglas.normalizar_numero(numero)}"],
        )


def porcentaje_para(lleva_iva: bool) -> Decimal:
    """El IVA que se suma según la respuesta a "¿Lleva IVA?"."""
    return reglas.porcentaje_a_aplicar(lleva_iva, porcentaje_iva())


def facturar_linea(linea, numero, total_factura, *, actor, lleva_iva=True, mostrar_valores=True):
    """Factura una línea suelta si el total digitado es su valor (más IVA, si lo lleva) y el número
    está libre."""
    with transaction.atomic():
        _bloquear_numero(numero)
        bloqueada = LineaCobro.objects.select_for_update().get(pk=linea.pk)
        if bloqueada.estado != EstadoCobro.POR_FACTURAR:
            raise CobroInvalido("Solo se factura una línea por facturar")
        cuenta = liquidar_lineas([bloqueada], porcentaje_para(lleva_iva))
        reglas.verificar_total(cuenta.total, total_factura, mostrar_valores=mostrar_valores)
        reglas.verificar_numero_libre(numero, donde_esta_la_factura(numero, excepto=[bloqueada.pk]))
        return operaciones.facturar(bloqueada, numero, actor=actor)


def facturar_relacion(relacion, numero, total_factura, *, actor) -> RelacionCobro:
    """Factura toda la relación si el total digitado es el de su orden y el número está libre."""
    with transaction.atomic():
        _bloquear_numero(numero)
        bloqueada = RelacionCobro.objects.select_for_update().get(pk=relacion.pk)
        if bloqueada.estado != EstadoRelacion.ARMADA:
            raise CobroInvalido("Solo se factura una relación armada")
        lineas = list(
            LineaCobro.objects.filter(
                inclusiones__relacion=bloqueada, inclusiones__reservada=True
            )
        )
        cuenta = liquidar_relacion(bloqueada, lineas)
        reglas.verificar_total(cuenta.total, total_factura)
        reglas.verificar_numero_libre(
            numero, donde_esta_la_factura(numero, excepto=[linea.pk for linea in lineas])
        )
        return relaciones.facturar(bloqueada, numero, actor=actor)
