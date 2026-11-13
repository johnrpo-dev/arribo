from typing import ClassVar

from django import forms

from .models import COSTO_MENSUAL_RETENCION, MAXIMO_FOTOS, Configuracion

UMBRALES = (
    "alerta_sin_asignar_minutos",
    "alerta_programado_sin_asignar_horas",
    "alerta_sin_en_camino_minutos",
    "alerta_recogido_sin_entregado_horas",
    "alerta_sin_facturar_dias",
    "alerta_sin_pagar_dias",
)


class HoraInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")


class FormularioConfiguracion(forms.ModelForm):
    # El administrador siempre ve valores: se muestra marcado y deshabilitado, y no se guarda desde
    # el formulario (el campo del modelo no es editable y la base lo exige verdadero).
    ven_valores_administrador = forms.BooleanField(
        label="Administrador", required=False, disabled=True, initial=True
    )

    class Meta:
        model = Configuracion
        fields = (
            "momento_placa_vin",
            "minimo_fotos",
            "ven_valores_logistica",
            "ven_valores_facturacion",
            "retencion_fotos",
            *UMBRALES,
            "nocturno_inicio",
            "nocturno_fin",
            "formato_exportacion",
        )
        labels: ClassVar[dict] = {
            "ven_valores_logistica": "Logística",
            "ven_valores_facturacion": "Facturación",
            "nocturno_inicio": "Inicio",
            "nocturno_fin": "Fin",
        }
        widgets: ClassVar[dict] = {
            "momento_placa_vin": forms.RadioSelect,
            "retencion_fotos": forms.RadioSelect,
            "minimo_fotos": forms.NumberInput(attrs={"min": 0, "max": MAXIMO_FOTOS}),
            **{nombre: forms.NumberInput(attrs={"min": 1}) for nombre in UMBRALES},
            "nocturno_inicio": HoraInput,
            "nocturno_fin": HoraInput,
        }
        error_messages: ClassVar[dict] = {
            "minimo_fotos": {
                "min_value": f"El mínimo de fotos va de 0 a {MAXIMO_FOTOS}.",
                "max_value": f"El mínimo de fotos va de 0 a {MAXIMO_FOTOS}.",
            },
            **{nombre: {"min_value": "Escriba un número mayor que cero."} for nombre in UMBRALES},
        }

    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get("nocturno_inicio"), datos.get("nocturno_fin")
        if inicio is not None and fin is not None and inicio == fin:
            self.add_error("nocturno_fin", "El fin debe ser distinto del inicio.")
        return datos

    def campos_umbral(self):
        return [self[nombre] for nombre in UMBRALES]

    def opciones_retencion(self):
        """Cada opción de retención con su costo mensual estimado."""
        return [
            (opcion, COSTO_MENSUAL_RETENCION[opcion.data["value"]])
            for opcion in self["retencion_fotos"]
        ]
