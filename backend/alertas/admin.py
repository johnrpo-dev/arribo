"""Admin de alertas: se consultan y se marcan como resueltas; no se agregan, editan ni borran.

Es lo que hay para verlas hasta que la tarea 1a-18 construya el tablero.
"""
from django.contrib import admin

from solicitudes.admin import SoloLecturaAdmin

from .models import Alerta
from .operaciones import resolver_alerta


@admin.register(Alerta)
class AlertaAdmin(SoloLecturaAdmin):
    list_display = ("creada_en", "tipo", "mensaje", "es_abierta", "resuelta_en", "resuelta_por")
    list_filter = ("tipo", ("resuelta_en", admin.EmptyFieldListFilter))
    search_fields = ("mensaje", "registro_id")
    date_hierarchy = "creada_en"
    actions = ("resolver",)

    @admin.display(boolean=True, description="abierta")
    def es_abierta(self, obj):
        return obj.abierta

    @admin.action(
        description="Marcar como resueltas las alertas seleccionadas", permissions=["view"]
    )
    def resolver(self, request, queryset):
        abiertas = [alerta for alerta in queryset if alerta.abierta]
        for alerta in abiertas:
            resolver_alerta(alerta, por=request.user)
        self.message_user(request, f"Alertas resueltas: {len(abiertas)}.")
