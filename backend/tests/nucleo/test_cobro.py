from decimal import Decimal

import pytest

from nucleo.cobro import (
    CobroInvalido,
    EstadoCobro,
    LineaCobro,
    anular_factura,
    facturar,
    fijar_valor,
    formato_pesos,
    leer_pesos,
    linea_inicial,
    pagar,
    validar_division,
)

D = Decimal


def test_linea_nace_sin_valor_si_no_se_ha_digitado():
    assert linea_inicial(None).estado == EstadoCobro.SIN_VALOR


def test_linea_nace_por_facturar_si_ya_tiene_valor():
    linea = linea_inicial(D("180000"))
    assert (linea.estado, linea.valor) == (EstadoCobro.POR_FACTURAR, D("180000"))


def test_servicio_no_cobrable():
    assert linea_inicial(D("180000"), cobrable=False).estado == EstadoCobro.NO_COBRABLE


def test_ciclo_completo():
    linea = fijar_valor(linea_inicial(None), D("250000"))
    linea = facturar(linea, " FE-1024 ")
    assert (linea.estado, linea.numero_factura) == (EstadoCobro.FACTURADO, "FE-1024")
    assert pagar(linea).estado == EstadoCobro.PAGADO


def test_no_se_factura_sin_valor_ni_sin_numero():
    with pytest.raises(CobroInvalido):
        facturar(linea_inicial(None), "FE-1")
    with pytest.raises(CobroInvalido):
        facturar(linea_inicial(D("1000")), "  ")


def test_no_se_paga_lo_que_no_esta_facturado():
    with pytest.raises(CobroInvalido):
        pagar(linea_inicial(D("1000")))


def test_valor_no_cambia_despues_de_facturar():
    linea = facturar(linea_inicial(D("1000")), "FE-1")
    with pytest.raises(CobroInvalido):
        fijar_valor(linea, D("2000"))


@pytest.mark.parametrize("valor", [D("0"), D("-1")])
def test_valor_debe_ser_positivo(valor):
    with pytest.raises(CobroInvalido):
        fijar_valor(linea_inicial(None), valor)


def test_anular_factura_devuelve_a_por_facturar_con_motivo():
    linea = facturar(linea_inicial(D("1000")), "FE-1")
    with pytest.raises(CobroInvalido):
        anular_factura(linea, "")
    anulada = anular_factura(linea, "factura con NIT errado")
    assert anulada == LineaCobro(EstadoCobro.POR_FACTURAR, D("1000"), None)


def test_no_se_anula_una_factura_pagada():
    linea = pagar(facturar(linea_inicial(D("1000")), "FE-1"))
    with pytest.raises(CobroInvalido):
        anular_factura(linea, "error")


def test_division_entre_dos_pagadores_debe_sumar_el_total():
    validar_division(D("300000"), [D("300000")])
    validar_division(D("300000"), [D("200000"), D("100000")])
    with pytest.raises(CobroInvalido):
        validar_division(D("300000"), [D("200000"), D("50000")])


def test_division_admite_maximo_dos_pagadores_y_partes_positivas():
    with pytest.raises(CobroInvalido):
        validar_division(D("300"), [D("100"), D("100"), D("100")])
    with pytest.raises(CobroInvalido):
        validar_division(D("300"), [])
    with pytest.raises(CobroInvalido):
        validar_division(D("300"), [D("300"), D("0")])


# --- Pesos escritos a mano ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("180000", "180000"),
        ("180.000", "180000"),
        ("180,000", "180000"),
        ("$ 180.000", "180000"),
        ("$180.000", "180000"),
        (" 1.250.000 ", "1250000"),
        ("180.000,50", "180000.50"),
        ("180000,5", "180000.5"),
        ("180000.50", "180000.50"),
        ("950", "950"),
    ],
)
def test_leer_pesos_entiende_como_se_escriben_en_colombia(texto, valor):
    assert leer_pesos(texto) == Decimal(valor)


@pytest.mark.parametrize(
    "texto",
    ["", "   ", "$", "ciento ochenta", "180.00.0", "18.0000", "1.80.000", "180000,505", "-5", "1e5", ","],
)
def test_leer_pesos_rechaza_lo_que_no_es_un_valor(texto):
    with pytest.raises(CobroInvalido, match="números"):
        leer_pesos(texto)


def test_leer_pesos_devuelve_decimal_nunca_float():
    assert type(leer_pesos("180.000")) is Decimal


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (Decimal(180000), "$ 180.000"),
        (Decimal("180000.00"), "$ 180.000"),
        (Decimal("1250000.5"), "$ 1.250.000,50"),
        (Decimal(950), "$ 950"),
        (None, "—"),
    ],
)
def test_formato_pesos(valor, texto):
    assert formato_pesos(valor) == texto
