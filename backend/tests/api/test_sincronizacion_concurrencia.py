"""Sincronización con peticiones simultáneas de verdad: varios hilos, cada uno con su conexión a
PostgreSQL y su propia petición HTTP a la API.

El caso real: la app envía un lote, no recibe respuesta a tiempo y lo reintenta mientras la primera
petición sigue en curso. La llave primaria del evento (el id del celular) deja entrar uno solo.
Pruebas transaccionales: pytest-django las corre después de las demás.
"""
import threading
import time
import uuid

import pytest

from alertas.models import Alerta, TipoAlerta
from api.models import TokenDispositivo
from cobros.models import LineaCobro
from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import EventoEstado, Evidencia

from ..solicitudes.test_concurrencia import en_paralelo
from .conftest import cliente_con, enviar, evento_json, subir

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("media_temporal")]

E = Estado


@pytest.fixture
def clave(ana_app):
    """El token de Ana en claro: cada hilo arma su propio cliente HTTP con él."""
    return TokenDispositivo.emitir(ana_app, "celular-de-ana", "Moto G de Ana")[1]


def test_el_mismo_lote_enviado_dos_veces_a_la_vez_se_aplica_una_sola_vez(clave, crear_servicio):
    for _ in range(5):  # varias rondas: el cruce de los hilos cambia en cada una
        servicio = crear_servicio(E.ASIGNADO)
        lote = [
            evento_json(servicio, E.EN_CAMINO, secuencia=1),
            evento_json(servicio, E.RECOGIDO, secuencia=2),
            evento_json(servicio, E.ENTREGADO, secuencia=3),
        ]

        salidas = en_paralelo(
            lambda lote=lote: enviar(cliente_con(clave), *lote),
            lambda lote=lote: enviar(cliente_con(clave), *lote),
        )

        assert not any(isinstance(salida, Exception) for salida in salidas), salidas
        for posicion in range(3):
            # Cada evento lo aplicó una petición y la otra lo vio duplicado; nunca un conflicto.
            assert [salida[posicion]["resultado"] for salida in salidas] == ["aplicado"] * 2
            assert sorted(salida[posicion]["duplicado"] for salida in salidas) == [False, True]
        assert servicio.eventos.count() == 3
        assert list(
            servicio.eventos.order_by("hora_sincronizacion").values_list("destino", flat=True)
        ) == ["en_camino", "recogido", "entregado"]
        servicio.refresh_from_db()
        assert servicio.estado == E.ENTREGADO
        assert LineaCobro.objects.filter(servicio=servicio).count() == 1
    assert not Alerta.objects.exists()


def test_el_mismo_evento_a_la_vez_llega_hasta_la_llave_primaria_y_entra_uno_solo(
    monkeypatch, clave, crear_servicio
):
    # Sin las consultas previas, las dos peticiones llegan al INSERT: solo la llave las separa.
    monkeypatch.setattr(operaciones, "_ya_recibido", lambda evento_id: False)
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO)

    salidas = en_paralelo(
        lambda: enviar(cliente_con(clave), evento),
        lambda: enviar(cliente_con(clave), evento),
    )

    assert not any(isinstance(salida, Exception) for salida in salidas), salidas
    assert [salida[0]["resultado"] for salida in salidas] == ["aplicado"] * 2
    assert sorted(salida[0]["duplicado"] for salida in salidas) == [False, True]
    assert EventoEstado.objects.count() == 1
    servicio.refresh_from_db()
    assert servicio.estado == E.EN_CAMINO


def test_el_mismo_conflicto_a_la_vez_deja_un_evento_y_una_sola_alerta(clave, crear_servicio):
    servicio = crear_servicio(E.CANCELADO)
    evento = evento_json(servicio, E.EN_CAMINO)

    salidas = en_paralelo(
        lambda: enviar(cliente_con(clave), evento),
        lambda: enviar(cliente_con(clave), evento),
    )

    assert not any(isinstance(salida, Exception) for salida in salidas), salidas
    assert [salida[0]["resultado"] for salida in salidas] == ["conflicto"] * 2
    assert [salida[0]["motivo"] for salida in salidas] == ["servicio_cancelado"] * 2
    assert sorted(salida[0]["duplicado"] for salida in salidas) == [False, True]
    assert EventoEstado.objects.count() == 1
    alerta = Alerta.objects.get()
    assert (alerta.tipo, alerta.registro_id) == (TipoAlerta.CONFLICTO_SINCRONIZACION, evento["id"])


def test_abrir_la_misma_alerta_a_la_vez_deja_una_sola(ana):
    from alertas.operaciones import abrir_alerta

    salidas = en_paralelo(
        *[lambda: abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "a la vez") for _ in range(4)]
    )

    assert not any(isinstance(salida, Exception) for salida in salidas), salidas
    assert len({salida.pk for salida in salidas}) == 1
    assert Alerta.objects.count() == 1


def test_la_misma_foto_subida_dos_veces_a_la_vez_queda_una_sola(
    clave, crear_servicio, media_temporal
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)
    enviar(cliente_con(clave), evento)
    evidencia_id = uuid.uuid4()

    def subida():
        respuesta, _ = subir(cliente_con(clave), servicio, evento["id"], evidencia_id=evidencia_id)
        return respuesta.status_code

    salidas = en_paralelo(subida, subida)

    assert sorted(salidas) == [200, 201], salidas
    assert Evidencia.objects.count() == 1
    archivos = [ruta for ruta in media_temporal.rglob("*") if ruta.is_file()]
    assert [ruta.name for ruta in archivos] == [f"{evidencia_id}.jpg"]


def test_la_foto_y_su_evento_a_la_vez_siempre_terminan_enlazados(clave, crear_servicio):
    """La subida de la foto y la llegada del evento bloquean la misma fila del servicio: o la
    foto ve el evento ya guardado, o el evento ve la foto en espera. Nunca queda suelta."""
    for _ in range(8):
        servicio = crear_servicio(E.EN_CAMINO)
        evento = evento_json(servicio, E.RECOGIDO)
        evidencia_id = uuid.uuid4()
        # Para que la grúa de Ana (un puesto) no marque capacidad excedida en la ronda siguiente.
        entregado = evento_json(servicio, E.ENTREGADO, secuencia=2)

        def subida(servicio=servicio, evento=evento, evidencia_id=evidencia_id):
            return subir(
                cliente_con(clave), servicio, evento["id"], evidencia_id=evidencia_id
            )[0].status_code

        salidas = en_paralelo(
            subida, lambda evento=evento: enviar(cliente_con(clave), evento)[0]["resultado"]
        )

        assert salidas == [201, "aplicado"], salidas
        assert str(Evidencia.objects.get(pk=evidencia_id).evento_id) == evento["id"]
        enviar(cliente_con(clave), entregado)


def test_un_hilo_que_espera_el_bloqueo_del_servicio_ve_el_evento_que_el_otro_guardo(
    monkeypatch, clave, crear_servicio
):
    """El cruce del reintento, forzado: la primera petición ya tiene bloqueado el servicio y aún
    no ha guardado el evento cuando llega la segunda, que pasa la consulta previa, espera el
    bloqueo y, al seguir, debe ver el evento ya guardado."""
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO)
    bloqueado = threading.Event()
    bloquear = operaciones._bloquear

    def bloquear_y_demorar(llave):
        fila = bloquear(llave)
        if not bloqueado.is_set():
            bloqueado.set()
            time.sleep(0.5)  # la segunda alcanza a quedar esperando el bloqueo
        return fila

    monkeypatch.setattr(operaciones, "_bloquear", bloquear_y_demorar)

    def segunda():
        assert bloqueado.wait(timeout=10)
        return enviar(cliente_con(clave), evento)[0]

    salidas = en_paralelo(lambda: enviar(cliente_con(clave), evento)[0], segunda)

    assert not any(isinstance(salida, Exception) for salida in salidas), salidas
    assert [(s["resultado"], s["duplicado"]) for s in salidas] == [
        ("aplicado", False),
        ("aplicado", True),
    ]
    assert EventoEstado.objects.count() == 1
