"""Admin de solicitudes. Nada se borra; los eventos de estado y las evidencias son de solo lectura.

El estado, el conductor y la grúa de un servicio no se editan aquí: cambian con
`solicitudes/operaciones.py`, que deja el evento de estado.
"""
from django.contrib import admin

from clientes.admin import SinBorrarInline
from flota.admin import SinBorrarAdmin
from nucleo.identificacion import normalizar_placa, normalizar_vin

from .models import EventoEstado, Evidencia, Servicio, Solicitud, Vehiculo

CAMPOS_OPERATIVOS = ("estado", "estado_previo", "conductor", "grua")


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SoloLecturaInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Vehiculo)
class VehiculoAdmin(SinBorrarAdmin):
    list_display = ("placa", "vin", "marca", "linea", "color")
    search_fields = ("placa", "vin", "marca", "linea")

    def get_search_results(self, request, queryset, search_term):
        # Buscar "abc-123" o "1hg-cm826…" también encuentra la placa o el VIN ya normalizados.
        resultados, hay_duplicados = super().get_search_results(request, queryset, search_term)
        placa, vin = normalizar_placa(search_term), normalizar_vin(search_term)
        if placa:
            resultados = resultados | queryset.filter(placa=placa)
            hay_duplicados = True
        if vin:
            resultados = resultados | queryset.filter(vin=vin)
            hay_duplicados = True
        return resultados, hay_duplicados


class ServicioInline(SinBorrarInline, admin.TabularInline):
    model = Servicio
    fk_name = "solicitud"
    extra = 1
    fields = ("vehiculo", "orden_ronda", "referencia_externa", *CAMPOS_OPERATIVOS)
    readonly_fields = CAMPOS_OPERATIVOS
    autocomplete_fields = ("vehiculo",)
    show_change_link = True


@admin.register(Solicitud)
class SolicitudAdmin(SinBorrarAdmin):
    list_display = (
        "__str__",
        "solicitante",
        "pagador",
        "tipo",
        "estado_mostrado",
        "programada_para",
        "creada_en",
    )
    list_filter = ("tipo", "estado_registro")
    search_fields = ("solicitante__nombre", "pagador__nombre", "origen", "destino")
    autocomplete_fields = ("solicitante", "pagador", "contacto_origen", "contacto_destino")
    readonly_fields = ("estado_mostrado", "creada_en", "creada_por")
    inlines = (ServicioInline,)

    @admin.display(description="estado")
    def estado_mostrado(self, obj):
        return obj.estado_etiqueta if obj else ""

    def save_model(self, request, obj, form, change):
        if not change and obj.creada_por_id is None:
            obj.creada_por = request.user
        super().save_model(request, obj, form, change)


class EventoEstadoInline(SoloLecturaInline):
    model = EventoEstado
    fields = (
        "hora_sincronizacion",
        "destino",
        "origen",
        "resultado",
        "capacidad_excedida",
        "actor",
        "conductor",
        "motivo",
        "nombre_quien",
        "secuencia",
        "hora_dispositivo",
    )
    readonly_fields = fields
    ordering = ("hora_sincronizacion",)


@admin.register(Servicio)
class ServicioAdmin(SinBorrarAdmin):
    list_display = ("__str__", "solicitud", "estado", "conductor", "grua", "orden_ronda")
    list_filter = ("estado",)
    search_fields = (
        "vehiculo__placa",
        "vehiculo__vin",
        "referencia_externa",
        "solicitud__solicitante__nombre",
    )
    autocomplete_fields = ("solicitud", "vehiculo", "regreso_de")
    readonly_fields = CAMPOS_OPERATIVOS
    inlines = (EventoEstadoInline,)


@admin.register(EventoEstado)
class EventoEstadoAdmin(SoloLecturaAdmin):
    list_display = (
        "hora_sincronizacion",
        "servicio",
        "destino",
        "origen",
        "resultado",
        "capacidad_excedida",
        "actor",
        "conductor",
    )
    list_filter = ("resultado", "origen", "destino", "capacidad_excedida")
    search_fields = ("id", "servicio__vehiculo__placa", "conductor__nombre", "motivo")
    date_hierarchy = "hora_sincronizacion"


@admin.register(Evidencia)
class EvidenciaAdmin(SoloLecturaAdmin):
    list_display = ("creada_en", "servicio", "tipo", "evento", "archivo")
    list_filter = ("tipo",)
    search_fields = ("id", "servicio__vehiculo__placa")
