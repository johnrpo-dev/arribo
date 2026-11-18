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


class FormularioDescarte(forms.Form):
    motivo = forms.CharField(
        label="Motivo del descarte",
        max_length=500,
        error_messages={"required": "Escriba por qué se descarta la relación."},
        widget=forms.Textarea(attrs={"rows": 2}),
    )
