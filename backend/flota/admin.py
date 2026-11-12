"""Admin de la flota. Nada se borra: se desactiva la grúa o el conductor, o se cierra la asignación."""
from django.contrib import admin

from .models import AsignacionConductorGrua, Conductor, Grua


class SinBorrarAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Grua)
class GruaAdmin(SinBorrarAdmin):
    list_display = ("placa", "descripcion", "capacidad", "estado_operativo", "activa")
    list_filter = ("activa", "estado_operativo", "capacidad")
    search_fields = ("placa", "descripcion")


@admin.register(Conductor)
class ConductorAdmin(SinBorrarAdmin):
    list_display = ("nombre", "celular", "usuario", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "celular")
    autocomplete_fields = ("usuario",)


@admin.register(AsignacionConductorGrua)
class AsignacionConductorGruaAdmin(SinBorrarAdmin):
    list_display = ("conductor", "grua", "inicio", "fin", "es_vigente", "temporal", "motivo")
    list_filter = ("temporal", "grua")
    search_fields = ("conductor__nombre", "conductor__celular", "grua__placa")
    autocomplete_fields = ("conductor", "grua")
    date_hierarchy = "inicio"

    @admin.display(boolean=True, description="vigente")
    def es_vigente(self, obj):
        return obj.vigente
