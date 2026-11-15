"""Restablecer datos de prueba: borra lo operativo, conserva la configuración y a quien restablece,
y solo existe cuando la instalación lo permite. Contra PostgreSQL (usa TRUNCATE)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client

from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import abrir_alerta
from clientes.models import Cliente
from configuracion.models import Configuracion, HistorialConfiguracion, configuracion_vigente
from configuracion.operaciones import guardar_configuracion
from configuracion.restablecer import RestablecerNoPermitido, _borrar_archivos, restablecer
from documentos.models import TipoDocumento
from flota.models import Conductor, Grua
from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import EventoEstado, Servicio, Solicitud
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db

RUTA = "/configuracion/restablecer/"


@pytest.fixture(autouse=True)
def ajustes(settings, tmp_path):
    settings.ARRIBO_PERMITIR_RESTABLECER = True
    settings.MEDIA_ROOT = tmp_path
    return settings


@pytest.fixture
def admin(client, crear_usuario):
    usuario = crear_usuario("administrador")
    client.force_login(usuario)
    return usuario


@pytest.fixture
def datos_de_prueba(crear_servicio, usuario, beto):
    """Dos servicios de una solicitud; uno con eventos (de solo agregar) y una alerta."""
    servicio = crear_servicio(Estado.PENDIENTE_ASIGNAR)
    operaciones.asignar(servicio, beto, actor=usuario)
    operaciones.cambiar_estado(servicio, Estado.EN_CAMINO, actor=usuario)
    abrir_alerta(TipoAlerta.CONFLICTO_SINCRONIZACION, servicio, "prueba")
    crear_servicio(Estado.PENDIENTE_ASIGNAR)
    assert EventoEstado.objects.exists()
    return servicio


def test_borra_lo_operativo_aunque_sea_de_solo_agregar(admin, datos_de_prueba):
    restablecer(conservar=admin)
    for modelo in (Solicitud, Servicio, EventoEstado, Alerta, Cliente, Conductor, Grua):
        assert not modelo.objects.exists(), modelo.__name__


def test_los_numeros_de_solicitud_vuelven_a_empezar(admin, datos_de_prueba, cliente):
    restablecer(conservar=admin)
    nuevo = Cliente.objects.create(nombre="Nuevo", tipo=cliente.tipo)
    assert crear_solicitud(nuevo).pk == 1


def test_conserva_configuracion_tipos_de_documento_y_al_administrador(admin, datos_de_prueba):
    configuracion = configuracion_vigente()
    configuracion.minimo_fotos = 6
    guardar_configuracion(configuracion, usuario=admin)
    tipos = TipoDocumento.objects.count()

    restablecer(conservar=admin)

    assert Configuracion.objects.get().minimo_fotos == 6
    assert HistorialConfiguracion.objects.filter(usuario=admin).exists()
    assert TipoDocumento.objects.count() == tipos
    assert get_user_model().objects.filter(pk=admin.pk, is_active=True).exists()


def test_borra_usuarios_salvo_superusuarios(admin, crear_usuario):
    oficina = crear_usuario("logistica")
    jefe = crear_usuario(superusuario=True)
    restablecer(conservar=admin)
    usuarios = get_user_model().objects
    assert not usuarios.filter(pk=oficina.pk).exists()
    assert usuarios.filter(pk=jefe.pk).exists()


def test_quien_cambio_la_configuracion_se_desactiva_en_vez_de_borrarse(admin, crear_usuario):
    otro = crear_usuario("administrador")
    configuracion = configuracion_vigente()
    configuracion.minimo_fotos = 5
    guardar_configuracion(configuracion, usuario=otro)

    restablecer(conservar=admin)

    otro.refresh_from_db()
    assert not otro.is_active


def test_cierra_las_sesiones_de_los_demas_y_conserva_la_propia(client, admin, crear_usuario):
    Client().force_login(crear_usuario(superusuario=True))
    assert Session.objects.count() == 2

    restablecer(conservar=admin)

    assert Session.objects.count() == 1
    assert client.get("/configuracion/").status_code == 200


def test_borra_las_fotos_y_los_archivos_de_documentos(ajustes):
    raiz = ajustes.MEDIA_ROOT
    for carpeta in ("evidencias/1", "documentos/conductor/1"):
        (raiz / carpeta).mkdir(parents=True)
        (raiz / carpeta / "a.jpg").write_bytes(b"x")
    (raiz / "otra").mkdir()

    _borrar_archivos()  # restablecer lo programa con on_commit

    assert not (raiz / "evidencias").exists()
    assert not (raiz / "documentos").exists()
    assert (raiz / "otra").exists()


def test_programa_el_borrado_de_archivos_al_confirmar(admin, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        restablecer(conservar=admin)
    assert _borrar_archivos in callbacks


def test_no_funciona_si_la_instalacion_no_lo_permite(admin, settings, datos_de_prueba):
    settings.ARRIBO_PERMITIR_RESTABLECER = False
    with pytest.raises(RestablecerNoPermitido):
        restablecer(conservar=admin)
    assert Servicio.objects.exists()


# --- Pantalla ----------------------------------------------------------------------------------


def test_configuracion_muestra_el_boton_solo_si_esta_permitido(client, admin, settings):
    assert RUTA in client.get("/configuracion/").content.decode()
    settings.ARRIBO_PERMITIR_RESTABLECER = False
    assert RUTA not in client.get("/configuracion/").content.decode()
    assert client.get(RUTA).status_code == 404


def test_la_pantalla_muestra_lo_que_se_borrara(client, admin, datos_de_prueba):
    html = client.get(RUTA).content.decode()
    assert "Servicios: 2" in html
    assert "Solicitudes: 1" in html


def test_sin_escribir_borrar_no_borra(client, admin, datos_de_prueba):
    respuesta = client.post(RUTA, {"confirmacion": "si"})
    assert respuesta.status_code == 200
    assert "Escriba BORRAR" in respuesta.content.decode()
    assert Servicio.objects.count() == 2


def test_escribiendo_borrar_restablece_y_vuelve_al_inicio(client, admin, datos_de_prueba):
    respuesta = client.post(RUTA, {"confirmacion": "borrar"})
    assert respuesta.status_code == 302
    assert not Servicio.objects.exists()
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("rol", ["logistica", "facturacion"])
def test_solo_el_administrador_puede_restablecer(client, crear_usuario, datos_de_prueba, rol):
    client.force_login(crear_usuario(rol))
    assert client.post(RUTA, {"confirmacion": "BORRAR"}).status_code == 403
    assert Servicio.objects.count() == 2
