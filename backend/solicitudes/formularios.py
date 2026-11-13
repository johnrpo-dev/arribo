"""Formularios de solicitudes: validan y normalizan lo digitado; no guardan nada.

- `FormularioSolicitud`: el orden de los campos es el de una llamada en curso: quién llama, qué
  servicio, de dónde a dónde, cuándo, si un evento tiene regreso y quién paga.
- `FormularioVehiculos`: una fila por vehículo (cada vehículo es un servicio); se agregan filas
  con HTMX y, al completar un borrador, una fila de un servicio ya guardado se puede quitar.
- `FormularioNoConcretada`: motivo y detalle para cerrar una solicitud que no se concretó.
- `FormularioAsignacion`: el conductor (con su disponibilidad) para asignar o reasignar un servicio.

Lo que guarda es `solicitudes/registro.py`.
"""
from datetime import datetime

from django import forms
from django.urls import reverse_lazy
from django.utils import timezone

from clientes.models import Cliente, TipoCliente, buscar_cliente_por_telefono
from nucleo.identificacion import (
    TelefonoInvalido,
    VinInvalido,
    normalizar_placa,
    normalizar_telefono,
    normalizar_vin,
    validar_vin,
)
from nucleo.tipos import TipoServicio

from .models import OPCIONES_TIPO_SERVICIO, MotivoNoConcretada, Servicio, Solicitud, Vehiculo
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
LARGO_REFERENCIA = Servicio._meta.get_field("referencia_externa").max_length
PREFIJO_VEHICULOS = "vehiculos"
SI, NO = "si", "no"


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


def _fecha_hora(etiqueta, ayuda):
    return forms.DateTimeField(
        label=etiqueta,
        required=False,
        input_formats=[FORMATO_FECHA_HORA],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=FORMATO_FECHA_HORA),
        help_text=ayuda,
        error_messages={"invalid": "Escriba la fecha y la hora completas."},
    )


def _exigir_hora(formulario, campo):
    """Django también acepta solo la fecha (y la deja a medianoche): aquí se exige la hora."""
    texto = (formulario.data.get(formulario.add_prefix(campo)) or "").strip()
    if texto:
        try:
            datetime.strptime(texto, FORMATO_FECHA_HORA)
        except ValueError as error:
            raise forms.ValidationError("Escriba la fecha y la hora completas.") from error
    return formulario.cleaned_data[campo]


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
    programada_para = _fecha_hora(
        "Programada para", "Déjelo vacío si es inmediato. Hora de Colombia."
    )
    tiene_regreso = forms.ChoiceField(
        label="¿Tiene regreso?",
        required=False,
        choices=[(SI, "Sí"), (NO, "No")],
        widget=forms.RadioSelect,
    )
    fecha_regreso = _fecha_hora("Fecha y hora del regreso", "Hora de Colombia.")
    pagador_telefono = forms.CharField(
        label="Teléfono del pagador",
        max_length=30,
        required=False,
        help_text="Solo si paga otro cliente ya registrado. Vacío = paga quien llama.",
        widget=forms.TextInput(attrs=_busqueda_htmx("pagador")),
    )

    # Solo al completar un borrador cuyo pagador no es el solicitante: el pagador se conserva
    # aunque no tenga teléfono, y solo cambia si se busca otro o se marca `paga_solicitante`.
    pagador_actual = forms.IntegerField(required=False, widget=forms.HiddenInput)
    paga_solicitante = forms.BooleanField(
        label="Que pague quien llama (en vez del pagador actual)", required=False
    )

    solicitante: Cliente | None = None
    pagador: Cliente | None = None

    def __init__(self, *args, solicitud: Solicitud | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.solicitud = solicitud

    @property
    def pagador_a_conservar(self) -> Cliente | None:
        """El pagador del borrador, si es distinto del solicitante (None en otro caso)."""
        s = self.solicitud
        if s is None or s.pagador_id is None or s.pagador_id == s.solicitante_id:
            return None
        return s.pagador

    def _pagador(self, datos):
        """Quién paga. Sin teléfono de pagador: en un registro nuevo, quien llama; al completar
        un borrador, el pagador que ya tenía, salvo que se marque `paga_solicitante`. El
        pagador nunca cambia por ausencia de un dato."""
        conservar = self.pagador_a_conservar
        mostrado = datos.get("pagador_actual")
        if mostrado is not None and (conservar is None or mostrado != conservar.pk):
            # El formulario se abrió con otro pagador: otra persona lo cambió mientras tanto.
            self.add_error(
                None, "El pagador de esta solicitud cambió mientras tanto. Recargue la página."
            )
            return
        if self.pagador is None and conservar is not None and not datos.get("paga_solicitante"):
            self.pagador = conservar

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
        return _exigir_hora(self, "programada_para")

    def clean_fecha_regreso(self):
        return _exigir_hora(self, "fecha_regreso")

    def clean_tipo(self):
        tipo = self.cleaned_data["tipo"]
        if not tipo:
            raise forms.ValidationError("Elija el tipo de servicio.")
        return tipo

    # --- Conjunto ---------------------------------------------------------------------------

    def clean(self):
        datos = super().clean()
        self._solicitante(datos)
        for lugar in ("origen", "destino"):
            self._contacto(datos, lugar)
        self._regreso(datos)
        if "pagador_telefono" not in self.errors:
            self._pagador(datos)
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

    def _regreso(self, datos):
        """En un evento con regreso, la fecha del regreso va con la respuesta (la base lo exige)."""
        if datos.get("tipo") != TipoServicio.EVENTO or "fecha_regreso" in self.errors:
            return
        if datos.get("tiene_regreso") == SI and not datos.get("fecha_regreso"):
            self.add_error("fecha_regreso", "Escriba la fecha y la hora del regreso.")

    # --- Salida -----------------------------------------------------------------------------

    def datos_registro(self, vehiculos: tuple[DatosVehiculo, ...]) -> DatosRegistro:
        """Lo validado, listo para `registro.registrar_solicitud` o `completar_borrador`."""
        d = self.cleaned_data
        cliente_nuevo = None
        if self.solicitante is None:
            cliente_nuevo = ClienteNuevo(d["nuevo_nombre"], d["nuevo_tipo"], d["telefono"])
        respuesta = {SI: True, NO: False}.get(d["tiene_regreso"])
        return DatosRegistro(
            tipo=d["tipo"],
            solicitante=self.solicitante,
            cliente_nuevo=cliente_nuevo,
            pagador=self.pagador,
            origen=d["origen"],
            destino=d["destino"],
            contacto_origen=self._datos_contacto("origen"),
            contacto_destino=self._datos_contacto("destino"),
            vehiculos=vehiculos,
            programada_para=d["programada_para"],
            tiene_regreso=respuesta,
            fecha_regreso=d["fecha_regreso"] if respuesta else None,
        )

    def _datos_contacto(self, lugar):
        nombre = self.cleaned_data[f"contacto_{lugar}_nombre"].strip()
        if not nombre:
            return None
        return DatosContacto(nombre, self.cleaned_data[f"contacto_{lugar}_telefono"])


def inicial_de(solicitud: Solicitud) -> dict:
    """Los datos de un borrador para mostrarlos en el formulario al completarlo."""
    pagador_telefono, pagador_actual = "", None
    if solicitud.pagador_id != solicitud.solicitante_id:
        pagador_telefono = _primer_telefono(solicitud.pagador)
        pagador_actual = solicitud.pagador_id
    regreso = {True: SI, False: NO}.get(solicitud.tiene_regreso, "")
    inicial = {
        "telefono": _primer_telefono(solicitud.solicitante),
        "tipo": solicitud.tipo,
        "origen": solicitud.origen,
        "destino": solicitud.destino,
        "programada_para": _hora_local(solicitud.programada_para),
        "tiene_regreso": regreso,
        "fecha_regreso": _hora_local(solicitud.fecha_regreso),
        "pagador_telefono": pagador_telefono,
        "pagador_actual": pagador_actual,
    }
    for lugar in ("origen", "destino"):
        contacto = getattr(solicitud, f"contacto_{lugar}")
        if contacto is not None:
            inicial[f"contacto_{lugar}_nombre"] = contacto.nombre
            inicial[f"contacto_{lugar}_telefono"] = contacto.telefono
    return inicial


def _primer_telefono(cliente) -> str:
    telefono = cliente.telefonos.order_by("pk").first()
    return telefono.numero if telefono else ""


def _hora_local(momento):
    return timezone.localtime(momento) if momento else None


# --- Vehículos ---------------------------------------------------------------------------------


class FormularioVehiculo(forms.Form):
    """Una fila: un vehículo, que será un servicio de la solicitud."""

    servicio = forms.IntegerField(required=False, widget=forms.HiddenInput)
    placa = _texto("Placa", 20)
    vin = _texto("VIN", 25)
    marca = _texto("Marca", 60)
    linea = _texto("Línea", 60)
    color = _texto("Color", 40)
    referencia_externa = _texto(
        "Referencia externa",
        LARGO_REFERENCIA,
        help_text="Número de caso. Obligatoria si paga una aseguradora.",
    )
    quitar = forms.BooleanField(label="Quitar este vehículo", required=False)

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

    def clean(self):
        datos = super().clean()
        if self.errors:
            return datos
        fila = self.datos()
        if fila.servicio_id is not None and not fila.quitar and not fila.tiene_datos:
            self.add_error("placa", "Escriba los datos del vehículo o marque Quitar.")
        elif fila.servicio_id is None and not fila.tiene_datos and fila.referencia_externa:
            self.add_error("placa", "Escriba la placa, el VIN u otro dato del vehículo.")
        if fila.quitar:
            return datos
        try:
            vehiculo_existente(fila.placa, fila.vin)
        except VehiculoEnConflicto as error:
            self.add_error(error.campo, str(error))
        return datos

    def datos(self) -> DatosVehiculo:
        d = self.cleaned_data
        return DatosVehiculo(
            placa=d.get("placa", ""),
            vin=d.get("vin", ""),
            marca=d.get("marca", ""),
            linea=d.get("linea", ""),
            color=d.get("color", ""),
            referencia_externa=d.get("referencia_externa", "").strip(),
            servicio_id=d.get("servicio"),
            quitar=bool(d.get("servicio") is not None and d.get("quitar")),
        )


class BaseFormularioVehiculos(forms.BaseFormSet):
    """Las filas de vehículos. `servicios` son los servicios del borrador que se pueden editar."""

    def __init__(self, *args, servicios=frozenset(), **kwargs):
        kwargs.setdefault("prefix", PREFIJO_VEHICULOS)
        super().__init__(*args, **kwargs)
        self.servicios = frozenset(servicios)

    def clean(self):
        if any(self.errors):
            return
        vistos = {}
        for fila in self.forms:
            datos = fila.datos()
            if datos.servicio_id is not None and datos.servicio_id not in self.servicios:
                raise forms.ValidationError("Un vehículo no es de esta solicitud. Recargue la página.")
            if datos.quitar:
                continue
            for campo in ("placa", "vin"):
                valor = getattr(datos, campo)
                if not valor:
                    continue
                if (campo, valor) in vistos:
                    fila.add_error(campo, "Este vehículo ya está en otra fila.")
                vistos[(campo, valor)] = fila

    def datos(self) -> tuple[DatosVehiculo, ...]:
        """Las filas con algo digitado (o que quitan un servicio), en orden."""
        filas = (fila.datos() for fila in self.forms)
        return tuple(f for f in filas if f.tiene_datos or f.servicio_id is not None)


FormularioVehiculos = forms.formset_factory(
    FormularioVehiculo, formset=BaseFormularioVehiculos, extra=0
)


def inicial_vehiculos(servicios) -> list[dict]:
    """Una fila por servicio del borrador; sin servicios, una fila vacía."""
    filas = [
        {
            "servicio": s.pk,
            "placa": s.vehiculo.placa,
            "vin": s.vehiculo.vin,
            "marca": s.vehiculo.marca,
            "linea": s.vehiculo.linea,
            "color": s.vehiculo.color,
            "referencia_externa": s.referencia_externa,
        }
        for s in servicios
    ]
    return filas or [{}]


def fila_vehiculo(indice: int) -> FormularioVehiculo:
    """Una fila nueva y vacía para agregar con HTMX (la posición `indice` del conjunto)."""
    return FormularioVehiculo(prefix=f"{PREFIJO_VEHICULOS}-{indice}")


# --- No concretada -----------------------------------------------------------------------------


class FormularioNoConcretada(forms.Form):
    motivo = forms.ChoiceField(
        label="Motivo",
        choices=[("", "Elija el motivo")] + MotivoNoConcretada.choices,
        error_messages={"required": "Elija el motivo por el que no se concretó."},
    )
    detalle = forms.CharField(
        label="Detalle",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class SelectConDeshabilitadas(forms.Select):
    """Un select en el que algunas opciones se ven pero no se pueden elegir."""

    def __init__(self, *args, deshabilitadas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.deshabilitadas = {str(valor) for valor in deshabilitadas}

    def create_option(self, name, value, *args, **kwargs):
        opcion = super().create_option(name, value, *args, **kwargs)
        if str(value) in self.deshabilitadas:
            opcion["attrs"]["disabled"] = True
        return opcion


def describir_disponibilidad(disponibilidad) -> str:
    """Texto de un conductor en la lista para elegir: grúa, carga o por qué está bloqueado."""
    nombre = disponibilidad.conductor.nombre
    if disponibilidad.bloqueado:
        return f"{nombre} · bloqueado: {' '.join(disponibilidad.motivos)}"
    grua = disponibilidad.grua
    puestos = "1 puesto" if grua.capacidad == 1 else f"{grua.capacidad} puestos"
    return (
        f"{nombre} · {grua.placa}, {puestos} · {disponibilidad.no_terminales} en ronda, "
        f"{disponibilidad.montados} montados"
    )


class FormularioAsignacion(forms.Form):
    """Elegir conductor para asignar o reasignar un servicio. Los bloqueados se ven deshabilitados
    con su motivo; si de todos modos llegan, la operación los rechaza."""

    conductor = forms.TypedChoiceField(
        label="Conductor",
        coerce=int,
        error_messages={
            "required": "Elija el conductor.",
            "invalid_choice": "Elija un conductor de la lista.",
        },
    )
    motivo = forms.CharField(
        label="Motivo del cambio (opcional)", required=False, max_length=200
    )

    def __init__(self, *args, disponibilidades, excluir=None, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = [
            (d.conductor.pk, describir_disponibilidad(d))
            for d in disponibilidades
            if d.conductor.pk != excluir
        ]
        campo = self.fields["conductor"]
        campo.choices = [("", "Elija el conductor")] + opciones
        campo.widget = SelectConDeshabilitadas(
            choices=campo.choices,
            deshabilitadas=[d.conductor.pk for d in disponibilidades if d.bloqueado],
        )


def _mensaje_telefono(error: TelefonoInvalido) -> str:
    return str(error).split(";")[0] + "."


def _telefono(texto):
    try:
        return normalizar_telefono(texto)
    except TelefonoInvalido as error:
        raise forms.ValidationError(_mensaje_telefono(error)) from error
