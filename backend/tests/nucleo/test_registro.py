"""Obligatorios para que una solicitud deje de ser borrador."""
import pytest

from nucleo.registro import (
    Faltante,
    describir_faltantes,
    destino_obligatorio,
    faltantes_para_abrir,
)
from nucleo.tipos import TipoServicio


def completa(**cambios):
    datos = {
        "tiene_solicitante": True,
        "tipo": TipoServicio.TRASLADO,
        "origen": "Calle 10 # 43-20",
        "destino": "Carrera 70 # 1-50",
        "vehiculos": 1,
        "tiene_regreso": None,
    }
    datos.update(cambios)
    return faltantes_para_abrir(**datos)


def test_traslado_completo_no_tiene_faltantes():
    assert completa() == []


def test_sin_solicitante_falta_el_solicitante():
    assert completa(tiene_solicitante=False) == [Faltante.SOLICITANTE]


@pytest.mark.parametrize("tipo", [None, ""])
def test_sin_tipo_falta_el_tipo(tipo):
    assert completa(tipo=tipo) == [Faltante.TIPO]


@pytest.mark.parametrize("origen", [None, "", "   "])
def test_sin_origen_falta_el_origen(origen):
    assert completa(origen=origen) == [Faltante.ORIGEN]


def test_sin_vehiculo_falta_el_vehiculo():
    assert completa(vehiculos=0) == [Faltante.VEHICULO]


@pytest.mark.parametrize("destino", [None, "", "  "])
def test_traslado_sin_destino_no_sale_de_borrador(destino):
    assert completa(destino=destino) == [Faltante.DESTINO]


def test_evento_sin_destino_no_sale_de_borrador():
    assert Faltante.DESTINO in completa(tipo=TipoServicio.EVENTO, destino="", tiene_regreso=False)


def test_desvare_sin_destino_sale_de_borrador():
    assert completa(tipo=TipoServicio.DESVARE, destino="") == []


def test_sin_tipo_el_destino_se_exige():
    assert destino_obligatorio(None) is True
    assert completa(tipo=None, destino="") == [Faltante.TIPO, Faltante.DESTINO]


@pytest.mark.parametrize("tipo, obligatorio", [("traslado", True), ("evento", True), ("desvare", False)])
def test_destino_obligatorio_segun_el_tipo(tipo, obligatorio):
    assert destino_obligatorio(tipo) is obligatorio


def test_evento_sin_responder_regreso_no_sale_de_borrador():
    assert completa(tipo=TipoServicio.EVENTO) == [Faltante.RESPUESTA_REGRESO]


@pytest.mark.parametrize("respuesta", [True, False])
def test_evento_con_respuesta_de_regreso_sale_de_borrador(respuesta):
    assert completa(tipo=TipoServicio.EVENTO, tiene_regreso=respuesta) == []


def test_el_regreso_no_se_pide_fuera_de_eventos():
    assert completa(tipo=TipoServicio.TRASLADO, tiene_regreso=None) == []
    assert completa(tipo=TipoServicio.DESVARE, tiene_regreso=None, destino="") == []


def test_los_faltantes_salen_en_el_orden_del_formulario():
    assert faltantes_para_abrir(
        tiene_solicitante=False, tipo=None, origen="", destino="", vehiculos=0
    ) == [
        Faltante.SOLICITANTE,
        Faltante.TIPO,
        Faltante.ORIGEN,
        Faltante.DESTINO,
        Faltante.VEHICULO,
    ]


def test_describir_faltantes_en_una_frase():
    assert describir_faltantes([]) == ""
    assert describir_faltantes([Faltante.ORIGEN]) == "el origen"
    assert (
        describir_faltantes([Faltante.ORIGEN, Faltante.DESTINO, Faltante.VEHICULO])
        == "el origen, el destino y al menos un vehículo"
    )
