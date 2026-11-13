"""Obligatorios para que una solicitud deje de ser borrador."""
import pytest

from nucleo.estados import Estado
from nucleo.registro import (
    CierreNoPermitido,
    Faltante,
    crea_regreso,
    describir_faltantes,
    destino_obligatorio,
    faltantes_para_abrir,
    verificar_cierre_no_concretada,
)
from nucleo.tipos import TipoServicio


def completa(**cambios):
    datos = {
        "tiene_solicitante": True,
        "tipo": TipoServicio.TRASLADO,
        "origen": "Calle 10 # 43-20",
        "destino": "Carrera 70 # 1-50",
        "vehiculos": 1,
        "tiene_regreso": None,
    }
    datos.update(cambios)
    return faltantes_para_abrir(**datos)


def test_traslado_completo_no_tiene_faltantes():
    assert completa() == []


def test_sin_solicitante_falta_el_solicitante():
    assert completa(tiene_solicitante=False) == [Faltante.SOLICITANTE]


@pytest.mark.parametrize("tipo", [None, ""])
def test_sin_tipo_falta_el_tipo(tipo):
    assert completa(tipo=tipo) == [Faltante.TIPO]


@pytest.mark.parametrize("origen", [None, "", "   "])
def test_sin_origen_falta_el_origen(origen):
    assert completa(origen=origen) == [Faltante.ORIGEN]


def test_sin_vehiculo_falta_el_vehiculo():
    assert completa(vehiculos=0) == [Faltante.VEHICULO]


@pytest.mark.parametrize("destino", [None, "", "  "])
def test_traslado_sin_destino_no_sale_de_borrador(destino):
    assert completa(destino=destino) == [Faltante.DESTINO]


def test_evento_sin_destino_no_sale_de_borrador():
    assert Faltante.DESTINO in completa(tipo=TipoServicio.EVENTO, destino="", tiene_regreso=False)


def test_desvare_sin_destino_sale_de_borrador():
    assert completa(tipo=TipoServicio.DESVARE, destino="") == []


def test_sin_tipo_el_destino_se_exige():
    assert destino_obligatorio(None) is True
    assert completa(tipo=None, destino="") == [Faltante.TIPO, Faltante.DESTINO]


@pytest.mark.parametrize("tipo, obligatorio", [("traslado", True), ("evento", True), ("desvare", False)])
def test_destino_obligatorio_segun_el_tipo(tipo, obligatorio):
    assert destino_obligatorio(tipo) is obligatorio


def test_evento_sin_responder_regreso_no_sale_de_borrador():
    assert completa(tipo=TipoServicio.EVENTO) == [Faltante.RESPUESTA_REGRESO]


@pytest.mark.parametrize("respuesta", [True, False])
def test_evento_con_respuesta_de_regreso_sale_de_borrador(respuesta):
    assert completa(tipo=TipoServicio.EVENTO, tiene_regreso=respuesta) == []


def test_el_regreso_no_se_pide_fuera_de_eventos():
    assert completa(tipo=TipoServicio.TRASLADO, tiene_regreso=None) == []
    assert completa(tipo=TipoServicio.DESVARE, tiene_regreso=None, destino="") == []


def test_los_faltantes_salen_en_el_orden_del_formulario():
    assert faltantes_para_abrir(
        tiene_solicitante=False, tipo=None, origen="", destino="", vehiculos=0
    ) == [
        Faltante.SOLICITANTE,
        Faltante.TIPO,
        Faltante.ORIGEN,
        Faltante.DESTINO,
        Faltante.VEHICULO,
    ]


def test_describir_faltantes_en_una_frase():
    assert describir_faltantes([]) == ""
    assert describir_faltantes([Faltante.ORIGEN]) == "el origen"
    assert (
        describir_faltantes([Faltante.ORIGEN, Faltante.DESTINO, Faltante.VEHICULO])
        == "el origen, el destino y al menos un vehículo"
    )


# --- Referencia externa (aseguradora) ----------------------------------------------------------


def test_si_paga_una_aseguradora_cada_vehiculo_exige_referencia_externa():
    assert completa(paga_aseguradora=True, vehiculos_sin_referencia=1) == [
        Faltante.REFERENCIA_EXTERNA
    ]


def test_si_paga_una_aseguradora_con_todas_las_referencias_sale_de_borrador():
    assert completa(paga_aseguradora=True, vehiculos_sin_referencia=0) == []


def test_si_no_paga_una_aseguradora_la_referencia_no_se_exige():
    assert completa(paga_aseguradora=False, vehiculos_sin_referencia=1) == []


def test_la_referencia_sale_despues_del_vehiculo_y_antes_del_regreso():
    assert completa(
        tipo=TipoServicio.EVENTO, paga_aseguradora=True, vehiculos_sin_referencia=2
    ) == [Faltante.REFERENCIA_EXTERNA, Faltante.RESPUESTA_REGRESO]


# --- Regreso -----------------------------------------------------------------------------------


def test_un_evento_con_regreso_crea_servicios_de_regreso():
    assert crea_regreso(TipoServicio.EVENTO, True) is True


@pytest.mark.parametrize("respuesta", [False, None])
def test_un_evento_sin_regreso_o_sin_respuesta_no_crea_regreso(respuesta):
    assert crea_regreso(TipoServicio.EVENTO, respuesta) is False


@pytest.mark.parametrize("tipo", [TipoServicio.TRASLADO, TipoServicio.DESVARE])
def test_fuera_de_eventos_nunca_se_crea_regreso(tipo):
    assert crea_regreso(tipo, True) is False


# --- No concretada -----------------------------------------------------------------------------


E = Estado


def cierre(**cambios):
    datos = {
        "ya_no_concretada": False,
        "estados": [E.PENDIENTE_ASIGNAR],
        "alguno_fue_asignado": False,
        "motivo": "precio",
    }
    datos.update(cambios)
    verificar_cierre_no_concretada(**datos)


def test_se_cierra_como_no_concretada_sin_servicios_asignados():
    cierre()
    cierre(estados=[])
    cierre(estados=[E.PENDIENTE_ASIGNAR, E.PENDIENTE_ASIGNAR])


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_cerrar_como_no_concretada_exige_motivo(motivo):
    with pytest.raises(CierreNoPermitido, match="motivo"):
        cierre(motivo=motivo)


@pytest.mark.parametrize(
    "estado", [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO, E.NOVEDAD]
)
def test_no_se_cierra_como_no_concretada_con_un_servicio_asignado_o_en_curso(estado):
    with pytest.raises(CierreNoPermitido, match="asignado"):
        cierre(estados=[E.PENDIENTE_ASIGNAR, estado])


def test_no_se_cierra_si_algun_servicio_estuvo_asignado_aunque_ya_no_lo_este():
    # Por ejemplo, se asignó y luego se canceló o volvió a la cola: la grúa ya se movió.
    with pytest.raises(CierreNoPermitido, match="asignado"):
        cierre(estados=[E.CANCELADO], alguno_fue_asignado=True)


def test_un_servicio_cancelado_que_nunca_se_asigno_no_impide_cerrar():
    cierre(estados=[E.CANCELADO, E.PENDIENTE_ASIGNAR])


def test_una_solicitud_ya_no_concretada_no_se_vuelve_a_cerrar():
    with pytest.raises(CierreNoPermitido, match="ya"):
        cierre(ya_no_concretada=True)
