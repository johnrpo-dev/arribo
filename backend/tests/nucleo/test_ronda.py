import pytest

from nucleo.ronda import Direccion, MovimientoInvalido, mover, numerar, siguiente_orden


def test_el_primero_de_la_ronda_es_el_1():
    assert siguiente_orden([]) == 1


def test_un_servicio_nuevo_entra_al_final_de_la_ronda():
    assert siguiente_orden([1, 2, 3]) == 4


def test_los_huecos_no_se_rellenan_al_entrar_al_final():
    assert siguiente_orden([1, 4]) == 5


def test_los_servicios_sin_orden_no_cuentan():
    assert siguiente_orden([None, 2, None]) == 3


def test_subir_cambia_de_puesto_con_el_anterior():
    assert mover(["a", "b", "c"], "c", Direccion.SUBIR) == ["a", "c", "b"]


def test_bajar_cambia_de_puesto_con_el_siguiente():
    assert mover(["a", "b", "c"], "a", "bajar") == ["b", "a", "c"]


def test_el_primero_no_sube():
    with pytest.raises(MovimientoInvalido, match="primero"):
        mover(["a", "b"], "a", Direccion.SUBIR)


def test_el_ultimo_no_baja():
    with pytest.raises(MovimientoInvalido, match="último"):
        mover(["a", "b"], "b", Direccion.BAJAR)


def test_no_se_mueve_un_servicio_que_no_esta_en_la_ronda():
    with pytest.raises(MovimientoInvalido):
        mover(["a"], "z", Direccion.BAJAR)


def test_direccion_desconocida_falla():
    with pytest.raises(ValueError):
        mover(["a", "b"], "a", "lado")


def test_numerar_da_puestos_consecutivos_desde_1():
    assert numerar(["c", "a", "b"]) == {"c": 1, "a": 2, "b": 3}
