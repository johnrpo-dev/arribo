"""Límite de intentos fallidos de ingreso, guardado en la base y con el reloj controlado.

5 fallos dentro de 15 minutos bloquean el celular 15 minutos: mientras tanto ni el PIN correcto
entra. Vale igual para un celular que no es de nadie, para no revelar cuáles existen.
"""
import pytest

from api.models import IntentosIngreso, TokenDispositivo
from nucleo.ingreso import DURACION_BLOQUEO

from .conftest import CELULAR_ANA, CELULAR_DE_NADIE, OTRO_PIN, ingresar

pytestmark = pytest.mark.django_db

BLOQUEADO = {
    "version": 1,
    "error": "demasiados_intentos",
    "detalle": "Demasiados intentos fallidos. Intente de nuevo en 15 minutos.",
    "reintentar_en": 900,
}


def fallar(api, veces, celular=CELULAR_ANA):
    for _ in range(veces):
        assert ingresar(api, celular=celular, pin=OTRO_PIN).status_code == 401


def test_cinco_fallos_bloquean_el_celular_aunque_despues_llegue_el_pin_correcto(
    api, ana_app, reloj
):
    fallar(api, 5)

    respuesta = ingresar(api)

    assert respuesta.status_code == 429
    assert respuesta.json() == BLOQUEADO
    assert respuesta["Retry-After"] == "900"
    assert not TokenDispositivo.objects.exists()


def test_cuatro_fallos_no_bloquean(api, ana_app, reloj):
    fallar(api, 4)

    assert ingresar(api).status_code == 200


def test_el_bloqueo_queda_guardado_en_la_base(api, ana_app, reloj):
    fallar(api, 5)

    intentos = IntentosIngreso.objects.get(celular=CELULAR_ANA)
    assert intentos.bloqueado_hasta == reloj.ahora + DURACION_BLOQUEO
    assert intentos.fallos == 0


def test_el_bloqueo_se_levanta_al_vencer_los_quince_minutos(api, ana_app, reloj):
    fallar(api, 5)

    reloj.avanzar(minutes=14, seconds=59)
    casi = ingresar(api)
    assert casi.status_code == 429
    assert casi.json()["reintentar_en"] == 1
    assert casi.json()["detalle"] == "Demasiados intentos fallidos. Intente de nuevo en 1 minuto."

    reloj.avanzar(seconds=1)
    assert ingresar(api).status_code == 200


def test_tras_el_bloqueo_la_cuenta_empieza_de_cero(api, ana_app, reloj):
    fallar(api, 5)
    reloj.avanzar(minutes=15)

    fallar(api, 4)

    assert ingresar(api).status_code == 200


def test_durante_el_bloqueo_los_intentos_no_alargan_el_bloqueo(api, ana_app, reloj):
    fallar(api, 5)
    for _ in range(3):
        reloj.avanzar(minutes=4)
        assert ingresar(api, pin=OTRO_PIN).status_code == 429

    reloj.avanzar(minutes=3)
    assert ingresar(api).status_code == 200


def test_un_acierto_reinicia_la_cuenta_de_fallos(api, ana_app, reloj):
    fallar(api, 4)
    assert ingresar(api).status_code == 200

    fallar(api, 4)

    assert ingresar(api).status_code == 200


def test_fallos_espaciados_mas_de_quince_minutos_no_bloquean(api, ana_app, reloj):
    for _ in range(6):
        fallar(api, 1)
        reloj.avanzar(minutes=16)

    assert ingresar(api).status_code == 200


def test_un_celular_que_no_es_de_nadie_se_bloquea_igual_y_con_la_misma_respuesta(
    api, ana_app, reloj
):
    fallar(api, 5, celular=CELULAR_DE_NADIE)
    fallar(api, 5, celular=CELULAR_ANA)

    de_nadie = ingresar(api, celular=CELULAR_DE_NADIE)
    de_ana = ingresar(api, celular=CELULAR_ANA)

    assert de_nadie.status_code == de_ana.status_code == 429
    assert de_nadie.content == de_ana.content
    assert de_nadie["Retry-After"] == de_ana["Retry-After"]


def test_el_mismo_celular_escrito_de_otra_forma_comparte_la_cuenta(api, ana_app, reloj):
    for celular in ["3000000001", "+57 300 000 0001", "300-000-0001", "573000000001", "300 0000001"]:
        assert ingresar(api, celular=celular, pin=OTRO_PIN).status_code == 401

    assert ingresar(api).status_code == 429
    assert IntentosIngreso.objects.count() == 1


def test_el_bloqueo_de_un_celular_no_afecta_a_otro(api, ana_app, beto_app, reloj):
    fallar(api, 5)

    assert ingresar(api, celular="3000000002", dispositivo_id="celular-de-beto").status_code == 200
