"""El admin de solicitudes abre, no deja borrar ni editar estados o eventos, y avisa en español."""
import pytest

from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import EventoEstado, Servicio, Solicitud, Vehiculo

from .conftest import VIN

pytestmark = pytest.mark.django_db

EDITABLES = ["vehiculo", "solicitud", "servicio"]
SOLO_LECTURA = ["eventoestado", "evidencia"]


@pytest.mark.parametrize("modelo", EDITABLES)
def test_el_admin_abre_la_lista_y_el_formulario(admin_client, modelo):
    assert admin_client.get(f"/admin/solicitudes/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/solicitudes/{modelo}/add/").status_code == 200


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


def test_el_estado_conductor_y_grua_del_servicio_no_se_editan_en_el_admin(
    admin_client, crear_servicio
):
    servicio = crear_servicio(Estado.EN_CAMINO)
    contenido = admin_client.get(f"/admin/solicitudes/servicio/{servicio.pk}/change/").content
    contenido = contenido.decode()
    for campo in ("estado", "estado_previo", "conductor", "grua"):
        assert f'name="{campo}"' not in contenido
    assert 'name="referencia_externa"' in contenido
    assert "En camino" in contenido  # se ve, aunque no se edite


def test_editar_la_referencia_de_un_servicio_en_el_admin_no_toca_su_estado(
    admin_client, crear_servicio
):
    servicio = crear_servicio(Estado.EN_CAMINO)
    respuesta = admin_client.post(
        f"/admin/solicitudes/servicio/{servicio.pk}/change/",
        {
            "solicitud": servicio.solicitud_id,
            "vehiculo": servicio.vehiculo_id,
            "orden_ronda": "1",
            "referencia_externa": "CASO-77",
            "regreso_de": "",
            "eventos-TOTAL_FORMS": "0",
            "eventos-INITIAL_FORMS": "0",
        },
    )
    assert respuesta.status_code == 302, respuesta.content.decode()
    servicio.refresh_from_db()
    assert (servicio.referencia_externa, servicio.estado) == ("CASO-77", Estado.EN_CAMINO)
    assert not EventoEstado.objects.exists()


def test_crear_vehiculo_en_el_admin_normaliza_placa_y_vin(admin_client):
    respuesta = admin_client.post(
        "/admin/solicitudes/vehiculo/add/",
        {"placa": "abc-123", "vin": "1hg-cm826-33a004352", "marca": "Honda", "linea": "Accord"},
    )
    assert respuesta.status_code == 302, respuesta.content.decode()
    vehiculo = Vehiculo.objects.get()
    assert (vehiculo.placa, vehiculo.vin) == ("ABC123", VIN)


def test_el_admin_avisa_si_la_placa_ya_existe(admin_client):
    Vehiculo.objects.create(placa="ABC123")
    respuesta = admin_client.post("/admin/solicitudes/vehiculo/add/", {"placa": "abc 123"})
    assert respuesta.status_code == 200
    assert "Ya hay un vehículo con la placa ABC123." in respuesta.content.decode()
    assert Vehiculo.objects.count() == 1


def test_el_admin_avisa_si_el_vin_no_es_valido(admin_client):
    respuesta = admin_client.post("/admin/solicitudes/vehiculo/add/", {"vin": VIN[:-1] + "Q"})
    assert respuesta.status_code == 200
    assert "sin I, O ni Q" in respuesta.content.decode()
    assert not Vehiculo.objects.exists()


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


def test_el_admin_avisa_que_un_evento_debe_responder_si_tiene_regreso(admin_client, cliente):
    datos = _formulario_solicitud(cliente)
    respuesta = admin_client.post("/admin/solicitudes/solicitud/add/", datos)
    assert respuesta.status_code == 200
    assert "En un evento hay que responder si tiene regreso." in respuesta.content.decode()
    assert not Solicitud.objects.exists()


def test_crear_solicitud_en_el_admin_guarda_quien_la_creo_y_paga_el_solicitante(
    admin_client, admin_user, cliente
):
    datos = _formulario_solicitud(
        cliente,
        tiene_regreso="true",
        fecha_regreso_0="2026-11-20",
        fecha_regreso_1="17:00:00",
    )
    respuesta = admin_client.post("/admin/solicitudes/solicitud/add/", datos)
    assert respuesta.status_code == 302, respuesta.content.decode()
    solicitud = Solicitud.objects.get()
    assert (solicitud.creada_por, solicitud.pagador) == (admin_user, cliente)
    assert solicitud.tiene_regreso is True
    assert solicitud.estado == "abierta"
