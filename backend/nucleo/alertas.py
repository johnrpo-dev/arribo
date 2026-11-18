"""Alertas por umbral (1a-18): cuándo un servicio o un documento ya requiere que alguien actúe.

Reglas (umbrales de la configuración, `docs/arquitectura.md`):
- Sin asignar, inmediato: lleva `minutos` o más desde que se registró la solicitud.
- Sin asignar, programado: faltan `horas` o menos para su hora (o ya pasó). En un regreso, la hora
  es la fecha de regreso (`nucleo.trayecto.hora_programada`).
- Recogido sin Entregado: lleva `horas` o más desde que se marcó Recogido.
- Documento: hay que avisar (por vencer, o "aún no aplica" que empieza a exigirse pronto) o ya
  está vencido. Lo que falta no alerta (no hay documento al que apuntar; Flota lo muestra).
- Estas alertas son de una condición: se abren mientras la condición se cumple y se cierran solas
  cuando deja de cumplirse (se asignó, se entregó, se registró el documento nuevo). No se marcan
  resueltas a mano: volverían a abrirse en la siguiente revisión.

Los límites son inclusivos: a los 10 minutos exactos ya alerta.
"""
from datetime import date, datetime, timedelta

from nucleo.documentos import Documento, EstadoDocumento, estado_documento, requiere_aviso


def _positivo(valor: int, nombre: str) -> None:
    if valor < 1:
        raise ValueError(f"El umbral {nombre} es mayor que cero.")


def sin_asignar_vencido(
    *,
    ahora: datetime,
    registrada: datetime,
    hora_programada: datetime | None,
    minutos_inmediato: int,
    horas_programado: int,
) -> bool:
    """¿El servicio pendiente de asignar ya pasó su umbral?"""
    _positivo(minutos_inmediato, "de inmediato sin asignar")
    _positivo(horas_programado, "de programado sin asignar")
    if hora_programada is None:
        return ahora - registrada >= timedelta(minutes=minutos_inmediato)
    return hora_programada - ahora <= timedelta(hours=horas_programado)


def recogido_sin_entregado_vencido(
    *, ahora: datetime, recogido_en: datetime, horas: int
) -> bool:
    """¿El vehículo lleva montado (Recogido) el umbral o más sin marcarse Entregado?"""
    _positivo(horas, "de Recogido sin Entregado")
    return ahora - recogido_en >= timedelta(hours=horas)


def documento_alerta(documento: Documento | None, hoy: date, dias_anticipacion: int) -> bool:
    """¿El documento vigente de un tipo requiere atención? Por vencer o vencido."""
    if documento is None:
        return False
    return requiere_aviso(documento, hoy, dias_anticipacion) or (
        estado_documento(documento, hoy, dias_anticipacion) == EstadoDocumento.VENCIDO
    )

