"""PUT /api/v1/push/ (1a-14): la app registra el token de push de su celular. Queda ligado a la
sesión de ese celular (`TokenDispositivo`), se borra al cerrar sesión y nunca lo comparten dos
sesiones. Contra PostgreSQL."""
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.ingreso import revocar_tokens
from api.models import TokenDispositivo

from .conftest import URL_SALIDA, cliente_con, ingresar

pytestmark = pytest.mark.django_db

URL_PUSH = "/api/v1/push/"
TOKEN_FCM = "fcm-ana:APA91b-token_de_prueba-1"


def registrar(cliente, token=TOKEN_FCM):
    return cliente.put(URL_PUSH, {"token": token}, format="json")


def _error(respuesta):
    return respuesta.status_code, respuesta.json()["error"]


@pytest.fixture
def sesion_beto(beto_app):
    token, clave = TokenDispositivo.emitir(beto_app, "celular-de-beto")
    cliente = cliente_con(clave)
    cliente.token = token
    return cliente


# --- Autenticación ---------------------------------------------------------------------------------


def test_registrar_el_token_de_push_exige_el_token_del_celular(api):
    assert _error(registrar(api)) == (401, "no_autenticado")


def test_la_sesion_del_panel_no_registra_tokens_de_push(client, django_user_model, ana_app):
    client.force_login(django_user_model.objects.create_superuser("jefe"))

    respuesta = client.put(URL_PUSH, {"token": TOKEN_FCM}, content_type="application/json")

    assert respuesta.status_code == 401
    assert not TokenDispositivo.objects.exclude(push_token="").exists()


def test_un_token_de_celular_revocado_no_registra_push(sesion):
    revocar_tokens(TokenDispositivo.objects.all())

    assert _error(registrar(sesion)) == (401, "sesion_invalida")
    sesion.token.refresh_from_db()
    assert sesion.token.push_token == ""


# --- Queda ligado a la sesión de su celular --------------------------------------------------------


def test_el_token_de_push_queda_en_la_sesion_de_ese_celular(sesion, sesion_beto, reloj):
    respuesta = registrar(sesion)

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    sesion.token.refresh_from_db()
    assert sesion.token.push_token == TOKEN_FCM
    assert sesion.token.push_registrado_en == reloj.ahora
    sesion_beto.token.refresh_from_db()
    assert sesion_beto.token.push_token == ""


def test_registrar_otra_vez_reemplaza_el_token_y_lo_reactiva(sesion, reloj):
    registrar(sesion, "token-viejo")
    TokenDispositivo.objects.filter(pk=sesion.token.pk).update(
        push_token="", push_desactivado_en=timezone.now()
    )  # FCM dijo que el viejo ya no existía
    reloj.avanzar(minutes=5)

    assert registrar(sesion, "token-nuevo").status_code == 204

    sesion.token.refresh_from_db()
    assert sesion.token.push_token == "token-nuevo"
    assert sesion.token.push_registrado_en == reloj.ahora
    assert sesion.token.push_desactivado_en is None


def test_registrar_el_mismo_token_dos_veces_no_falla(sesion):
    assert registrar(sesion).status_code == 204
    assert registrar(sesion).status_code == 204
    assert TokenDispositivo.objects.filter(push_token=TOKEN_FCM).count() == 1


def test_el_mismo_token_de_push_pasa_a_la_ultima_sesion_que_lo_registra(sesion, sesion_beto):
    """El mismo celular, prestado: Ana no cerró sesión con señal y Beto entra con su cuenta en
    otra sesión. Los avisos le llegan solo a quien lo tiene ahora."""
    registrar(sesion)

    assert registrar(sesion_beto).status_code == 204

    sesion.token.refresh_from_db()
    sesion_beto.token.refresh_from_db()
    assert (sesion.token.push_token, sesion_beto.token.push_token) == ("", TOKEN_FCM)
    assert sesion.token.vigente  # su sesión sigue; solo deja de recibir push


# --- Entrada inválida ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [{}, {"token": ""}, {"token": "con espacio"}, {"token": "x" * 1001}, {"token": None}],
)
def test_un_token_de_push_vacio_mal_escrito_o_muy_largo_responde_400(sesion, cuerpo):
    respuesta = sesion.put(URL_PUSH, cuerpo, format="json")

    assert respuesta.status_code == 400
    datos = respuesta.json()
    assert (datos["version"], datos["error"]) == (1, "datos_invalidos")
    assert set(datos["campos"]) == {"token"}
    sesion.token.refresh_from_db()
    assert sesion.token.push_token == ""


def test_un_cuerpo_que_no_es_json_responde_400_o_415(sesion):
    assert _error(sesion.put(URL_PUSH, data="{token", content_type="application/json")) == (
        400,
        "json_invalido",
    )
    assert sesion.put(URL_PUSH, data="token=x", content_type="text/plain").status_code == 415


def test_el_registro_de_push_solo_acepta_put(sesion):
    assert _error(sesion.get(URL_PUSH)) == (405, "metodo_no_permitido")
    assert _error(sesion.post(URL_PUSH, {"token": TOKEN_FCM}, format="json")) == (
        405,
        "metodo_no_permitido",
    )


# --- Al cerrar la sesión, el token de push se borra ------------------------------------------------


def test_cerrar_sesion_borra_el_token_de_push(sesion):
    registrar(sesion)

    assert sesion.post(URL_SALIDA).status_code == 204

    sesion.token.refresh_from_db()
    assert sesion.token.push_token == ""


def test_volver_a_ingresar_en_el_celular_borra_el_push_de_la_sesion_anterior(api, sesion, ana_app):
    registrar(sesion)

    assert ingresar(api, dispositivo_id="celular-de-ana").status_code == 200

    sesion.token.refresh_from_db()
    assert (sesion.token.vigente, sesion.token.push_token) == (False, "")


def test_el_admin_muestra_si_hay_push_pero_no_el_token(admin_client, sesion):
    registrar(sesion)

    pagina = admin_client.get(f"/admin/api/tokendispositivo/{sesion.token.pk}/change/")

    assert pagina.status_code == 200
    assert TOKEN_FCM not in pagina.content.decode()


# --- Restricciones de la base ----------------------------------------------------------------------


def test_la_base_no_deja_el_mismo_token_de_push_en_dos_sesiones(ana_app, beto_app):
    uno, _ = TokenDispositivo.emitir(ana_app, "celular-1")
    otro, _ = TokenDispositivo.emitir(beto_app, "celular-2")
    TokenDispositivo.objects.filter(pk=uno.pk).update(push_token=TOKEN_FCM)

    with pytest.raises(IntegrityError), transaction.atomic():
        TokenDispositivo.objects.filter(pk=otro.pk).update(push_token=TOKEN_FCM)

    # Las sesiones sin push (token vacío) no chocan entre sí.
    TokenDispositivo.objects.update(push_token="")


def test_la_base_no_deja_una_sesion_revocada_con_token_de_push(ana_app):
    token, _ = TokenDispositivo.emitir(ana_app, "celular-1")

    with pytest.raises(IntegrityError), transaction.atomic():
        TokenDispositivo.objects.filter(pk=token.pk).update(
            revocado_en=timezone.now(), push_token=TOKEN_FCM
        )
