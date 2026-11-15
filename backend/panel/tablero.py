"""Datos del tablero de logística: cifras de arriba, servicios por asignar con su espera y el
formulario para asignarlos ahí mismo, y una tarjeta por conductor con su grúa, su ocupación y sus
servicios en curso. Vive en `panel` porque junta solicitudes, flota, configuración y alertas.

No decide reglas: la disponibilidad sale de `solicitudes.disponibilidad` (que usa el núcleo) y los
umbrales de espera, de la configuración.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.utils import timezone

from alertas.operaciones import alertas_para_tablero
from configuracion.models import configuracion_vigente
from nucleo.estados import Estado
from nucleo.trayecto import hora_programada, puntos_del_servicio
from solicitudes import consultas
from solicitudes.disponibilidad import Disponibilidad, disponibilidad_de_conductores
from solicitudes.formularios import FormularioAsignacion
from solicitudes.models import EventoEstado, Servicio


@dataclass
class PorAsignar:
    servicio: Servicio
    formulario: FormularioAsignacion
    espera: str  # "12 min", "2 h 5 min"; vacío si es programado
    urgente: bool  # pasó el umbral de la configuración
    hora: datetime | None = None  # para cuándo es; None es inmediato (en un regreso, la fecha de regreso)
    recoger: str = ""  # dónde se recoge (en un regreso, el destino de la solicitud)
    entregar: str = ""  # dónde se entrega


@dataclass
class TarjetaConductor:
    disponibilidad: Disponibilidad
    servicios: list[Servicio] = field(default_factory=list)

    @property
    def conductor(self):
        return self.disponibilidad.conductor

    @property
    def grua(self):
        return self.disponibilidad.grua

    @property
    def capacidad(self) -> int:
        return self.grua.capacidad if self.grua else 0

    @property
    def montados(self) -> int:
        return self.disponibilidad.montados

    @property
    def ocupacion(self) -> int:
        """Porcentaje de la grúa ocupado por vehículos montados (para la barra)."""
        if not self.capacidad:
            return 0
        return min(100, round(100 * self.montados / self.capacidad))

    @property
    def situacion(self) -> str:
        """libre, ocupado, lleno o bloqueado: da el color de la tarjeta."""
        if self.disponibilidad.bloqueado:
            return "bloqueado"
        if not self.servicios:
            return "libre"
        if self.capacidad and self.montados >= self.capacidad:
            return "lleno"
        return "ocupado"


def _texto_espera(minutos: int) -> str:
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def _por_asignar(ahora, configuracion, disponibilidades) -> list[PorAsignar]:
    limite_inmediato = timedelta(minutes=configuracion.alerta_sin_asignar_minutos)
    limite_programado = timedelta(hours=configuracion.alerta_programado_sin_asignar_horas)
    filas = []
    for servicio in consultas.por_asignar():
        solicitud = servicio.solicitud
        es_regreso = servicio.regreso_de_id is not None
        hora = hora_programada(es_regreso, solicitud.programada_para, solicitud.fecha_regreso)
        recoger, entregar = puntos_del_servicio(es_regreso, solicitud.origen, solicitud.destino)
        if hora:
            espera, urgente = "", hora - ahora <= limite_programado
        else:
            transcurrido = ahora - solicitud.creada_en
            espera = _texto_espera(max(0, int(transcurrido.total_seconds() // 60)))
            urgente = transcurrido >= limite_inmediato
        formulario = FormularioAsignacion(
            prefix=f"s{servicio.pk}", disponibilidades=disponibilidades
        )
        filas.append(PorAsignar(servicio, formulario, espera, urgente, hora, recoger, entregar))
    return filas


def _inicio_del_dia(ahora):
    local = timezone.localtime(ahora)
    return timezone.make_aware(datetime.combine(local.date(), time.min), local.tzinfo)


def entregados_hoy(ahora=None) -> int:
    """Servicios marcados Entregado desde la medianoche de Medellín (por hora de sincronización)."""
    ahora = ahora or timezone.now()
    return (
        EventoEstado.objects.filter(
            destino=Estado.ENTREGADO.value, hora_sincronizacion__gte=_inicio_del_dia(ahora)
        )
        .values("servicio")
        .distinct()
        .count()
    )


def datos_del_tablero(ahora=None) -> dict:
    ahora = ahora or timezone.now()
    configuracion = configuracion_vigente()
    disponibilidades = [d for d in disponibilidad_de_conductores() if d.conductor.activo]
    por_asignar = _por_asignar(ahora, configuracion, disponibilidades)

    tarjetas = {d.conductor.pk: TarjetaConductor(d) for d in disponibilidades}
    for ronda in consultas.en_curso():
        tarjeta = tarjetas.get(ronda.conductor.pk)
        if tarjeta is None:  # conductor desactivado con servicios aún abiertos
            continue
        tarjeta.servicios = ronda.servicios
    orden = {"lleno": 0, "ocupado": 1, "libre": 2, "bloqueado": 3}
    conductores = sorted(tarjetas.values(), key=lambda t: orden[t.situacion])

    alertas = alertas_para_tablero()
    en_curso = sum(len(t.servicios) for t in tarjetas.values())
    return {
        "ahora": ahora,
        "por_asignar": por_asignar,
        "borradores": consultas.borradores(),
        "alertas": alertas,
        "conductores": conductores,
        "cifras": {
            "por_asignar": len(por_asignar),
            "urgentes": sum(1 for p in por_asignar if p.urgente),
            "en_curso": en_curso,
            "entregados_hoy": entregados_hoy(ahora),
            "libres": sum(1 for t in conductores if t.situacion == "libre"),
            "conductores": len(conductores),
            "alertas": len(alertas),
        },
    }
