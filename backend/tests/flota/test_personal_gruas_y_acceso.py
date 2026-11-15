"""Grúas en "Personal y grúas" y el acceso a la pantalla: solo administrador, sin borrar nada."""
import pytest

from flota.models import Conductor, Grua

pytestmark = pytest.mark.django_db

URL_NUEVA = "/flota/gruas/nueva/"


def datos_grua(**otros):
    datos = {"placa": "abc-123", "descripcion": "Hino blanca", "capacidad": "2",
             "estado_operativo": "operativa"}
    datos.update(otros)
    return datos


# --- Grúas -----------------------------------------------------------------------------------------


def test_crear_grua_normaliza_la_placa(client, administrador):
    respuesta = client.post(URL_NUEVA, datos_grua())

    assert respuesta.status_code == 302
    grua = Grua.objects.get()
    assert (grua.placa, grua.capacidad, grua.activa) == ("ABC123", 2, True)


def test_placa_repetida_da_error_visible(client, administrador, grua1):
    respuesta = client.post(URL_NUEVA, datos_grua(placa="gru 001"))

    assert respuesta.status_code == 200
    assert "Ya hay una grúa con esa placa." in respuesta.content.decode()
    assert Grua.objects.count() == 1


def test_la_capacidad_es_1_o_2(client, administrador):
    respuesta = client.post(URL_NUEVA, datos_grua(capacidad="3"))

    assert respuesta.status_code == 200
    assert not Grua.objects.exists()


def test_editar_grua_y_cambiar_su_estado(client, administrador, grua1):
    respuesta = client.post(
        f"/flota/gruas/{grua1.pk}/",
        datos_grua(placa="GRU001", capacidad="1", estado_operativo="fuera_de_servicio",
                   activa=""),
    )

    assert respuesta.status_code == 302
    grua1.refresh_from_db()
    assert grua1.estado_operativo == Grua.EstadoOperativo.FUERA_DE_SERVICIO
    assert not grua1.activa
    assert grua1.descripcion == "Hino blanca"


# --- Acceso ----------------------------------------------------------------------------------------


@pytest.fixture
def rutas(ana, crear_usuario):
    lina = crear_usuario("logistica", username="lina")
    grua = Grua.objects.get(placa="GRU001")
    return [
        "/flota/",
        "/flota/conductores/nuevo/",
        f"/flota/conductores/{ana.pk}/",
        f"/flota/conductores/{ana.pk}/desactivar/",
        "/flota/usuarios/nuevo/",
        f"/flota/usuarios/{lina.pk}/",
        "/flota/gruas/nueva/",
        f"/flota/gruas/{grua.pk}/",
    ]


ACCIONES_POST = [
    "conductores/{c}/habilitar/",
    "conductores/{c}/pin/",
    "conductores/{c}/grua/",
    "conductores/{c}/desactivar/",
    "conductores/{c}/reactivar/",
    "usuarios/{u}/rol/",
    "usuarios/{u}/contrasena/",
    "usuarios/{u}/desactivar/",
    "usuarios/{u}/reactivar/",
]


@pytest.mark.parametrize("rol", ["logistica", "facturacion"])
def test_logistica_y_facturacion_reciben_403(client, crear_usuario, rutas, ana, rol):
    otro = crear_usuario(rol)
    client.force_login(otro)

    for ruta in rutas:
        assert client.get(ruta).status_code == 403, ruta
    for accion in ACCIONES_POST:
        ruta = "/flota/" + accion.format(c=ana.pk, u=otro.pk)
        assert client.post(ruta).status_code == 403, ruta
    ana.refresh_from_db()
    assert ana.activo


def test_sin_sesion_lleva_al_ingreso(client, rutas):
    for ruta in rutas:
        respuesta = client.get(ruta)
        assert respuesta.status_code == 302
        assert respuesta.url.startswith("/ingresar/")


def test_el_administrador_abre_todas_las_pantallas(client, administrador, rutas):
    for ruta in rutas:
        assert client.get(ruta).status_code == 200, ruta


def test_el_superusuario_sin_roles_entra(client, crear_usuario, rutas):
    client.force_login(crear_usuario(superusuario=True))

    for ruta in rutas:
        assert client.get(ruta).status_code == 200, ruta


def test_las_acciones_solo_aceptan_post(client, administrador, ana):
    for accion in ACCIONES_POST:
        if "desactivar" in accion and "conductores" in accion:
            continue  # su GET es la confirmación
        ruta = "/flota/" + accion.format(c=ana.pk, u=administrador.pk)
        assert client.get(ruta).status_code == 405, ruta
    ana.refresh_from_db()
    assert ana.activo


def test_ninguna_pantalla_tiene_boton_de_borrar(client, administrador, rutas, ana_app):
    Conductor.objects.create(nombre="Flaco", celular="3204445566", activo=False)
    for ruta in [*rutas, f"/flota/usuarios/{administrador.pk}/"]:
        contenido = client.get(ruta).content.decode().lower()
        for palabra in ("borrar", "eliminar", "delete"):
            assert palabra not in contenido, (ruta, palabra)


def test_la_pantalla_no_habla_de_grupos_ni_permisos(client, administrador, rutas, crear_usuario):
    dueno = crear_usuario(superusuario=True, username="john")
    for ruta in [*rutas, f"/flota/usuarios/{dueno.pk}/"]:
        contenido = client.get(ruta).content.decode().lower()
        for palabra in ("grupo", "permiso", "staff", "superusuario"):
            assert palabra not in contenido, (ruta, palabra)
