"""Formularios de "Flota y personal". Validan lo que escribe la persona de oficina con las reglas que
ya existen (PIN en `nucleo/ingreso.py`, celular en `nucleo/identificacion.py`, contraseña con los
validadores de Django) y muestran los errores en español junto a cada campo."""
from typing import ClassVar

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator

from nucleo.identificacion import TelefonoInvalido, normalizar_telefono
from nucleo.ingreso import LARGO_PIN, PinInvalido, validar_pin
from panel.roles import ADMINISTRADOR, FACTURACION, LOGISTICA, NOMBRES_DE_ROL

from .models import Conductor, Grua

Usuario = get_user_model()

OPCIONES_DE_ROL = [(rol, NOMBRES_DE_ROL[rol]) for rol in (LOGISTICA, FACTURACION, ADMINISTRADOR)]


def _campo_secreto(etiqueta, *, numerico=False, ayuda=""):
    atributos = {"autocomplete": "new-password"}
    if numerico:
        atributos.update(inputmode="numeric", maxlength=str(LARGO_PIN))
    return forms.CharField(
        label=etiqueta,
        strip=False,
        widget=forms.PasswordInput(render_value=False, attrs=atributos),
        help_text=ayuda,
    )


class _ConPin(forms.Form):
    pin = _campo_secreto(
        "PIN de la app",
        numerico=True,
        ayuda=f"{LARGO_PIN} dígitos. El conductor entra a la app con su celular y este PIN. "
        "No se puede volver a ver: si lo olvida, se le pone uno nuevo.",
    )
    pin_confirmacion = _campo_secreto("Repita el PIN", numerico=True)

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        try:
            validar_pin(pin)
        except PinInvalido as error:
            raise forms.ValidationError(str(error)) from error
        return pin

    def clean(self):
        datos = super().clean()
        if datos.get("pin") and datos.get("pin_confirmacion") != datos["pin"]:
            self.add_error("pin_confirmacion", "Los dos PIN no coinciden.")
        return datos


def _opciones_de_grua():
    return Grua.objects.filter(activa=True).order_by("placa")


class _CampoGrua(forms.ModelChoiceField):
    def label_from_instance(self, grua):
        texto = f"{grua.placa} ({grua.get_capacidad_display()})"
        if grua.estado_operativo != Grua.EstadoOperativo.OPERATIVA:
            texto += f", {grua.get_estado_operativo_display().lower()}"
        return texto


class _DatosConductor(forms.Form):
    """Nombre y celular. El celular se normaliza y no puede ser de otro conductor."""

    nombre = forms.CharField(label="Nombre", max_length=Conductor._meta.get_field("nombre").max_length)
    celular = forms.CharField(
        label="Celular",
        max_length=30,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
        help_text="Con el que el conductor entra a la app.",
    )

    def __init__(self, *args, conductor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.conductor = conductor

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if not nombre:
            raise forms.ValidationError("Escriba el nombre del conductor.")
        return nombre

    def clean_celular(self):
        try:
            celular = normalizar_telefono(self.cleaned_data["celular"])
        except TelefonoInvalido as error:
            raise forms.ValidationError(str(error)) from error
        otros = Conductor.objects.filter(celular=celular)
        if self.conductor is not None:
            otros = otros.exclude(pk=self.conductor.pk)
        otro = otros.first()
        if otro is not None:
            raise forms.ValidationError(f"Ya hay un conductor con el celular {celular}: {otro}.")
        return celular


class FormularioDatosConductor(_DatosConductor):
    """Nombre, celular y grúa en un solo formulario de la página del conductor."""

    grua = _CampoGrua(
        label="Grúa",
        queryset=Grua.objects.none(),
        required=False,
        empty_label="Sin grúa",
        help_text="Si la cambia, rige desde ahora. Los servicios ya hechos conservan la suya.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grua"].queryset = _opciones_de_grua()


class FormularioNuevoConductor(_ConPin, _DatosConductor):
    grua = _CampoGrua(
        label="Grúa",
        queryset=Grua.objects.none(),
        required=False,
        empty_label="Sin grúa por ahora",
        help_text="Opcional. Queda asignada desde ahora.",
    )

    field_order = ("nombre", "celular", "pin", "pin_confirmacion", "grua")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grua"].queryset = _opciones_de_grua()


class FormularioPin(_ConPin):
    pass


class _ConContrasena(forms.Form):
    contrasena = _campo_secreto("Contraseña")
    contrasena_confirmacion = _campo_secreto("Repita la contraseña")

    def usuario_para_validar(self):
        raise NotImplementedError

    def clean(self):
        datos = super().clean()
        contrasena = datos.get("contrasena")
        if not contrasena:
            return datos
        if datos.get("contrasena_confirmacion") != contrasena:
            self.add_error("contrasena_confirmacion", "Las dos contraseñas no coinciden.")
            return datos
        try:
            password_validation.validate_password(contrasena, self.usuario_para_validar())
        except forms.ValidationError as error:
            self.add_error("contrasena", error)
        return datos


class FormularioNuevoUsuario(_ConContrasena):
    nombre = forms.CharField(label="Nombre", max_length=150)
    usuario = forms.CharField(
        label="Usuario",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "none"}),
        help_text="Con el que entra al panel. Letras, números y los signos . @ + - _ (sin espacios).",
    )
    rol = forms.ChoiceField(label="Rol", choices=OPCIONES_DE_ROL)

    field_order = ("nombre", "usuario", "contrasena", "contrasena_confirmacion", "rol")

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if not nombre:
            raise forms.ValidationError("Escriba el nombre.")
        return nombre

    def clean_usuario(self):
        usuario = self.cleaned_data["usuario"].strip()
        try:
            UnicodeUsernameValidator()(usuario)
        except forms.ValidationError as error:
            raise forms.ValidationError(
                "Use solo letras, números y los signos . @ + - _ (sin espacios)."
            ) from error
        if Usuario.objects.filter(username__iexact=usuario).exists():
            raise forms.ValidationError(f"Ya existe un usuario llamado {usuario}. Elija otro.")
        return usuario

    def usuario_para_validar(self):
        return Usuario(
            username=self.cleaned_data.get("usuario", ""),
            first_name=self.cleaned_data.get("nombre", ""),
        )


class FormularioContrasena(_ConContrasena):
    contrasena = _campo_secreto("Contraseña nueva")
    contrasena_confirmacion = _campo_secreto("Repita la contraseña nueva")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def usuario_para_validar(self):
        return self.usuario


class FormularioRol(forms.Form):
    rol = forms.ChoiceField(label="Rol", choices=OPCIONES_DE_ROL)


class FormularioGrua(forms.ModelForm):
    class Meta:
        model = Grua
        fields = ("placa", "descripcion", "capacidad", "estado_operativo")
        widgets: ClassVar[dict] = {"placa": forms.TextInput(attrs={"autocapitalize": "characters"})}
        error_messages: ClassVar[dict] = {"placa": {"unique": "Ya hay una grúa con esa placa."}}
        help_texts: ClassVar[dict] = {
            "placa": "Se guarda en mayúsculas, sin espacios ni guiones.",
            "descripcion": "Opcional, por ejemplo marca y color.",
            "estado_operativo": "Una grúa fuera de servicio no recibe servicios nuevos.",
        }


class FormularioEditarGrua(FormularioGrua):
    class Meta(FormularioGrua.Meta):
        fields = (*FormularioGrua.Meta.fields, "activa")
        help_texts: ClassVar[dict] = {
            **FormularioGrua.Meta.help_texts,
            "activa": "Una grúa que ya no es de la empresa se desactiva; no se borra.",
        }
