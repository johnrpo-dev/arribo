"""Placas y teléfonos escritos de distintas formas quedan iguales."""
import pytest

from nucleo.identificacion import TelefonoInvalido, normalizar_placa, normalizar_telefono
from nucleo.tipos import TipoServicio


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
