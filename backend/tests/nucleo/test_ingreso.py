"""Formato del PIN y límite de intentos fallidos por celular (reglas puras, con el reloj fijo)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nucleo.ingreso import (
    DURACION_BLOQUEO,
    MAXIMO_FALLOS,
    VENTANA_FALLOS,
    Intentos,
    PinInvalido,
    bloqueado,
    registrar_acierto,
    registrar_fallo,
    segundos_de_bloqueo,
    validar_pin,
)

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=ZoneInfo("America/Bogota"))


def minutos(n: float) -> datetime:
    return T0 + timedelta(minutes=n)


def fallar(veces: int, *, desde: Intentos | None = None, cada: float = 1, inicio: float = 0):
    intentos = desde or Intentos()
    for vez in range(veces):
        intentos = registrar_fallo(intentos, minutos(inicio + vez * cada))
    return intentos


# --- PIN -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("pin", ["000000", "482913", "999999"])
def test_el_pin_tiene_seis_digitos(pin):
    validar_pin(pin)


@pytest.mark.parametrize(
    "pin",
    ["", "1234", "12345", "1234567", "12a456", " 123456", "123456 ", "12 456", "١٢٣٤٥٦", None, 123456],
)
def test_el_pin_rechaza_lo_que_no_son_seis_digitos(pin):
    with pytest.raises(PinInvalido, match="6 dígitos"):
        validar_pin(pin)


# --- Intentos ------------------------------------------------------------------------------------


def test_el_limite_es_cinco_fallos_en_quince_minutos_con_bloqueo_de_quince_minutos():
    assert MAXIMO_FALLOS == 5
    assert VENTANA_FALLOS == timedelta(minutes=15)
    assert DURACION_BLOQUEO == timedelta(minutes=15)


def test_sin_fallos_no_hay_bloqueo():
    assert not bloqueado(Intentos(), T0)
    assert segundos_de_bloqueo(Intentos(), T0) == 0


def test_cuatro_fallos_no_bloquean():
    intentos = fallar(4)
    assert intentos.fallos == 4
    assert not bloqueado(intentos, minutos(4))


def test_el_quinto_fallo_en_la_ventana_bloquea_quince_minutos():
    intentos = fallar(5)
    assert intentos.bloqueado_hasta == minutos(4) + DURACION_BLOQUEO
    assert bloqueado(intentos, minutos(5))
    assert bloqueado(intentos, minutos(18.99))


def test_el_bloqueo_vence_a_los_quince_minutos():
    intentos = fallar(5)
    assert not bloqueado(intentos, minutos(4) + DURACION_BLOQUEO)


def test_al_bloquear_la_cuenta_de_fallos_vuelve_a_cero():
    intentos = fallar(5)
    assert intentos.fallos == 0
    assert intentos.primer_fallo is None


def test_tras_el_bloqueo_vuelven_a_caber_cuatro_fallos():
    vencido = minutos(4) + DURACION_BLOQUEO
    intentos = fallar(4, desde=fallar(5), inicio=(vencido - T0).total_seconds() / 60)
    assert not bloqueado(intentos, vencido + timedelta(minutes=4))
    assert intentos.fallos == 4


def test_los_fallos_espaciados_mas_de_quince_minutos_no_bloquean():
    intentos = fallar(10, cada=16)
    assert not bloqueado(intentos, minutos(10 * 16))
    assert intentos.fallos == 1


def test_la_ventana_se_cuenta_desde_el_primer_fallo():
    # Cuatro fallos, y el quinto llega justo a los 15 minutos del primero: ventana nueva.
    intentos = fallar(4)
    intentos = registrar_fallo(intentos, minutos(15))
    assert not bloqueado(intentos, minutos(15))
    assert intentos.fallos == 1
    assert intentos.primer_fallo == minutos(15)


def test_un_fallo_durante_el_bloqueo_no_lo_alarga():
    intentos = fallar(5)
    assert registrar_fallo(intentos, minutos(10)) == intentos


def test_los_segundos_de_bloqueo_se_redondean_hacia_arriba():
    intentos = fallar(5)
    assert segundos_de_bloqueo(intentos, minutos(4)) == 15 * 60
    assert segundos_de_bloqueo(intentos, minutos(4) + timedelta(seconds=0.5)) == 15 * 60
    assert segundos_de_bloqueo(intentos, minutos(18) + timedelta(seconds=59.1)) == 1


def test_un_acierto_borra_la_cuenta_de_fallos():
    assert registrar_acierto() == Intentos()
