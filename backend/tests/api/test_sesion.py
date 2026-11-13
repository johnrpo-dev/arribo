"""Token por celular: autentica, se revoca (admin o cerrar sesión) y deja de servir con el conductor
inactivo. Toda respuesta 401 lleva la cabecera WWW-Authenticate y el código del contrato."""
import secrets

import pytest
from django.db import IntegrityError, transaction

from api.ingreso import revocar_tokens
from api.models import IntentosIngreso, TokenDispositivo

from .conftest import URL_ASIGNACIONES, URL_SALIDA, cliente_con

pytestmark = pytest.mark.django_db

REINO = 'Bearer realm="arribo"'


def _error(respuesta):
    return respuesta.status_code, respuesta.json()["error"]


def test_sin_token_responde_401_no_autenticado(api):
    respuesta = api.get(URL_ASIGNACIONES)

    assert _error(respuesta) == (401, "no_autenticado")
    assert respuesta["WWW-Authenticate"] == REINO
    assert respuesta.json()["version"] == 1


@pytest.mark.parametrize(
    "cabecera", ["Bearer token-que-no-existe", "Bearer", "Bearer dos partes", "Bearer ñandú"]
)
def test_un_token_desconocido_o_mal_escrito_responde_401(api, ana_app, cabecera):
    api.credentials(HTTP_AUTHORIZATION=cabecera)

    respuesta = api.get(URL_ASIGNACIONES)

    assert _error(respuesta) == (401, "sesion_invalida")
    assert respuesta["WWW-Authenticate"] == REINO


def test_otro_esquema_de_autorizacion_cuenta_como_sin_token(sesion, api):
    api.credentials(HTTP_AUTHORIZATION=f"Token {sesion.clave}")

    assert _error(api.get(URL_ASIGNACIONES)) == (401, "no_autenticado")


def test_un_token_vigente_entra(sesion):
    assert sesion.get(URL_ASIGNACIONES).status_code == 200


def test_un_token_revocado_responde_401(sesion):
    revocar_tokens(TokenDispositivo.objects.all())

    assert _error(sesion.get(URL_ASIGNACIONES)) == (401, "sesion_invalida")


def test_un_conductor_inactivo_con_token_vigente_recibe_401(sesion, ana_app):
    ana_app.activo = False
    ana_app.save()

    assert _error(sesion.get(URL_ASIGNACIONES)) == (401, "conductor_no_habilitado")


def test_un_usuario_inactivo_con_token_vigente_recibe_401(sesion, ana_app):
    ana_app.usuario.is_active = False
    ana_app.usuario.save()

    assert _error(sesion.get(URL_ASIGNACIONES)) == (401, "conductor_no_habilitado")


def test_un_usuario_sacado_del_grupo_conductor_recibe_401(sesion, ana_app):
    ana_app.usuario.groups.clear()

    assert _error(sesion.get(URL_ASIGNACIONES)) == (401, "conductor_no_habilitado")


def test_reactivar_al_conductor_devuelve_el_acceso_con_el_mismo_token(sesion, ana_app):
    ana_app.activo = False
    ana_app.save()
    assert sesion.get(URL_ASIGNACIONES).status_code == 401

    ana_app.activo = True
    ana_app.save()

    assert sesion.get(URL_ASIGNACIONES).status_code == 200


def test_la_sesion_del_panel_no_sirve_en_la_api(client, django_user_model, ana_app):
    administrador = django_user_model.objects.create_superuser("jefe")
    client.force_login(administrador)

    respuesta = client.get(URL_ASIGNACIONES)

    assert respuesta.status_code == 401


def test_cada_peticion_guarda_el_ultimo_uso(sesion, reloj):
    sesion.get(URL_ASIGNACIONES)
    sesion.token.refresh_from_db()
    assert sesion.token.ultimo_uso == reloj.ahora

    reloj.avanzar(minutes=7)
    sesion.get(URL_ASIGNACIONES)
    sesion.token.refresh_from_db()

    assert sesion.token.ultimo_uso == reloj.ahora


# --- Cerrar sesión -------------------------------------------------------------------------------


def test_cerrar_sesion_revoca_el_token(sesion):
    respuesta = sesion.post(URL_SALIDA)

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    sesion.token.refresh_from_db()
    assert not sesion.token.vigente
    assert _error(sesion.get(URL_ASIGNACIONES)) == (401, "sesion_invalida")


def test_cerrar_sesion_en_un_celular_no_cierra_la_de_otro(sesion, ana_app):
    _, otra_clave = TokenDispositivo.emitir(ana_app, "tableta-de-ana")

    sesion.post(URL_SALIDA)

    assert cliente_con(otra_clave).get(URL_ASIGNACIONES).status_code == 200


def test_cerrar_sesion_exige_token(api):
    assert _error(api.post(URL_SALIDA)) == (401, "no_autenticado")


def test_cerrar_sesion_dos_veces_responde_401_la_segunda(sesion):
    sesion.post(URL_SALIDA)

    assert _error(sesion.post(URL_SALIDA)) == (401, "sesion_invalida")


# --- Lo que garantiza la base --------------------------------------------------------------------


def test_la_base_permite_un_solo_token_vigente_por_conductor_y_celular(ana_app):
    TokenDispositivo.emitir(ana_app, "celular-de-ana")

    with (
        pytest.raises(IntegrityError, match="token_uno_vigente_por_dispositivo"),
        transaction.atomic(),
    ):
        TokenDispositivo.emitir(ana_app, "celular-de-ana")


def test_un_token_revocado_no_estorba_al_nuevo_del_mismo_celular(ana_app):
    TokenDispositivo.emitir(ana_app, "celular-de-ana")
    revocar_tokens(TokenDispositivo.objects.all())

    nuevo, _ = TokenDispositivo.emitir(ana_app, "celular-de-ana")

    assert nuevo.vigente


def test_la_base_no_acepta_un_token_guardado_en_claro(ana_app):
    with pytest.raises(IntegrityError, match="token_solo_hash"):
        TokenDispositivo.objects.create(
            conductor=ana_app, clave_hash=secrets.token_urlsafe(32), dispositivo_id="celular"
        )


def test_la_base_exige_el_identificador_del_celular(ana_app):
    with pytest.raises(IntegrityError, match="token_con_dispositivo"):
        TokenDispositivo.objects.create(conductor=ana_app, clave_hash="a" * 64, dispositivo_id="")


# --- Admin ---------------------------------------------------------------------------------------


def test_el_admin_revoca_los_tokens_seleccionados(admin_client, ana_app):
    elegido, clave_elegida = TokenDispositivo.emitir(ana_app, "celular-1")
    _, clave_otra = TokenDispositivo.emitir(ana_app, "celular-2")

    respuesta = admin_client.post(
        "/admin/api/tokendispositivo/",
        {"action": "revocar", "_selected_action": [elegido.pk]},
        follow=True,
    )

    assert "Tokens revocados: 1." in respuesta.content.decode()
    elegido.refresh_from_db()
    assert not elegido.vigente
    assert cliente_con(clave_elegida).get(URL_ASIGNACIONES).status_code == 401
    assert cliente_con(clave_otra).get(URL_ASIGNACIONES).status_code == 200


def test_el_admin_lista_los_tokens_y_no_los_crea_ni_los_borra(admin_client, ana_app):
    token, _ = TokenDispositivo.emitir(ana_app, "celular-1", "Moto G de Ana")

    lista = admin_client.get("/admin/api/tokendispositivo/")
    assert lista.status_code == 200
    assert "Moto G de Ana" in lista.content.decode()
    assert token.clave_hash not in admin_client.get(
        f"/admin/api/tokendispositivo/{token.pk}/change/"
    ).content.decode()
    assert admin_client.get("/admin/api/tokendispositivo/add/").status_code == 403
    assert admin_client.get(f"/admin/api/tokendispositivo/{token.pk}/delete/").status_code == 403
    assert TokenDispositivo.objects.filter(pk=token.pk).exists()


def test_el_admin_muestra_los_intentos_de_ingreso_solo_para_consultar(admin_client):
    intentos = IntentosIngreso.objects.create(celular="3109999999", fallos=3)

    assert admin_client.get("/admin/api/intentosingreso/").status_code == 200
    assert admin_client.get("/admin/api/intentosingreso/add/").status_code == 403
    assert (
        admin_client.get(f"/admin/api/intentosingreso/{intentos.pk}/delete/").status_code == 403
    )
