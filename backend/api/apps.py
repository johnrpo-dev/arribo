from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "API del conductor"

    def ready(self):
        # solicitudes no importa api: avisa con la señal y api encola los avisos push (1a-14).
        from solicitudes.models import Servicio
        from solicitudes.senales import servicio_asignado

        from .receptores import encolar_avisos_push

        servicio_asignado.connect(
            encolar_avisos_push,
            sender=Servicio,
            dispatch_uid="api.encolar_avisos_push",
        )
