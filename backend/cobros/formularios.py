"""Formularios de la sección Cobros. Solo validan lo que se digita; las reglas del cobro las
aplican `cobros/operaciones.py` y `nucleo/cobro.py`."""
from typing import ClassVar

from django import forms

from clientes.models import Cliente
from nucleo.cobro import CobroInvalido, leer_pesos

SI, NO = "si", "no"


def _campo_lleva_iva():
    """La pregunta "¿Lleva IVA?" de Cobros. Sin respuesta por defecto: hay que elegir."""
    return forms.TypedChoiceField(
        label="¿Lleva IVA?",
        choices=[(SI, "Sí"), (NO, "No")],
        coerce=lambda valor: valor == SI,
        widget=forms.RadioSelect,
        error_messages={
            "required": "Responda si lleva IVA.",
            "invalid_choice": "Responda si lleva IVA.",
        },
    )


class ConPreguntaIva:
    """Las opciones de "¿Lleva IVA?" pueden decir el total que queda en cada caso."""

    def poner_opciones_iva(self, opciones):
        if opciones:
            si, no = opciones
            self.fields["lleva_iva"].choices = [(SI, si), (NO, no)]


class FormularioValor(forms.Form):
    valor = forms.CharField(
        label="Valor",
        max_length=30,
        error_messages={"required": "Escriba el valor."},
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
        help_text="En pesos, por ejemplo 180.000",
    )

    def clean_valor(self):
        try:
            return leer_pesos(self.cleaned_data["valor"])
        except CobroInvalido as error:
            raise forms.ValidationError(str(error)) from error


class FormularioFactura(forms.Form):
    """Número y total de la factura que se hizo en el programa de facturación (1a-19b): el total
    se compara con el de la orden para atrapar errores de digitación."""

    numero_factura = forms.CharField(
        label="Número de factura",
        max_length=60,
        error_messages={"required": "Escriba el número de factura."},
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    total_factura = forms.CharField(
        label="Total de la factura",
        max_length=30,
        error_messages={"required": "Escriba el total de la factura."},
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
        help_text="Tal como sale en la factura (con el IVA, si lo lleva), por ejemplo 1.190.000",
    )

    def clean_total_factura(self):
        try:
            return leer_pesos(self.cleaned_data["total_factura"])
        except CobroInvalido as error:
            raise forms.ValidationError(str(error)) from error


class FormularioFacturaLinea(ConPreguntaIva, FormularioFactura):
    """Facturar una línea suelta: además del número y el total, si lleva IVA."""

    lleva_iva = _campo_lleva_iva()

    def __init__(self, *args, opciones_iva=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.poner_opciones_iva(opciones_iva)


class FormularioDatosFacturacion(forms.ModelForm):
    """Datos de facturación del pagador (1a-19b). Se guardan en el cliente: la próxima orden ya los
    trae."""

    class Meta:
        model = Cliente
        fields = ("razon_social", "documento", "direccion", "ciudad", "correo_facturacion")
        labels: ClassVar[dict] = {"documento": "NIT o documento"}


class FormularioAnulacion(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación",
        max_length=500,
        error_messages={"required": "Escriba por qué se anula la factura."},
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class FormularioRelacion(forms.Form):
    """Pagador y rango de fechas para armar una relación. Las opciones de pagador son los clientes
    con líneas por facturar libres; la vista las pasa."""

    pagador = forms.ModelChoiceField(
        label="Pagador",
        queryset=None,
        empty_label="Elija el pagador",
        error_messages={"required": "Elija el pagador.", "invalid_choice": "Elija el pagador."},
    )
    desde = forms.DateField(
        label="Desde",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Elija la fecha inicial.", "invalid": "Fecha no válida."},
    )
    hasta = forms.DateField(
        label="Hasta",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Elija la fecha final.", "invalid": "Fecha no válida."},
    )

    def __init__(self, *args, pagadores, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pagador"].queryset = pagadores

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("hasta", "La fecha final va después de la inicial.")
        return datos


class FormularioArmarRelacion(ConPreguntaIva, FormularioRelacion):
    """Armar la relación ya vista: pagador y fechas (ocultos) y si lleva IVA."""

    lleva_iva = _campo_lleva_iva()

    def __init__(self, *args, opciones_iva=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.poner_opciones_iva(opciones_iva)


class FormularioDescarte(forms.Form):
    motivo = forms.CharField(
        label="Motivo del descarte",
        max_length=500,
        error_messages={"required": "Escriba por qué se descarta la relación."},
        widget=forms.Textarea(attrs={"rows": 2}),
    )
