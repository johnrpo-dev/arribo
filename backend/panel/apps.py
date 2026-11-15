from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "panel"
    verbose_name = "Panel web"

    def ready(self):
        from panel.admin_consulta import dejar_admin_de_solo_consulta

        dejar_admin_de_solo_consulta()
