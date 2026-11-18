from datetime import UTC, date, datetime, timedelta

import pytest

from nucleo.alertas import (
    documento_alerta,
    recogido_sin_entregado_vencido,
    sin_asignar_vencido,
)
from nucleo.documentos import Documento

AHORA = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
HOY = date(2026, 11, 18)


def sin_asignar(registrada=AHORA, hora=None, minutos=10, horas=2) -> bool:
    return sin_asignar_vencido(
        ahora=AHORA,
        registrada=registrada,
        hora_programada=hora,
        minutos_inmediato=minutos,
        horas_programado=horas,
    )


@pytest.mark.parametrize(
    ("hace", "alerta"), [(0, False), (9, False), (10, True), (45, True)]
)
def test_inmediato_sin_asignar_alerta_desde_el_umbral_en_minutos(hace, alerta):
    assert sin_asignar(registrada=AHORA - timedelta(minutes=hace)) is alerta


def test_el_umbral_de_minutos_sale_de_la_configuracion():
    registrada = AHORA - timedelta(minutes=12)
    assert sin_asignar(registrada=registrada, minutos=10)
    assert not sin_asignar(registrada=registrada, minutos=15)


@pytest.mark.parametrize(
    ("faltan", "alerta"),
    [(timedelta(hours=5), False), (timedelta(hours=2, minutes=1), False),
     (timedelta(hours=2), True), (timedelta(minutes=30), True), (timedelta(hours=-1), True)],
)
def test_programado_sin_asignar_alerta_desde_horas_antes(faltan, alerta):
    # Registrado hace mucho: en un programado no cuenta la espera, sino lo que falta.
    vieja = AHORA - timedelta(days=3)
    assert sin_asignar(registrada=vieja, hora=AHORA + faltan) is alerta


@pytest.mark.parametrize(("hace", "alerta"), [(3, False), (4, True), (9, True)])
def test_recogido_sin_entregado_alerta_desde_el_umbral_en_horas(hace, alerta):
    recogido = AHORA - timedelta(hours=hace)
    assert recogido_sin_entregado_vencido(ahora=AHORA, recogido_en=recogido, horas=4) is alerta


def test_un_umbral_en_cero_no_se_acepta():
    with pytest.raises(ValueError):
        sin_asignar(minutos=0)
    with pytest.raises(ValueError):
        recogido_sin_entregado_vencido(ahora=AHORA, recogido_en=AHORA, horas=0)


@pytest.mark.parametrize(
    ("documento", "alerta"),
    [
        (Documento(vence=HOY + timedelta(days=31)), False),  # vigente
        (Documento(vence=HOY + timedelta(days=30)), True),  # por vencer
        (Documento(vence=HOY), True),  # último día
        (Documento(vence=HOY - timedelta(days=1)), True),  # vencido
        (Documento(aplica_desde=HOY + timedelta(days=90)), False),  # aún no aplica, lejos
        (Documento(aplica_desde=HOY + timedelta(days=10)), True),  # se exige pronto
        (None, False),  # falta: no hay documento al que apuntar
    ],
)
def test_documento_alerta_por_vencer_o_vencido(documento, alerta):
    assert documento_alerta(documento, HOY, 30) is alerta

