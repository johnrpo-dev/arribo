"""`requiere_rol` probado directamente, sin pasar por las URLs."""
import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from panel.roles import requiere_rol, tiene_rol

pytestmark = pytest.mark.django_db


@requiere_rol("logistica", "administrador")
def vista_de_prueba(request):
    return HttpResponse("dentro")


def peticion(usuario, ruta="/algo/?x=1"):
    request = RequestFactory().get(ruta)
    request.user = usuario
    return request


def test_sin_sesion_redirige_al_ingreso_con_la_ruta_completa():
    respuesta = vista_de_prueba(peticion(AnonymousUser()))
    assert respuesta.status_code == 302
    assert respuesta.url == "/ingresar/?next=/algo/%3Fx%3D1"


@pytest.mark.parametrize("roles", [("logistica",), ("administrador",), ("logistica", "facturacion")])
def test_con_un_rol_permitido_entra(crear_usuario, roles):
    respuesta = vista_de_prueba(peticion(crear_usuario(*roles)))
    assert respuesta.content == b"dentro"


@pytest.mark.parametrize("roles", [(), ("facturacion",), ("conductor",)])
def test_sin_un_rol_permitido_niega_el_acceso(crear_usuario, roles):
    with pytest.raises(PermissionDenied):
        vista_de_prueba(peticion(crear_usuario(*roles)))


def test_el_grupo_conductor_niega_aunque_tenga_un_rol_permitido(crear_usuario):
    with pytest.raises(PermissionDenied):
        vista_de_prueba(peticion(crear_usuario("conductor", "logistica")))


def test_el_superusuario_pasa_siempre(crear_usuario):
    assert vista_de_prueba(peticion(crear_usuario(superusuario=True))).content == b"dentro"


def test_un_usuario_desactivado_no_tiene_rol(crear_usuario):
    usuario = crear_usuario("logistica", is_active=False)
    assert not tiene_rol(usuario, ["logistica"])


def test_guarda_los_roles_permitidos_y_el_nombre_de_la_vista():
    assert vista_de_prueba.roles_permitidos == ("logistica", "administrador")
    assert vista_de_prueba.__name__ == "vista_de_prueba"


def test_exige_al_menos_un_rol():
    with pytest.raises(ValueError):
        requiere_rol()


@pytest.mark.parametrize("rol", ["conductor", "logística", "admin"])
def test_rechaza_roles_que_no_son_del_panel(rol):
    with pytest.raises(ValueError):
        requiere_rol(rol)


def test_consulta_los_grupos_una_sola_vez_por_peticion(crear_usuario, django_assert_num_queries):
    usuario = crear_usuario("logistica")
    with django_assert_num_queries(1):
        assert tiene_rol(usuario, ["logistica"])
        assert tiene_rol(usuario, ["administrador", "logistica"])
        assert not tiene_rol(usuario, ["facturacion"])
