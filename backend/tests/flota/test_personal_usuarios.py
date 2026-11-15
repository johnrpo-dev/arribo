"""Usuarios de oficina en "Personal y grúas", contra PostgreSQL: crearlos con un rol, cambiar rol,
restablecer contraseña, desactivar y reactivar, sin quedarse nunca sin administrador."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from flota import operaciones as op
from nucleo.personal import UltimoAdministrador

from ..panel.conftest import CLAVE

pytestmark = pytest.mark.django_db

Usuario = get_user_model()
URL_NUEVO = "/flota/usuarios/nuevo/"
CONTRASENA = "grua-amarilla-2026"


def url(usuario, accion=""):
    return f"/flota/usuarios/{usuario.pk}/{accion}"


def datos_nuevo(**otros):
    datos = {
        "nombre": "Lina Restrepo",
        "usuario": "lina",
        "contrasena": CONTRASENA,
        "contrasena_confirmacion": CONTRASENA,
        "rol": "logistica",
    }
    datos.update(otros)
    return datos


def navegacion(cliente):
    html = cliente.get("/").content.decode()
    nav = re.search(r'<nav class="navegacion".*?</nav>', html, re.DOTALL).group(0)
    return re.findall(r"<a [^>]*>([^<]+)</a>", nav)


# --- Crear -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "secciones"),
    [
        ("logistica", ["Tablero", "Nueva solicitud", "Solicitudes"]),
        # Cobros y Panel del dueño no salen en el menú hasta tener pantalla (1a-08c).
        ("facturacion", []),
        (
            "administrador",
            ["Tablero", "Nueva solicitud", "Solicitudes", "Flota y personal", "Configuración"],
        ),
    ],
)
def test_el_usuario_creado_con_cada_rol_entra_y_ve_sus_secciones(
    client, administrador, rol, secciones
):
    respuesta = client.post(URL_NUEVO, datos_nuevo(rol=rol))

    assert respuesta.status_code == 302
    nuevo = Usuario.objects.get(username="lina")
    assert nuevo.first_name == "Lina Restrepo"
    assert list(nuevo.groups.values_list("name", flat=True)) == [rol]
    assert not nuevo.is_staff and not nuevo.is_superuser
    otro = Client()
    assert otro.login(username="lina", password=CONTRASENA)
    assert navegacion(otro) == secciones


@pytest.mark.parametrize(
    ("contrasena", "mensaje"),
    [
        ("corta1", "demasiado corta"),
        ("12345678901", "completamente numérica"),
        ("password123", "demasiado común"),
        ("lina-restrepo", "muy parecida"),
    ],
)
def test_contrasena_debil_da_error_visible_en_espanol(client, administrador, contrasena, mensaje):
    respuesta = client.post(
        URL_NUEVO, datos_nuevo(contrasena=contrasena, contrasena_confirmacion=contrasena)
    )

    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert mensaje in contenido
    assert "No se guardó" in contenido
    assert not Usuario.objects.filter(username="lina").exists()


def test_las_contrasenas_deben_coincidir(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(contrasena_confirmacion="otra-cosa-2026"))

    assert "Las dos contraseñas no coinciden." in respuesta.content.decode()
    assert not Usuario.objects.filter(username="lina").exists()


@pytest.mark.parametrize("nombre", ["lina", "LINA"])
def test_usuario_repetido_da_error(client, administrador, crear_usuario, nombre):
    crear_usuario("facturacion", username="lina")

    respuesta = client.post(URL_NUEVO, datos_nuevo(usuario=nombre))

    assert f"Ya existe un usuario llamado {nombre}." in respuesta.content.decode()
    assert Usuario.objects.filter(username__iexact="lina").count() == 1


def test_usuario_con_espacios_da_error(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(usuario="lina restrepo"))

    assert "sin espacios" in respuesta.content.decode()
    assert not Usuario.objects.filter(first_name="Lina Restrepo").exists()


def test_la_contrasena_nunca_vuelve_a_la_pantalla(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(usuario="lina restrepo"))

    assert CONTRASENA not in respuesta.content.decode()


def test_la_lista_no_muestra_a_los_conductores(client, administrador, ana_app):
    contenido = client.get("/flota/").content.decode()

    assert ana_app.usuario.username not in contenido
    assert "Olga" in contenido


# --- Rol -------------------------------------------------------------------------------------------


def test_cambiar_rol_deja_un_solo_rol(client, administrador, crear_usuario):
    lina = crear_usuario("logistica", "facturacion")

    respuesta = client.post(url(lina, "rol/"), {"rol-rol": "administrador"})

    assert respuesta.status_code == 302
    assert list(lina.groups.values_list("name", flat=True)) == ["administrador"]


def test_el_ultimo_administrador_no_se_quita_el_rol(client, administrador):
    respuesta = client.post(url(administrador, "rol/"), {"rol-rol": "logistica"})

    assert respuesta.status_code == 200
    assert "único administrador activo" in respuesta.content.decode()
    assert administrador.groups.filter(name="administrador").exists()


def test_con_otro_administrador_si_puede_quitarse_el_rol(client, administrador, crear_usuario):
    crear_usuario("administrador")

    respuesta = client.post(url(administrador, "rol/"), {"rol-rol": "logistica"})

    assert respuesta.status_code == 302
    assert respuesta.url == "/"
    assert list(administrador.groups.values_list("name", flat=True)) == ["logistica"]
    assert client.get("/flota/").status_code == 403


def test_un_administrador_inactivo_no_cuenta_como_el_que_queda(
    client, administrador, crear_usuario
):
    crear_usuario("administrador", is_active=False)

    respuesta = client.post(url(administrador, "rol/"), {"rol-rol": "facturacion"})

    assert "único administrador activo" in respuesta.content.decode()


def test_un_superusuario_activo_cuenta_como_administrador(client, administrador, crear_usuario):
    crear_usuario(superusuario=True)

    respuesta = client.post(url(administrador, "rol/"), {"rol-rol": "facturacion"})

    assert respuesta.status_code == 302


def test_al_superusuario_no_se_le_cambia_rol_ni_estado_desde_la_pantalla(
    client, administrador, crear_usuario
):
    dueno = crear_usuario(superusuario=True, username="john")

    pagina = client.get(url(dueno)).content.decode()
    client.post(url(dueno, "rol/"), {"rol-rol": "logistica"})
    client.post(url(dueno, "desactivar/"))

    dueno.refresh_from_db()
    assert "acceso total" in pagina
    assert 'name="rol-rol"' not in pagina
    assert dueno.is_active and dueno.is_superuser
    assert not dueno.groups.exists()


# --- Contraseña ------------------------------------------------------------------------------------


def test_restablecer_contrasena(client, administrador, crear_usuario):
    lina = crear_usuario("logistica", username="lina")

    respuesta = client.post(
        url(lina, "contrasena/"),
        {"clave-contrasena": CONTRASENA, "clave-contrasena_confirmacion": CONTRASENA},
    )

    assert respuesta.status_code == 302
    assert Client().login(username="lina", password=CONTRASENA)
    assert not Client().login(username="lina", password=CLAVE)


def test_restablecer_contrasena_debil_muestra_el_error(client, administrador, crear_usuario):
    lina = crear_usuario("logistica", username="lina")

    respuesta = client.post(
        url(lina, "contrasena/"),
        {"clave-contrasena": "123", "clave-contrasena_confirmacion": "123"},
    )

    assert respuesta.status_code == 200
    assert "demasiado corta" in respuesta.content.decode()
    assert Client().login(username="lina", password=CLAVE)


def test_cambiar_la_propia_contrasena_no_cierra_la_sesion(client, administrador):
    client.post(
        url(administrador, "contrasena/"),
        {"clave-contrasena": CONTRASENA, "clave-contrasena_confirmacion": CONTRASENA},
    )

    assert client.get("/flota/").status_code == 200


def test_un_administrador_no_restablece_la_contrasena_del_superusuario(
    client, administrador, crear_usuario
):
    dueno = crear_usuario(superusuario=True, username="john")

    respuesta = client.post(
        url(dueno, "contrasena/"),
        {"clave-contrasena": CONTRASENA, "clave-contrasena_confirmacion": CONTRASENA},
        follow=True,
    )

    assert "no se cambia desde esta pantalla" in respuesta.content.decode()
    assert Client().login(username="john", password=CLAVE)


def test_el_superusuario_si_cambia_su_propia_contrasena(client, crear_usuario):
    dueno = crear_usuario(superusuario=True, username="john")
    client.force_login(dueno)

    respuesta = client.post(
        url(dueno, "contrasena/"),
        {"clave-contrasena": CONTRASENA, "clave-contrasena_confirmacion": CONTRASENA},
    )

    assert respuesta.status_code == 302
    assert Client().login(username="john", password=CONTRASENA)


# --- Desactivar ------------------------------------------------------------------------------------


def test_desactivar_y_reactivar_un_usuario(client, administrador, crear_usuario):
    lina = crear_usuario("logistica", username="lina")

    client.post(url(lina, "desactivar/"))
    lina.refresh_from_db()
    assert not lina.is_active
    assert not Client().login(username="lina", password=CLAVE)

    client.post(url(lina, "reactivar/"))
    lina.refresh_from_db()
    assert lina.is_active
    assert Client().login(username="lina", password=CLAVE)


def test_nadie_se_desactiva_a_si_mismo(client, administrador, crear_usuario):
    crear_usuario("administrador")

    respuesta = client.post(url(administrador, "desactivar/"), follow=True)

    administrador.refresh_from_db()
    assert administrador.is_active
    assert "No puede desactivar su propio usuario" in respuesta.content.decode()


def test_no_se_desactiva_al_ultimo_administrador(crear_usuario):
    unico = crear_usuario("administrador")
    de_logistica = crear_usuario("logistica")

    with pytest.raises(UltimoAdministrador):
        op.desactivar_usuario(unico, por=de_logistica)

    unico.refresh_from_db()
    assert unico.is_active


def test_otro_administrador_si_puede_desactivarse_si_queda_uno(
    client, administrador, crear_usuario
):
    otro = crear_usuario("administrador")

    client.post(url(otro, "desactivar/"))

    otro.refresh_from_db()
    assert not otro.is_active
