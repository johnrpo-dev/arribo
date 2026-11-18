"""Evaluar las alertas por umbral (1a-18): servicio sin asignar, Recogido sin Entregado y documento
por vencer o vencido. Las reglas están en `nucleo/alertas.py`; los umbrales, en la configuración.

Cada revisión abre la alerta de lo que cumple la condición (una sola abierta por registro, la base
lo garantiza) y cierra las abiertas de lo que ya no la cumple (se asignó, se entregó, se registró
el documento nuevo), sin usuario: las cerró el sistema. Correrla dos veces seguidas no cambia nada.

La corre `manage.py evaluar_alertas` (en producción, cada minuto) y también el tablero al
cargarse, para que lo que se ve esté al día aunque el temporizador no haya corrido.

La alerta de conflicto de sincronización no se evalúa aquí: la abre la sincronización en el
momento en que llega el evento que no encaja (`alertas/receptores.py`).
"""
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from configuracion.models import configuracion_vigente
from documentos.consultas import por_vencer_o_vencidos
from nucleo import alertas as reglas
from nucleo.documentos import EstadoDocumento
from nucleo.estados import Estado
from nucleo.trayecto import hora_programada
from solicitudes import consultas
from solicitudes.models import EventoEstado, ResultadoEvento, Servicio

from .models import TIPOS_POR_CONDICION, Alerta, TipoAlerta
from .operaciones import abrir_alerta


@dataclass
class Resumen:
    abiertas: dict[str, int] = field(default_factory=dict)  # nuevas en esta revisión, por tipo
    cerradas: dict[str, int] = field(default_factory=dict)

    @property
    def total_abiertas(self) -> int:
        return sum(self.abiertas.values())

    @property
    def total_cerradas(self) -> int:
        return sum(self.cerradas.values())


def _hora(momento) -> str:
    return timezone.localtime(momento).strftime("%d/%m %H:%M")


def _quien(servicio) -> str:
    cliente = servicio.solicitud.solicitante.nombre
    return f"Servicio N.º {servicio.pk} ({servicio.vehiculo}, {cliente})"


def _sin_asignar(ahora, configuracion) -> dict:
    deben = {}
    for servicio in consultas.por_asignar():
        solicitud = servicio.solicitud
        hora = hora_programada(
            servicio.regreso_de_id is not None, solicitud.programada_para, solicitud.fecha_regreso
        )
        if not reglas.sin_asignar_vencido(
            ahora=ahora,
            registrada=solicitud.creada_en,
            hora_programada=hora,
            minutos_inmediato=configuracion.alerta_sin_asignar_minutos,
            horas_programado=configuracion.alerta_programado_sin_asignar_horas,
        ):
            continue
        if hora is None:
            mensaje = (
                f"{_quien(servicio)}: inmediato, registrado el {_hora(solicitud.creada_en)} y "
                f"sigue sin asignar (umbral: {configuracion.alerta_sin_asignar_minutos} min)."
            )
        else:
            mensaje = (
                f"{_quien(servicio)}: programado para el {_hora(hora)} y sigue sin asignar "
                f"(umbral: {configuracion.alerta_programado_sin_asignar_horas} h antes)."
            )
        deben[servicio] = mensaje
    return deben


def _recogidos(ahora, configuracion) -> dict:
    recogida = (
        EventoEstado.objects.filter(
            servicio=OuterRef("pk"),
            destino=Estado.RECOGIDO.value,
            resultado=ResultadoEvento.APLICADO,
        )
        .order_by("-hora_sincronizacion")
        .annotate(momento=Coalesce("hora_dispositivo", "hora_sincronizacion"))
        .values("momento")[:1]
    )
    servicios = (
        Servicio.objects.filter(estado=Estado.RECOGIDO.value)
        .select_related("vehiculo", "conductor", "solicitud__solicitante")
        .annotate(recogido_en=Subquery(recogida))
        .order_by("pk")
    )
    horas = configuracion.alerta_recogido_sin_entregado_horas
    deben = {}
    for servicio in servicios:
        if servicio.recogido_en is None:  # sin evento (dato viejo): no hay desde cuándo contar
            continue
        if reglas.recogido_sin_entregado_vencido(
            ahora=ahora, recogido_en=servicio.recogido_en, horas=horas
        ):
            quien = f" por {servicio.conductor}" if servicio.conductor else ""
            deben[servicio] = (
                f"{_quien(servicio)}: recogido{quien} el {_hora(servicio.recogido_en)} y sin "
                f"marcarse Entregado (umbral: {horas} h)."
            )
    return deben


def _documentos(ahora) -> dict:
    hoy = timezone.localdate(ahora)
    deben = {}
    for estado in por_vencer_o_vencidos(hoy):
        nucleo = estado.documento.como_nucleo()
        if estado.estado == EstadoDocumento.VENCIDO:
            detalle = "está vencido: bloquea asignaciones nuevas"
        elif nucleo.aplica_desde is not None:
            detalle = f"se exige desde el {nucleo.aplica_desde.strftime('%d/%m/%Y')}"
        else:
            detalle = f"vence el {nucleo.ultimo_dia_valido.strftime('%d/%m/%Y')}"
        deben[estado.documento] = f"{estado.descripcion} {detalle}."
    return deben


def _sincronizar(tipo: TipoAlerta, deben: dict, abiertas: list, resumen: Resumen, ahora) -> None:
    """Abre lo que debe estar abierto y cierra lo que ya no; deben = {registro: mensaje}."""
    ya = {(a.tipo_registro_id, a.registro_id) for a in abiertas}
    claves = set()
    nuevas = 0
    for registro, mensaje in deben.items():
        clave = (ContentType.objects.get_for_model(registro).pk, str(registro.pk))
        claves.add(clave)
        if clave not in ya:
            abrir_alerta(tipo, registro, mensaje)
            nuevas += 1
    cerrar = [a.pk for a in abiertas if (a.tipo_registro_id, a.registro_id) not in claves]
    if cerrar:
        Alerta.objects.filter(pk__in=cerrar, resuelta_en__isnull=True).update(resuelta_en=ahora)
    resumen.abiertas[tipo.value] = nuevas
    resumen.cerradas[tipo.value] = len(cerrar)


def evaluar(ahora=None, configuracion=None) -> Resumen:
    ahora = ahora or timezone.now()
    configuracion = configuracion or configuracion_vigente()
    resumen = Resumen()
    with transaction.atomic():
        abiertas = {tipo: [] for tipo in TIPOS_POR_CONDICION}
        for alerta in Alerta.objects.filter(
            tipo__in=[t.value for t in TIPOS_POR_CONDICION], resuelta_en__isnull=True
        ).only("pk", "tipo", "tipo_registro_id", "registro_id"):
            abiertas[TipoAlerta(alerta.tipo)].append(alerta)
        for tipo, deben in (
            (TipoAlerta.SIN_ASIGNAR, _sin_asignar(ahora, configuracion)),
            (TipoAlerta.RECOGIDO_SIN_ENTREGADO, _recogidos(ahora, configuracion)),
            (TipoAlerta.DOCUMENTO_POR_VENCER, _documentos(ahora)),
        ):
            _sincronizar(tipo, deben, abiertas[tipo], resumen, ahora)
    return resumen
