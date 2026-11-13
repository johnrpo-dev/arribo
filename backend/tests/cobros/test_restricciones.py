"""Una línea de cobro no puede quedar en un estado inválido: lo rechaza PostgreSQL.

Las pruebas escriben con objects.create() o con update() directo, sin pasar por save() ni por las
operaciones: lo que rechaza es la base, con el nombre de la restricción.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from clientes.models import Cliente, TipoCliente
from cobros.models import LineaCobro
from nucleo.cobro import EstadoCobro
from nucleo.estados import Estado

from .conftest import guardar_linea

pytestmark = pytest.mark.django_db

D = Decimal
C = EstadoCobro
POR_FACTURAR_VALIDA = {"estado": C.POR_FACTURAR, "valor": D("1000"), "numero_factura": ""}

INVALIDAS = [
    pytest.param(
        {"estado": C.POR_FACTURAR, "valor": None},
        "linea_cobro_por_facturar_coherente",
        id="por_facturar_sin_valor",
    ),
    pytest.param(
        {"estado": C.POR_FACTURAR, "valor": D("0")},
        "linea_cobro_por_facturar_coherente",
        id="por_facturar_valor_cero",
    ),
    pytest.param(
        {"estado": C.POR_FACTURAR, "valor": D("-1")},
        "linea_cobro_por_facturar_coherente",
        id="por_facturar_valor_negativo",
    ),
    pytest.param(
        {"estado": C.POR_FACTURAR, "valor": D("1000"), "numero_factura": "FE-1"},
        "linea_cobro_por_facturar_coherente",
        id="por_facturar_con_factura",
    ),
    pytest.param(
        {"estado": C.FACTURADO, "valor": D("1000"), "numero_factura": ""},
        "linea_cobro_facturada_coherente",
        id="facturado_sin_numero",
    ),
    pytest.param(
        {"estado": C.FACTURADO, "valor": D("1000"), "numero_factura": "   "},
        "linea_cobro_facturada_coherente",
        id="facturado_numero_en_blanco",
    ),
    pytest.param(
        {"estado": C.FACTURADO, "valor": D("1000"), "numero_factura": "\t \n"},
        "linea_cobro_facturada_coherente",
        id="facturado_numero_con_tabulador_y_salto",
    ),
    pytest.param(
        {"estado": C.FACTURADO, "valor": None, "numero_factura": "FE-1"},
        "linea_cobro_facturada_coherente",
        id="facturado_sin_valor",
    ),
    pytest.param(
        {"estado": C.FACTURADO, "valor": D("0"), "numero_factura": "FE-1"},
        "linea_cobro_facturada_coherente",
        id="facturado_valor_cero",
    ),
    pytest.param(
        {"estado": C.PAGADO, "valor": D("1000"), "numero_factura": ""},
        "linea_cobro_facturada_coherente",
        id="pagado_sin_numero",
    ),
    pytest.param(
        {"estado": C.PAGADO, "valor": None, "numero_factura": "FE-1"},
        "linea_cobro_facturada_coherente",
        id="pagado_sin_valor",
    ),
    pytest.param(
        {"estado": C.SIN_VALOR, "valor": D("1000"), "numero_factura": ""},
        "linea_cobro_sin_valor_coherente",
        id="sin_valor_con_valor",
    ),
    pytest.param(
        {"estado": C.SIN_VALOR, "valor": None, "numero_factura": "FE-1"},
        "linea_cobro_sin_valor_coherente",
        id="sin_valor_con_factura",
    ),
    pytest.param(
        {"estado": C.NO_COBRABLE, "valor": None, "numero_factura": "FE-1"},
        "linea_cobro_no_cobrable_sin_factura",
        id="no_cobrable_con_factura",
    ),
    pytest.param({"estado": "regalado"}, "linea_cobro_estado_valido", id="estado_desconocido"),
    pytest.param({"posicion": 3}, "linea_cobro_posicion_valida", id="posicion_3"),
    pytest.param({"posicion": 0}, "linea_cobro_posicion_valida", id="posicion_0"),
]

VALIDAS = [
    pytest.param({"estado": C.SIN_VALOR, "valor": None}, id="sin_valor"),
    pytest.param({"estado": C.POR_FACTURAR, "valor": D("0.01")}, id="por_facturar"),
    pytest.param(
        {"estado": C.FACTURADO, "valor": D("1000"), "numero_factura": "FE-1"}, id="facturado"
    ),
    pytest.param({"estado": C.PAGADO, "valor": D("1000"), "numero_factura": "FE-1"}, id="pagado"),
    pytest.param({"estado": C.NO_COBRABLE, "valor": None}, id="no_cobrable"),
    pytest.param({"estado": C.NO_COBRABLE, "valor": D("1000")}, id="no_cobrable_con_valor"),
    pytest.param({"posicion": 2}, id="posicion_2"),
]


def rechazado_por_la_base(restriccion, escribir):
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        escribir()


# --- Coherencia entre estado, valor y factura --------------------------------------------------


@pytest.mark.parametrize(("cambios", "restriccion"), INVALIDAS)
def test_la_base_rechaza_la_combinacion_invalida_con_un_update_directo(
    entregado, cliente, cambios, restriccion
):
    linea = guardar_linea(entregado, cliente, **POR_FACTURAR_VALIDA)
    rechazado_por_la_base(
        restriccion, lambda: LineaCobro.objects.filter(pk=linea.pk).update(**cambios)
    )
    linea.refresh_from_db()
    assert (linea.estado, linea.valor, linea.numero_factura, linea.posicion) == (
        C.POR_FACTURAR,
        D("1000"),
        "",
        1,
    )


@pytest.mark.parametrize(("cambios", "restriccion"), INVALIDAS)
def test_la_base_rechaza_crear_una_linea_con_la_combinacion_invalida(
    entregado, cliente, cambios, restriccion
):
    rechazado_por_la_base(
        restriccion, lambda: guardar_linea(entregado, cliente, **{**POR_FACTURAR_VALIDA, **cambios})
    )
    assert not LineaCobro.objects.exists()


@pytest.mark.parametrize("cambios", VALIDAS)
def test_las_combinaciones_validas_se_aceptan(entregado, cliente, cambios):
    linea = guardar_linea(entregado, cliente, **POR_FACTURAR_VALIDA)
    LineaCobro.objects.filter(pk=linea.pk).update(**cambios)
    linea.refresh_from_db()
    for campo, valor in cambios.items():
        assert getattr(linea, campo) == valor


def test_una_linea_nueva_nace_sin_valor_en_la_posicion_1(entregado, cliente):
    linea = LineaCobro.objects.create(servicio=entregado, pagador=cliente)
    linea.refresh_from_db()
    assert (linea.estado, linea.valor, linea.numero_factura, linea.posicion) == (
        C.SIN_VALOR,
        None,
        "",
        1,
    )
    assert linea.creada_en is not None


# --- Máximo dos líneas por servicio, sin repetir pagador ---------------------------------------


@pytest.fixture
def tercer_cliente():
    return Cliente.objects.create(nombre="Transportes del Norte", tipo=TipoCliente.CONCESIONARIO)


def test_dos_pagadores_distintos_se_permiten(entregado, cliente, otro_cliente):
    guardar_linea(entregado, cliente, posicion=1)
    guardar_linea(entregado, otro_cliente, posicion=2)
    assert entregado.lineas_cobro.count() == 2


@pytest.mark.parametrize(
    ("posicion", "restriccion"),
    [
        (1, "linea_cobro_unica_por_servicio_y_posicion"),
        (2, "linea_cobro_unica_por_servicio_y_posicion"),
        (3, "linea_cobro_posicion_valida"),
    ],
)
def test_una_tercera_linea_para_el_servicio_se_rechaza(
    entregado, cliente, otro_cliente, tercer_cliente, posicion, restriccion
):
    guardar_linea(entregado, cliente, posicion=1)
    guardar_linea(entregado, otro_cliente, posicion=2)
    rechazado_por_la_base(
        restriccion, lambda: guardar_linea(entregado, tercer_cliente, posicion=posicion)
    )
    assert entregado.lineas_cobro.count() == 2


def test_el_mismo_pagador_dos_veces_en_un_servicio_se_rechaza(entregado, cliente):
    guardar_linea(entregado, cliente, posicion=1)
    rechazado_por_la_base(
        "linea_cobro_unica_por_servicio_y_pagador",
        lambda: guardar_linea(entregado, cliente, posicion=2),
    )
    assert entregado.lineas_cobro.count() == 1


def test_un_update_tampoco_repite_posicion_ni_pagador(entregado, cliente, otro_cliente):
    guardar_linea(entregado, cliente, posicion=1)
    segunda = guardar_linea(entregado, otro_cliente, posicion=2)
    rechazado_por_la_base(
        "linea_cobro_unica_por_servicio_y_posicion",
        lambda: LineaCobro.objects.filter(pk=segunda.pk).update(posicion=1),
    )
    rechazado_por_la_base(
        "linea_cobro_unica_por_servicio_y_pagador",
        lambda: LineaCobro.objects.filter(pk=segunda.pk).update(pagador=cliente),
    )


def test_el_mismo_pagador_si_puede_estar_en_servicios_distintos(
    entregado, crear_servicio, cliente
):
    otro_servicio = crear_servicio(Estado.ENTREGADO)
    guardar_linea(entregado, cliente)
    guardar_linea(otro_servicio, cliente)
    assert LineaCobro.objects.filter(pagador=cliente).count() == 2


# --- clean(): los mismos mensajes, en español y atados al campo --------------------------------


@pytest.mark.parametrize(
    ("campos", "campo", "mensaje"),
    [
        ({"estado": C.SIN_VALOR, "valor": D("1")}, "valor", "Una línea sin valor no lleva valor."),
        ({"estado": C.POR_FACTURAR, "valor": None}, "valor", "mayor que cero"),
        ({"estado": C.POR_FACTURAR, "valor": D("-5")}, "valor", "mayor que cero"),
        (
            {"estado": C.FACTURADO, "valor": D("1"), "numero_factura": "  "},
            "numero_factura",
            "exige el número de factura",
        ),
        (
            {"estado": C.POR_FACTURAR, "valor": D("1"), "numero_factura": "FE-1"},
            "numero_factura",
            "solo va en una línea facturada o pagada",
        ),
        (
            {"estado": C.NO_COBRABLE, "numero_factura": "FE-1"},
            "numero_factura",
            "solo va en una línea facturada o pagada",
        ),
    ],
)
def test_clean_explica_en_espanol_que_esta_mal(entregado, cliente, campos, campo, mensaje):
    linea = LineaCobro(servicio=entregado, pagador=cliente, **campos)
    with pytest.raises(ValidationError) as error:
        linea.clean()
    assert mensaje in " ".join(error.value.message_dict[campo])


@pytest.mark.parametrize("cambios", VALIDAS)
def test_clean_acepta_las_combinaciones_validas(entregado, cliente, cambios):
    LineaCobro(servicio=entregado, pagador=cliente, **{**POR_FACTURAR_VALIDA, **cambios}).clean()
