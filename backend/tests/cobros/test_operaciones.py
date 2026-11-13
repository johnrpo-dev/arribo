"""Operaciones de cobro contra PostgreSQL: delegan la regla en nucleo/cobro.py, dejan un registro de
historial por paso y, si la regla no se cumple, no queda ni cambio ni historial.
"""
from decimal import Decimal

import pytest

from cobros import operaciones
from cobros.models import AccionCobro, HistorialCobro, LineaCobro
from nucleo.cobro import CobroInvalido, EstadoCobro

pytestmark = pytest.mark.django_db

D = Decimal
C = EstadoCobro


def foto(linea):
    """Lo que no debe cambiar cuando una operación se rechaza: la línea y su historial."""
    guardada = LineaCobro.objects.get(pk=linea.pk)
    historial = list(guardada.historial.values_list("pk", flat=True))
    return (guardada.estado, guardada.valor, guardada.numero_factura, historial)


@pytest.fixture
def por_facturar(linea, usuario):
    operaciones.fijar_valor(linea, D("250000"), actor=usuario)
    return linea


@pytest.fixture
def facturada(por_facturar, usuario):
    operaciones.facturar(por_facturar, "FE-1024", actor=usuario)
    return por_facturar


@pytest.fixture
def pagada(facturada, usuario):
    operaciones.pagar(facturada, actor=usuario)
    return facturada


# --- Ciclo completo ----------------------------------------------------------------------------


def test_ciclo_completo_sin_valor_por_facturar_facturado_pagado(linea, usuario):
    assert (linea.estado, linea.valor, linea.numero_factura) == (C.SIN_VALOR, None, "")
    assert linea.historial.count() == 1

    valor = operaciones.fijar_valor(linea, D("250000"), actor=usuario)
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, D("250000"))
    assert linea.historial.count() == 2

    factura = operaciones.facturar(linea, " FE-1024 ", actor=usuario)
    assert (linea.estado, linea.valor, linea.numero_factura) == (C.FACTURADO, D("250000"), "FE-1024")
    assert linea.historial.count() == 3

    pago = operaciones.pagar(linea, actor=usuario)
    assert (linea.estado, linea.valor, linea.numero_factura) == (C.PAGADO, D("250000"), "FE-1024")
    assert linea.historial.count() == 4

    assert [registro.accion for registro in linea.historial.all()] == [
        AccionCobro.CREADA,
        AccionCobro.VALOR,
        AccionCobro.FACTURADA,
        AccionCobro.PAGADA,
    ]
    assert (factura.numero_factura, factura.usuario) == ("FE-1024", usuario)
    assert (pago.numero_factura, pago.usuario) == ("FE-1024", usuario)
    assert valor.fecha is not None


def test_el_cambio_de_valor_guarda_quien_cuando_y_el_valor_anterior(linea, usuario,
                                                                    django_user_model):
    facturacion = django_user_model.objects.create_user("facturacion")
    primero = operaciones.fijar_valor(linea, D("250000"), actor=usuario)
    ajuste = operaciones.fijar_valor(linea, D("230000.50"), actor=facturacion)

    assert (primero.usuario, primero.valor_anterior, primero.valor_nuevo) == (
        usuario,
        None,
        D("250000"),
    )
    assert (ajuste.usuario, ajuste.valor_anterior, ajuste.valor_nuevo) == (
        facturacion,
        D("250000"),
        D("230000.50"),
    )
    assert primero.fecha is not None and ajuste.fecha >= primero.fecha
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, D("230000.50"))


def test_las_operaciones_devuelven_el_registro_de_historial_que_dejan(por_facturar, usuario):
    registro = operaciones.facturar(por_facturar, "FE-7", actor=usuario)
    assert isinstance(registro, HistorialCobro)
    assert por_facturar.historial.last() == registro


def test_las_operaciones_aceptan_la_llave_primaria_de_la_linea(linea, usuario):
    operaciones.fijar_valor(linea.pk, D("1000"), actor=usuario)
    operaciones.facturar(linea.pk, "FE-1", actor=usuario)
    linea.refresh_from_db()
    assert linea.estado == C.FACTURADO


def test_las_operaciones_deciden_sobre_lo_guardado_no_sobre_una_copia_vieja(linea, usuario):
    copia_vieja = LineaCobro.objects.get(pk=linea.pk)  # aún sin valor
    operaciones.fijar_valor(linea, D("1000"), actor=usuario)
    operaciones.facturar(linea, "FE-1", actor=usuario)
    with pytest.raises(CobroInvalido):
        operaciones.fijar_valor(copia_vieja, D("2000"), actor=usuario)
    assert LineaCobro.objects.get(pk=linea.pk).valor == D("1000")


# --- El valor ----------------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["facturada", "pagada"])
def test_el_valor_no_cambia_despues_de_facturar(request, usuario, estado):
    linea = request.getfixturevalue(estado)
    antes = foto(linea)
    with pytest.raises(CobroInvalido, match="No se cambia el valor"):
        operaciones.fijar_valor(linea, D("300000"), actor=usuario)
    assert foto(linea) == antes


@pytest.mark.parametrize("valor", [D("0"), D("-1"), D("-0.01")])
def test_el_valor_debe_ser_mayor_que_cero(linea, usuario, valor):
    antes = foto(linea)
    with pytest.raises(CobroInvalido, match="mayor que cero"):
        operaciones.fijar_valor(linea, valor, actor=usuario)
    assert foto(linea) == antes


@pytest.mark.parametrize("valor", [250000.0, 250000, "250000"])
def test_el_valor_va_en_decimal_nunca_en_float(linea, usuario, valor):
    antes = foto(linea)
    with pytest.raises(TypeError, match="Decimal"):
        operaciones.fijar_valor(linea, valor, actor=usuario)
    assert foto(linea) == antes


@pytest.mark.parametrize("valor", [D("NaN"), D("Infinity")])
def test_un_valor_que_no_es_un_numero_se_rechaza(linea, usuario, valor):
    antes = foto(linea)
    with pytest.raises(CobroInvalido):
        operaciones.fijar_valor(linea, valor, actor=usuario)
    assert foto(linea) == antes


# --- Facturar y pagar --------------------------------------------------------------------------


def test_no_se_factura_una_linea_sin_valor(linea, usuario):
    antes = foto(linea)
    with pytest.raises(CobroInvalido, match="Solo se factura una línea por facturar"):
        operaciones.facturar(linea, "FE-1", actor=usuario)
    assert foto(linea) == antes


@pytest.mark.parametrize("numero", ["", "   ", None])
def test_no_se_factura_sin_numero_de_factura(por_facturar, usuario, numero):
    antes = foto(por_facturar)
    with pytest.raises(CobroInvalido, match="exige número de factura"):
        operaciones.facturar(por_facturar, numero, actor=usuario)
    assert foto(por_facturar) == antes


def test_no_se_factura_dos_veces(facturada, usuario):
    antes = foto(facturada)
    with pytest.raises(CobroInvalido):
        operaciones.facturar(facturada, "FE-2", actor=usuario)
    assert foto(facturada) == antes


@pytest.mark.parametrize("estado", ["linea", "por_facturar", "pagada"])
def test_solo_se_paga_una_linea_facturada(request, usuario, estado):
    linea = request.getfixturevalue(estado)
    antes = foto(linea)
    with pytest.raises(CobroInvalido, match="Solo se marca pagada una línea facturada"):
        operaciones.pagar(linea, actor=usuario)
    assert foto(linea) == antes


# --- Anular factura ----------------------------------------------------------------------------


def test_anular_factura_devuelve_a_por_facturar_y_guarda_numero_y_motivo(facturada, usuario):
    registro = operaciones.anular_factura(facturada, "  NIT errado en la factura  ", actor=usuario)

    assert (facturada.estado, facturada.valor, facturada.numero_factura) == (
        C.POR_FACTURAR,
        D("250000"),
        "",
    )
    assert registro.accion == AccionCobro.FACTURA_ANULADA
    assert (registro.numero_factura, registro.motivo) == ("FE-1024", "NIT errado en la factura")
    assert registro.usuario == usuario
    assert facturada.historial.count() == 4  # creada, valor, facturada, anulada


def test_despues_de_anular_se_puede_ajustar_el_valor_y_volver_a_facturar(facturada, usuario):
    operaciones.anular_factura(facturada, "Valor mal acordado", actor=usuario)
    operaciones.fijar_valor(facturada, D("240000"), actor=usuario)
    operaciones.facturar(facturada, "FE-1030", actor=usuario)
    assert (facturada.estado, facturada.valor, facturada.numero_factura) == (
        C.FACTURADO,
        D("240000"),
        "FE-1030",
    )


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_anular_factura_exige_motivo(facturada, usuario, motivo):
    antes = foto(facturada)
    with pytest.raises(CobroInvalido, match="exige motivo"):
        operaciones.anular_factura(facturada, motivo, actor=usuario)
    assert foto(facturada) == antes


def test_no_se_anula_la_factura_de_una_linea_pagada(pagada, usuario):
    antes = foto(pagada)
    with pytest.raises(CobroInvalido, match="sin pagar"):
        operaciones.anular_factura(pagada, "Error", actor=usuario)
    assert foto(pagada) == antes


@pytest.mark.parametrize("estado", ["linea", "por_facturar"])
def test_no_se_anula_lo_que_no_esta_facturado(request, usuario, estado):
    linea = request.getfixturevalue(estado)
    antes = foto(linea)
    with pytest.raises(CobroInvalido):
        operaciones.anular_factura(linea, "Error", actor=usuario)
    assert foto(linea) == antes
