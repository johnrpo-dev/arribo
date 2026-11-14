from datetime import date, timedelta

import pytest

from nucleo.documentos import (
    DIAS_ANTICIPACION_POR_DEFECTO,
    TAMANO_MAXIMO_ARCHIVO,
    Documento,
    EstadoDocumento,
    bloquea,
    estado_documento,
    excede_el_tamano,
    requiere_aviso,
    tipo_de_archivo,
    vencidos,
)

HOY = date(2026, 11, 13)


def vence_en(dias: int) -> Documento:
    return Documento(vence=HOY + timedelta(days=dias))


def test_la_anticipacion_por_defecto_es_30_dias():
    assert DIAS_ANTICIPACION_POR_DEFECTO == 30


def test_documento_que_vence_hoy_sigue_sirviendo_todo_el_dia():
    assert estado_documento(vence_en(0), HOY, 30) == EstadoDocumento.POR_VENCER


def test_documento_que_vencio_ayer_esta_vencido():
    assert estado_documento(vence_en(-1), HOY, 30) == EstadoDocumento.VENCIDO


def test_por_vencer_desde_los_dias_de_anticipacion_inclusive():
    assert estado_documento(vence_en(30), HOY, 30) == EstadoDocumento.POR_VENCER
    assert estado_documento(vence_en(31), HOY, 30) == EstadoDocumento.VIGENTE


def test_dias_de_anticipacion_por_tipo_cambian_el_estado():
    documento = vence_en(10)
    assert estado_documento(documento, HOY, 15) == EstadoDocumento.POR_VENCER
    assert estado_documento(documento, HOY, 5) == EstadoDocumento.VIGENTE


def test_con_cero_dias_de_anticipacion_solo_avisa_el_ultimo_dia():
    assert estado_documento(vence_en(0), HOY, 0) == EstadoDocumento.POR_VENCER
    assert estado_documento(vence_en(1), HOY, 0) == EstadoDocumento.VIGENTE


def test_sin_documento_falta():
    assert estado_documento(None, HOY, 30) == EstadoDocumento.FALTA


def test_aun_no_aplica_antes_de_la_fecha_desde_la_que_aplica():
    documento = Documento(aplica_desde=HOY + timedelta(days=1))
    assert estado_documento(documento, HOY, 30) == EstadoDocumento.AUN_NO_APLICA


def test_aun_no_aplica_cuenta_como_vencido_desde_el_dia_en_que_aplica():
    documento = Documento(aplica_desde=HOY)
    assert estado_documento(documento, HOY, 30) == EstadoDocumento.VENCIDO


def test_documento_lleva_vencimiento_o_fecha_desde_la_que_aplica_no_ambas():
    with pytest.raises(ValueError):
        Documento()
    with pytest.raises(ValueError):
        Documento(vence=HOY, aplica_desde=HOY)


def test_dias_de_anticipacion_negativos_no_se_aceptan():
    with pytest.raises(ValueError):
        estado_documento(vence_en(5), HOY, -1)


def test_solo_vencido_bloquea():
    assert bloquea(EstadoDocumento.VENCIDO)
    for estado in (
        EstadoDocumento.VIGENTE,
        EstadoDocumento.POR_VENCER,
        EstadoDocumento.AUN_NO_APLICA,
        EstadoDocumento.FALTA,
    ):
        assert not bloquea(estado)


def test_vencidos_devuelve_solo_los_nombres_que_bloquean():
    estados = {
        "SOAT": EstadoDocumento.VENCIDO,
        "Tecnomecánica": EstadoDocumento.FALTA,
        "Licencia": EstadoDocumento.POR_VENCER,
    }
    assert vencidos(estados) == ("SOAT",)


def test_requiere_aviso_por_vencer_y_no_vencido_ni_falta():
    assert requiere_aviso(vence_en(30), HOY, 30)
    assert not requiere_aviso(vence_en(31), HOY, 30)
    assert not requiere_aviso(vence_en(-1), HOY, 30)
    assert not requiere_aviso(None, HOY, 30)


def test_requiere_aviso_aun_no_aplica_que_empieza_dentro_de_la_anticipacion():
    # Aplica desde dentro de 31 días: su último día sin exigirse es dentro de 30.
    assert requiere_aviso(Documento(aplica_desde=HOY + timedelta(days=31)), HOY, 30)
    assert not requiere_aviso(Documento(aplica_desde=HOY + timedelta(days=32)), HOY, 30)


def test_tipo_de_archivo_se_mira_por_el_contenido():
    assert tipo_de_archivo(b"\xff\xd8\xff\xe0resto") == "jpeg"
    assert tipo_de_archivo(b"\x89PNG\r\n\x1a\nresto") == "png"
    assert tipo_de_archivo(b"%PDF-1.7 resto") == "pdf"
    assert tipo_de_archivo(b"GIF89a") is None
    assert tipo_de_archivo(b"") is None


def test_archivo_que_pasa_del_tamano_maximo_se_rechaza():
    assert not excede_el_tamano(TAMANO_MAXIMO_ARCHIVO)
    assert excede_el_tamano(TAMANO_MAXIMO_ARCHIVO + 1)
