"""Conductores en "Personal y grúas", contra PostgreSQL: crearlos con su acceso a la app en una sola
transacción, habilitar a uno existente, cambiar PIN y grúa, desactivar y reactivar."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from api.models import TokenDispositivo
from flota import operaciones as op
from flota.models import AsignacionConductorGrua, Conductor, Grua, grua_vigente
from nucleo.estados import Estado

from ..api.conftest import PIN, URL_ASIGNACIONES, ingresar

pytestmark = pytest.mark.django_db

Usuario = get_user_model()
URL_NUEVO = "/personal/conductores/nuevo/"
NUEVO_PIN = "246810"


def url(conductor, accion=""):
    return f"/personal/conductores/{conductor.pk}/{accion}"


def datos_nuevo(**otros):
    datos = {
        "nombre": "Carlos",
        "celular": "+57 310 555 1234",
        "pin": NUEVO_PIN,
        "pin_confirmacion": NUEVO_PIN,
        "grua": "",
    }
    datos.update(otros)
    return datos


@pytest.fixture
def grua3():
    return Grua.objects.create(placa="GRU003", capacidad=2)


# --- Crear -----------------------------------------------------------------------------------------


def test_crear_conductor_crea_usuario_en_el_grupo_conductor_ficha_y_asignacion(
    client, administrador, grua3
):
    respuesta = client.post(URL_NUEVO, datos_nuevo(grua=grua3.pk))

    conductor = Conductor.objects.get(nombre="Carlos")
    assert respuesta.status_code == 302
    assert respuesta.url == url(conductor)
    assert conductor.celular == "3105551234"
    assert conductor.activo and conductor.verificar_pin(NUEVO_PIN)
    usuario = conductor.usuario
    assert usuario.username == "conductor-3105551234"
    assert usuario.first_name == "Carlos"
    assert usuario.is_active
    assert list(usuario.groups.values_list("name", flat=True)) == ["conductor"]
    assert not usuario.has_usable_password()
    assert not usuario.is_staff and not usuario.is_superuser
    assert grua_vigente(conductor) == grua3
    assert AsignacionConductorGrua.objects.get(conductor=conductor).fin is None


def test_crear_conductor_sin_grua_no_abre_asignacion(client, administrador):
    client.post(URL_NUEVO, datos_nuevo())

    conductor = Conductor.objects.get(nombre="Carlos")
    assert not conductor.asignaciones.exists()
    assert conductor.usuario is not None


def test_el_conductor_creado_puede_ingresar_a_la_app_con_su_celular_y_pin(
    client, administrador, api
):
    client.post(URL_NUEVO, datos_nuevo())

    respuesta = ingresar(api, celular="310 555 1234", pin=NUEVO_PIN, dispositivo_id="cel-carlos")

    assert respuesta.status_code == 200, respuesta.content
    assert respuesta.json()["conductor"]["nombre"] == "Carlos"


def test_el_usuario_del_conductor_no_entra_al_panel(client, administrador):
    client.post(URL_NUEVO, datos_nuevo())
    usuario = Conductor.objects.get(nombre="Carlos").usuario

    otro = client.__class__()
    assert not otro.login(username=usuario.username, password="")
    assert not otro.login(username=usuario.username, password=NUEVO_PIN)


def test_si_la_grua_ya_la_tiene_otro_conductor_no_se_crea_nada(client, administrador, ana):
    usuarios_antes = Usuario.objects.count()

    respuesta = client.post(URL_NUEVO, datos_nuevo(grua=grua_vigente(ana).pk))

    assert respuesta.status_code == 200
    assert "La grúa GRU001 ya la tiene Ana." in respuesta.content.decode()
    assert not Conductor.objects.filter(nombre="Carlos").exists()
    assert Usuario.objects.count() == usuarios_antes
    assert AsignacionConductorGrua.objects.count() == 1


def test_si_algo_falla_al_final_no_queda_ni_usuario_ni_ficha(monkeypatch, grua3):
    def falla(*args, **kwargs):
        raise RuntimeError("falla simulada al guardar la asignación")

    monkeypatch.setattr(AsignacionConductorGrua, "save", falla)

    with pytest.raises(RuntimeError):
        op.crear_conductor(nombre="Carlos", celular="3105551234", pin=NUEVO_PIN, grua=grua3)

    assert not Conductor.objects.exists()
    assert not Usuario.objects.filter(username__startswith="conductor-").exists()


@pytest.mark.parametrize("celular", ["3000000001", "+57 300 000 0001", "300-000-0001"])
def test_celular_duplicado_da_error_visible(client, administrador, ana, celular):
    respuesta = client.post(URL_NUEVO, datos_nuevo(celular=celular))

    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert "Ya hay un conductor con el celular 3000000001: Ana." in contenido
    assert "No se guardó" in contenido
    assert Conductor.objects.count() == 1


def test_celular_mal_escrito_da_error_visible(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(celular="12"))

    assert "El teléfono debe tener entre 7 y 15 dígitos" in respuesta.content.decode()
    assert not Conductor.objects.exists()


@pytest.mark.parametrize("pin", ["1234", "12345a", "1234567", " 123456"])
def test_pin_invalido_da_error_visible(client, administrador, pin):
    respuesta = client.post(URL_NUEVO, datos_nuevo(pin=pin, pin_confirmacion=pin))

    assert respuesta.status_code == 200
    assert "El PIN tiene exactamente 6 dígitos, del 0 al 9." in respuesta.content.decode()
    assert not Conductor.objects.exists()


def test_los_dos_pin_deben_coincidir(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(pin_confirmacion="135790"))

    assert "Los dos PIN no coinciden." in respuesta.content.decode()
    assert not Conductor.objects.exists()


def test_el_pin_nunca_vuelve_a_la_pantalla(client, administrador):
    respuesta = client.post(URL_NUEVO, datos_nuevo(celular="12"))

    assert NUEVO_PIN not in respuesta.content.decode()


def test_si_el_usuario_derivado_ya_existe_se_usa_otro(client, administrador, django_user_model):
    django_user_model.objects.create_user("conductor-3105551234")

    client.post(URL_NUEVO, datos_nuevo())

    assert Conductor.objects.get().usuario.username == "conductor-3105551234-2"


# --- Habilitar a uno existente ---------------------------------------------------------------------


def test_habilitar_a_un_conductor_existente_sin_usuario(client, administrador, api):
    juan = Conductor(nombre="juan", celular="3201112233")
    juan.fijar_pin(PIN)
    juan.save()
    assert "Falta habilitar" in client.get(url(juan)).content.decode()

    respuesta = client.post(url(juan, "habilitar/"))

    juan.refresh_from_db()
    assert respuesta.status_code == 302
    assert juan.usuario.groups.filter(name="conductor").exists()
    assert not juan.usuario.has_usable_password()
    assert juan.verificar_pin(PIN)  # el PIN no cambia
    assert ingresar(api, celular="3201112233", dispositivo_id="cel-juan").status_code == 200


def test_habilitar_a_un_inactivo_sin_pin_no_lo_reactiva_y_avisa_que_falta_el_pin(
    client, administrador
):
    flaco = Conductor.objects.create(nombre="Flaco", celular="3204445566", activo=False)

    respuesta = client.post(url(flaco, "habilitar/"), follow=True)

    flaco.refresh_from_db()
    assert not flaco.activo
    assert flaco.usuario is not None and not flaco.usuario.is_active
    assert "Falta ponerle el PIN" in respuesta.content.decode()


def test_habilitar_a_un_conductor_enlazado_a_un_usuario_de_oficina_no_toca_ese_usuario(
    client, administrador, crear_usuario, ana, api
):
    de_logistica = crear_usuario("logistica")
    ana.usuario = de_logistica
    ana.fijar_pin(PIN)
    ana.save()
    pagina = client.get(url(ana)).content.decode()
    assert "enlazado a una cuenta que no es de conductor" in pagina
    assert ingresar(api).json()["error"] == "conductor_no_habilitado"

    client.post(url(ana, "habilitar/"))

    ana.refresh_from_db()
    de_logistica.refresh_from_db()
    assert ana.usuario != de_logistica
    assert ana.usuario.groups.filter(name="conductor").exists()
    assert list(de_logistica.groups.values_list("name", flat=True)) == ["logistica"]
    assert de_logistica.is_active and de_logistica.has_usable_password()
    assert ingresar(api).status_code == 200


def test_no_se_habilita_dos_veces(client, administrador, ana_app):
    usuario = ana_app.usuario

    respuesta = client.post(url(ana_app, "habilitar/"), follow=True)

    ana_app.refresh_from_db()
    assert ana_app.usuario == usuario
    assert "ya está habilitado para la app" in respuesta.content.decode()


# --- PIN -------------------------------------------------------------------------------------------


def test_cambiar_pin(client, administrador, ana_app, api):
    respuesta = client.post(
        url(ana_app, "pin/"), {"pin-pin": NUEVO_PIN, "pin-pin_confirmacion": NUEVO_PIN}
    )

    ana_app.refresh_from_db()
    assert respuesta.status_code == 302
    assert ana_app.verificar_pin(NUEVO_PIN)
    assert ingresar(api, pin=NUEVO_PIN).status_code == 200


def test_cambiar_pin_invalido_muestra_el_error_y_no_cambia(client, administrador, ana_app):
    respuesta = client.post(url(ana_app, "pin/"), {"pin-pin": "12", "pin-pin_confirmacion": "12"})

    ana_app.refresh_from_db()
    assert respuesta.status_code == 200
    assert "El PIN tiene exactamente 6 dígitos" in respuesta.content.decode()
    assert ana_app.verificar_pin(PIN)


# --- Grúa ------------------------------------------------------------------------------------------


def test_cambiar_de_grua_cierra_la_vigente_y_abre_otra_sin_traslape(
    client, administrador, ana, grua3
):
    anterior = AsignacionConductorGrua.objects.get(conductor=ana)

    respuesta = client.post(url(ana, "grua/"), {"grua-grua": grua3.pk})

    assert respuesta.status_code == 302
    anterior.refresh_from_db()
    nueva = AsignacionConductorGrua.objects.get(conductor=ana, fin__isnull=True)
    assert nueva.grua == grua3
    assert anterior.fin == nueva.inicio  # [inicio, fin): se tocan sin cruzarse
    assert grua_vigente(ana) == grua3
    assert grua_vigente(ana, en=anterior.fin - timedelta(seconds=1)).placa == "GRU001"


def test_la_grua_anterior_queda_libre_para_otro_conductor(client, administrador, ana, beto, grua3):
    client.post(url(ana, "grua/"), {"grua-grua": grua3.pk})

    respuesta = client.post(url(beto, "grua/"), {"grua-grua": Grua.objects.get(placa="GRU001").pk})

    assert respuesta.status_code == 302
    assert grua_vigente(beto).placa == "GRU001"


def test_cambiar_a_una_grua_ocupada_explica_quien_la_tiene_y_no_cambia_nada(
    client, administrador, ana, beto
):
    respuesta = client.post(url(ana, "grua/"), {"grua-grua": grua_vigente(beto).pk})

    assert respuesta.status_code == 200
    assert "La grúa GRU002 ya la tiene Beto." in respuesta.content.decode()
    assert grua_vigente(ana).placa == "GRU001"
    assert AsignacionConductorGrua.objects.filter(fin__isnull=False).count() == 0


def test_dejar_sin_grua_cierra_la_asignacion(client, administrador, ana):
    client.post(url(ana, "grua/"), {"grua-grua": ""})

    assert grua_vigente(ana) is None
    assert AsignacionConductorGrua.objects.get(conductor=ana).fin is not None


def test_elegir_la_misma_grua_no_cambia_nada(client, administrador, ana):
    respuesta = client.post(url(ana, "grua/"), {"grua-grua": grua_vigente(ana).pk})

    assert "Ana ya tiene la grúa GRU001." in respuesta.content.decode()
    assert AsignacionConductorGrua.objects.get(conductor=ana).fin is None


def test_una_grua_inactiva_no_se_ofrece(client, administrador, ana, grua3):
    grua3.activa = False
    grua3.save()

    respuesta = client.post(url(ana, "grua/"), {"grua-grua": grua3.pk})

    assert respuesta.status_code == 200
    assert grua_vigente(ana).placa == "GRU001"


def test_el_servicio_hecho_conserva_la_grua_al_cambiarla(
    client, administrador, ana, grua3, crear_servicio
):
    servicio = crear_servicio(Estado.ENTREGADO)

    client.post(url(ana, "grua/"), {"grua-grua": grua3.pk})

    servicio.refresh_from_db()
    assert servicio.grua.placa == "GRU001"


# --- Desactivar y reactivar ------------------------------------------------------------------------


def test_desactivar_pide_confirmacion_con_los_servicios_activos(
    client, administrador, ana_app, crear_servicio
):
    crear_servicio(Estado.ASIGNADO)
    crear_servicio(Estado.RECOGIDO)
    crear_servicio(Estado.ENTREGADO)

    respuesta = client.get(url(ana_app, "desactivar/"))

    contenido = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Ana tiene 2 servicios activos" in contenido
    ana_app.refresh_from_db()
    assert ana_app.activo  # un GET no desactiva


def test_desactivar_revoca_las_sesiones_y_la_api_responde_no_habilitado(
    client, administrador, sesion, api
):
    token = sesion.token
    token.push_token = "token-push-de-ana"
    token.save()

    respuesta = client.post(url(token.conductor, "desactivar/"))

    assert respuesta.status_code == 302
    conductor = Conductor.objects.get(pk=token.conductor.pk)
    assert not conductor.activo
    assert not conductor.usuario.is_active
    token.refresh_from_db()
    assert token.revocado_en is not None
    assert token.push_token == ""
    assert sesion.get(URL_ASIGNACIONES).json()["error"] == "sesion_invalida"
    reingreso = ingresar(api)
    assert reingreso.status_code == 401
    assert reingreso.json()["error"] == "conductor_no_habilitado"
    assert not TokenDispositivo.objects.filter(revocado_en__isnull=True).exists()


def test_desactivar_no_toca_sus_servicios_en_curso(client, administrador, ana_app, crear_servicio):
    servicio = crear_servicio(Estado.EN_CAMINO)

    client.post(url(ana_app, "desactivar/"))

    servicio.refresh_from_db()
    assert servicio.estado == Estado.EN_CAMINO
    assert servicio.conductor == ana_app


def test_reactivar_le_devuelve_el_acceso(client, administrador, ana_app, api):
    client.post(url(ana_app, "desactivar/"))

    client.post(url(ana_app, "reactivar/"))

    ana_app.refresh_from_db()
    assert ana_app.activo and ana_app.usuario.is_active
    assert ingresar(api).status_code == 200


def test_desactivar_un_conductor_enlazado_a_un_usuario_de_oficina_no_desactiva_ese_usuario(
    client, administrador, crear_usuario, ana
):
    de_logistica = crear_usuario("logistica")
    ana.usuario = de_logistica
    ana.save()

    client.post(url(ana, "desactivar/"))

    de_logistica.refresh_from_db()
    assert de_logistica.is_active


# --- Lista -----------------------------------------------------------------------------------------


def test_la_lista_muestra_grua_pin_activo_y_acceso_a_la_app(client, administrador, ana_app, beto):
    Conductor.objects.create(nombre="Flaco", celular="3204445566", activo=False)

    contenido = client.get("/personal/").content.decode()

    assert "Nuevo conductor" in contenido
    for texto in ("Ana", "3000000001", "GRU001", "Beto", "GRU002", "Flaco"):
        assert texto in contenido
    assert "Puede entrar" in contenido  # Ana
    assert "Falta habilitar" in contenido  # Beto, sin usuario
    assert "Inactivo" in contenido  # Flaco


def test_la_lista_no_hace_una_consulta_por_conductor(
    client, administrador, dar_acceso, django_assert_max_num_queries
):
    for numero in range(8):
        dar_acceso(Conductor.objects.create(nombre=f"C{numero}", celular=f"30100000{numero:02d}"))
    Group.objects.get_or_create(name="conductor")

    with django_assert_max_num_queries(12):
        client.get("/personal/")

