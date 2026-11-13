"""Admin de cobros: solo para consultar. Nada se borra ni se edita aquí.

Las líneas cambian con `cobros/operaciones.py`, que deja el historial; las pantallas de cobro son de
la tarea 1a-16b. El historial se ve dentro de la línea y es de solo lectura.
"""
from django.contrib import admin

from solicitudes.admin import SoloLecturaAdmin, SoloLecturaInline

from .models import HistorialCobro, LineaCobro


class HistorialCobroInline(SoloLecturaInline):
    model = HistorialCobro
    fields = (
        "fecha",
        "accion",
        "valor_anterior",
        "valor_nuevo",
        "numero_factura",
        "motivo",
        "usuario",
    )
    readonly_fields = fields
    ordering = ("fecha", "pk")


@admin.register(LineaCobro)
class LineaCobroAdmin(SoloLecturaAdmin):
    list_display = (
        "servicio",
        "pagador",
        "posicion",
        "estado",
        "valor",
        "numero_factura",
        "creada_en",
    )
    list_filter = ("estado",)
    search_fields = ("numero_factura", "pagador__nombre", "servicio__vehiculo__placa")
    date_hierarchy = "creada_en"
    inlines = (HistorialCobroInline,)
