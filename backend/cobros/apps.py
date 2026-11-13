from django.apps import AppConfig


class CobrosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cobros"
    verbose_name = "Cobros"

    def ready(self):
        # solicitudes no importa cobros: avisa con una señal y cobros la escucha.
        from solicitudes.models import Servicio
        from solicitudes.senales import servicio_entregado

        from .receptores import crear_linea_del_servicio_entregado

        servicio_entregado.connect(
            crear_linea_del_servicio_entregado,
            sender=Servicio,
            dispatch_uid="cobros.crear_linea_del_servicio_entregado",
        )
