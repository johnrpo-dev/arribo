"""Admin de las sesiones de la app. Nada se edita ni se borra: un token se revoca con la acción
"Revocar los tokens seleccionados" y el celular pierde la sesión en su siguiente petición."""
from django.contrib import admin

from .ingreso import revocar_tokens
from .models import IntentosIngreso, TokenDispositivo


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
    )
    list_filter = (("revocado_en", admin.EmptyFieldListFilter),)
    search_fields = ("conductor__nombre", "conductor__celular", "dispositivo_nombre",
                     "dispositivo_id")
    list_select_related = ("conductor",)
    fields = ("conductor", "dispositivo_nombre", "dispositivo_id", "creado_en", "ultimo_uso",
              "revocado_en")
    readonly_fields = fields
    actions = ("revocar",)

    @admin.display(boolean=True, description="vigente")
    def es_vigente(self, obj):
        return obj.vigente

    @admin.action(description="Revocar los tokens seleccionados", permissions=["change"])
    def revocar(self, request, queryset):
        revocados = revocar_tokens(queryset)
        self.message_user(request, f"Tokens revocados: {revocados}.")

    def has_add_permission(self, request):
        return False  # los tokens los crea el ingreso desde la app

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
