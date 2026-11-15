"""Admin de las sesiones de la app. Nada se edita ni se borra: un token se revoca con la acción
"Revocar los tokens seleccionados" y el celular pierde la sesión en su siguiente petición."""
from django.contrib import admin

from .ingreso import revocar_tokens
from .models import IntentosIngreso, NotificacionPush, TokenDispositivo


@admin.register(TokenDispositivo)
class TokenDispositivoAdmin(admin.ModelAdmin):
    list_display = (
        "conductor",
        "dispositivo_nombre",
        "dispositivo_id",
        "creado_en",
        "ultimo_uso",
        "es_vigente",
        "revocado_en",
        "tiene_push",
    )
    list_filter = (("revocado_en", admin.EmptyFieldListFilter),)
    search_fields = ("conductor__nombre", "conductor__celular", "dispositivo_nombre",
                     "dispositivo_id")
    list_select_related = ("conductor",)
    # El token de push no se muestra: basta saber si lo hay y desde cuándo.
    fields = ("conductor", "dispositivo_nombre", "dispositivo_id", "creado_en", "ultimo_uso",
              "revocado_en", "tiene_push", "push_registrado_en", "push_desactivado_en")
    readonly_fields = fields
    actions = ("revocar",)

    @admin.display(boolean=True, description="vigente")
    def es_vigente(self, obj):
        return obj.vigente

    @admin.display(boolean=True, description="recibe push")
    def tiene_push(self, obj):
        return bool(obj.push_token)

    @admin.action(description="Revocar los tokens seleccionados", permissions=["change"])
    def revocar(self, request, queryset):
        revocados = revocar_tokens(queryset)
        self.message_user(request, f"Tokens revocados: {revocados}.")

    def has_add_permission(self, request):
        return False  # los tokens los crea el ingreso desde la app

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificacionPush)
class NotificacionPushAdmin(admin.ModelAdmin):
    """Solo para consultar los avisos push: cuáles salieron, cuáles fallaron y por qué. Las
    pendientes las reenvía `manage.py enviar_notificaciones_pendientes`."""

    list_display = (
        "creada_en",
        "servicio",
        "conductor",
        "tipo",
        "estado",
        "intentos",
        "enviada_en",
        "error",
    )
    list_filter = ("estado", "tipo")
    search_fields = ("dispositivo__conductor__nombre", "servicio__vehiculo__placa")
    list_select_related = ("dispositivo__conductor", "servicio__vehiculo")
    fields = ("servicio", "dispositivo", "tipo", "titulo", "cuerpo", "estado", "intentos",
              "proximo_intento", "creada_en", "enviada_en", "error")
    readonly_fields = fields

    @admin.display(description="conductor", ordering="dispositivo__conductor__nombre")
    def conductor(self, obj):
        return obj.dispositivo.conductor

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IntentosIngreso)
class IntentosIngresoAdmin(admin.ModelAdmin):
    """Solo para consultar: el bloqueo vence solo a los 15 minutos."""

    list_display = ("celular", "fallos", "primer_fallo", "bloqueado_hasta")
    search_fields = ("celular",)
    readonly_fields = ("celular", "fallos", "primer_fallo", "bloqueado_hasta")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
