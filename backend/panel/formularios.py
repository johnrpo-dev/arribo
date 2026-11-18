from typing import ClassVar

from django import forms
from django.contrib.auth.forms import AuthenticationForm


class FormularioIngreso(AuthenticationForm):
    """El de Django, con etiquetas y mensajes en el español del panel."""

    error_messages: ClassVar[dict[str, str]] = {
        "invalid_login": "Usuario o contraseña incorrectos. Revise mayúsculas y minúsculas.",
        "inactive": "Este usuario está desactivado. Pida ayuda al administrador.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["password"].label = "Contraseña"
        self.fields["password"].widget = forms.PasswordInput(
            attrs={"autocomplete": "current-password"}
        )


class FormularioPeriodo(forms.Form):
    """Del día tal al día tal (los dos incluidos), para el panel del dueño. Vacío = hoy."""

    desde = forms.DateField(
        label="Desde", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    hasta = forms.DateField(
        label="Hasta", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            raise forms.ValidationError("La fecha inicial va antes de la final.")
        return datos
