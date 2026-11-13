from django.apps import AppConfig


class AlertasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alertas"
    verbose_name = "Alertas"

    def ready(self):
        # solicitudes no importa alertas: avisa con señales y alertas las escucha.
        from solicitudes.models import EventoEstado
        from solicitudes.senales import (
            evento_del_conductor_guardado,
            evento_del_conductor_rechazado,
        )

        from .receptores import alertar_por_evento_guardado, alertar_por_evento_rechazado

        evento_del_conductor_guardado.connect(
            alertar_por_evento_guardado,
            sender=EventoEstado,
            dispatch_uid="alertas.alertar_por_evento_guardado",
        )
        evento_del_conductor_rechazado.connect(
            alertar_por_evento_rechazado,
            sender=EventoEstado,
            dispatch_uid="alertas.alertar_por_evento_rechazado",
        )
