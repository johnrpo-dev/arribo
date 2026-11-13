"""Ingreso, salida y redirección al ingreso sin sesión."""
import pytest
from django.contrib.staticfiles import finders

from tests.panel.conftest import CLAVE

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("ruta", ["/", "/tablero/", "/cobros/", "/configuracion/", "/estilos/"])
def test_sin_sesion_redirige_al_ingreso_con_la_ruta_pedida(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert respuesta.url == f"/ingresar/?next={ruta}"


def test_la_pagina_de_ingreso_es_publica_y_en_espanol(client):
    respuesta = client.get("/ingresar/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert '<html lang="es">' in html
    assert "Ingresar al panel" in html
    assert "Usuario" in html and "Contraseña" in html


def test_ingreso_correcto_lleva_al_inicio(client, crear_usuario):
    crear_usuario("logistica", username="marta")
    respuesta = client.post("/ingresar/", {"username": "marta", "password": CLAVE})
    assert respuesta.status_code == 302
    assert respuesta.url == "/"
    assert client.get("/").status_code == 200


def test_ingreso_correcto_respeta_la_pagina_pedida(client, crear_usuario):
    crear_usuario("logistica", username="marta")
    respuesta = client.post(
        "/ingresar/?next=/tablero/", {"username": "marta", "password": CLAVE, "next": "/tablero/"}
    )
    assert respuesta.status_code == 302
    assert respuesta.url == "/tablero/"


def test_ingreso_no_redirige_a_otro_sitio(client, crear_usuario):
    crear_usuario("logistica", username="marta")
    respuesta = client.post(
        "/ingresar/", {"username": "marta", "password": CLAVE, "next": "https://ejemplo.com/"}
    )
    assert respuesta.url == "/"


def test_ingreso_incorrecto_muestra_error_en_espanol_y_no_abre_sesion(client, crear_usuario):
    crear_usuario("logistica", username="marta")
    respuesta = client.post("/ingresar/", {"username": "marta", "password": "otra"})
    assert respuesta.status_code == 200
    assert "Usuario o contraseña incorrectos" in respuesta.content.decode()
    assert "_auth_user_id" not in client.session
    assert client.get("/").status_code == 302


def test_usuario_con_sesion_que_abre_el_ingreso_va_al_inicio(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    respuesta = client.get("/ingresar/")
    assert respuesta.status_code == 302
    assert respuesta.url == "/"


def test_salir_por_get_no_cierra_la_sesion(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    assert client.get("/salir/").status_code == 405
    assert client.get("/").status_code == 200


def test_salir_por_post_cierra_la_sesion_y_vuelve_al_ingreso(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    respuesta = client.post("/salir/")
    assert respuesta.status_code == 302
    assert respuesta.url == "/ingresar/"
    assert client.get("/").status_code == 302


def test_salud_sigue_publica_y_sin_cambios(client):
    respuesta = client.get("/salud/")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "servicio": "arribo"}


def test_la_plantilla_base_carga_estilos_htmx_y_el_token_csrf(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    html = client.get("/").content.decode()
    assert "/static/panel/arribo.css" in html
    assert "/static/panel/htmx-2.0.11.min.js" in html
    assert "hx-headers='{\"X-CSRFToken\": \"" in html
    assert 'href="#contenido"' in html and 'id="contenido"' in html
    assert "<nav" in html and "<main" in html and "<header" in html


def test_los_estaticos_existen():
    assert finders.find("panel/arribo.css")
    assert finders.find("panel/htmx-2.0.11.min.js")
