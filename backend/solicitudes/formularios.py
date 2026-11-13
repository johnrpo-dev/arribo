"""Formulario de registro de solicitud: valida y normaliza lo digitado; no guarda nada.

El orden de los campos es el de una llamada en curso: quién llama, qué servicio, de dónde a dónde,
qué vehículo, cuándo y quién paga. Lo que guarda es `solicitudes/registro.py`.
"""
from dataclasses import astuple
from datetime import datetime

from django import forms
from django.urls import reverse_lazy

from clientes.models import Cliente, TipoCliente, buscar_cliente_por_telefono
from nucleo.identificacion import (
    TelefonoInvalido,
    VinInvalido,
    normalizar_placa,
    normalizar_telefono,
    normalizar_vin,
    validar_vin,
)

from .models import OPCIONES_TIPO_SERVICIO, Vehiculo
from .registro import (
    ClienteNuevo,
    DatosContacto,
    DatosRegistro,
    DatosVehiculo,
    VehiculoEnConflicto,
    vehiculo_existente,
)

FORMATO_FECHA_HORA = "%Y-%m-%dT%H:%M"
LARGO_PLACA = Vehiculo._meta.get_field("placa").max_length


def _busqueda_htmx(para):
    """Atributos del campo de teléfono que busca al cliente sin recargar la página."""
    return {
        "type": "tel",
        "autocomplete": "off",
        "hx-get": reverse_lazy("buscar_cliente"),
        "hx-trigger": "input changed delay:300ms, change",
        "hx-target": f"#resultado-{para}",
        "hx-vals": f'{{"para": "{para}"}}',
        "hx-sync": "this:replace",
    }


def _texto(etiqueta, largo, **otros):
    return forms.CharField(label=etiqueta, max_length=largo, required=False, **otros)


class FormularioSolicitud(forms.Form):
    telefono = forms.CharField(
        label="Teléfono de quien llama",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"autofocus": True, **_busqueda_htmx("solicitante")}),
    )
    nuevo_nombre = _texto("Nombre del cliente nuevo", 200)
    nuevo_tipo = forms.ChoiceField(
        label="Tipo de cliente",
        required=False,
        choices=[("", "Elija el tipo")] + TipoCliente.choices,
    )
    tipo = forms.ChoiceField(
        label="Tipo de servicio",
        required=False,
        choices=[("", "Elija el tipo")] + OPCIONES_TIPO_SERVICIO,
    )
    origen = _texto("Origen", 300)
    contacto_origen_nombre = _texto("Contacto en el origen", 120)
    contacto_origen_telefono = _texto(
        "Teléfono del contacto en el origen", 30, widget=forms.TextInput(attrs={"type": "tel"})
    )
    destino = _texto("Destino", 300, help_text="Opcional en un desvare.")
    contacto_destino_nombre = _texto("Contacto en el destino", 120)
    contacto_destino_telefono = _texto(
        "Teléfono del contacto en el destino", 30, widget=forms.TextInput(attrs={"type": "tel"})
    )
    placa = _texto("Placa", 20)
    vin = _texto("VIN", 25)
    marca = _texto("Marca", 60)
    linea = _texto("Línea", 60)
    color = _texto("Color", 40)
    programada_para = forms.DateTimeField(
        label="Programada para",
        required=False,
        input_formats=[FORMATO_FECHA_HORA],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=FORMATO_FECHA_HORA),
        help_text="Déjelo vacío si es inmediato. Hora de Colombia.",
        error_messages={"invalid": "Escriba la fecha y la hora completas."},
    )
    pagador_telefono = forms.CharField(
        label="Teléfono del pagador",
        max_length=30,
        required=False,
        help_text="Solo si paga otro cliente ya registrado. Vacío = paga quien llama.",
        widget=forms.TextInput(attrs=_busqueda_htmx("pagador")),
    )

    solicitante: Cliente | None = None
    pagador: Cliente | None = None

    # --- Campos -----------------------------------------------------------------------------

    def clean_telefono(self):
        texto = self.cleaned_data["telefono"]
        if not texto.strip():
            raise forms.ValidationError("Escriba el teléfono de quien llama.")
        return _telefono(texto)

    def clean_pagador_telefono(self):
        texto = self.cleaned_data["pagador_telefono"]
        if not texto.strip():
            return ""
        numero = _telefono(texto)
        self.pagador = buscar_cliente_por_telefono(numero)
        if self.pagador is None:
            raise forms.ValidationError("No hay ningún cliente con ese teléfono.")
        return numero

    def clean_programada_para(self):
        # Django también acepta solo la fecha (y la deja a medianoche): aquí se exige la hora.
        texto = (self.data.get("programada_para") or "").strip()
        if texto:
            try:
                datetime.strptime(texto, FORMATO_FECHA_HORA)
            except ValueError as error:
                raise forms.ValidationError("Escriba la fecha y la hora completas.") from error
        return self.cleaned_data["programada_para"]

    def clean_tipo(self):
        tipo = self.cleaned_data["tipo"]
        if not tipo:
            raise forms.ValidationError("Elija el tipo de servicio.")
        return tipo

    def clean_placa(self):
        placa = normalizar_placa(self.cleaned_data["placa"])
        if len(placa) > LARGO_PLACA:
            raise forms.ValidationError(
                f"La placa tiene como máximo {LARGO_PLACA} letras o dígitos."
            )
        return placa

    def clean_vin(self):
        vin = normalizar_vin(self.cleaned_data["vin"])
        if vin:
            try:
                validar_vin(vin)
            except VinInvalido as error:
                raise forms.ValidationError(str(error)) from error
        return vin

    # --- Conjunto ---------------------------------------------------------------------------

    def clean(self):
        datos = super().clean()
        self._solicitante(datos)
        for lugar in ("origen", "destino"):
            self._contacto(datos, lugar)
        self._vehiculo(datos)
        return datos

    def _solicitante(self, datos):
        numero = datos.get("telefono")
        if not numero:
            return
        self.solicitante = buscar_cliente_por_telefono(numero)
        if self.solicitante is not None:
            return
        if not datos.get("nuevo_nombre", "").strip():
            self.add_error("nuevo_nombre", "Escriba el nombre del cliente nuevo.")
        if not datos.get("nuevo_tipo"):
            self.add_error("nuevo_tipo", "Elija el tipo de cliente.")

    def _contacto(self, datos, lugar):
        """Nombre y teléfono van juntos: con uno solo, el error queda junto al que falta."""
        campo_nombre, campo_telefono = f"contacto_{lugar}_nombre", f"contacto_{lugar}_telefono"
        if campo_nombre in self.errors or campo_telefono in self.errors:
            return
        nombre, texto = datos.get(campo_nombre, ""), datos.get(campo_telefono, "")
        if nombre and not texto:
            self.add_error(campo_telefono, "Escriba el teléfono del contacto.")
        elif texto and not nombre:
            self.add_error(campo_nombre, "Escriba el nombre del contacto.")
        elif nombre:
            try:
                datos[campo_telefono] = normalizar_telefono(texto)
            except TelefonoInvalido as error:
                self.add_error(campo_telefono, _mensaje_telefono(error))

    def _vehiculo(self, datos):
        if "placa" in self.errors or "vin" in self.errors:
            return
        try:
            vehiculo_existente(datos.get("placa", ""), datos.get("vin", ""))
        except VehiculoEnConflicto as error:
            self.add_error(error.campo, str(error))

    # --- Salida -----------------------------------------------------------------------------

    def datos_registro(self) -> DatosRegistro:
        """Lo validado, listo para `registro.registrar_solicitud`."""
        d = self.cleaned_data
        cliente_nuevo = None
        if self.solicitante is None:
            cliente_nuevo = ClienteNuevo(d["nuevo_nombre"], d["nuevo_tipo"], d["telefono"])
        vehiculo = DatosVehiculo(d["placa"], d["vin"], d["marca"], d["linea"], d["color"])
        return DatosRegistro(
            tipo=d["tipo"],
            solicitante=self.solicitante,
            cliente_nuevo=cliente_nuevo,
            pagador=self.pagador,
            origen=d["origen"],
            destino=d["destino"],
            contacto_origen=self._datos_contacto("origen"),
            contacto_destino=self._datos_contacto("destino"),
            vehiculo=vehiculo if any(astuple(vehiculo)) else None,
            programada_para=d["programada_para"],
        )

    def _datos_contacto(self, lugar):
        nombre = self.cleaned_data[f"contacto_{lugar}_nombre"].strip()
        if not nombre:
            return None
        return DatosContacto(nombre, self.cleaned_data[f"contacto_{lugar}_telefono"])


def _mensaje_telefono(error: TelefonoInvalido) -> str:
    return str(error).split(";")[0] + "."


def _telefono(texto):
    try:
        return normalizar_telefono(texto)
    except TelefonoInvalido as error:
        raise forms.ValidationError(_mensaje_telefono(error)) from error
