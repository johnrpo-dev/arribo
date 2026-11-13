from datetime import datetime

import pytest

from nucleo.estados import Estado, Servicio, transicionar
from nucleo.sincronizacion import (
    DESTINOS_DESDE_LA_APP,
    DETALLE,
    MOTIVOS_DE_CONFLICTO,
    MOTIVOS_DE_RECHAZO,
    Evento,
    Motivo,
    Resultado,
    aplicar_evento,
    decidir,
    es_reenvio,
    ordenar,
)

CONDUCTOR = "conductor-1"


def evento(destino: Estado, *, id: str = "ev-1", secuencia: int = 1, conductor: str = CONDUCTOR,
           motivo: str | None = None, hora: datetime = datetime(2026, 11, 12, 8, 0)) -> Evento:
    return Evento(id=id, servicio_id="s-1", conductor_id=conductor, destino=destino,
                  secuencia=secuencia, hora_dispositivo=hora, motivo=motivo)


def test_evento_valido_se_aplica():
    servicio, resultado = aplicar_evento(
        Servicio(Estado.ASIGNADO), CONDUCTOR, evento(Estado.EN_CAMINO), set()
    )
    assert (servicio.estado, resultado) == (Estado.EN_CAMINO, Resultado.APLICADO)


def test_evento_repetido_no_se_aplica_dos_veces():
    inicial = Servicio(Estado.ASIGNADO)
    ev = evento(Estado.EN_CAMINO)
    aplicados: set[str] = set()

    servicio, primero = aplicar_evento(inicial, CONDUCTOR, ev, aplicados)
    aplicados.add(ev.id)
    servicio_2, segundo = aplicar_evento(servicio, CONDUCTOR, ev, aplicados)

    assert (primero, segundo) == (Resultado.APLICADO, Resultado.DUPLICADO)
    assert servicio_2 == servicio


def test_lote_reenviado_completo_deja_el_mismo_resultado():
    lote = [
        evento(Estado.EN_CAMINO, id="a", secuencia=1),
        evento(Estado.RECOGIDO, id="b", secuencia=2),
        evento(Estado.ENTREGADO, id="c", secuencia=3),
    ]
    servicio, aplicados = Servicio(Estado.ASIGNADO), set()
    for _ in range(2):  # el celular reenvía porque no recibió la confirmación
        for ev in lote:
            servicio, resultado = aplicar_evento(servicio, CONDUCTOR, ev, aplicados)
            if resultado == Resultado.APLICADO:
                aplicados.add(ev.id)
    assert servicio.estado == Estado.ENTREGADO
    assert aplicados == {"a", "b", "c"}


def test_servicio_cancelado_mientras_el_conductor_estaba_sin_senal_es_conflicto():
    cancelado = transicionar(Servicio(Estado.ASIGNADO), Estado.CANCELADO, motivo="cliente desistió")
    servicio, resultado = aplicar_evento(cancelado, CONDUCTOR, evento(Estado.EN_CAMINO), set())
    assert resultado == Resultado.CONFLICTO
    assert servicio == cancelado  # el estado no cambia; el evento se guarda aparte


def test_servicio_reasignado_a_otro_conductor_es_conflicto():
    _, resultado = aplicar_evento(
        Servicio(Estado.ASIGNADO), "conductor-2", evento(Estado.EN_CAMINO), set()
    )
    assert resultado == Resultado.CONFLICTO


def test_salto_de_estado_es_conflicto_y_no_error():
    _, resultado = aplicar_evento(
        Servicio(Estado.ASIGNADO), CONDUCTOR, evento(Estado.ENTREGADO), set()
    )
    assert resultado == Resultado.CONFLICTO


def test_novedad_sin_motivo_es_conflicto():
    _, resultado = aplicar_evento(
        Servicio(Estado.EN_CAMINO), CONDUCTOR, evento(Estado.NOVEDAD), set()
    )
    assert resultado == Resultado.CONFLICTO


def test_desde_la_app_solo_se_aceptan_los_cuatro_botones_del_conductor():
    assert DESTINOS_DESDE_LA_APP == {
        Estado.EN_CAMINO,
        Estado.RECOGIDO,
        Estado.ENTREGADO,
        Estado.NOVEDAD,
    }


@pytest.mark.parametrize(
    ("origen", "destino", "motivo"),
    [
        (Estado.ASIGNADO, Estado.EN_CAMINO, None),
        (Estado.EN_CAMINO, Estado.RECOGIDO, None),
        (Estado.RECOGIDO, Estado.ENTREGADO, None),
        (Estado.RECOGIDO, Estado.NOVEDAD, "Destino cerrado"),
    ],
)
def test_los_cuatro_destinos_de_la_app_se_aplican(origen, destino, motivo):
    servicio, resultado = aplicar_evento(
        Servicio(origen), CONDUCTOR, evento(destino, motivo=motivo), set()
    )
    assert (servicio.estado, resultado) == (destino, Resultado.APLICADO)


@pytest.mark.parametrize("origen", [Estado.ASIGNADO, Estado.EN_CAMINO, Estado.RECOGIDO])
def test_el_conductor_no_cancela_desde_la_app_aunque_traiga_motivo(origen):
    inicial = Servicio(origen)
    servicio, resultado = aplicar_evento(
        inicial, CONDUCTOR, evento(Estado.CANCELADO, motivo="El cliente no estaba"), set()
    )
    assert resultado == Resultado.CONFLICTO
    assert servicio == inicial


@pytest.mark.parametrize("destino", [Estado.PENDIENTE_ASIGNAR, Estado.ASIGNADO])
def test_la_app_no_asigna_ni_devuelve_a_la_cola(destino):
    inicial = Servicio(Estado.PENDIENTE_ASIGNAR)
    servicio, resultado = aplicar_evento(inicial, CONDUCTOR, evento(destino, motivo="x"), set())
    assert (servicio, resultado) == (inicial, Resultado.CONFLICTO)


def test_un_destino_no_permitido_repetido_sigue_siendo_duplicado():
    ev = evento(Estado.CANCELADO, motivo="x")
    _, resultado = aplicar_evento(Servicio(Estado.ASIGNADO), CONDUCTOR, ev, {ev.id})
    assert resultado == Resultado.DUPLICADO


def test_el_orden_lo_da_la_secuencia_y_no_el_reloj_del_celular():
    reloj_atrasado = evento(Estado.RECOGIDO, id="b", secuencia=2, hora=datetime(2020, 1, 1))
    primero = evento(Estado.EN_CAMINO, id="a", secuencia=1, hora=datetime(2026, 11, 12))
    assert [e.id for e in ordenar([reloj_atrasado, primero])] == ["a", "b"]


# --- Motivo del conflicto: lo que se le dice al conductor y a logística ------------------------


@pytest.mark.parametrize(
    ("servicio", "asignado", "destino", "motivo_del_evento", "esperado"),
    [
        (Servicio(Estado.ASIGNADO), CONDUCTOR, Estado.CANCELADO, "x", Motivo.DESTINO_NO_PERMITIDO),
        (Servicio(Estado.ASIGNADO), "conductor-2", Estado.EN_CAMINO, None,
         Motivo.SERVICIO_NO_ASIGNADO),
        (Servicio(Estado.PENDIENTE_ASIGNAR), None, Estado.EN_CAMINO, None,
         Motivo.SERVICIO_NO_ASIGNADO),
        (Servicio(Estado.CANCELADO), CONDUCTOR, Estado.EN_CAMINO, None, Motivo.SERVICIO_CANCELADO),
        (Servicio(Estado.ENTREGADO), CONDUCTOR, Estado.ENTREGADO, None, Motivo.SERVICIO_ENTREGADO),
        (Servicio(Estado.NOVEDAD, Estado.EN_CAMINO), CONDUCTOR, Estado.RECOGIDO, None,
         Motivo.NOVEDAD_ABIERTA),
        (Servicio(Estado.ASIGNADO), CONDUCTOR, Estado.RECOGIDO, None, Motivo.SALTO_DE_ESTADO),
        (Servicio(Estado.RECOGIDO), CONDUCTOR, Estado.EN_CAMINO, None, Motivo.SALTO_DE_ESTADO),
        (Servicio(Estado.EN_CAMINO), CONDUCTOR, Estado.NOVEDAD, "  ", Motivo.NOVEDAD_SIN_MOTIVO),
    ],
)
def test_cada_conflicto_dice_por_que_no_encajo(
    servicio, asignado, destino, motivo_del_evento, esperado
):
    decision = decidir(servicio, asignado, evento(destino, motivo=motivo_del_evento), set())
    assert (decision.resultado, decision.motivo) == (Resultado.CONFLICTO, esperado)
    assert decision.servicio == servicio  # un conflicto nunca cambia el servicio


def test_un_evento_aplicado_o_duplicado_no_lleva_motivo():
    ev = evento(Estado.EN_CAMINO)
    aplicado = decidir(Servicio(Estado.ASIGNADO), CONDUCTOR, ev, set())
    duplicado = decidir(Servicio(Estado.EN_CAMINO), CONDUCTOR, ev, {ev.id})
    assert (aplicado.resultado, aplicado.motivo) == (Resultado.APLICADO, None)
    assert aplicado.servicio == Servicio(Estado.EN_CAMINO)
    assert (duplicado.resultado, duplicado.motivo) == (Resultado.DUPLICADO, None)


def test_el_servicio_reasignado_y_luego_cancelado_se_explica_por_la_reasignacion():
    # El conductor ya no era el del servicio cuando lo cancelaron: lo suyo es que se lo quitaron.
    decision = decidir(Servicio(Estado.CANCELADO), "conductor-2", evento(Estado.EN_CAMINO), set())
    assert decision.motivo == Motivo.SERVICIO_NO_ASIGNADO


def test_aplicar_evento_y_decidir_dan_siempre_lo_mismo():
    casos = [
        (Servicio(Estado.ASIGNADO), CONDUCTOR, evento(Estado.EN_CAMINO)),
        (Servicio(Estado.ASIGNADO), CONDUCTOR, evento(Estado.ENTREGADO)),
        (Servicio(Estado.CANCELADO), CONDUCTOR, evento(Estado.EN_CAMINO)),
    ]
    for servicio, asignado, ev in casos:
        decision = decidir(servicio, asignado, ev, set())
        assert aplicar_evento(servicio, asignado, ev, set()) == (
            decision.servicio,
            decision.resultado,
        )


def test_todo_motivo_tiene_un_texto_legible_en_espanol():
    for motivo in Motivo:
        assert DETALLE[motivo].strip().endswith(".")


def test_los_motivos_de_conflicto_y_los_de_rechazo_no_se_mezclan():
    assert MOTIVOS_DE_CONFLICTO.isdisjoint(MOTIVOS_DE_RECHAZO)
    assert Motivo.ID_REUTILIZADO in MOTIVOS_DE_RECHAZO
    assert Motivo.SERVICIO_CANCELADO in MOTIVOS_DE_CONFLICTO


# --- Mismo id con otro contenido ---------------------------------------------------------------


def test_un_reenvio_es_el_mismo_id_con_el_mismo_contenido():
    guardado = evento(Estado.EN_CAMINO, secuencia=7)
    # La hora y el motivo no cuentan: el celular reenvía lo mismo, y el reloj no es de fiar.
    reenviado = evento(Estado.EN_CAMINO, secuencia=7, hora=datetime(2031, 1, 1), motivo="x")
    assert es_reenvio(guardado, reenviado)


@pytest.mark.parametrize(
    "otro",
    [
        evento(Estado.RECOGIDO, secuencia=7),  # otro destino
        evento(Estado.EN_CAMINO, secuencia=8),  # otra secuencia
        evento(Estado.EN_CAMINO, secuencia=7, conductor="conductor-2"),  # otro conductor
        Evento(id="ev-1", servicio_id="s-2", conductor_id=CONDUCTOR, destino=Estado.EN_CAMINO,
               secuencia=7, hora_dispositivo=datetime(2026, 11, 12, 8, 0)),  # otro servicio
    ],
)
def test_el_mismo_id_con_otro_contenido_no_es_un_reenvio(otro):
    assert not es_reenvio(evento(Estado.EN_CAMINO, secuencia=7), otro)


def test_el_orden_conserva_el_de_llegada_cuando_la_secuencia_se_repite():
    primero = evento(Estado.EN_CAMINO, id="a", secuencia=5)
    segundo = evento(Estado.RECOGIDO, id="b", secuencia=5)
    assert [e.id for e in ordenar([primero, segundo])] == ["a", "b"]
