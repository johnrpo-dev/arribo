"""Consultas de solo lectura para la lista de solicitudes y el tablero de inicio (1a-08c).

- `lista` filtra, busca y ordena solicitudes con sus servicios precargados: el estado que se
  muestra lo deriva `Solicitud.estado` (es decir, `nucleo.estados.estado_solicitud`) sin una
  consulta por fila.
- Los filtros por estado se hacen en la base para poder paginar. Usan las mismas definiciones que
  el núcleo: una solicitud abierta está terminada (completada o cancelada) cuando tiene servicios y
  todos son terminales (`nucleo.estados.TERMINALES`). `tests/solicitudes/test_lista.py` comprueba
  que el filtro y `estado_solicitud` coinciden en todas las combinaciones de dos servicios.
- `tablero` reúne lo que requiere acción ahora para logística: servicios por asignar, borradores
  con lo que les falta, alertas abiertas y servicios en curso por conductor.
"""
import re
from dataclasses import dataclass
from itertools import groupby

from django.db.models import Exists, F, OuterRef, Prefetch, Q

from clientes.models import TelefonoCliente
from nucleo.estados import TERMINALES, Estado
from nucleo.identificacion import TelefonoInvalido, normalizar_placa, normalizar_telefono
from nucleo.registro import describir_faltantes

from .models import VALORES_EN_RONDA, EstadoRegistro, Servicio, Solicitud
from .registro import faltantes_de

POR_PAGINA = 25
# Cuántos dígitos o letras hacen falta para buscar por parte del teléfono, la placa o el VIN: con
# menos, "12" traería medio archivo.
MINIMO_PARCIAL = 3

FILTROS = {
    "activas": "Activas",
    "por_asignar": "Por asignar",
    "borradores": "Borradores",
    "programadas": "Programadas",
    "terminadas": "Terminadas",
    "todas": "Todas",
}
FILTRO_POR_DEFECTO = "activas"

_TERMINALES = [estado.value for estado in TERMINALES]


def _servicios_de(referencia="pk"):
    return Servicio.objects.filter(solicitud=OuterRef(referencia))


def con_situacion(solicitudes):
    """Anota lo necesario para filtrar por estado derivado sin traer los servicios."""
    return solicitudes.annotate(
        hay_servicios=Exists(_servicios_de()),
        hay_no_terminales=Exists(_servicios_de().exclude(estado__in=_TERMINALES)),
        hay_pendientes=Exists(_servicios_de().filter(estado=Estado.PENDIENTE_ASIGNAR.value)),
    )


# Abierta con servicios y todos terminales: completada o cancelada según el núcleo.
_ABIERTA_TERMINADA = Q(
    estado_registro=EstadoRegistro.ABIERTA, hay_servicios=True, hay_no_terminales=False
)
_TERMINADA = Q(estado_registro=EstadoRegistro.NO_CONCRETADA) | _ABIERTA_TERMINADA
# Borrador, abierta o en curso.
_ACTIVA = Q(estado_registro=EstadoRegistro.BORRADOR) | (
    Q(estado_registro=EstadoRegistro.ABIERTA) & ~_ABIERTA_TERMINADA
)
_RECIENTES = ("-creada_en", "-pk")
_POR_HORA = (F("programada_para").asc(nulls_first=True), "creada_en", "pk")


def filtrar(solicitudes, filtro: str):
    """Aplica uno de FILTROS a un queryset anotado con `con_situacion`."""
    if filtro == "activas":
        return solicitudes.filter(_ACTIVA).order_by(*_RECIENTES)
    if filtro == "por_asignar":
        return solicitudes.filter(
            estado_registro=EstadoRegistro.ABIERTA, hay_pendientes=True
        ).order_by(*_POR_HORA)
    if filtro == "borradores":
        return solicitudes.filter(estado_registro=EstadoRegistro.BORRADOR).order_by(*_RECIENTES)
    if filtro == "programadas":
        return solicitudes.filter(_ACTIVA, programada_para__isnull=False).order_by(
            "programada_para", "pk"
        )
    if filtro == "terminadas":
        return solicitudes.filter(_TERMINADA).order_by(*_RECIENTES)
    return solicitudes.order_by(*_RECIENTES)


def buscar(solicitudes, texto: str):
    """Por nombre o teléfono del cliente (quien pide o quien paga), número de solicitud, placa,
    VIN o referencia externa de alguno de sus vehículos."""
    texto = (texto or "").strip()
    if not texto:
        return solicitudes
    condicion = Q(solicitante__nombre__icontains=texto) | Q(pagador__nombre__icontains=texto)

    numero = texto.lstrip("#").strip()
    if numero.isdigit():
        condicion |= Q(pk=int(numero))

    digitos = re.sub(r"\D", "", texto)
    if len(digitos) >= MINIMO_PARCIAL:
        try:
            digitos = normalizar_telefono(texto)  # quita el +57 si lo trae
        except TelefonoInvalido:
            pass
        clientes = TelefonoCliente.objects.filter(numero__contains=digitos).values("cliente_id")
        condicion |= Q(solicitante_id__in=clientes) | Q(pagador_id__in=clientes)

    de_servicios = Q(referencia_externa__icontains=texto)
    alfanumerico = normalizar_placa(texto)
    if len(alfanumerico) >= MINIMO_PARCIAL:
        de_servicios |= Q(vehiculo__placa__contains=alfanumerico)
        de_servicios |= Q(vehiculo__vin__contains=alfanumerico)
    elif alfanumerico:
        de_servicios |= Q(vehiculo__placa=alfanumerico)
    condicion |= Q(pk__in=Servicio.objects.filter(de_servicios).values("solicitud_id"))
    return solicitudes.filter(condicion)


def lista(filtro: str = FILTRO_POR_DEFECTO, texto: str = ""):
    """Solicitudes del filtro y la búsqueda, con lo que la tabla muestra ya cargado."""
    if filtro not in FILTROS:
        filtro = FILTRO_POR_DEFECTO
    solicitudes = Solicitud.objects.select_related("solicitante").prefetch_related(
        Prefetch(
            "servicios",
            queryset=Servicio.objects.select_related("vehiculo", "conductor").order_by("pk"),
        )
    )
    return buscar(filtrar(con_situacion(solicitudes), filtro), texto)


@dataclass(frozen=True)
class Fila:
    """Una fila de la lista de solicitudes."""

    solicitud: Solicitud
    vehiculos: list[str]
    conductores: list[str]


def filas(solicitudes) -> list[Fila]:
    """Vehículos (placa o VIN, sin repetir los de regreso) y conductores de cada solicitud, desde
    los servicios precargados."""
    resultado = []
    for solicitud in solicitudes:
        vehiculos, conductores = {}, {}
        for servicio in solicitud.servicios.all():
            if servicio.estado == Estado.CANCELADO and servicio.regreso_de_id is None:
                continue  # un vehículo quitado del borrador
            vehiculo = servicio.vehiculo
            vehiculos.setdefault(vehiculo.pk, vehiculo.placa or vehiculo.vin or "Sin placa ni VIN")
            if servicio.conductor_id:
                conductores.setdefault(servicio.conductor_id, servicio.conductor.nombre)
        resultado.append(Fila(solicitud, list(vehiculos.values()), list(conductores.values())))
    return resultado


# --- Tablero -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Borrador:
    solicitud: Solicitud
    falta: str  # vacío si ya tiene todo para abrirse


@dataclass(frozen=True)
class RondaEnCurso:
    conductor: object
    servicios: list[Servicio]


def por_asignar():
    """Servicios pendientes de asignar de solicitudes abiertas: los inmediatos primero (por hora de
    registro) y luego los programados por hora."""
    return list(
        Servicio.objects.filter(
            estado=Estado.PENDIENTE_ASIGNAR.value,
            solicitud__estado_registro=EstadoRegistro.ABIERTA,
        )
        .select_related("vehiculo", "solicitud__solicitante")
        .order_by(
            F("solicitud__programada_para").asc(nulls_first=True),
            "solicitud__creada_en",
            "pk",
        )
    )


def borradores() -> list[Borrador]:
    """Borradores, el más antiguo primero, con lo que les falta para abrirse."""
    solicitudes = (
        Solicitud.objects.filter(estado_registro=EstadoRegistro.BORRADOR)
        .select_related("solicitante", "pagador")
        .prefetch_related("servicios")
        .order_by("creada_en", "pk")
    )
    return [Borrador(s, describir_faltantes(faltantes_de(s))) for s in solicitudes]


def en_curso() -> list[RondaEnCurso]:
    """Servicios asignados, en camino, recogidos o en novedad, agrupados por conductor y en el
    orden de su ronda."""
    servicios = (
        Servicio.objects.filter(estado__in=VALORES_EN_RONDA)
        .select_related("conductor", "grua", "vehiculo", "solicitud__solicitante")
        .order_by(
            "conductor__nombre", "conductor_id", F("orden_ronda").asc(nulls_last=True), "pk"
        )
    )
    return [
        RondaEnCurso(conductor, list(grupo))
        for conductor, grupo in groupby(servicios, key=lambda s: s.conductor)
    ]
