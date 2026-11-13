"""Registro de una solicitud desde el formulario del panel.

`registrar_solicitud` crea en una sola transacción el cliente nuevo (si lo hay), los contactos, el
vehículo, la solicitud y su servicio. Si algo falla a mitad, no queda nada guardado. Qué le falta a
la solicitud para quedar abierta lo decide `nucleo/registro.py`; aquí solo se cargan los datos, se
pregunta al núcleo y se guarda.
"""
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from clientes.models import Cliente, Contacto, TelefonoCliente
from nucleo.registro import Faltante, faltantes_para_abrir

from .models import EstadoRegistro, Servicio, Solicitud, Vehiculo

# Filas del historial reciente que se muestran al encontrar al cliente por su teléfono.
FILAS_HISTORIAL = 5


@dataclass(frozen=True)
class ClienteNuevo:
    nombre: str
    tipo: str
    telefono: str  # ya normalizado


@dataclass(frozen=True)
class DatosContacto:
    nombre: str
    telefono: str  # ya normalizado


@dataclass(frozen=True)
class DatosVehiculo:
    placa: str  # ya normalizada
    vin: str  # ya normalizado y válido
    marca: str = ""
    linea: str = ""
    color: str = ""


@dataclass(frozen=True)
class DatosRegistro:
    """Lo que trae el formulario ya validado. `solicitante` o `cliente_nuevo`, uno de los dos."""

    tipo: str
    solicitante: Cliente | None = None
    cliente_nuevo: ClienteNuevo | None = None
    pagador: Cliente | None = None  # None = paga el solicitante
    origen: str = ""
    destino: str = ""
    contacto_origen: DatosContacto | None = None
    contacto_destino: DatosContacto | None = None
    vehiculo: DatosVehiculo | None = None
    programada_para: datetime | None = None


class VehiculoEnConflicto(ValueError):
    """La placa y el VIN digitados no pueden ser del mismo vehículo guardado."""

    def __init__(self, campo, mensaje):
        super().__init__(mensaje)
        self.campo = campo


def vehiculo_existente(placa: str, vin: str) -> Vehiculo | None:
    """El vehículo ya guardado con esa placa o ese VIN, o None si es nuevo.

    La placa y el VIN son únicos: si apuntan a vehículos distintos, o el vehículo guardado tiene
    otra placa u otro VIN, se lanza VehiculoEnConflicto con el campo al que corresponde el error.
    """
    por_placa = Vehiculo.objects.filter(placa=placa).first() if placa else None
    por_vin = Vehiculo.objects.filter(vin=vin).first() if vin else None
    if por_placa and por_vin and por_placa.pk != por_vin.pk:
        raise VehiculoEnConflicto("vin", f"Ese VIN ya es del vehículo {por_vin}.")
    if por_placa and vin and por_placa.vin and por_placa.vin != vin:
        raise VehiculoEnConflicto(
            "vin", f"El vehículo con placa {placa} ya tiene otro VIN: {por_placa.vin}."
        )
    if por_vin and placa and por_vin.placa and por_vin.placa != placa:
        raise VehiculoEnConflicto(
            "placa", f"El vehículo con ese VIN ya tiene otra placa: {por_vin.placa}."
        )
    return por_placa or por_vin


def historial_reciente(cliente) -> list[Solicitud]:
    """Últimas solicitudes que pidió el cliente, la más reciente primero."""
    return list(
        Solicitud.objects.filter(solicitante=cliente).order_by("-creada_en")[:FILAS_HISTORIAL]
    )


def faltantes_de(solicitud: Solicitud) -> list[Faltante]:
    """Lo que le falta a una solicitud guardada para quedar abierta."""
    return faltantes_para_abrir(
        tiene_solicitante=solicitud.solicitante_id is not None,
        tipo=solicitud.tipo,
        origen=solicitud.origen,
        destino=solicitud.destino,
        vehiculos=solicitud.servicios.count(),
        tiene_regreso=solicitud.tiene_regreso,
    )


def registrar_solicitud(
    datos: DatosRegistro, *, usuario, abrir: bool = True
) -> tuple[Solicitud, list[Faltante]]:
    """Guarda la solicitud. Queda abierta si `abrir` y no le falta nada; si no, borrador.

    Devuelve la solicitud y lo que le falta para quedar abierta (vacío si nada). Con vehículo,
    crea su servicio pendiente de asignar también en un borrador, para no perder lo digitado: un
    servicio de un borrador no se puede asignar (`operaciones.asignar` lo impide).
    """
    with transaction.atomic():
        solicitante = datos.solicitante or _crear_cliente(datos.cliente_nuevo)
        vehiculo = _vehiculo(datos.vehiculo) if datos.vehiculo else None
        faltantes = faltantes_para_abrir(
            tiene_solicitante=True,
            tipo=datos.tipo,
            origen=datos.origen,
            destino=datos.destino,
            vehiculos=1 if vehiculo else 0,
        )
        abierta = abrir and not faltantes
        solicitud = Solicitud.objects.create(
            solicitante=solicitante,
            pagador=datos.pagador or solicitante,
            tipo=datos.tipo,
            origen=datos.origen.strip(),
            destino=datos.destino.strip(),
            contacto_origen=_contacto(datos.contacto_origen),
            contacto_destino=_contacto(datos.contacto_destino),
            programada_para=datos.programada_para,
            estado_registro=EstadoRegistro.ABIERTA if abierta else EstadoRegistro.BORRADOR,
            creada_por=usuario,
        )
        if vehiculo is not None:
            _crear_servicio(solicitud, vehiculo)
    return solicitud, faltantes


def _crear_cliente(nuevo: ClienteNuevo) -> Cliente:
    cliente = Cliente.objects.create(nombre=nuevo.nombre.strip(), tipo=nuevo.tipo)
    TelefonoCliente.objects.create(cliente=cliente, numero=nuevo.telefono)
    return cliente


def _contacto(datos: DatosContacto | None) -> Contacto | None:
    """El contacto ya guardado con ese nombre y teléfono, o uno nuevo."""
    if datos is None:
        return None
    nombre = datos.nombre.strip()
    existente = Contacto.objects.filter(telefono=datos.telefono, nombre__iexact=nombre).first()
    return existente or Contacto.objects.create(nombre=nombre, telefono=datos.telefono)


def _vehiculo(datos: DatosVehiculo) -> Vehiculo:
    """El vehículo guardado (completando lo que le faltaba) o uno nuevo."""
    vehiculo = vehiculo_existente(datos.placa, datos.vin)
    if vehiculo is None:
        return Vehiculo.objects.create(
            placa=datos.placa,
            vin=datos.vin,
            marca=datos.marca.strip(),
            linea=datos.linea.strip(),
            color=datos.color.strip(),
        )
    cambios = []
    for campo in ("placa", "vin", "marca", "linea", "color"):
        nuevo = getattr(datos, campo).strip()
        if nuevo and not getattr(vehiculo, campo):
            setattr(vehiculo, campo, nuevo)
            cambios.append(campo)
    if cambios:
        vehiculo.save(update_fields=cambios)
    return vehiculo


def _crear_servicio(solicitud: Solicitud, vehiculo: Vehiculo) -> Servicio:
    return Servicio.objects.create(solicitud=solicitud, vehiculo=vehiculo)
