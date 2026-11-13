"""Trayecto de un servicio: la ida va del origen al destino; el regreso, al revés y en su fecha."""
from datetime import datetime
from zoneinfo import ZoneInfo

from nucleo.trayecto import hora_programada, puntos_del_servicio

BOGOTA = ZoneInfo("America/Bogota")
IDA = datetime(2026, 11, 20, 8, 0, tzinfo=BOGOTA)
REGRESO = datetime(2026, 11, 22, 17, 0, tzinfo=BOGOTA)


def test_la_ida_va_del_origen_al_destino():
    assert puntos_del_servicio(False, "origen", "destino") == ("origen", "destino")


def test_el_regreso_va_del_destino_al_origen():
    assert puntos_del_servicio(True, "origen", "destino") == ("destino", "origen")


def test_la_ida_es_para_la_hora_programada():
    assert hora_programada(False, IDA, REGRESO) == IDA


def test_la_ida_sin_hora_programada_es_inmediata():
    assert hora_programada(False, None, REGRESO) is None


def test_el_regreso_es_para_la_fecha_de_regreso():
    assert hora_programada(True, IDA, REGRESO) == REGRESO
