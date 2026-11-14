"""Admin de documentos: solo consulta. Los tipos y los documentos se manejan en el panel
(Flota y documentos); nada se borra y un documento guardado no se edita."""
from django.contrib import admin

from .models import Documento, TipoDocumento


class SoloConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(SoloConsultaAdmin):
    list_display = ("nombre", "aplica_a", "dias_anticipacion", "activo")
    list_filter = ("aplica_a", "activo")


@admin.register(Documento)
class DocumentoAdmin(SoloConsultaAdmin):
    list_display = ("tipo", "grua", "conductor", "numero", "vence", "aplica_desde",
                    "registrado_en", "registrado_por")
    list_filter = ("tipo", "aplica_a")
    search_fields = ("numero", "grua__placa", "conductor__nombre")
    date_hierarchy = "registrado_en"
