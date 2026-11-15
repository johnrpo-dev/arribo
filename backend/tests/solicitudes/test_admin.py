"""El admin de solicitudes abre, no deja borrar ni editar estados o eventos, y avisa en español."""
import pytest

from solicitudes import operaciones
from solicitudes.models import EventoEstado, Servicio, Vehiculo

pytestmark = pytest.mark.django_db

EDITABLES = ["vehiculo", "solicitud", "servicio"]
SOLO_LECTURA = ["eventoestado", "evidencia"]


@pytest.mark.parametrize("modelo", EDITABLES)
def test_el_admin_abre_la_lista_pero_no_deja_agregar(admin_client, modelo):
    assert admin_client.get(f"/admin/solicitudes/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/solicitudes/{modelo}/add/").status_code == 403


@pytest.mark.parametrize("modelo", SOLO_LECTURA)
def test_eventos_y_evidencias_se_ven_pero_no_se_agregan(admin_client, modelo):
    assert admin_client.get(f"/admin/solicitudes/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/solicitudes/{modelo}/add/").status_code == 403


@pytest.mark.parametrize("modelo", ["solicitud", "vehiculo"])
def test_la_marca_de_demostracion_no_se_edita_en_el_admin(admin_client, modelo):
    contenido = admin_client.get(f"/admin/solicitudes/{modelo}/add/").content.decode()
    assert 'name="es_demo"' not in contenido


def test_el_admin_no_deja_borrar_nada(admin_client, crear_servicio, ana, usuario):
    servicio = crear_servicio()
    evento = operaciones.asignar(servicio, ana, actor=usuario)
    rutas = {
        "vehiculo": servicio.vehiculo_id,
        "solicitud": servicio.solicitud_id,
        "servicio": servicio.pk,
        "eventoestado": evento.pk,
    }
    for modelo, pk in rutas.items():
        assert admin_client.get(f"/admin/solicitudes/{modelo}/{pk}/delete/").status_code == 403
    assert Servicio.objects.filter(pk=servicio.pk).exists()
    assert EventoEstado.objects.filter(pk=evento.pk).exists()


def test_un_evento_se_ve_en_el_admin_pero_no_se_modifica(admin_client, crear_servicio, ana,
                                                          usuario):
    servicio = crear_servicio()
    evento = operaciones.asignar(servicio, ana, actor=usuario, motivo="Primero en la ruta")
    url = f"/admin/solicitudes/eventoestado/{evento.pk}/change/"

    respuesta = admin_client.get(url)
    assert respuesta.status_code == 200
    assert 'name="motivo"' not in respuesta.content.decode()
    assert admin_client.post(url, {"motivo": "Otro"}).status_code == 403
    assert EventoEstado.objects.get(pk=evento.pk).motivo == "Primero en la ruta"


@pytest.mark.parametrize("busqueda", ["abc-123", "ABC 123", "abc123"])
def test_buscar_un_vehiculo_por_placa_escrita_de_cualquier_forma(admin_client, busqueda):
    Vehiculo.objects.create(placa="ABC123", marca="Mazda")
    Vehiculo.objects.create(placa="XYZ987", marca="Renault")
    contenido = admin_client.get("/admin/solicitudes/vehiculo/", {"q": busqueda}).content.decode()
    assert "Mazda" in contenido
    assert "Renault" not in contenido


def _formulario_solicitud(cliente, **extra):
    datos = {
        "solicitante": cliente.pk,
        "pagador": "",
        "tipo": "evento",
        "origen": "Concesionario El Poblado",
        "origen_ubicacion": "",
        "contacto_origen": "",
        "destino": "Plaza Mayor",
        "destino_ubicacion": "https://maps.google.com/?q=6.2442,-75.5812",
        "contacto_destino": "",
        "programada_para_0": "",
        "programada_para_1": "",
        "tiene_regreso": "unknown",
        "fecha_regreso_0": "",
        "fecha_regreso_1": "",
        "estado_registro": "abierta",
        "motivo_no_concretada": "",
        "detalle_no_concretada": "",
        "servicios-TOTAL_FORMS": "0",
        "servicios-INITIAL_FORMS": "0",
    }
    datos.update(extra)
    return datos

