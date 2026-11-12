"""Eventos de la app del conductor contra PostgreSQL: idempotentes, nunca descartados, ordenados por
secuencia. Lo que no encaja se guarda como conflicto y el servicio no cambia.
"""
import uuid

import pytest

from nucleo.estados import Estado
from nucleo.sincronizacion import Resultado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EventoEstado, OrigenEvento, Servicio
from solicitudes.operaciones import aplicar_evento_del_conductor, aplicar_lote_del_conductor

from .conftest import VIN, crear_solicitud, hora

pytestmark = pytest.mark.django_db

E = Estado
APLICADO, DUPLICADO, CONFLICTO = Resultado.APLICADO, Resultado.DUPLICADO, Resultado.CONFLICTO


def estado_de(servicio):
    servicio.refresh_from_db()
    return servicio.estado


def guardado(evento_id) -> EventoEstado:
    return EventoEstado.objects.get(pk=evento_id)


# --- Evento válido -----------------------------------------------------------------------------


def test_un_evento_valido_se_aplica_y_se_guarda_con_todo_lo_que_manda_el_celular(
    crear_servicio, ana, evento_app
):
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(
        servicio,
        E.RECOGIDO,
        secuencia=7,
        nombre_quien="Portero Juan",
        latitud=6.2442,
        longitud=-75.5812,
    )

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(servicio) == E.RECOGIDO
    evento = guardado(datos["id"])
    assert evento.origen == OrigenEvento.APP
    assert evento.resultado == EventoEstado.Resultado.APLICADO
    assert (evento.servicio, evento.conductor, evento.actor) == (servicio, ana, None)
    assert (evento.destino, evento.secuencia) == (E.RECOGIDO, 7)
    assert evento.hora_dispositivo == hora(7)
    assert evento.hora_sincronizacion is not None  # se guardan las dos horas
    assert evento.hora_sincronizacion != evento.hora_dispositivo
    assert (evento.latitud, evento.longitud) == (6.2442, -75.5812)
    assert evento.nombre_quien == "Portero Juan"
    assert evento.capacidad_excedida is False


def test_el_id_del_celular_puede_llegar_como_texto(crear_servicio, evento_app):
    servicio = crear_servicio(E.ASIGNADO)
    texto = str(uuid.uuid4())
    assert aplicar_evento_del_conductor(**evento_app(servicio, "en_camino", id=texto)) == APLICADO
    assert aplicar_evento_del_conductor(**evento_app(servicio, "en_camino", id=texto.upper())) == (
        DUPLICADO
    )
    assert EventoEstado.objects.filter(pk=uuid.UUID(texto)).count() == 1


def test_una_novedad_con_motivo_se_aplica(crear_servicio, evento_app):
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(servicio, E.NOVEDAD, motivo="Vehículo no encontrado")
    assert aplicar_evento_del_conductor(**datos) == APLICADO
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.estado_previo) == (E.NOVEDAD, E.EN_CAMINO)
    assert guardado(datos["id"]).motivo == "Vehículo no encontrado"


# --- Idempotencia ------------------------------------------------------------------------------


def test_el_mismo_evento_dos_veces_deja_una_fila_y_cambia_el_estado_una_vez(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    datos = evento_app(servicio, E.EN_CAMINO)

    assert aplicar_evento_del_conductor(**datos) == APLICADO
    assert aplicar_evento_del_conductor(**datos) == DUPLICADO

    assert EventoEstado.objects.count() == 1
    assert estado_de(servicio) == E.EN_CAMINO


def test_un_lote_de_tres_reenviado_completo_deja_exactamente_el_mismo_resultado(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    lote = [
        evento_app(servicio, E.EN_CAMINO, secuencia=1),
        evento_app(servicio, E.RECOGIDO, secuencia=2, nombre_quien="Portero"),
        evento_app(servicio, E.ENTREGADO, secuencia=3, nombre_quien="Recepción"),
    ]
    ids = [str(datos["id"]) for datos in lote]

    primero = aplicar_lote_del_conductor(lote)
    filas = list(EventoEstado.objects.order_by("secuencia").values())
    # El celular no recibió la confirmación y reenvía el lote entero.
    segundo = aplicar_lote_del_conductor(lote)

    assert primero == [(i, APLICADO) for i in ids]
    assert segundo == [(i, DUPLICADO) for i in ids]
    assert list(EventoEstado.objects.order_by("secuencia").values()) == filas
    assert len(filas) == 3
    assert estado_de(servicio) == E.ENTREGADO


def test_un_evento_repetido_despues_de_que_el_estado_avanzo_no_lo_devuelve(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    en_camino = evento_app(servicio, E.EN_CAMINO, secuencia=1)
    recogido = evento_app(servicio, E.RECOGIDO, secuencia=2)
    aplicar_evento_del_conductor(**en_camino)
    aplicar_evento_del_conductor(**recogido)

    assert aplicar_evento_del_conductor(**en_camino) == DUPLICADO

    assert estado_de(servicio) == E.RECOGIDO
    assert EventoEstado.objects.count() == 2
    assert guardado(en_camino["id"]).resultado == EventoEstado.Resultado.APLICADO


def test_un_conflicto_reenviado_es_duplicado_y_no_se_vuelve_a_evaluar(
    crear_servicio, evento_app, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    salto = evento_app(servicio, E.RECOGIDO, secuencia=2)
    assert aplicar_evento_del_conductor(**salto) == CONFLICTO
    # Logística avanza el servicio: ahora el mismo evento sí encajaría, pero ya se recibió.
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)

    assert aplicar_evento_del_conductor(**salto) == DUPLICADO

    assert estado_de(servicio) == E.EN_CAMINO
    assert guardado(salto["id"]).resultado == EventoEstado.Resultado.CONFLICTO
    assert servicio.eventos.filter(origen=OrigenEvento.APP).count() == 1


def test_un_lote_desordenado_se_aplica_por_secuencia_y_no_por_la_hora_del_celular(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    # Llegan al revés y con el reloj del celular atrasado en el segundo.
    lote = [
        evento_app(servicio, E.ENTREGADO, secuencia=3, hora_dispositivo=hora(30)),
        evento_app(servicio, E.RECOGIDO, secuencia=2, hora_dispositivo=hora(-600)),
        evento_app(servicio, E.EN_CAMINO, secuencia=1, hora_dispositivo=hora(10)),
    ]
    resultados = aplicar_lote_del_conductor(lote)
    assert [resultado for _, resultado in resultados] == [APLICADO] * 3
    assert [i for i, _ in resultados] == [str(d["id"]) for d in reversed(lote)]
    assert estado_de(servicio) == E.ENTREGADO
    assert list(
        EventoEstado.objects.order_by("hora_sincronizacion").values_list("secuencia", flat=True)
    ) == [1, 2, 3]


# --- Carrera: dos peticiones con el mismo id a la vez ------------------------------------------


def test_choque_de_llave_por_carrera_en_otro_servicio_no_aplica_nada_ni_lanza_error(
    monkeypatch, crear_servicio, evento_app
):
    """Simula que la segunda petición pasó las consultas previas antes de que la primera guardara:
    llega hasta el INSERT y choca con la llave primaria del evento."""
    primero = crear_servicio(E.ASIGNADO)
    segundo = crear_servicio(E.ASIGNADO)
    id_repetido = uuid.uuid4()
    assert aplicar_evento_del_conductor(**evento_app(primero, E.EN_CAMINO, id=id_repetido)) == (
        APLICADO
    )

    monkeypatch.setattr(operaciones, "_ya_recibido", lambda evento_id: False)
    resultado = aplicar_evento_del_conductor(**evento_app(segundo, E.EN_CAMINO, id=id_repetido))

    assert resultado == DUPLICADO
    assert estado_de(segundo) == E.ASIGNADO  # su cambio de estado se deshizo con el choque
    assert estado_de(primero) == E.EN_CAMINO
    assert EventoEstado.objects.count() == 1
    assert guardado(id_repetido).servicio == primero


def test_choque_de_llave_por_carrera_en_el_mismo_servicio_no_aplica_dos_veces(
    monkeypatch, crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    datos = evento_app(servicio, E.EN_CAMINO)
    assert aplicar_evento_del_conductor(**datos) == APLICADO

    monkeypatch.setattr(operaciones, "_ya_recibido", lambda evento_id: False)
    assert aplicar_evento_del_conductor(**datos) == DUPLICADO

    assert estado_de(servicio) == E.EN_CAMINO
    assert EventoEstado.objects.count() == 1
    assert guardado(datos["id"]).resultado == EventoEstado.Resultado.APLICADO


def test_un_error_de_base_que_no_es_el_choque_de_llave_no_se_esconde(
    monkeypatch, crear_servicio, evento_app
):
    from django.db import IntegrityError

    servicio = crear_servicio(E.ASIGNADO)

    def falla(*args, **kwargs):
        raise IntegrityError("otra restricción")

    monkeypatch.setattr(Servicio, "_guardar_cambio_operativo", falla)
    datos = evento_app(servicio, E.EN_CAMINO)
    with pytest.raises(IntegrityError, match="otra restricción"):
        aplicar_evento_del_conductor(**datos)
    assert not EventoEstado.objects.exists()  # se deshizo también el evento
    assert estado_de(servicio) == E.ASIGNADO


# --- Conflictos: se guardan y el servicio no cambia --------------------------------------------


def test_evento_sobre_servicio_cancelado_se_guarda_como_conflicto(
    crear_servicio, evento_app, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo="El cliente desistió")
    datos = evento_app(servicio, E.EN_CAMINO)

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    assert estado_de(servicio) == E.CANCELADO
    evento = guardado(datos["id"])
    assert (evento.resultado, evento.destino) == (EventoEstado.Resultado.CONFLICTO, E.EN_CAMINO)
    assert evento.hora_dispositivo == datos["hora_dispositivo"]


def test_evento_de_un_conductor_al_que_le_reasignaron_el_servicio_es_conflicto(
    crear_servicio, ana, beto, evento_app, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    operaciones.reasignar(servicio, beto, actor=usuario)
    datos = evento_app(servicio, E.EN_CAMINO)  # Ana, sin señal, no se enteró

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor) == (E.ASIGNADO, beto)
    evento = guardado(datos["id"])
    assert (evento.resultado, evento.conductor) == (EventoEstado.Resultado.CONFLICTO, ana)


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        (E.ASIGNADO, E.RECOGIDO),
        (E.ASIGNADO, E.ENTREGADO),
        (E.EN_CAMINO, E.ENTREGADO),
        (E.RECOGIDO, E.EN_CAMINO),
        (E.ENTREGADO, E.RECOGIDO),
        (E.ASIGNADO, E.ASIGNADO),
        (E.ASIGNADO, E.PENDIENTE_ASIGNAR),
    ],
)
def test_salto_o_retroceso_de_estado_se_guarda_como_conflicto(
    crear_servicio, evento_app, origen, destino
):
    servicio = crear_servicio(origen)
    datos = evento_app(servicio, destino)

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    assert estado_de(servicio) == origen
    assert guardado(datos["id"]).resultado == EventoEstado.Resultado.CONFLICTO


@pytest.mark.parametrize("motivo", [None, "", "  "])
def test_novedad_sin_motivo_se_guarda_como_conflicto(crear_servicio, evento_app, motivo):
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(servicio, E.NOVEDAD, motivo=motivo)
    assert aplicar_evento_del_conductor(**datos) == CONFLICTO
    assert estado_de(servicio) == E.EN_CAMINO
    assert EventoEstado.objects.filter(pk=datos["id"]).exists()


@pytest.mark.parametrize("origen", [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO])
def test_cancelar_desde_la_app_se_guarda_como_conflicto_y_el_servicio_no_cambia(
    crear_servicio, ana, evento_app, origen
):
    # El conductor no cancela: la app solo tiene En camino, Recogido, Entregado y Novedad.
    servicio = crear_servicio(origen)
    grua = servicio.grua
    datos = evento_app(servicio, E.CANCELADO, motivo="El cliente no estaba")

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor, servicio.grua) == (origen, ana, grua)
    evento = guardado(datos["id"])
    assert (evento.resultado, evento.destino, evento.motivo) == (
        EventoEstado.Resultado.CONFLICTO,
        E.CANCELADO,
        "El cliente no estaba",
    )
    assert aplicar_evento_del_conductor(**datos) == DUPLICADO
    assert EventoEstado.objects.count() == 1


def test_evento_sobre_servicio_aun_sin_asignar_es_conflicto(crear_servicio, evento_app):
    servicio = crear_servicio()
    assert aplicar_evento_del_conductor(**evento_app(servicio, E.EN_CAMINO)) == CONFLICTO
    assert estado_de(servicio) == E.PENDIENTE_ASIGNAR


def test_un_conflicto_en_un_lote_no_detiene_los_demas(crear_servicio, evento_app, usuario):
    cancelado = crear_servicio(E.ASIGNADO)
    operaciones.cambiar_estado(cancelado, E.CANCELADO, actor=usuario, motivo="Desistió")
    vigente = crear_servicio(E.ASIGNADO)
    lote = [
        evento_app(cancelado, E.EN_CAMINO, secuencia=1),
        evento_app(vigente, E.EN_CAMINO, secuencia=2),
    ]
    assert [r for _, r in aplicar_lote_del_conductor(lote)] == [CONFLICTO, APLICADO]
    assert (estado_de(cancelado), estado_de(vigente)) == (E.CANCELADO, E.EN_CAMINO)


# --- Identificación al recoger -----------------------------------------------------------------


def test_recogido_sin_placa_ni_vin_se_guarda_como_conflicto(
    crear_servicio, nuevo_vehiculo, evento_app
):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    datos = evento_app(servicio, E.RECOGIDO)
    assert aplicar_evento_del_conductor(**datos) == CONFLICTO
    assert estado_de(servicio) == E.EN_CAMINO
    assert guardado(datos["id"]).resultado == EventoEstado.Resultado.CONFLICTO


def test_recogido_de_un_desvare_sin_placa_se_guarda_como_conflicto(
    cliente, crear_servicio, nuevo_vehiculo, evento_app
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(vin=VIN), solicitud_de=desvare)
    assert aplicar_evento_del_conductor(**evento_app(servicio, E.RECOGIDO)) == CONFLICTO
    assert estado_de(servicio) == E.EN_CAMINO


# --- Capacidad desde la app: se aplica y se marca ----------------------------------------------


def test_recogido_que_excede_la_capacidad_se_aplica_y_queda_marcado(crear_servicio, evento_app):
    crear_servicio(E.RECOGIDO)  # la grúa de Ana, de un puesto, ya va llena
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(servicio, E.RECOGIDO)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(servicio) == E.RECOGIDO
    evento = guardado(datos["id"])
    assert evento.capacidad_excedida is True
    assert evento.resultado == EventoEstado.Resultado.APLICADO


def test_novedad_con_vehiculo_montado_ocupa_puesto_tambien_desde_la_app(
    crear_servicio, evento_app
):
    crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(servicio, E.RECOGIDO)
    assert aplicar_evento_del_conductor(**datos) == APLICADO
    assert guardado(datos["id"]).capacidad_excedida is True


def test_recogido_con_puesto_libre_no_queda_marcado(crear_servicio, beto, evento_app):
    crear_servicio(E.RECOGIDO, conductor=beto)  # grúa de dos puestos
    servicio = crear_servicio(E.EN_CAMINO, conductor=beto)
    datos = evento_app(servicio, E.RECOGIDO, conductor=beto)
    assert aplicar_evento_del_conductor(**datos) == APLICADO
    assert guardado(datos["id"]).capacidad_excedida is False


def test_sin_identificacion_es_conflicto_aunque_tambien_exceda_la_capacidad(
    crear_servicio, nuevo_vehiculo, evento_app
):
    crear_servicio(E.RECOGIDO)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    datos = evento_app(servicio, E.RECOGIDO)
    assert aplicar_evento_del_conductor(**datos) == CONFLICTO
    evento = guardado(datos["id"])
    assert (evento.resultado, evento.capacidad_excedida) == (
        EventoEstado.Resultado.CONFLICTO,
        False,
    )
    assert estado_de(servicio) == E.EN_CAMINO
