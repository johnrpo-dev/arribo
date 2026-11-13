"""Operaciones sobre líneas de cobro: la única forma de crearlas o de cambiar su estado, su valor o
su número de factura.

Cada función corre en su propia transacción, bloquea la fila (`select_for_update`) y deja
exactamente un registro de historial por cambio. Las reglas son las de `nucleo/cobro.py`: aquí solo
se cargan los datos, se llama al núcleo y se guarda lo que decide. Si una regla no se cumple, se
lanza la excepción del núcleo (`CobroInvalido`) o una de este módulo, y no queda ni cambio ni
historial.

- `crear_linea_al_entregar`: la llama el receptor de `servicio_entregado`, en la transacción del
  cambio de estado. Idempotente.
- `marcar_cobrable`: un servicio cancelado que sí se cobra (la grúa se desplazó y el vehículo no
  estaba). Idempotente.
- `fijar_valor`, `facturar`, `pagar`, `anular_factura`.

La división entre dos pagadores (posición 2) no se construye todavía.
"""
from decimal import Decimal

from django.db import transaction

from clientes.models import tarifa_propuesta
from nucleo import cobro
from nucleo.estados import Estado
from solicitudes.models import Servicio

from .models import AccionCobro, HistorialCobro, LineaCobro


class EstadoNoCobrable(Exception):
    """El servicio no está en el estado que la operación exige (Entregado o Cancelado)."""


# --- Creación de la línea ----------------------------------------------------------------------


def crear_linea_al_entregar(servicio, *, actor=None) -> LineaCobro:
    """La línea inicial de un servicio Entregado: pagador de la solicitud, posición 1 y el valor de
    la tarifa vigente si hay (nace por facturar) o sin valor.

    Idempotente: si el servicio ya tiene línea, la devuelve sin crear otra ni cambiarla.
    """
    with transaction.atomic():
        bloqueado = _bloquear_servicio(servicio)
        if bloqueado.estado != Estado.ENTREGADO:
            raise EstadoNoCobrable(
                "La línea de cobro nace cuando el servicio queda Entregado."
            )
        return _linea_inicial(bloqueado, accion=AccionCobro.CREADA, actor=actor)


def marcar_cobrable(servicio, *, actor) -> LineaCobro:
    """Un servicio cancelado no tiene línea (no se cobra), salvo que se marque cobrable: por
    ejemplo, la grúa se desplazó y el vehículo no estaba. Crea la misma línea inicial que al
    entregar. Idempotente.
    """
    with transaction.atomic():
        bloqueado = _bloquear_servicio(servicio)
        if bloqueado.estado != Estado.CANCELADO:
            raise EstadoNoCobrable(
                "Solo un servicio cancelado se marca cobrable; uno entregado ya tiene su línea."
            )
        return _linea_inicial(bloqueado, accion=AccionCobro.MARCADA_COBRABLE, actor=actor)


def _linea_inicial(servicio: Servicio, *, accion, actor) -> LineaCobro:
    """Con la fila del servicio ya bloqueada: dos llamadas simultáneas quedan en fila y la segunda
    ve la línea de la primera. La unicidad (servicio, posición) en la base es la garantía final.
    """
    existente = servicio.lineas_cobro.order_by("posicion").first()
    if existente is not None:
        return existente
    pagador_id = servicio.solicitud.pagador_id
    nueva = cobro.linea_inicial(tarifa_propuesta(pagador_id, servicio.solicitud.tipo))
    linea = LineaCobro(servicio=servicio, pagador_id=pagador_id, posicion=1)
    linea.tomar_del_nucleo(nueva)
    linea.save()
    HistorialCobro.objects.create(
        linea=linea, accion=accion, valor_nuevo=linea.valor, usuario=actor
    )
    return linea


# --- Cambios de la línea -----------------------------------------------------------------------


def fijar_valor(linea, valor, *, actor) -> HistorialCobro:
    """Digitar o ajustar el valor (sin valor o por facturar → por facturar). Guarda quién, cuándo y
    el valor anterior. El valor no cambia después de facturar.
    """
    _exigir_decimal(valor)
    with transaction.atomic():
        bloqueada = _bloquear_linea(linea)
        anterior = bloqueada.valor
        nueva = cobro.fijar_valor(bloqueada.como_nucleo(), valor)
        registro = _guardar(
            bloqueada,
            nueva,
            accion=AccionCobro.VALOR,
            actor=actor,
            valor_anterior=anterior,
            valor_nuevo=nueva.valor,
        )
    _refrescar(linea)
    return registro


def facturar(linea, numero_factura, *, actor) -> HistorialCobro:
    """Por facturar → Facturado, con número de factura obligatorio (se guarda sin espacios)."""
    with transaction.atomic():
        bloqueada = _bloquear_linea(linea)
        nueva = cobro.facturar(bloqueada.como_nucleo(), numero_factura)
        registro = _guardar(
            bloqueada,
            nueva,
            accion=AccionCobro.FACTURADA,
            actor=actor,
            numero_factura=nueva.numero_factura,
        )
    _refrescar(linea)
    return registro


def pagar(linea, *, actor) -> HistorialCobro:
    """Facturado → Pagado."""
    with transaction.atomic():
        bloqueada = _bloquear_linea(linea)
        nueva = cobro.pagar(bloqueada.como_nucleo())
        registro = _guardar(
            bloqueada,
            nueva,
            accion=AccionCobro.PAGADA,
            actor=actor,
            numero_factura=bloqueada.numero_factura,
        )
    _refrescar(linea)
    return registro


def anular_factura(linea, motivo, *, actor) -> HistorialCobro:
    """Facturado (sin pagar) → Por facturar, con motivo. El historial guarda el número anulado."""
    with transaction.atomic():
        bloqueada = _bloquear_linea(linea)
        anulada = bloqueada.numero_factura
        nueva = cobro.anular_factura(bloqueada.como_nucleo(), motivo)
        registro = _guardar(
            bloqueada,
            nueva,
            accion=AccionCobro.FACTURA_ANULADA,
            actor=actor,
            numero_factura=anulada,
            motivo=motivo.strip(),
        )
    _refrescar(linea)
    return registro


# --- Apoyo -------------------------------------------------------------------------------------


def _pk(objeto):
    return getattr(objeto, "pk", objeto)


def _bloquear_servicio(servicio) -> Servicio:
    """La fila del servicio, bloqueada hasta el fin de la transacción (solo esa fila)."""
    return (
        Servicio.objects.select_for_update(of=("self",))
        .select_related("solicitud")
        .get(pk=_pk(servicio))
    )


def _bloquear_linea(linea) -> LineaCobro:
    return LineaCobro.objects.select_for_update().get(pk=_pk(linea))


def _refrescar(linea):
    """Quien llamó con una instancia la ve ya con el estado nuevo."""
    if isinstance(linea, LineaCobro):
        linea.refresh_from_db()


def _exigir_decimal(valor):
    """Dinero siempre en Decimal: un float se rechaza antes de llegar al núcleo o a la base."""
    if not isinstance(valor, Decimal):
        raise TypeError(f"El valor va en Decimal, no en {type(valor).__name__}.")
    if not valor.is_finite():
        raise cobro.CobroInvalido("El valor debe ser un número.")


def _guardar(linea: LineaCobro, nueva: cobro.LineaCobro, *, accion, actor, **historial):
    linea.tomar_del_nucleo(nueva)
    linea._guardar_cambio_de_cobro()
    return HistorialCobro.objects.create(linea=linea, accion=accion, usuario=actor, **historial)
