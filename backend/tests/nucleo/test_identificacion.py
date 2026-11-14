"""Placas, VIN y teléfonos escritos de distintas formas quedan iguales; placa o VIN exigidos."""
import re

import pytest

from nucleo.identificacion import (
    PATRON_VIN,
    CampoIdentificacion,
    Complemento,
    DatoPorRevisar,
    IdentificacionIncompleta,
    MomentoIdentificacion,
    PlacaInvalida,
    Revision,
    TelefonoInvalido,
    VinInvalido,
    completar_identificacion,
    identificacion_exigida,
    normalizar_placa,
    normalizar_telefono,
    normalizar_vin,
    validar_identificacion,
    validar_identificacion_al_recoger,
    validar_placa,
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


# --- Momento en que se exige la placa o el VIN -------------------------------------------------

M = MomentoIdentificacion


def test_configurado_al_asignar_se_exige_al_asignar():
    assert identificacion_exigida(M.AL_ASIGNAR, M.AL_ASIGNAR) is True


def test_configurado_al_recoger_no_se_exige_al_asignar():
    assert identificacion_exigida(M.AL_RECOGER, M.AL_ASIGNAR) is False


@pytest.mark.parametrize("configurado", [M.AL_ASIGNAR, M.AL_RECOGER])
def test_al_recoger_se_exige_siempre(configurado):
    assert identificacion_exigida(configurado, M.AL_RECOGER) is True


def test_el_momento_se_acepta_como_texto_guardado():
    assert identificacion_exigida("asignar", "asignar") is True
    assert identificacion_exigida("recoger", "asignar") is False


# --- Placa: lo que cabe en el vehículo -----------------------------------------------------------


@pytest.mark.parametrize("placa", ["ABC123", "ABC12D", "A", "ABCDEFGHIJ"])
def test_placa_de_1_a_10_letras_o_digitos_es_valida(placa):
    validar_placa(placa)


@pytest.mark.parametrize("placa", ["", "ABCDEFGHIJK", "abc123", "ABC-123"])
def test_placa_vacia_larga_o_sin_normalizar_es_invalida(placa):
    with pytest.raises(PlacaInvalida, match="de 1 a 10 letras o dígitos"):
        validar_placa(placa)


def test_placa_invalida_es_un_value_error():
    assert issubclass(PlacaInvalida, ValueError)


# --- Placa o VIN digitados al recoger ------------------------------------------------------------

C, R = CampoIdentificacion, Revision


def test_al_recoger_cuenta_la_placa_digitada_si_el_vehiculo_no_tiene_identificacion():
    validar_identificacion_al_recoger("", "", "abc-123", None, TipoServicio.TRASLADO)


def test_al_recoger_cuenta_el_vin_digitado_en_un_traslado():
    validar_identificacion_al_recoger(None, None, None, VIN, TipoServicio.TRASLADO)


def test_al_recoger_un_desvare_exige_la_placa_aunque_digiten_el_vin():
    with pytest.raises(IdentificacionIncompleta, match="desvare exige la placa"):
        validar_identificacion_al_recoger("", "", "", VIN, TipoServicio.DESVARE)


def test_al_recoger_un_desvare_con_vin_guardado_se_completa_con_la_placa_digitada():
    validar_identificacion_al_recoger("", VIN, "ABC123", None, TipoServicio.DESVARE)


@pytest.mark.parametrize("digitada", [None, "", " - "])
def test_al_recoger_sin_nada_digitado_ni_guardado_falta_identificacion(digitada):
    with pytest.raises(IdentificacionIncompleta, match="placa o VIN"):
        validar_identificacion_al_recoger("", "", digitada, digitada, TipoServicio.TRASLADO)


def test_al_recoger_lo_digitado_cuenta_aunque_no_sea_valido():
    # El conductor lo leyó del vehículo: el Recogido se aplica y logística revisa el dato.
    validar_identificacion_al_recoger("", "", None, VIN[:16], TipoServicio.TRASLADO)
    validar_identificacion_al_recoger("", "", "ABCDEFGHIJKLM", None, TipoServicio.DESVARE)


def test_al_recoger_con_el_vehiculo_identificado_no_hace_falta_digitar():
    validar_identificacion_al_recoger("ABC123", "", None, None, TipoServicio.DESVARE)


def test_completar_guarda_la_placa_digitada_normalizada_si_el_vehiculo_no_tiene():
    complemento = completar_identificacion("", "", "abc-123", None)
    assert (complemento.placa, complemento.vin) == ("ABC123", "")
    assert complemento.nuevos == (C.PLACA,)
    assert complemento.por_revisar == ()


def test_completar_guarda_placa_y_vin_digitados_si_el_vehiculo_no_tiene_ninguno():
    complemento = completar_identificacion(None, None, "ABC123", VIN.lower())
    assert (complemento.placa, complemento.vin) == ("ABC123", VIN)
    assert complemento.nuevos == (C.PLACA, C.VIN)


def test_completar_agrega_el_vin_a_un_vehiculo_que_solo_tenia_placa():
    complemento = completar_identificacion("ABC123", "", None, VIN)
    assert (complemento.placa, complemento.vin, complemento.nuevos) == ("ABC123", VIN, (C.VIN,))


def test_completar_con_el_mismo_dato_no_cambia_nada_ni_pide_revision():
    complemento = completar_identificacion("ABC123", VIN, "abc 123", VIN.lower())
    assert (complemento.nuevos, complemento.por_revisar) == ((), ())


def test_completar_no_sobreescribe_una_placa_distinta_y_la_deja_por_revisar():
    complemento = completar_identificacion("ABC123", "", "XYZ789", None)
    assert complemento.placa == "ABC123"
    assert complemento.nuevos == ()
    assert complemento.por_revisar == (
        DatoPorRevisar(C.PLACA, "XYZ789", R.DISTINTO, existente="ABC123"),
    )


def test_completar_no_sobreescribe_un_vin_distinto():
    otro = "WVWZZZ1JZXW000001"
    complemento = completar_identificacion("", VIN, None, otro)
    assert complemento.vin == VIN
    assert complemento.por_revisar == (DatoPorRevisar(C.VIN, otro, R.DISTINTO, existente=VIN),)


@pytest.mark.parametrize("vin", [VIN[:16], VIN[:-1] + "O", "1HGCM.82633A004352"])
def test_completar_no_guarda_un_vin_invalido_y_lo_deja_por_revisar(vin):
    complemento = completar_identificacion("", "", None, vin)
    assert complemento.vin == ""
    assert complemento.nuevos == ()
    assert complemento.por_revisar == (DatoPorRevisar(C.VIN, normalizar_vin(vin), R.INVALIDO),)


def test_completar_no_guarda_una_placa_que_no_cabe_y_la_deja_por_revisar():
    complemento = completar_identificacion("", "", "ABC-DEF-GHI-JK", None)
    assert complemento.placa == ""
    assert complemento.por_revisar == (DatoPorRevisar(C.PLACA, "ABCDEFGHIJK", R.INVALIDO),)


def test_completar_un_vin_invalido_no_impide_guardar_la_placa():
    complemento = completar_identificacion("", "", "ABC123", "MALO")
    assert (complemento.placa, complemento.vin) == ("ABC123", "")
    assert complemento.nuevos == (C.PLACA,)
    assert [dato.campo for dato in complemento.por_revisar] == [C.VIN]


def test_completar_sin_nada_digitado_deja_el_vehiculo_como_estaba():
    complemento = completar_identificacion("ABC123", "", None, " - ")
    assert complemento == Complemento("ABC123", "", (), ())
