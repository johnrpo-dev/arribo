"""Datos de las pruebas de cobros, siempre contra PostgreSQL. Usa los de `tests/conftest.py`.

`entregado` es un servicio guardado directamente como Entregado (sin pasar por las operaciones), así
que todavía no tiene línea; `linea` es su línea inicial creada con la operación (sin valor, porque
el cliente no tiene tarifa).
"""
from decimal import Decimal

import pytest

from clientes.models import Cliente, Tarifa, TipoCliente
from cobros import operaciones
from cobros.models import LineaCobro
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio

VALOR = Decimal(180000)


@pytest.fixture
def otro_cliente():
    return Cliente.objects.create(nombre="Seguros Andinos", tipo=TipoCliente.ASEGURADORA)


@pytest.fixture
def tarifa_traslado(cliente):
    """Tarifa vigente de traslado del cliente de siempre (solicitante y pagador por defecto)."""
    return Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=VALOR)


@pytest.fixture
def entregado(crear_servicio):
    return crear_servicio(Estado.ENTREGADO)


@pytest.fixture
def linea(entregado) -> LineaCobro:
    return operaciones.crear_linea_al_entregar(entregado)


def guardar_linea(servicio, pagador, **campos) -> LineaCobro:
    """Una línea guardada directamente, sin operaciones: por defecto, posición 1 y sin valor."""
    datos = {"servicio": servicio, "pagador": pagador, "posicion": 1}
    datos.update(campos)
    return LineaCobro.objects.create(**datos)
