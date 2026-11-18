"""Formularios de la sección Cobros. Solo validan lo que se digita; las reglas del cobro las
aplican `cobros/operaciones.py` y `nucleo/cobro.py`."""
from django import forms

from nucleo.cobro import CobroInvalido, leer_pesos


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
    numero_factura = forms.CharField(
        label="Número de factura",
        max_length=60,
        error_messages={"required": "Escriba el número de factura."},
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )


class FormularioAnulacion(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación",
        max_length=500,
        error_messages={"required": "Escriba por qué se anula la factura."},
        widget=forms.Textarea(attrs={"rows": 2}),
    )
