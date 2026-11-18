"""403 en español para quien tiene sesión pero no el rol; el conductor no entra al panel."""
import pytest

pytestmark = pytest.mark.django_db


def test_el_conductor_no_entra_al_panel(client, crear_usuario):
    client.force_login(crear_usuario("conductor"))
    respuesta = client.get("/")
    assert respuesta.status_code == 403
    html = respuesta.content.decode()
    assert "Sin acceso a esta página" in html
    assert "use la app del celular" in html


def test_el_conductor_no_entra_aunque_tenga_otro_rol(client, crear_usuario):
    client.force_login(crear_usuario("conductor", "logistica"))
    assert client.get("/").status_code == 403
    assert client.get("/tablero/").status_code == 403


def test_usuario_sin_rol_recibe_403(client, crear_usuario):
    client.force_login(crear_usuario())
    assert client.get("/").status_code == 403


@pytest.mark.parametrize(
    "rol, ruta",
    [
        ("facturacion", "/tablero/"),
        ("facturacion", "/solicitudes/nueva/"),
        ("facturacion", "/solicitudes/"),
        ("logistica", "/cobros/"),
        ("logistica", "/flota/"),
        ("logistica", "/dueno/"),
        ("logistica", "/configuracion/"),
        ("facturacion", "/configuracion/"),
        ("logistica", "/estilos/"),
        ("facturacion", "/estilos/"),
    ],
)
def test_rol_sin_permiso_sobre_la_seccion_recibe_403(client, crear_usuario, rol, ruta):
    client.force_login(crear_usuario(rol))
    respuesta = client.get(ruta)
    assert respuesta.status_code == 403
    assert "Sin acceso a esta página" in respuesta.content.decode()


def test_el_403_ofrece_salir_y_volver_al_inicio(client, crear_usuario):
    client.force_login(crear_usuario("facturacion"))
    html = client.get("/tablero/").content.decode()
    assert 'action="/salir/"' in html
    assert "Volver al inicio" in html


def test_seccion_sin_pantalla_dice_aun_no_disponible_en_su_url_directa(client, crear_usuario):
    client.force_login(crear_usuario("administrador"))
    respuesta = client.get("/dueno/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "<h1 class=\"titulo-pagina\">Panel del dueño</h1>" in html
    assert "Aún no disponible" in html
    assert 'href="/dueno/"' not in html  # no está en el menú mientras no tenga pantalla


def test_inicio_saluda_por_nombre(client, crear_usuario):
    client.force_login(crear_usuario("logistica", first_name="Marta", last_name="Gómez"))
    html = client.get("/").content.decode()
    assert "Hola, Marta" in html
    assert "Marta Gómez" in html  # nombre completo en la barra lateral
    assert "Logística" in html  # rol en la barra lateral


def test_inicio_sin_nombre_saluda_con_el_usuario(client, crear_usuario):
    client.force_login(crear_usuario("facturacion", username="caja"))
    assert "Hola, caja" in client.get("/").content.decode()


def test_el_inicio_de_facturacion_lleva_a_cobros(client, crear_usuario):
    client.force_login(crear_usuario("facturacion"))
    html = client.get("/").content.decode()
    assert 'href="/cobros/"' in html
    assert 'href="/dueno/"' not in html  # sección aún no disponible
    assert "Aún no disponible" not in html


def test_un_usuario_sin_rol_no_entra_al_inicio(client, crear_usuario):
    usuario = crear_usuario(superusuario=False)
    client.force_login(usuario)
    assert client.get("/").status_code == 403


def test_estilos_abre_para_el_administrador(client, crear_usuario):
    client.force_login(crear_usuario("administrador"))
    respuesta = client.get("/estilos/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    for clase in ("boton--principal", "boton--secundario", "boton--peligro", "campo-error",
                  "aviso--exito", "aviso--error", "estado--novedad", "vacio", "tabla"):
        assert clase in html
    assert html.count('<span class="estado estado--') >= 10  # siete de muestra y tres en la tabla
