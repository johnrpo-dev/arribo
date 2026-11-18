"""Consultas de solo lectura de la sección Cobros (1a-16b): la lista de líneas por estado, la
búsqueda y los servicios cancelados que se podrían marcar cobrables.

Los valores se formatean aquí (`nucleo.cobro.formato_pesos`) y solo para quien puede verlos
(`configuracion.operaciones.puede_ver_valores`): la plantilla nunca recibe el valor de una línea
si el usuario no lo puede ver.
"""
from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef, Q

from nucleo.cobro import EstadoCobro, formato_pesos
from nucleo.estados import Estado
from nucleo.identificacion import normalizar_placa
from solicitudes.models import EventoEstado, Servicio

from .models import LineaCobro

POR_PAGINA = 25
MINIMO_PARCIAL = 3

E = EstadoCobro
# clave → (nombre de la pestaña, estados de cobro que incluye). "cancelados" no son líneas.
FILTROS = {
    "pendientes": ("Pendientes", (E.SIN_VALOR, E.POR_FACTURAR)),
    "sin_valor": ("Sin valor", (E.SIN_VALOR,)),
    "por_facturar": ("Por facturar", (E.POR_FACTURAR,)),
    "facturadas": ("Facturadas sin pagar", (E.FACTURADO,)),
    "pagadas": ("Pagadas", (E.PAGADO,)),
    "todas": ("Todas", tuple(E)),
    "cancelados": ("Cancelados", ()),
}
FILTRO_POR_DEFECTO = "pendientes"
_MAS_ANTIGUA_PRIMERO = ("pendientes", "sin_valor", "por_facturar")


def lineas(filtro: str = FILTRO_POR_DEFECTO, texto: str = ""):
    """Líneas del filtro y la búsqueda: las pendientes, la más antigua primero (es la que más
    espera); las demás, la más reciente primero."""
    if filtro not in FILTROS or filtro == "cancelados":
        filtro = FILTRO_POR_DEFECTO
    estados = [e.value for e in FILTROS[filtro][1]]
    if filtro in _MAS_ANTIGUA_PRIMERO:
        orden = ("creada_en", "pk")
    else:
        orden = ("-creada_en", "-pk")
    consulta = (
        LineaCobro.objects.filter(estado__in=estados)
        .select_related("pagador", "servicio__vehiculo", "servicio__solicitud")
        .order_by(*orden)
    )
    return buscar(consulta, texto)


def buscar(consulta, texto: str):
    """Por pagador, placa o VIN, número de servicio o de solicitud y número de factura."""
    texto = (texto or "").strip()
    if not texto:
        return consulta
    condicion = Q(pagador__nombre__icontains=texto) | Q(numero_factura__icontains=texto)
    numero = texto.lstrip("#").strip()
    if numero.isdigit():
        condicion |= Q(servicio_id=int(numero)) | Q(servicio__solicitud_id=int(numero))
    alfanumerico = normalizar_placa(texto)
    if len(alfanumerico) >= MINIMO_PARCIAL:
        condicion |= Q(servicio__vehiculo__placa__contains=alfanumerico)
        condicion |= Q(servicio__vehiculo__vin__contains=alfanumerico)
    return consulta.filter(condicion)


def cuantas() -> dict[str, int]:
    """Cuántas líneas hay en cada pestaña y cuántos cancelados hay por revisar."""
    por_estado = dict(
        LineaCobro.objects.order_by().values("estado").annotate(n=Count("pk"))
        .values_list("estado", "n")
    )
    resultado = {
        clave: sum(por_estado.get(e.value, 0) for e in estados)
        for clave, (_, estados) in FILTROS.items()
    }
    resultado["cancelados"] = cancelados_sin_cobro().count()
    return resultado


def cancelados_sin_cobro():
    """Servicios cancelados después de asignarse (tenían conductor: la grúa pudo haber salido) y
    sin línea de cobro. Se decide si se cobran con "Marcar cobrable". Los vehículos quitados de un
    borrador nunca tuvieron conductor y no aparecen."""
    return (
        Servicio.objects.filter(estado=Estado.CANCELADO.value, conductor__isnull=False)
        .exclude(Exists(LineaCobro.objects.filter(servicio=OuterRef("pk"))))
        .select_related("vehiculo", "conductor", "solicitud__pagador")
        .order_by("-pk")
    )


def motivos_de_cancelacion(servicios) -> dict[int, str]:
    """El motivo del último evento Cancelado de cada servicio, en una consulta."""
    motivos = {}
    for servicio_id, motivo in (
        EventoEstado.objects.filter(
            servicio__in=[s.pk for s in servicios], destino=Estado.CANCELADO.value
        )
        .order_by("hora_sincronizacion")
        .values_list("servicio_id", "motivo")
    ):
        motivos[servicio_id] = motivo
    return motivos


@dataclass(frozen=True)
class FilaCobro:
    linea: LineaCobro
    valor: str | None  # None: el usuario no ve valores


def filas(lineas_de_la_pagina, *, ve_valores: bool) -> list[FilaCobro]:
    return [
        FilaCobro(linea, formato_pesos(linea.valor) if ve_valores else None)
        for linea in lineas_de_la_pagina
    ]
