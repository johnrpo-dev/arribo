"""Admin de la flota. Nada se borra: se desactiva la grúa o el conductor, o se cierra la asignación.

El PIN de la app del conductor se fija aquí (no hay pantalla del panel para eso): el formulario del
conductor tiene el campo "Nuevo PIN de la app", que guarda solo su hash y nunca lo muestra.
"""
from django import forms
from django.contrib import admin

from nucleo.ingreso import LARGO_PIN, PinInvalido, validar_pin

from .models import AsignacionConductorGrua, Conductor, Grua


class SinBorrarAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Grua)
class GruaAdmin(SinBorrarAdmin):
    list_display = ("placa", "descripcion", "capacidad", "estado_operativo", "activa")
    list_filter = ("activa", "estado_operativo", "capacidad")
    search_fields = ("placa", "descripcion")


class ConductorForm(forms.ModelForm):
    nuevo_pin = forms.CharField(
        label="Nuevo PIN de la app",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"autocomplete": "new-password", "inputmode": "numeric"}
        ),
        help_text=f"{LARGO_PIN} dígitos. Se guarda solo su hash: no se puede volver a ver. "
        "Vacío = no cambia.",
    )

    class Meta:
        model = Conductor
        fields = "__all__"

    def clean_nuevo_pin(self):
        pin = self.cleaned_data["nuevo_pin"]
        if pin:
            try:
                validar_pin(pin)
            except PinInvalido as error:
                raise forms.ValidationError(str(error)) from error
        return pin

    def save(self, commit=True):
        conductor = super().save(commit=False)
        if self.cleaned_data.get("nuevo_pin"):
            conductor.fijar_pin(self.cleaned_data["nuevo_pin"])
        if commit:
            conductor.save()
            self.save_m2m()
        return conductor


@admin.register(Conductor)
class ConductorAdmin(SinBorrarAdmin):
    form = ConductorForm
    list_display = ("nombre", "celular", "usuario", "activo", "pin_fijado")
    list_filter = ("activo",)
    search_fields = ("nombre", "celular")
    autocomplete_fields = ("usuario",)

    @admin.display(boolean=True, description="PIN fijado")
    def pin_fijado(self, obj):
        return obj.tiene_pin


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
