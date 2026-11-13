"""La navegación muestra solo las secciones del rol, definidas en `panel/secciones.py`."""
import re

import pytest
from django.urls import resolve, reverse

from panel import views
from panel.roles import ROLES_DEL_PANEL
from panel.secciones import SECCIONES

pytestmark = pytest.mark.django_db

TODAS = [s.nombre for s in SECCIONES]


def nombres_en_la_navegacion(html):
    nav = re.search(r'<nav class="navegacion".*?</nav>', html, re.DOTALL).group(0)
    return re.findall(r"<a [^>]*>([^<]+)</a>", nav)


def comprobar_navegacion(client, usuario, esperadas):
    client.force_login(usuario)
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert nombres_en_la_navegacion(respuesta.content.decode()) == esperadas
    for seccion in SECCIONES:
        codigo = client.get(f"/{seccion.ruta}").status_code
        assert codigo == (200 if seccion.nombre in esperadas else 403), seccion.ruta


def test_navegacion_de_logistica(client, crear_usuario):
    comprobar_navegacion(
        client, crear_usuario("logistica"), ["Tablero", "Nueva solicitud", "Solicitudes"]
    )


def test_navegacion_de_facturacion(client, crear_usuario):
    comprobar_navegacion(client, crear_usuario("facturacion"), ["Cobros"])


def test_navegacion_del_administrador(client, crear_usuario):
    comprobar_navegacion(client, crear_usuario("administrador"), TODAS)


def test_navegacion_de_logistica_y_facturacion_juntas(client, crear_usuario):
    comprobar_navegacion(
        client,
        crear_usuario("logistica", "facturacion"),
        ["Tablero", "Nueva solicitud", "Solicitudes", "Cobros"],
    )


def test_el_superusuario_ve_todo(client, crear_usuario):
    usuario = crear_usuario(superusuario=True)
    comprobar_navegacion(client, usuario, TODAS)
    assert client.get("/estilos/").status_code == 200
    assert "Superusuario" in client.get("/").content.decode()


def test_el_superusuario_ve_todo_aunque_este_en_el_grupo_conductor(client, crear_usuario):
    comprobar_navegacion(client, crear_usuario("conductor", superusuario=True), TODAS)


def test_las_secciones_son_las_pedidas_en_orden():
    assert [(s.nombre, set(s.roles)) for s in SECCIONES] == [
        ("Tablero", {"logistica", "administrador"}),
        ("Nueva solicitud", {"logistica", "administrador"}),
        ("Solicitudes", {"logistica", "administrador"}),
        ("Cobros", {"facturacion", "administrador"}),
        ("Flota y documentos", {"administrador"}),
        ("Panel del dueño", {"administrador"}),
        ("Configuración", {"administrador"}),
    ]


def test_cada_seccion_tiene_clave_y_ruta_unicas_y_roles_del_panel():
    assert len({s.clave for s in SECCIONES}) == len(SECCIONES)
    assert len({s.ruta for s in SECCIONES}) == len(SECCIONES)
    for seccion in SECCIONES:
        assert set(seccion.roles) <= set(ROLES_DEL_PANEL)
        assert seccion.ruta.endswith("/") and not seccion.ruta.startswith("/")


def test_cada_seccion_tiene_su_url_protegida_con_sus_roles():
    for seccion in SECCIONES:
        assert reverse(seccion.clave) == f"/{seccion.ruta}"
        coincidencia = resolve(f"/{seccion.ruta}")
        assert coincidencia.func.roles_permitidos == seccion.roles


def test_las_secciones_sin_pantalla_usan_la_vista_generica():
    for seccion in SECCIONES:
        if not seccion.disponible:
            coincidencia = resolve(f"/{seccion.ruta}")
            assert coincidencia.func.__wrapped__ is views.no_disponible
            assert coincidencia.kwargs == {"clave": seccion.clave}
