import pytest

from nucleo.estados import (
    Estado,
    EstadoSolicitud,
    Resolucion,
    Servicio,
    TransicionInvalida,
    a_bordo,
    estado_solicitud,
    reasignar,
    resolver_novedad,
    transicionar,
)

E = Estado


def en(estado: Estado) -> Servicio:
    return Servicio(estado=estado)


def test_camino_feliz_completo():
    s = Servicio()
    for destino in (E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO):
        s = transicionar(s, destino)
    assert s.estado == E.ENTREGADO


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        (E.PENDIENTE_ASIGNAR, E.EN_CAMINO),
        (E.ASIGNADO, E.RECOGIDO),
        (E.EN_CAMINO, E.ENTREGADO),
        (E.RECOGIDO, E.EN_CAMINO),
        (E.ENTREGADO, E.RECOGIDO),
    ],
)
def test_no_se_saltan_ni_se_devuelven_estados(origen, destino):
    with pytest.raises(TransicionInvalida):
        transicionar(en(origen), destino)


@pytest.mark.parametrize("terminal", [E.ENTREGADO, E.CANCELADO])
def test_un_estado_terminal_no_cambia(terminal):
    for destino in E:
        with pytest.raises(TransicionInvalida):
            transicionar(en(terminal), destino, motivo="x")


@pytest.mark.parametrize("origen", [E.PENDIENTE_ASIGNAR, E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO])
def test_cancelar_exige_motivo(origen):
    with pytest.raises(TransicionInvalida):
        transicionar(en(origen), E.CANCELADO)
    with pytest.raises(TransicionInvalida):
        transicionar(en(origen), E.CANCELADO, motivo="   ")
    assert transicionar(en(origen), E.CANCELADO, motivo="cliente desistió").estado == E.CANCELADO


def test_novedad_solo_desde_servicio_asignado_y_recuerda_el_estado_previo():
    with pytest.raises(TransicionInvalida):
        transicionar(en(E.PENDIENTE_ASIGNAR), E.NOVEDAD, motivo="x")
    s = transicionar(en(E.EN_CAMINO), E.NOVEDAD, motivo="vehículo no encontrado")
    assert (s.estado, s.estado_previo) == (E.NOVEDAD, E.EN_CAMINO)


def test_de_una_novedad_no_se_avanza_sin_resolverla():
    s = transicionar(en(E.EN_CAMINO), E.NOVEDAD, motivo="contacto ausente")
    with pytest.raises(TransicionInvalida):
        transicionar(s, E.RECOGIDO)


def test_reanudar_devuelve_al_estado_previo():
    s = transicionar(en(E.RECOGIDO), E.NOVEDAD, motivo="contacto ausente en destino")
    assert resolver_novedad(s, Resolucion.REANUDAR) == en(E.RECOGIDO)


def test_novedad_con_vehiculo_montado_no_se_reasigna():
    s = transicionar(en(E.RECOGIDO), E.NOVEDAD, motivo="contacto ausente")
    with pytest.raises(TransicionInvalida):
        resolver_novedad(s, Resolucion.REASIGNAR)


def test_novedad_antes_de_recoger_puede_volver_a_la_cola():
    s = transicionar(en(E.ASIGNADO), E.NOVEDAD, motivo="grúa varada")
    assert resolver_novedad(s, Resolucion.REASIGNAR) == en(E.PENDIENTE_ASIGNAR)


def test_cerrar_novedad_cancelando_exige_motivo():
    s = transicionar(en(E.EN_CAMINO), E.NOVEDAD, motivo="vehículo no apto")
    with pytest.raises(TransicionInvalida):
        resolver_novedad(s, Resolucion.CANCELAR)
    assert resolver_novedad(s, Resolucion.CANCELAR, motivo="no apto").estado == E.CANCELADO


def test_reasignar_solo_antes_de_recoger():
    assert reasignar(en(E.EN_CAMINO)) == en(E.ASIGNADO)
    for estado in (E.PENDIENTE_ASIGNAR, E.RECOGIDO, E.ENTREGADO, E.CANCELADO):
        with pytest.raises(TransicionInvalida):
            reasignar(en(estado))


def test_a_bordo_incluye_la_novedad_con_vehiculo_montado():
    assert a_bordo(en(E.RECOGIDO))
    assert a_bordo(transicionar(en(E.RECOGIDO), E.NOVEDAD, motivo="x"))
    assert not a_bordo(transicionar(en(E.EN_CAMINO), E.NOVEDAD, motivo="x"))
    assert not a_bordo(en(E.ENTREGADO))


@pytest.mark.parametrize(
    ("estados", "esperado"),
    [
        ([E.PENDIENTE_ASIGNAR, E.ASIGNADO], EstadoSolicitud.ABIERTA),
        ([E.ASIGNADO, E.EN_CAMINO], EstadoSolicitud.EN_CURSO),
        ([E.ENTREGADO, E.PENDIENTE_ASIGNAR], EstadoSolicitud.EN_CURSO),
        ([E.ENTREGADO, E.CANCELADO], EstadoSolicitud.COMPLETADA),
        ([E.CANCELADO, E.CANCELADO], EstadoSolicitud.CANCELADA),
        ([], EstadoSolicitud.ABIERTA),
    ],
)
def test_estado_de_la_solicitud_se_deriva(estados, esperado):
    assert estado_solicitud(estados) == esperado
