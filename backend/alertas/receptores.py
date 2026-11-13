"""Receptores de las señales de `solicitudes`. Se conectan en `AlertasConfig.ready()`.

No atrapan errores: si la alerta no se puede abrir, la transacción del evento se deshace entera y
el celular lo reenvía. Un conflicto nunca queda guardado sin su alerta.
"""
from django.utils import timezone

from nucleo.estados import Estado
from nucleo.sincronizacion import DETALLE, Motivo
from solicitudes.models import ETIQUETAS_ESTADO, ResultadoEvento

from .models import TipoAlerta
from .operaciones import abrir_alerta

LARGO_MAXIMO_DEL_CONTENIDO = 600


def _hora_local(momento) -> str:
    if momento is None:
        return "sin hora"
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def _toque(evento) -> str:
    """"Ana marcó Recogido en Servicio 12 · ABC123 (hora del celular 12/11/2026 08:07)"."""
    etiqueta = ETIQUETAS_ESTADO[Estado(evento.destino)]
    quien = evento.conductor or "Un conductor"
    return (
        f"{quien} marcó {etiqueta} en {evento.servicio} desde la app "
        f"(hora del celular: {_hora_local(evento.hora_dispositivo)})"
    )


def alertar_por_evento_guardado(sender, evento, montados=(), **kwargs):
    """Un evento en conflicto abre "conflicto de sincronización"; un Recogido aplicado con la grúa
    llena abre "capacidad excedida". Las dos apuntan al evento."""
    if evento.resultado == ResultadoEvento.CONFLICTO:
        motivo = DETALLE.get(evento.motivo_conflicto, "No encajó con el estado del servicio.")
        abrir_alerta(
            TipoAlerta.CONFLICTO_SINCRONIZACION,
            evento,
            f"{_toque(evento)} y no se aplicó: {motivo} El evento quedó guardado en el historial "
            "del servicio; revise qué pasó y corrija el estado si hace falta.",
        )
    if evento.capacidad_excedida:
        grua = evento.servicio.grua
        llevaba = f" Ya llevaba: {'; '.join(montados)}." if montados else ""
        abrir_alerta(
            TipoAlerta.CAPACIDAD_EXCEDIDA,
            evento,
            f"{_toque(evento)} con la grúa {grua} llena (capacidad {grua.capacidad}).{llevaba} "
            "Se aplicó porque el vehículo ya está montado; revise qué servicio falta marcar "
            "como Entregado.",
        )


def alertar_por_evento_rechazado(sender, conductor, motivo, contenido, original=None, **kwargs):
    """Un evento que no se pudo guardar no deja fila: la alerta lleva lo que llegó. Apunta al
    evento que ya tenía ese id, o al conductor si no hay ninguno."""
    texto = str(contenido)
    if len(texto) > LARGO_MAXIMO_DEL_CONTENIDO:
        texto = texto[:LARGO_MAXIMO_DEL_CONTENIDO] + "…"
    abrir_alerta(
        TipoAlerta.EVENTO_RECHAZADO,
        original or conductor,
        f"La app de {conductor} envió un evento que no se pudo guardar: {DETALLE[Motivo(motivo)]} "
        f"Lo que llegó: {texto}. Si hay más rechazos mientras esta alerta siga abierta, quedan "
        "solo en el registro del servidor.",
    )
