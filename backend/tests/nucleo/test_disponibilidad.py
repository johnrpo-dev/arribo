import pytest

from nucleo.disponibilidad import Carga, DatosConductor, carga, motivos_de_bloqueo
from nucleo.estados import Estado, Servicio

E = Estado


def test_conductor_activo_con_grua_operativa_esta_disponible():
    assert motivos_de_bloqueo(DatosConductor(activo=True, grua_placa="GRU001")) == []


def test_sin_grua_vigente_bloquea():
    assert motivos_de_bloqueo(DatosConductor(activo=True, grua_placa=None)) == [
        "No tiene una grúa asignada en este momento."
    ]


def test_grua_fuera_de_servicio_bloquea_y_nombra_la_grua():
    datos = DatosConductor(activo=True, grua_placa="GRU001", grua_operativa=False)
    assert motivos_de_bloqueo(datos) == ["La grúa GRU001 está fuera de servicio."]


def test_grua_inactiva_bloquea():
    datos = DatosConductor(activo=True, grua_placa="GRU001", grua_activa=False)
    assert motivos_de_bloqueo(datos) == ["La grúa GRU001 está inactiva."]


def test_conductor_inactivo_bloquea():
    datos = DatosConductor(activo=False, grua_placa="GRU001")
    assert motivos_de_bloqueo(datos) == ["El conductor está inactivo."]


def test_documento_vencido_bloquea_asignaciones_nuevas():
    datos = DatosConductor(activo=True, grua_placa="GRU001", documentos_vencidos=("SOAT",))
    assert motivos_de_bloqueo(datos) == ["Documento vencido: SOAT."]


def test_se_dicen_todos_los_motivos_a_la_vez():
    datos = DatosConductor(
        activo=False, grua_placa="GRU001", grua_operativa=False, grua_activa=False
    )
    assert len(motivos_de_bloqueo(datos)) == 3


def test_la_carga_cuenta_no_terminales_y_montados():
    servicios = [
        Servicio(E.ASIGNADO),
        Servicio(E.EN_CAMINO),
        Servicio(E.RECOGIDO),
        Servicio(E.NOVEDAD, estado_previo=E.RECOGIDO),
        Servicio(E.NOVEDAD, estado_previo=E.EN_CAMINO),
        Servicio(E.ENTREGADO),
        Servicio(E.CANCELADO),
    ]
    assert carga(servicios) == Carga(no_terminales=5, montados=2)


@pytest.mark.parametrize("estado", [E.ENTREGADO, E.CANCELADO])
def test_los_terminales_no_cuentan_en_la_carga(estado):
    assert carga([Servicio(estado)]) == Carga(0, 0)


def test_sin_servicios_la_carga_es_cero():
    assert carga([]) == Carga(0, 0)
