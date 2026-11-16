"""Trayecto de un servicio: la ida va del origen al destino; el regreso, al revés y en su fecha."""
from datetime import datetime
from zoneinfo import ZoneInfo

from nucleo.estados import Estado
from nucleo.trayecto import hora_programada, puntos_del_servicio, regreso_bloqueado

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


# --- El regreso espera a su ida -----------------------------------------------------------------

def test_el_regreso_no_avanza_mientras_la_ida_no_este_entregada():
    for destino in (Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO):
        assert regreso_bloqueado(True, False, destino)


def test_el_regreso_avanza_cuando_la_ida_esta_entregada():
    for destino in (Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO):
        assert not regreso_bloqueado(True, True, destino)


def test_la_novedad_del_regreso_se_puede_reportar_aunque_la_ida_no_este_entregada():
    assert not regreso_bloqueado(True, False, Estado.NOVEDAD)


def test_una_ida_nunca_se_bloquea_por_esta_regla():
    assert not regreso_bloqueado(False, False, Estado.EN_CAMINO)
