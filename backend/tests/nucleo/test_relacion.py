from datetime import date

import pytest

from nucleo.cobro import CobroInvalido, EstadoCobro
from nucleo.relacion import (
    EstadoRelacion,
    Relacion,
    armar,
    descartar,
    entra_en_relacion,
    facturar,
    pagar,
    validar_rango,
)

R = EstadoRelacion
DESDE, HASTA = date(2026, 11, 1), date(2026, 11, 15)


def entra(**cambios) -> bool:
    datos = {
        "estado_linea": EstadoCobro.POR_FACTURAR,
        "pagador_linea": 7,
        "pagador": 7,
        "fecha_servicio": date(2026, 11, 10),
        "desde": DESDE,
        "hasta": HASTA,
    }
    datos.update(cambios)
    return entra_en_relacion(**datos)


def test_entra_la_linea_por_facturar_del_pagador_dentro_del_rango():
    assert entra()


@pytest.mark.parametrize("fecha", [DESDE, HASTA])
def test_los_extremos_del_rango_estan_incluidos(fecha):
    assert entra(fecha_servicio=fecha)


@pytest.mark.parametrize("fecha", [date(2026, 10, 31), date(2026, 11, 16)])
def test_fuera_del_rango_no_entra(fecha):
    assert not entra(fecha_servicio=fecha)


def test_la_linea_de_otro_pagador_no_entra():
    assert not entra(pagador_linea=8)


@pytest.mark.parametrize("estado", [e for e in EstadoCobro if e != EstadoCobro.POR_FACTURAR])
def test_solo_entra_la_linea_por_facturar(estado):
    assert not entra(estado_linea=estado)


def test_el_rango_va_de_menor_a_mayor():
    validar_rango(DESDE, DESDE)
    with pytest.raises(CobroInvalido, match="antes"):
        validar_rango(HASTA, DESDE)


def test_una_relacion_sin_lineas_no_se_arma():
    with pytest.raises(CobroInvalido, match="No hay líneas"):
        armar(0)
    assert armar(3) == Relacion(R.ARMADA)


def test_facturar_exige_numero_y_lo_guarda_sin_espacios():
    with pytest.raises(CobroInvalido, match="número"):
        facturar(Relacion(R.ARMADA), "  ")
    assert facturar(Relacion(R.ARMADA), " FE-1 ") == Relacion(R.FACTURADA, numero_factura="FE-1")


def test_pagar_solo_una_relacion_facturada():
    facturada = facturar(Relacion(R.ARMADA), "FE-1")
    assert pagar(facturada).estado == R.PAGADA
    with pytest.raises(CobroInvalido):
        pagar(Relacion(R.ARMADA))


def test_descartar_exige_motivo_y_solo_si_esta_armada():
    with pytest.raises(CobroInvalido, match="motivo"):
        descartar(Relacion(R.ARMADA), "")
    descartada = descartar(Relacion(R.ARMADA), " Fechas equivocadas ")
    assert (descartada.estado, descartada.motivo_descarte) == (R.DESCARTADA, "Fechas equivocadas")
    with pytest.raises(CobroInvalido, match="armada"):
        descartar(facturar(Relacion(R.ARMADA), "FE-1"), "Tarde")


@pytest.mark.parametrize("estado", [R.FACTURADA, R.PAGADA, R.DESCARTADA])
def test_no_se_vuelve_a_facturar(estado):
    with pytest.raises(CobroInvalido):
        facturar(Relacion(estado, numero_factura="FE-1"), "FE-2")
