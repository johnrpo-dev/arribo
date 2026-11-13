"""El PIN del conductor: 6 dígitos, guardado solo con el hash de Django, fijado desde el admin."""
import pytest
from django.conf import global_settings
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, transaction

import config.settings as ajustes_del_proyecto
from flota.models import Conductor
from nucleo.ingreso import PinInvalido

from .conftest import OTRO_PIN, PIN

pytestmark = pytest.mark.django_db


def test_el_pin_se_guarda_con_el_hash_de_django_nunca_en_claro(settings, ana):
    settings.PASSWORD_HASHERS = global_settings.PASSWORD_HASHERS  # el de producción

    ana.fijar_pin(PIN)
    ana.save()
    ana.refresh_from_db()

    assert ana.pin_hash.startswith("pbkdf2_sha256$")
    assert PIN not in ana.pin_hash
    assert check_password(PIN, ana.pin_hash)
    assert ana.verificar_pin(PIN)
    assert not ana.verificar_pin(OTRO_PIN)


def test_el_proyecto_usa_los_hash_por_defecto_de_django():
    assert not hasattr(ajustes_del_proyecto, "PASSWORD_HASHERS")


def test_el_mismo_pin_en_dos_conductores_deja_hash_distintos(ana, beto):
    ana.fijar_pin(PIN)
    beto.fijar_pin(PIN)

    assert ana.pin_hash != beto.pin_hash


@pytest.mark.parametrize("pin", ["1234", "12345", "1234567", "12a456", "", " 482913"])
def test_fijar_un_pin_que_no_es_de_seis_digitos_falla_y_no_cambia_el_hash(ana, pin):
    ana.fijar_pin(PIN)
    antes = ana.pin_hash

    with pytest.raises(PinInvalido):
        ana.fijar_pin(pin)

    assert ana.pin_hash == antes


def test_sin_pin_fijado_ningun_pin_es_correcto(ana):
    assert not ana.tiene_pin
    assert not ana.verificar_pin("000000")


def test_la_base_rechaza_un_pin_guardado_en_claro(ana):
    with pytest.raises(IntegrityError, match="conductor_pin_solo_hash"), transaction.atomic():
        Conductor.objects.filter(pk=ana.pk).update(pin_hash=PIN)


def test_si_django_cambia_el_algoritmo_el_hash_se_rehace_al_ingresar(settings, ana):
    ana.fijar_pin(PIN)
    ana.save()
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.ScryptPasswordHasher",
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]

    assert ana.verificar_pin(PIN)

    ana.refresh_from_db()
    assert ana.pin_hash.startswith("scrypt$")
    assert ana.verificar_pin(PIN)


# --- Admin ---------------------------------------------------------------------------------------


def _formulario(conductor, **cambios):
    datos = {"nombre": conductor.nombre, "celular": conductor.celular, "usuario": "",
             "activo": "on", "nuevo_pin": ""}
    if conductor.usuario_id:
        datos["usuario"] = conductor.usuario_id
    datos.update(cambios)
    return datos


def _url(conductor):
    return f"/admin/flota/conductor/{conductor.pk}/change/"


def test_el_admin_fija_el_pin_y_guarda_solo_su_hash(admin_client, ana):
    respuesta = admin_client.post(_url(ana), _formulario(ana, nuevo_pin=PIN))

    assert respuesta.status_code == 302
    ana.refresh_from_db()
    assert ana.verificar_pin(PIN)
    assert PIN not in ana.pin_hash


def test_el_admin_rechaza_un_pin_que_no_es_de_seis_digitos(admin_client, ana):
    respuesta = admin_client.post(_url(ana), _formulario(ana, nuevo_pin="1234"))

    assert respuesta.status_code == 200
    assert "El PIN tiene exactamente 6 dígitos" in respuesta.content.decode()
    ana.refresh_from_db()
    assert not ana.tiene_pin


def test_dejar_vacio_el_nuevo_pin_en_el_admin_no_cambia_el_pin(admin_client, ana_app):
    antes = ana_app.pin_hash

    respuesta = admin_client.post(_url(ana_app), _formulario(ana_app, nombre="Ana María"))

    assert respuesta.status_code == 302
    ana_app.refresh_from_db()
    assert ana_app.nombre == "Ana María"
    assert ana_app.pin_hash == antes


def test_el_admin_no_muestra_el_pin_ni_su_hash(admin_client, ana_app):
    pagina = admin_client.get(_url(ana_app)).content.decode()

    assert 'name="nuevo_pin"' in pagina
    assert ana_app.pin_hash not in pagina
    assert 'name="pin_hash"' not in pagina


def test_la_lista_del_admin_dice_si_el_conductor_tiene_pin(admin_client, ana_app, beto):
    pagina = admin_client.get("/admin/flota/conductor/").content.decode()

    assert "PIN fijado" in pagina
