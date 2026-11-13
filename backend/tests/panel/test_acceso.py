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


def test_seccion_sin_pantalla_dice_aun_no_disponible(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    respuesta = client.get("/tablero/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "<h1 class=\"titulo-pagina\">Tablero</h1>" in html
    assert "Aún no disponible" in html
    assert 'aria-current="page"' in html


def test_inicio_saluda_por_nombre(client, crear_usuario):
    client.force_login(crear_usuario("logistica", first_name="Marta", last_name="Gómez"))
    html = client.get("/").content.decode()
    assert "Hola, Marta" in html
    assert "Marta Gómez" in html  # nombre completo en la barra lateral
    assert "Logística" in html  # rol en la barra lateral


def test_inicio_sin_nombre_saluda_con_el_usuario(client, crear_usuario):
    client.force_login(crear_usuario("facturacion", username="caja"))
    assert "Hola, caja" in client.get("/").content.decode()


def test_inicio_marca_las_secciones_aun_no_disponibles(client, crear_usuario):
    client.force_login(crear_usuario("facturacion"))
    html = client.get("/").content.decode()
    assert "Cobros" in html
    assert "Aún no disponible" in html


def test_estilos_abre_para_el_administrador(client, crear_usuario):
    client.force_login(crear_usuario("administrador"))
    respuesta = client.get("/estilos/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    for clase in ("boton--principal", "boton--secundario", "boton--peligro", "campo-error",
                  "aviso--exito", "aviso--error", "estado--novedad", "vacio", "tabla"):
        assert clase in html
    assert html.count('<span class="estado estado--') >= 10  # siete de muestra y tres en la tabla
