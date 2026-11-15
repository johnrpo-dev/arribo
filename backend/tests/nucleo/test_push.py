"""Reglas de los avisos push (`nucleo/push.py`): qué lleva un aviso, cuándo sigue valiendo, qué
hacer con cada respuesta de FCM y los reintentos acotados."""
from datetime import timedelta

import pytest

from nucleo.estados import Estado
from nucleo.push import (
    ESPERAS,
    MAXIMO_INTENTOS,
    Desenlace,
    TipoAviso,
    clasificar,
    contenido,
    espera_tras,
    sigue_vigente,
)


@pytest.mark.parametrize("tipo", list(TipoAviso))
def test_el_aviso_lleva_solo_el_numero_del_servicio_y_un_texto_fijo(tipo):
    aviso = contenido(tipo, 41)
    assert aviso.datos == {"tipo": tipo.value, "servicio_id": "41"}
    assert "41" in aviso.cuerpo
    # Mismo texto para cualquier servicio: no depende de cliente, vehículo, valor ni dirección.
    otro = contenido(tipo, 7)
    assert aviso.titulo == otro.titulo
    assert aviso.cuerpo.replace("41", "7") == otro.cuerpo


@pytest.mark.parametrize("tipo", list(TipoAviso))
def test_los_datos_del_aviso_son_textos_como_exige_fcm(tipo):
    assert all(isinstance(valor, str) for valor in contenido(tipo, 41).datos.values())


def test_el_aviso_de_asignado_y_el_de_retirado_dicen_cosas_distintas():
    asignado = contenido(TipoAviso.ASIGNADO, 41)
    retirado = contenido(TipoAviso.RETIRADO, 41)
    assert asignado.titulo != retirado.titulo
    assert "ya no está a su cargo" in retirado.cuerpo


@pytest.mark.parametrize(
    ("estado", "vigente"),
    [
        (Estado.ASIGNADO, True),
        (Estado.EN_CAMINO, True),
        (Estado.RECOGIDO, True),
        (Estado.NOVEDAD, True),
        (Estado.ENTREGADO, False),
        (Estado.CANCELADO, False),
    ],
)
def test_el_aviso_de_asignado_vale_mientras_el_servicio_sea_suyo_y_no_haya_terminado(
    estado, vigente
):
    assert sigue_vigente(
        TipoAviso.ASIGNADO,
        conductor_del_aviso="1",
        conductor_del_servicio="1",
        estado_del_servicio=estado,
    ) is vigente


@pytest.mark.parametrize("otro", ["2", None])
def test_el_aviso_de_asignado_no_vale_si_el_servicio_ya_es_de_otro_o_volvio_a_la_cola(otro):
    estado = Estado.ASIGNADO if otro else Estado.PENDIENTE_ASIGNAR
    assert not sigue_vigente(
        TipoAviso.ASIGNADO,
        conductor_del_aviso="1",
        conductor_del_servicio=otro,
        estado_del_servicio=estado,
    )


def test_el_aviso_de_retirado_no_vale_si_le_devolvieron_el_servicio():
    assert sigue_vigente(
        TipoAviso.RETIRADO,
        conductor_del_aviso="1",
        conductor_del_servicio="2",
        estado_del_servicio=Estado.ASIGNADO,
    )
    assert not sigue_vigente(
        TipoAviso.RETIRADO,
        conductor_del_aviso="1",
        conductor_del_servicio="1",
        estado_del_servicio=Estado.ASIGNADO,
    )


@pytest.mark.parametrize("estado_http", [200, 201])
def test_una_respuesta_2xx_es_enviado(estado_http):
    assert clasificar(estado_http) == Desenlace.ENVIADO


@pytest.mark.parametrize(
    ("estado_http", "codigo"),
    [(404, "UNREGISTERED"), (400, "UNREGISTERED"), (403, "SENDER_ID_MISMATCH")],
)
def test_un_token_que_fcm_no_reconoce_es_token_invalido(estado_http, codigo):
    assert clasificar(estado_http, codigo) == Desenlace.TOKEN_INVALIDO


def test_un_404_sin_codigo_de_fcm_no_desactiva_el_token():
    """Puede ser un proyecto mal escrito: no es culpa del token."""
    assert clasificar(404) == Desenlace.FALLIDO


@pytest.mark.parametrize(
    ("estado_http", "codigo"),
    [
        (None, None),
        (401, None),
        (403, None),
        (429, "QUOTA_EXCEEDED"),
        (500, "INTERNAL"),
        (503, "UNAVAILABLE"),
    ],
)
def test_sin_red_autenticacion_exceso_o_falla_de_fcm_se_reintenta(estado_http, codigo):
    assert clasificar(estado_http, codigo) == Desenlace.REINTENTAR


def test_un_mensaje_mal_formado_falla_sin_reintentar():
    assert clasificar(400, "INVALID_ARGUMENT") == Desenlace.FALLIDO


def test_los_reintentos_son_acotados_y_la_espera_crece():
    esperas = [espera_tras(n) for n in range(1, MAXIMO_INTENTOS)]
    assert esperas == list(ESPERAS)
    assert esperas == sorted(esperas)
    assert espera_tras(MAXIMO_INTENTOS) is None
    assert espera_tras(MAXIMO_INTENTOS + 3) is None


def test_un_aviso_deja_de_intentarse_antes_de_una_hora():
    assert sum(ESPERAS, timedelta()) < timedelta(hours=1)


def test_no_se_espera_antes_del_primer_intento():
    with pytest.raises(ValueError):
        espera_tras(0)
