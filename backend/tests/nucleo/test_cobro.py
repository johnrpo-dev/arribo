from decimal import Decimal

import pytest

from nucleo.cobro import (
    CobroInvalido,
    EstadoCobro,
    LineaCobro,
    anular_factura,
    facturar,
    fijar_valor,
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
