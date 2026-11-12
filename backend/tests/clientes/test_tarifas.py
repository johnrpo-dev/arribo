"""Tarifas: valor positivo, una sola vigente por cliente y tipo, y la propuesta de valor."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from clientes.models import Cliente, Tarifa, TipoCliente, tarifa_propuesta
from nucleo.tipos import TipoServicio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente():
    return Cliente.objects.create(nombre="Aseguradora Uno", tipo=TipoCliente.ASEGURADORA)


@pytest.mark.parametrize("valor", [Decimal(0), Decimal("0.00"), Decimal(-1), Decimal("-0.01")])
def test_la_base_rechaza_valor_de_tarifa_cero_o_negativo(cliente, valor):
    with pytest.raises(IntegrityError, match="tarifa_valor_mayor_que_cero"), transaction.atomic():
        Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=valor)


def test_el_admin_avisa_en_espanol_que_el_valor_debe_ser_positivo(cliente):
    with pytest.raises(ValidationError) as error:
        Tarifa(cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=Decimal(0)).full_clean()
    assert error.value.message_dict["valor"] == ["El valor de la tarifa debe ser mayor que cero."]


def test_la_base_rechaza_tipo_de_servicio_desconocido(cliente):
    with pytest.raises(IntegrityError, match="tarifa_tipo_servicio_valido"), transaction.atomic():
        Tarifa.objects.create(cliente=cliente, tipo_servicio="grua", valor=Decimal(100))


def test_dos_tarifas_vigentes_del_mismo_cliente_y_tipo_rechazadas(cliente):
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(1))
    with (
        pytest.raises(IntegrityError, match="tarifa_vigente_unica_por_cliente_y_tipo"),
        transaction.atomic(),
    ):
        Tarifa.objects.create(
            cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(2)
        )


def test_una_vigente_y_otras_no_vigentes_del_mismo_tipo_se_permiten(cliente):
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(1), vigente=False
    )
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(2), vigente=False
    )
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(3))
    assert cliente.tarifas.count() == 3


def test_tarifas_vigentes_de_distinto_tipo_o_distinto_cliente_se_permiten(cliente):
    otro = Cliente.objects.create(nombre="Otro", tipo=TipoCliente.PARTICULAR)
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(1))
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=Decimal(2))
    Tarifa.objects.create(cliente=otro, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(3))
    assert Tarifa.objects.filter(vigente=True).count() == 3


def test_el_admin_avisa_en_espanol_que_ya_hay_una_tarifa_vigente(cliente):
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.EVENTO, valor=Decimal(250000)
    )
    with pytest.raises(ValidationError) as error:
        Tarifa(
            cliente=cliente, tipo_servicio=TipoServicio.EVENTO, valor=Decimal(300000)
        ).full_clean()
    assert error.value.message_dict["tipo_servicio"][0].startswith(
        "El cliente ya tiene una tarifa vigente de 250000.00"
    )


def test_tarifa_propuesta_devuelve_el_valor_vigente_en_decimal(cliente):
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=Decimal(90000), vigente=False
    )
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=Decimal("120000.50")
    )
    propuesta = tarifa_propuesta(cliente, TipoServicio.DESVARE)
    assert propuesta == Decimal("120000.50")
    assert isinstance(propuesta, Decimal)


def test_tarifa_propuesta_acepta_el_tipo_como_texto(cliente):
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.DESVARE, valor=Decimal(5))
    assert tarifa_propuesta(cliente, "desvare") == Decimal(5)


def test_sin_tarifa_vigente_no_hay_propuesta(cliente):
    assert tarifa_propuesta(cliente, TipoServicio.TRASLADO) is None
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(1), vigente=False
    )
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.EVENTO, valor=Decimal(2))
    assert tarifa_propuesta(cliente, TipoServicio.TRASLADO) is None
