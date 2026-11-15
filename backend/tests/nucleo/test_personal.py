"""Reglas puras del personal: usuario interno del conductor y el último administrador."""
import pytest

from nucleo.personal import (
    DesactivarseASiMismo,
    UltimoAdministrador,
    nombre_de_usuario_de_conductor,
    validar_no_se_desactiva_a_si_mismo,
    validar_quedan_administradores,
)


def test_el_usuario_del_conductor_se_deriva_del_celular():
    assert nombre_de_usuario_de_conductor("3001234567", []) == "conductor-3001234567"


def test_si_el_usuario_ya_existe_se_le_agrega_un_numero():
    ocupados = ["conductor-3001234567", "conductor-3001234567-2"]
    assert nombre_de_usuario_de_conductor("3001234567", ocupados) == "conductor-3001234567-3"


def test_el_usuario_del_conductor_no_choca_aunque_cambien_las_mayusculas():
    assert nombre_de_usuario_de_conductor("3001234567", ["CONDUCTOR-3001234567"]) == (
        "conductor-3001234567-2"
    )


def test_no_se_puede_quedar_sin_administradores():
    with pytest.raises(UltimoAdministrador, match="único administrador"):
        validar_quedan_administradores(0)


def test_con_un_administrador_que_queda_se_permite():
    validar_quedan_administradores(1)


def test_nadie_se_desactiva_a_si_mismo():
    with pytest.raises(DesactivarseASiMismo):
        validar_no_se_desactiva_a_si_mismo(True)
    validar_no_se_desactiva_a_si_mismo(False)
