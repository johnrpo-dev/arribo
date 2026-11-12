import pytest

from nucleo.capacidad import CapacidadExcedida, verificar_recogida


def test_grua_vacia_puede_recoger():
    verificar_recogida(1, [])


def test_grua_de_un_puesto_llena_bloquea_y_dice_que_falta_entregar():
    with pytest.raises(CapacidadExcedida) as error:
        verificar_recogida(1, ["servicio-7"])
    assert error.value.pendientes_de_entregar == ["servicio-7"]


def test_grua_de_dos_puestos_admite_el_segundo_pero_no_el_tercero():
    verificar_recogida(2, ["a"])
    with pytest.raises(CapacidadExcedida):
        verificar_recogida(2, ["a", "b"])


def test_capacidad_invalida():
    with pytest.raises(ValueError):
        verificar_recogida(0, [])
