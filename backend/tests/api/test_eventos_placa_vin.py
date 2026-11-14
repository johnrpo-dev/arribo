"""`POST /api/v1/eventos/` con la placa o el VIN digitados al recoger (contrato 1.1, tarea 1a-13b).

El Recogido trae `placa` y `vin` opcionales. Lo que el vehículo no tenía se guarda en él y la app
lo ve en la siguiente lista; lo que no encaja se aplica igual y abre una alerta a logística, sin
tumbar el evento ni el lote. Las reglas se prueban en
`tests/solicitudes/test_identificacion_al_recoger.py`; aquí, la lectura del cuerpo y la respuesta.
"""
from decimal import Decimal

import pytest

from alertas.models import Alerta, TipoAlerta
from clientes.models import Cliente, Tarifa, TipoCliente
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes.models import EventoEstado

from ..conftest import VIN, crear_solicitud
from .conftest import URL_ASIGNACIONES, URL_EVENTOS, enviar, evento_json
from .test_asignaciones import FRAGMENTOS_DE_COBRO, _claves

pytestmark = pytest.mark.django_db

E = Estado


def guardado(evento) -> EventoEstado:
    return EventoEstado.objects.get(pk=evento["id"])


def alertas_por_revisar(evento):
    return Alerta.objects.filter(
        tipo=TipoAlerta.IDENTIFICACION_POR_REVISAR, registro_id=str(evento["id"])
    )


def vehiculo_en_la_lista(cliente, servicio) -> dict:
    respuesta = cliente.get(f"{URL_ASIGNACIONES}{servicio.pk}/")
    assert respuesta.status_code == 200
    return respuesta.json()["servicio"]["vehiculo"]


@pytest.fixture
def sin_identificar(nuevo_vehiculo):
    return nuevo_vehiculo(placa="", vin="")


@pytest.fixture
def por_recoger(crear_servicio, sin_identificar):
    return crear_servicio(E.EN_CAMINO, vehiculo=sin_identificar)


def test_recogido_con_placa_digitada_se_aplica_y_la_lista_ya_trae_la_placa(sesion, por_recoger):
    assert vehiculo_en_la_lista(sesion, por_recoger)["placa"] is None
    evento = evento_json(por_recoger, E.RECOGIDO, placa="abc-123", vin=None)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("aplicado", None)
    assert resultado["servicio"]["estado"] == "recogido"
    assert vehiculo_en_la_lista(sesion, por_recoger)["placa"] == "ABC123"
    assert guardado(evento).placa_digitada == "ABC123"


def test_recogido_con_vin_digitado_en_un_traslado_se_aplica(sesion, por_recoger):
    (resultado,) = enviar(sesion, evento_json(por_recoger, E.RECOGIDO, vin=VIN.lower()))
    assert resultado["resultado"] == "aplicado"
    assert vehiculo_en_la_lista(sesion, por_recoger)["vin"] == VIN


def test_un_desvare_con_solo_el_vin_digitado_es_conflicto_por_identificacion(
    sesion, cliente, crear_servicio, sin_identificar
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=sin_identificar, solicitud_de=desvare)
    evento = evento_json(servicio, E.RECOGIDO, vin=VIN)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == (
        "conflicto",
        "identificacion_incompleta",
    )
    assert guardado(evento).vin_digitado == VIN


def test_recogido_con_dato_invalido_que_llega_pese_a_la_app_se_aplica_con_alerta(
    sesion, por_recoger, sin_identificar
):
    evento = evento_json(por_recoger, E.RECOGIDO, vin="1HGCM82633A00435")

    (resultado,) = enviar(sesion, evento)

    assert resultado["resultado"] == "aplicado"
    sin_identificar.refresh_from_db()
    assert sin_identificar.vin == ""
    assert alertas_por_revisar(evento).count() == 1


def test_recogido_con_placa_de_otro_vehiculo_se_aplica_con_alerta_sin_romper_el_lote(
    sesion, crear_servicio, por_recoger, sin_identificar, nuevo_vehiculo
):
    nuevo_vehiculo(placa="ABC123")
    otro = crear_servicio(E.ASIGNADO)
    lote = [
        evento_json(por_recoger, E.RECOGIDO, secuencia=1, placa="ABC123"),
        evento_json(otro, E.EN_CAMINO, secuencia=2),
        evento_json(por_recoger, E.ENTREGADO, secuencia=3),
    ]

    resultados = enviar(sesion, *lote)

    assert [r["resultado"] for r in resultados] == ["aplicado"] * 3
    assert [r["motivo"] for r in resultados] == [None] * 3
    sin_identificar.refresh_from_db()
    assert sin_identificar.placa == ""
    assert alertas_por_revisar(lote[0]).count() == 1


@pytest.mark.parametrize(
    "ilegible",
    [
        {"placa": ["ABC123"], "vin": {"vin": "1HGCM82633A004352"}},
        {"placa": True, "vin": None},
        {"placa": "ABC\x00123", "vin": "1HGCM82633A00435\x00"},  # carácter nulo
    ],
)
def test_una_placa_o_un_vin_ilegibles_se_guardan_vacios_sin_tumbar_el_evento(
    sesion, crear_servicio, nuevo_vehiculo, ilegible
):
    vehiculo = nuevo_vehiculo(placa="XYZ789")
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    evento = {**evento_json(servicio, E.RECOGIDO), **ilegible}

    (resultado,) = enviar(sesion, evento)

    assert resultado["resultado"] == "aplicado"
    fila = guardado(evento)
    assert (fila.placa_digitada, fila.vin_digitado) == ("", "")
    vehiculo.refresh_from_db()
    assert (vehiculo.placa, vehiculo.vin) == ("XYZ789", "")
    assert not Alerta.objects.exists()


def test_una_placa_que_llega_como_numero_se_lee_como_texto(sesion, por_recoger):
    evento = evento_json(por_recoger, E.RECOGIDO, placa=123456)
    (resultado,) = enviar(sesion, evento)
    assert resultado["resultado"] == "aplicado"
    assert vehiculo_en_la_lista(sesion, por_recoger)["placa"] == "123456"


def test_el_reenvio_del_recogido_con_placa_es_duplicado_y_no_repite_efectos(
    sesion, por_recoger, sin_identificar, nuevo_vehiculo
):
    nuevo_vehiculo(placa="XYZ789")
    evento = evento_json(por_recoger, E.RECOGIDO, placa="ABC123", vin="MALO")

    (primero,) = enviar(sesion, evento)
    (segundo,) = enviar(sesion, evento)

    assert (primero["duplicado"], segundo["duplicado"]) == (False, True)
    assert segundo["resultado"] == primero["resultado"] == "aplicado"
    assert EventoEstado.objects.filter(servicio=por_recoger).count() == 1
    sin_identificar.refresh_from_db()
    assert sin_identificar.placa == "ABC123"
    assert Alerta.objects.count() == 1


def test_las_respuestas_del_recogido_con_placa_no_contienen_valores_de_cobro(
    sesion, cliente, crear_servicio, sin_identificar
):
    pagador = Cliente.objects.create(
        nombre="Aseguradora Pagadora Única", tipo=TipoCliente.ASEGURADORA
    )
    solicitud = crear_solicitud(cliente, pagador=pagador)
    Tarifa.objects.create(
        cliente=pagador, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal("876543.21")
    )
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=sin_identificar, solicitud_de=solicitud)
    lote = [
        evento_json(servicio, E.RECOGIDO, secuencia=1, placa="ABC123", vin="MALO"),
        evento_json(servicio, E.ENTREGADO, secuencia=2),  # nace la línea de cobro
    ]

    for _ in range(2):  # la primera vez y el reenvío
        respuesta = sesion.post(URL_EVENTOS, {"eventos": lote}, format="json")
        assert respuesta.status_code == 200
        assert [r["resultado"] for r in respuesta.json()["resultados"]] == ["aplicado"] * 2
        claves = set(_claves(respuesta.json()))
        assert not {c for c in claves if any(f in c.lower() for f in FRAGMENTOS_DE_COBRO)}
        texto = respuesta.content.decode()
        for prohibido in ("876543", "Aseguradora Pagadora", "por_facturar"):
            assert prohibido not in texto
