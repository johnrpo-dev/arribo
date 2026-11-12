from datetime import datetime

from nucleo.estados import Estado, Servicio, transicionar
from nucleo.sincronizacion import Evento, Resultado, aplicar_evento, ordenar

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


def test_el_orden_lo_da_la_secuencia_y_no_el_reloj_del_celular():
    reloj_atrasado = evento(Estado.RECOGIDO, id="b", secuencia=2, hora=datetime(2020, 1, 1))
    primero = evento(Estado.EN_CAMINO, id="a", secuencia=1, hora=datetime(2026, 11, 12))
    assert [e.id for e in ordenar([reloj_atrasado, primero])] == ["a", "b"]
