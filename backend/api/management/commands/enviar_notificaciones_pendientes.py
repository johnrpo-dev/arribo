"""`manage.py enviar_notificaciones_pendientes`: reenvía los avisos push que quedaron pendientes.

Cada aviso se intenta al asignar; si falló por algo pasajero (sin red, FCM caído), queda pendiente
con la hora de su próximo intento. Este comando envía los que ya tocan. En producción se corre
cada minuto (cron o temporizador del servidor, tarea 1a-21); en desarrollo, a mano.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import EstadoNotificacion, NotificacionPush
from api.notificaciones import enviar_pendientes


class Command(BaseCommand):
    help = "Envía los avisos push pendientes cuyo próximo intento ya llegó."

    def handle(self, *args, **opciones):
        resumen = enviar_pendientes()
        enviadas = resumen[EstadoNotificacion.ENVIADA]
        por_reintentar = resumen[EstadoNotificacion.PENDIENTE]
        fallidas = resumen[EstadoNotificacion.FALLIDA]
        self.stdout.write(
            f"Avisos push: {enviadas} enviados, {por_reintentar} por reintentar, "
            f"{fallidas} fallidos."
        )
        siguiente = (
            NotificacionPush.objects.filter(estado=EstadoNotificacion.PENDIENTE)
            .order_by("proximo_intento")
            .values_list("proximo_intento", flat=True)
            .first()
        )
        if siguiente is not None:
            hora = timezone.localtime(siguiente).strftime("%d/%m/%Y %H:%M")
            self.stdout.write(f"El próximo reintento toca el {hora}.")
