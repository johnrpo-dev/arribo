from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "panel"
    verbose_name = "Panel web"

    def ready(self):
        from panel.admin_consulta import dejar_admin_de_solo_consulta
        from panel.tunel_usb import iniciar_si_corresponde

        dejar_admin_de_solo_consulta()
        # En desarrollo, `runserver` mantiene vivo el túnel USB del celular (panel/tunel_usb.py).
        iniciar_si_corresponde()
