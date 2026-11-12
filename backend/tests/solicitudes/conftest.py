"""Datos comunes de las pruebas de solicitudes, siempre contra PostgreSQL.

Ana maneja la grúa GRU001 (1 puesto) y Beto la GRU002 (2 puestos), ambas asignaciones vigentes
desde ayer. `crear_servicio` deja un servicio en cualquier estado guardándolo directamente (sin
operaciones), con el conductor y la grúa que ese estado exige.
"""
import itertools
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from clientes.models import Cliente, TipoCliente
from flota.models import AsignacionConductorGrua, Conductor, Grua, grua_vigente
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes.models import EstadoRegistro, Servicio, Solicitud, Vehiculo

BOGOTA = ZoneInfo("America/Bogota")
VIN = "1HGCM82633A004352"


def hora(minuto: int) -> datetime:
    """Una hora fija del 12 de noviembre de 2026 en Medellín (para la hora del celular)."""
    return datetime(2026, 11, 12, 8, 0, tzinfo=BOGOTA) + timedelta(minutes=minuto)


def conductor_con_grua(nombre, celular, grua):
    conductor = Conductor.objects.create(nombre=nombre, celular=celular)
    AsignacionConductorGrua.objects.create(
        conductor=conductor, grua=grua, inicio=timezone.now() - timedelta(days=1)
    )
    return conductor


@pytest.fixture
def cliente():
    return Cliente.objects.create(nombre="Autos del Valle", tipo=TipoCliente.CONCESIONARIO)


@pytest.fixture
def grua1():
    return Grua.objects.create(placa="GRU001", capacidad=1)


@pytest.fixture
def grua2():
    return Grua.objects.create(placa="GRU002", capacidad=2)


@pytest.fixture
def ana(grua1):
    return conductor_con_grua("Ana", "3000000001", grua1)


@pytest.fixture
def beto(grua2):
    return conductor_con_grua("Beto", "3000000002", grua2)


@pytest.fixture
def usuario(django_user_model):
    return django_user_model.objects.create_user("logistica")


def crear_solicitud(cliente, tipo=TipoServicio.TRASLADO, **otros):
    datos = {
        "solicitante": cliente,
        "tipo": tipo,
        "origen": "Calle 10 # 43-20, El Poblado",
        "destino": "Carrera 70 # 1-50, Belén",
        "estado_registro": EstadoRegistro.ABIERTA,
    }
    datos.update(otros)
    return Solicitud.objects.create(**datos)


@pytest.fixture
def solicitud(cliente):
    """Solicitud abierta de traslado."""
    return crear_solicitud(cliente)


@pytest.fixture
def nuevo_vehiculo():
    """Fábrica de vehículos con placa distinta en cada llamada (o la identificación que se pida)."""
    numeros = itertools.count(1)

    def crear(**datos):
        if "placa" not in datos and "vin" not in datos:
            datos["placa"] = f"AAA{next(numeros):03d}"
        return Vehiculo.objects.create(**datos)

    return crear


@pytest.fixture
def crear_servicio(solicitud, ana, nuevo_vehiculo):
    """Fábrica de servicios guardados directamente en el estado pedido.

    Fuera de pendiente_asignar llevan conductor (Ana por defecto) y su grúa vigente; una novedad
    recuerda por defecto que venía de en_camino.
    """

    def crear(
        estado=Estado.PENDIENTE_ASIGNAR,
        *,
        conductor=None,
        grua=None,
        previo=None,
        vehiculo=None,
        solicitud_de=None,
    ):
        estado = Estado(estado)
        if estado == Estado.NOVEDAD and previo is None:
            previo = Estado.EN_CAMINO
        if estado != Estado.PENDIENTE_ASIGNAR:
            conductor = conductor or ana
            grua = grua or grua_vigente(conductor)
        return Servicio.objects.create(
            solicitud=solicitud_de or solicitud,
            vehiculo=vehiculo or nuevo_vehiculo(),
            estado=estado,
            estado_previo=Estado(previo).value if previo else "",
            conductor=conductor,
            grua=grua,
        )

    return crear


@pytest.fixture
def evento_app(ana):
    """Datos de un evento de la app con lo mínimo que manda el celular, más lo que se pase."""

    def datos(servicio, destino, *, secuencia=1, **otros):
        base = {
            "id": uuid.uuid4(),
            "servicio": servicio,
            "conductor": ana,
            "destino": destino,
            "secuencia": secuencia,
            "hora_dispositivo": hora(secuencia),
        }
        base.update(otros)
        return base

    return datos
