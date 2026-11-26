import pytest

from nucleo.capacidad import (
    CapacidadExcedida,
    InicioExcedido,
    verificar_inicio,
    verificar_recogida,
)


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


# ---------- servicios iniciados sin finalizar (al marcar En camino) ----------


def test_sin_servicios_iniciados_puede_tomar_el_siguiente():
    verificar_inicio(1, [])


def test_grua_de_un_puesto_con_un_servicio_iniciado_bloquea_y_dice_cual_terminar():
    with pytest.raises(InicioExcedido) as error:
        verificar_inicio(1, ["ABC123 (En camino)"])
    assert error.value.capacidad == 1
    assert error.value.sin_finalizar == ["ABC123 (En camino)"]
    assert str(error.value) == (
        "Tiene un servicio iniciado y no se ha finalizado: ABC123 (En camino). Debe terminarlo "
        "para tomar el siguiente."
    )


def test_grua_de_dos_puestos_admite_dos_iniciados_pero_no_un_tercero():
    verificar_inicio(2, ["ABC123 (Recogido)"])
    with pytest.raises(InicioExcedido) as error:
        verificar_inicio(2, ["ABC123 (Recogido)", "bodega 7 (En camino)"])
    assert error.value.sin_finalizar == ["ABC123 (Recogido)", "bodega 7 (En camino)"]
    assert str(error.value) == (
        "La grúa tiene 2 puestos y ya tiene 2 servicios iniciados sin finalizar: "
        "ABC123 (Recogido), bodega 7 (En camino). Termine uno para tomar el siguiente."
    )


def test_con_mas_iniciados_que_puestos_dice_cuantos_terminar():
    with pytest.raises(InicioExcedido) as error:
        verificar_inicio(1, ["A (En camino)", "B (Recogido)"])
    assert str(error.value) == (
        "La grúa tiene 1 puesto y ya tiene 2 servicios iniciados sin finalizar: A (En camino), "
        "B (Recogido). Termine 2 para tomar el siguiente."
    )


def test_capacidad_invalida_al_iniciar():
    with pytest.raises(ValueError):
        verificar_inicio(0, [])
