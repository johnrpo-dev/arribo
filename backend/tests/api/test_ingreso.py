"""Ingreso a la app con celular y PIN: quién entra, qué recibe y qué no revela."""
import hashlib

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from api.models import TokenDispositivo

from .conftest import (
    CELULAR_ANA,
    CELULAR_DE_NADIE,
    OTRO_PIN,
    PIN,
    URL_ASIGNACIONES,
    URL_INGRESO,
    cliente_con,
    ingresar,
)

pytestmark = pytest.mark.django_db

CREDENCIALES_INVALIDAS = {
    "version": 1,
    "error": "credenciales_invalidas",
    "detalle": "Celular o PIN incorrectos.",
}


def test_ingreso_correcto_entrega_el_token_y_los_datos_del_conductor(api, ana_app):
    respuesta = ingresar(api, dispositivo_nombre="Moto G de Ana")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert set(datos) == {"version", "token", "conductor"}
    assert datos["version"] == 1
    assert datos["conductor"] == {"id": ana_app.pk, "nombre": "Ana", "celular": CELULAR_ANA}
    token = TokenDispositivo.objects.get()
    assert token.conductor == ana_app
    assert (token.dispositivo_id, token.dispositivo_nombre) == ("celular-de-ana", "Moto G de Ana")
    assert token.vigente


def test_el_token_del_ingreso_sirve_para_pedir_las_asignaciones(api, ana_app):
    clave = ingresar(api).json()["token"]

    assert cliente_con(clave).get(URL_ASIGNACIONES).status_code == 200


@pytest.mark.parametrize("celular", ["+57 300 000 0001", "300-000-0001", "573000000001"])
def test_el_celular_se_puede_escribir_con_cualquier_formato(api, ana_app, celular):
    assert ingresar(api, celular=celular).status_code == 200


def test_del_token_solo_se_guarda_su_hash(api, ana_app):
    clave = ingresar(api).json()["token"]

    guardado = TokenDispositivo.objects.values().get()
    assert guardado["clave_hash"] == hashlib.sha256(clave.encode()).hexdigest()
    assert clave not in str(guardado)


def test_dos_ingresos_entregan_tokens_distintos(api, ana_app):
    primero = ingresar(api, dispositivo_id="celular-1").json()["token"]
    segundo = ingresar(api, dispositivo_id="celular-2").json()["token"]

    assert primero != segundo


def test_pin_incorrecto_responde_401_y_no_entrega_token(api, ana_app):
    respuesta = ingresar(api, pin=OTRO_PIN)

    assert respuesta.status_code == 401
    assert respuesta.json() == CREDENCIALES_INVALIDAS
    assert respuesta["WWW-Authenticate"] == 'Bearer realm="arribo"'
    assert not TokenDispositivo.objects.exists()


def test_celular_inexistente_y_pin_malo_reciben_exactamente_la_misma_respuesta(api, ana_app):
    pin_malo = ingresar(api, pin=OTRO_PIN)
    de_nadie = ingresar(api, celular=CELULAR_DE_NADIE)

    assert de_nadie.status_code == pin_malo.status_code == 401
    assert de_nadie.content == pin_malo.content
    assert de_nadie["WWW-Authenticate"] == pin_malo["WWW-Authenticate"]
    assert de_nadie.json() == CREDENCIALES_INVALIDAS


def test_un_conductor_sin_pin_fijado_no_entra_y_recibe_la_misma_respuesta(api, ana, dar_acceso):
    dar_acceso(ana)
    ana.pin_hash = ""
    ana.save()

    respuesta = ingresar(api)

    assert respuesta.status_code == 401
    assert respuesta.json() == CREDENCIALES_INVALIDAS


def test_un_conductor_inactivo_no_entra_aunque_el_pin_sea_correcto(api, ana_app):
    ana_app.activo = False
    ana_app.save()

    respuesta = ingresar(api)

    assert respuesta.status_code == 401
    assert respuesta.json() == {
        "version": 1,
        "error": "conductor_no_habilitado",
        "detalle": "Este conductor no tiene acceso a la app. Hable con logística.",
    }
    assert not TokenDispositivo.objects.exists()


def _sin_usuario(conductor):
    conductor.usuario = None
    conductor.save()


def _usuario_inactivo(conductor):
    conductor.usuario.is_active = False
    conductor.usuario.save()


def _fuera_del_grupo_conductor(conductor):
    conductor.usuario.groups.clear()


def _solo_de_logistica(conductor):
    conductor.usuario.groups.set([Group.objects.get(name="logistica")])


@pytest.mark.parametrize(
    "quitar_acceso",
    [_sin_usuario, _usuario_inactivo, _fuera_del_grupo_conductor, _solo_de_logistica],
)
def test_solo_entra_un_conductor_con_usuario_activo_del_grupo_conductor(
    api, ana_app, quitar_acceso
):
    quitar_acceso(ana_app)

    respuesta = ingresar(api)

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "conductor_no_habilitado"
    assert not TokenDispositivo.objects.exists()


def test_los_datos_incompletos_o_mal_escritos_responden_400_por_campo(api, ana_app):
    respuesta = api.post(URL_INGRESO, {"celular": "123", "pin": "1234"}, format="json")

    assert respuesta.status_code == 400
    datos = respuesta.json()
    assert (datos["version"], datos["error"]) == (1, "datos_invalidos")
    assert set(datos["campos"]) == {"celular", "pin", "dispositivo_id"}
    assert "6 dígitos" in datos["campos"]["pin"][0]


@pytest.mark.parametrize("pin", ["1234", "12345", "1234567", "48291a", " 482913"])
def test_un_pin_que_no_es_de_seis_digitos_no_se_acepta(api, ana_app, pin):
    respuesta = ingresar(api, pin=pin)

    assert respuesta.status_code == 400
    assert set(respuesta.json()["campos"]) == {"pin"}


def test_un_pin_con_otro_formato_no_cuenta_como_fallo(api, ana_app):
    for _ in range(6):
        assert ingresar(api, pin="1234").status_code == 400

    assert ingresar(api).status_code == 200


def test_un_cuerpo_que_no_es_json_valido_responde_400(api):
    respuesta = api.post(URL_INGRESO, data="{celular", content_type="application/json")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "json_invalido"


def test_el_ingreso_solo_acepta_post(api):
    respuesta = api.get(URL_INGRESO)

    assert respuesta.status_code == 405
    assert respuesta.json()["error"] == "metodo_no_permitido"


def test_un_token_viejo_en_la_cabecera_no_impide_volver_a_ingresar(api, ana_app):
    vieja = ingresar(api).json()["token"]
    TokenDispositivo.objects.update(revocado_en=timezone.now())

    respuesta = cliente_con(vieja).post(
        URL_INGRESO,
        {"celular": CELULAR_ANA, "pin": PIN, "dispositivo_id": "celular-de-ana"},
        format="json",
    )

    assert respuesta.status_code == 200


def test_volver_a_ingresar_en_el_mismo_celular_revoca_el_token_anterior(api, ana_app):
    anterior = ingresar(api).json()["token"]
    nuevo = ingresar(api).json()["token"]

    assert TokenDispositivo.objects.filter(revocado_en__isnull=True).count() == 1
    assert cliente_con(anterior).get(URL_ASIGNACIONES).status_code == 401
    assert cliente_con(nuevo).get(URL_ASIGNACIONES).status_code == 200


def test_ingresar_en_otro_celular_no_cierra_la_sesion_del_primero(api, ana_app):
    primero = ingresar(api, dispositivo_id="celular-1").json()["token"]
    segundo = ingresar(api, dispositivo_id="celular-2").json()["token"]

    assert cliente_con(primero).get(URL_ASIGNACIONES).status_code == 200
    assert cliente_con(segundo).get(URL_ASIGNACIONES).status_code == 200
