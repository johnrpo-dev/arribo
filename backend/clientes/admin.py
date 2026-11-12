"""Admin de clientes. Nada se borra: el cliente se desactiva y la tarifa se marca como no vigente."""
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from flota.admin import SinBorrarAdmin

from .models import Cliente, Contacto, Tarifa, TelefonoCliente, buscar_cliente_por_telefono


class SinBorrarInline:
    can_delete = False

    def has_delete_permission(self, request, obj=None):
        return False


class TelefonosDelClienteFormSet(BaseInlineFormSet):
    """El mismo número escrito de dos formas en un mismo envío: avisar antes de que falle la base."""

    def clean(self):
        super().clean()
        vistos = set()
        for formulario in self.forms:
            datos = getattr(formulario, "cleaned_data", None) or {}
            if not datos.get("numero"):
                continue
            numero = formulario.instance.numero  # ya normalizado por TelefonoCliente.clean()
            if numero in vistos:
                raise ValidationError(f"El teléfono {numero} está repetido.")
            vistos.add(numero)


class TelefonoClienteInline(SinBorrarInline, admin.TabularInline):
    model = TelefonoCliente
    formset = TelefonosDelClienteFormSet
    extra = 1


class TarifasDelClienteFormSet(BaseInlineFormSet):
    """Dos filas vigentes del mismo tipo en un mismo envío: avisar antes de que falle la base."""

    def clean(self):
        super().clean()
        vistos = set()
        for formulario in self.forms:
            datos = getattr(formulario, "cleaned_data", None) or {}
            if not datos.get("vigente") or not datos.get("tipo_servicio"):
                continue
            if datos["tipo_servicio"] in vistos:
                raise ValidationError(
                    "Hay dos tarifas vigentes para el mismo tipo de servicio. "
                    "Deje solo una como vigente."
                )
            vistos.add(datos["tipo_servicio"])


class TarifaInline(SinBorrarInline, admin.TabularInline):
    model = Tarifa
    formset = TarifasDelClienteFormSet
    extra = 1


@admin.register(Cliente)
class ClienteAdmin(SinBorrarAdmin):
    list_display = ("nombre", "tipo", "documento", "modalidad_cobro", "firma_obligatoria", "activo")
    list_filter = ("activo", "tipo", "modalidad_cobro")
    search_fields = ("nombre", "documento", "telefonos__numero")
    inlines = (TelefonoClienteInline, TarifaInline)

    def get_search_results(self, request, queryset, search_term):
        # Buscar "+57 300 123 4567" o "300-123-4567" también encuentra al dueño del teléfono.
        resultados, hay_duplicados = super().get_search_results(request, queryset, search_term)
        cliente = buscar_cliente_por_telefono(search_term)
        if cliente is not None:
            resultados = resultados | queryset.filter(pk=cliente.pk)
            hay_duplicados = True
        return resultados, hay_duplicados


@admin.register(TelefonoCliente)
class TelefonoClienteAdmin(SinBorrarAdmin):
    list_display = ("numero", "cliente", "etiqueta")
    search_fields = ("numero", "cliente__nombre")
    autocomplete_fields = ("cliente",)


@admin.register(Contacto)
class ContactoAdmin(SinBorrarAdmin):
    list_display = ("nombre", "telefono", "cliente")
    search_fields = ("nombre", "telefono", "cliente__nombre")
    autocomplete_fields = ("cliente",)


@admin.register(Tarifa)
class TarifaAdmin(SinBorrarAdmin):
    list_display = ("cliente", "tipo_servicio", "valor", "descripcion", "vigente")
    list_filter = ("vigente", "tipo_servicio")
    search_fields = ("cliente__nombre", "descripcion")
    autocomplete_fields = ("cliente",)
