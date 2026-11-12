"""Placas, VIN y teléfonos escritos de distintas formas quedan iguales; placa o VIN exigidos."""
import re

import pytest

from nucleo.identificacion import (
    PATRON_VIN,
    IdentificacionIncompleta,
    TelefonoInvalido,
    VinInvalido,
    normalizar_placa,
    normalizar_telefono,
    normalizar_vin,
    validar_identificacion,
    validar_vin,
)
from nucleo.tipos import TipoServicio

VIN = "1HGCM82633A004352"


@pytest.mark.parametrize("texto", ["abc-123", "ABC 123", "abc123", " a.b.c_1/2 3 "])
def test_normalizar_placa_deja_mayusculas_letras_y_digitos(texto):
    assert normalizar_placa(texto) == "ABC123"


def test_normalizar_placa_vacia_o_nula_da_texto_vacio():
    assert normalizar_placa("") == ""
    assert normalizar_placa(None) == ""
    assert normalizar_placa(" - ") == ""


@pytest.mark.parametrize(
    "texto", ["+57 300 123 4567", "300-123-4567", "3001234567", "(300) 123 45 67", "57 3001234567"]
)
def test_normalizar_telefono_deja_solo_digitos_sin_indicativo(texto):
    assert normalizar_telefono(texto) == "3001234567"


def test_el_57_solo_se_quita_si_quedan_12_digitos():
    # Un fijo de 7 dígitos o un número de 10 que empieza por 57 no pierden el 57.
    assert normalizar_telefono("5712345") == "5712345"
    assert normalizar_telefono("5712345678") == "5712345678"


def test_telefono_fijo_de_7_digitos_es_valido():
    assert normalizar_telefono("444 55 66") == "4445566"


def test_telefono_de_15_digitos_es_valido():
    assert normalizar_telefono("1" * 15) == "1" * 15


@pytest.mark.parametrize("texto", ["", None, "abc", "300 12", "123456", "1" * 16])
def test_telefono_con_menos_de_7_o_mas_de_15_digitos_es_invalido(texto):
    with pytest.raises(TelefonoInvalido, match="entre 7 y 15 dígitos"):
        normalizar_telefono(texto)


def test_telefono_invalido_es_un_value_error():
    assert issubclass(TelefonoInvalido, ValueError)


def test_tipos_de_servicio():
    assert [t.value for t in TipoServicio] == ["traslado", "evento", "desvare"]
    assert TipoServicio("desvare") is TipoServicio.DESVARE
    assert TipoServicio.EVENTO.etiqueta == "Evento o muestra de concesionario"


# --- VIN -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        VIN,
        "1hgcm82633a004352",
        " 1HG-CM826-33A004352 ",
        "1HG CM826 33A 004352",
        "1hg\tcm8263-3a004352",
    ],
)
def test_normalizar_vin_deja_mayusculas_sin_espacios_ni_guiones(texto):
    assert normalizar_vin(texto) == VIN


def test_normalizar_vin_vacio_o_nulo_da_texto_vacio():
    assert normalizar_vin("") == ""
    assert normalizar_vin(None) == ""
    assert normalizar_vin(" - ") == ""


def test_normalizar_vin_no_esconde_otros_simbolos():
    # Un punto o una barra son un error de digitación: se dejan para que la validación lo rechace.
    assert normalizar_vin("1HGCM.82633A004352") == "1HGCM.82633A004352"
    with pytest.raises(VinInvalido):
        validar_vin(normalizar_vin("1HGCM.82633A004352"))


@pytest.mark.parametrize(
    "vin", [VIN, "WVWZZZ1JZXW000001", "12345678901234567", "ABCDEFGHJKLMNPRST"]
)
def test_vin_de_17_caracteres_sin_i_o_q_es_valido(vin):
    validar_vin(vin)


@pytest.mark.parametrize("letra", ["I", "O", "Q"])
def test_vin_con_i_o_q_es_invalido(letra):
    with pytest.raises(VinInvalido, match="sin I, O ni Q"):
        validar_vin(VIN[:-1] + letra)


@pytest.mark.parametrize("vin", ["", VIN[:16], VIN + "1", "1" * 30])
def test_vin_con_largo_distinto_de_17_es_invalido(vin):
    with pytest.raises(VinInvalido, match="exactamente 17"):
        validar_vin(vin)


@pytest.mark.parametrize(
    "vin", ["1HGCM82633A00435*", "1HGCM82633A00435-", "1hgcm82633a004352", "1HGCM82633A00435Ñ"]
)
def test_vin_con_simbolos_minusculas_o_tildes_es_invalido(vin):
    # validar_vin recibe el VIN ya normalizado: así es como se guarda.
    with pytest.raises(VinInvalido):
        validar_vin(vin)


def test_vin_con_salto_de_linea_al_final_es_invalido():
    with pytest.raises(VinInvalido):
        validar_vin(VIN + "\n")


def test_vin_invalido_es_un_value_error():
    assert issubclass(VinInvalido, ValueError)


def test_el_patron_de_la_base_acepta_y_rechaza_lo_mismo_que_validar_vin():
    for vin in [VIN, VIN[:-1] + "I", VIN[:16], "1hgcm82633a004352"]:
        try:
            validar_vin(vin)
            valido = True
        except VinInvalido:
            valido = False
        assert bool(re.search(PATRON_VIN, vin)) is valido, vin


# --- Identificación del vehículo -------------------------------------------------------------


@pytest.mark.parametrize("tipo", [TipoServicio.TRASLADO, TipoServicio.EVENTO])
@pytest.mark.parametrize(("placa", "vin"), [("ABC123", ""), ("", VIN), ("ABC123", VIN)])
def test_traslado_o_evento_con_placa_o_vin_es_suficiente(tipo, placa, vin):
    validar_identificacion(placa, vin, tipo)


@pytest.mark.parametrize("tipo", list(TipoServicio))
@pytest.mark.parametrize(("placa", "vin"), [("", ""), (None, None), (" - ", "  ")])
def test_sin_placa_ni_vin_falta_identificacion(tipo, placa, vin):
    with pytest.raises(IdentificacionIncompleta):
        validar_identificacion(placa, vin, tipo)


def test_sin_placa_ni_vin_el_mensaje_lo_explica():
    with pytest.raises(IdentificacionIncompleta, match="placa o VIN"):
        validar_identificacion("", "", TipoServicio.TRASLADO)


def test_desvare_exige_placa_aunque_tenga_vin():
    with pytest.raises(IdentificacionIncompleta, match="Un desvare exige la placa"):
        validar_identificacion("", VIN, TipoServicio.DESVARE)


def test_desvare_con_placa_es_suficiente():
    validar_identificacion("ABC123", "", TipoServicio.DESVARE)
    validar_identificacion("abc-123", "", "desvare")


def test_identificacion_incompleta_es_un_value_error():
    assert issubclass(IdentificacionIncompleta, ValueError)
