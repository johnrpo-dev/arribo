"""Formularios de Flota y documentos: registrar un documento y crear o editar un tipo."""
from typing import ClassVar

from django import forms

from nucleo import documentos as regla

from .models import Documento, TipoDocumento

MEGAS_MAXIMOS = regla.TAMANO_MAXIMO_ARCHIVO // (1024 * 1024)


class FechaInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class FormularioDocumento(forms.Form):
    VENCE = "vence"
    AUN_NO_APLICA = "aun_no_aplica"

    situacion = forms.ChoiceField(
        label="Situación",
        choices=((VENCE, "Tiene fecha de vencimiento"), (AUN_NO_APLICA, "Aún no aplica")),
        initial=VENCE,
        widget=forms.RadioSelect,
    )
    vence = forms.DateField(
        label="Vence", required=False, widget=FechaInput,
        help_text="Sirve hasta este día inclusive.",
    )
    aplica_desde = forms.DateField(
        label="Aplica desde", required=False, widget=FechaInput,
        help_text="Solo si aún no aplica: el día desde el que se exige.",
    )
    numero = forms.CharField(
        label="Número", required=False, max_length=Documento._meta.get_field("numero").max_length
    )
    # Va al final del formulario: si el archivo pasa del máximo, lo que viene después no se lee.
    archivo = forms.FileField(
        label="Foto o PDF (opcional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
        help_text=f"JPEG, PNG o PDF de hasta {MEGAS_MAXIMOS} MB.",
    )

    def __init__(self, *args, archivo_excedido=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.archivo_excedido = archivo_excedido
        self.tipo_archivo = ""

    def clean_archivo(self):
        if self.archivo_excedido:
            raise forms.ValidationError(f"El archivo pesa más de {MEGAS_MAXIMOS} MB.")
        archivo = self.cleaned_data.get("archivo")
        if not archivo:
            return None
        if regla.excede_el_tamano(archivo.size):
            raise forms.ValidationError(f"El archivo pesa más de {MEGAS_MAXIMOS} MB.")
        tipo = regla.tipo_de_archivo(getattr(archivo, "cabecera", b""))
        if tipo is None:
            raise forms.ValidationError("El archivo debe ser una foto JPEG o PNG, o un PDF.")
        self.tipo_archivo = tipo
        return archivo

    def clean(self):
        datos = super().clean()
        situacion = datos.get("situacion")
        if situacion == self.VENCE:
            datos["aplica_desde"] = None
            if not datos.get("vence") and "vence" not in self.errors:
                self.add_error("vence", "Escriba la fecha de vencimiento.")
        elif situacion == self.AUN_NO_APLICA:
            datos["vence"] = None
            if not datos.get("aplica_desde") and "aplica_desde" not in self.errors:
                self.add_error("aplica_desde", "Escriba la fecha desde la que aplica.")
        return datos


class FormularioTipo(forms.ModelForm):
    class Meta:
        model = TipoDocumento
        fields = ("nombre", "aplica_a", "dias_anticipacion", "activo")
        widgets: ClassVar[dict] = {
            "aplica_a": forms.RadioSelect,
            "dias_anticipacion": forms.NumberInput(attrs={"min": 0}),
        }
        error_messages: ClassVar[dict] = {
            "dias_anticipacion": {"min_value": "Escriba un número de días, cero o más."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tiene_documentos = bool(self.instance.pk) and self.instance.documentos.exists()
        if self.tiene_documentos:
            # La base tampoco lo deja: sus documentos son de ese lado.
            self.fields["aplica_a"].disabled = True
            self.fields["aplica_a"].help_text = "Ya tiene documentos registrados: no cambia de lado."

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        if not nombre:
            raise forms.ValidationError("Escriba el nombre.")
        repetido = TipoDocumento.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya hay un tipo de documento con ese nombre.")
        return nombre
