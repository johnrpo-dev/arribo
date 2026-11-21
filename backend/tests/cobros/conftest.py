"""Datos de las pruebas de cobros, siempre contra PostgreSQL. Usa los de `tests/conftest.py`.

`entregado` es un servicio guardado directamente como Entregado (sin pasar por las operaciones), así
que todavía no tiene línea; `linea` es su línea inicial creada con la operación (sin valor, porque
el cliente no tiene tarifa).
"""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from clientes.models import Cliente, Tarifa, TipoCliente
from cobros import operaciones
from cobros.models import LineaCobro
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes.models import EventoEstado
from tests.panel.conftest import crear_usuario  # noqa: F401

VALOR = Decimal(180000)
EL_5_DE_NOVIEMBRE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


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


@pytest.fixture
def facturacion(client, crear_usuario):  # noqa: F811 - el fixture importado arriba
    usuario = crear_usuario("facturacion", first_name="Laura", last_name="Caja")
    client.force_login(usuario)
    return usuario


@pytest.fixture
def por_facturar(crear_servicio, facturacion):
    """Fábrica: un servicio entregado en `momento` (hora del celular) con su línea por facturar del
    pagador de la solicitud, con `valor`."""

    def crear(momento=EL_5_DE_NOVIEMBRE, valor=VALOR, referencia=""):
        servicio = crear_servicio(Estado.ENTREGADO)
        if referencia:
            servicio.referencia_externa = referencia
            servicio.save(update_fields=["referencia_externa"])
        EventoEstado.objects.create(
            servicio=servicio,
            destino=Estado.ENTREGADO.value,
            origen=EventoEstado.Origen.APP,
            resultado=EventoEstado.Resultado.APLICADO,
            conductor=servicio.conductor,
            hora_dispositivo=momento,
        )
        linea = operaciones.crear_linea_al_entregar(servicio)
        if valor is not None:
            operaciones.fijar_valor(linea, valor, actor=facturacion)
        linea.refresh_from_db()
        return linea

    return crear
