import pytest

from nucleo.estados import Estado
from nucleo.evidencia import (
    TAMANO_MAXIMO_FOTO,
    TIPOS_DESDE_LA_APP,
    Foto,
    acompana,
    es_jpeg,
    excede_el_tamano,
    misma_foto,
    se_enlaza,
)

SHA = "a" * 64


def foto(**cambios) -> Foto:
    datos = {
        "servicio_id": "41",
        "conductor_id": "3",
        "evento_id": "0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e",
        "tipo": "recogida",
        "sha256": SHA,
    }
    datos.update(cambios)
    return Foto(**datos)


# --- Tipo y tamaño ------------------------------------------------------------------------------


def test_un_jpeg_empieza_por_su_marca():
    assert es_jpeg(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    assert es_jpeg(b"\xff\xd8\xff\xe1")  # con Exif, como las de la cámara


@pytest.mark.parametrize(
    "cabecera",
    [
        b"",
        b"\xff\xd8",  # cortado antes de la marca completa
        b"\x89PNG\r\n\x1a\n",
        b"%PDF-1.7",
        b"GIF89a",
        b"<?php",
    ],
)
def test_lo_que_no_empieza_como_un_jpeg_no_es_una_foto(cabecera):
    assert not es_jpeg(cabecera)


def test_el_tamano_maximo_de_una_foto_es_5_mb():
    assert TAMANO_MAXIMO_FOTO == 5 * 1024 * 1024
    assert not excede_el_tamano(TAMANO_MAXIMO_FOTO)
    assert excede_el_tamano(TAMANO_MAXIMO_FOTO + 1)


# --- A qué evento acompaña ----------------------------------------------------------------------


def test_desde_la_app_solo_llegan_fotos_de_recogida_y_de_entrega():
    assert TIPOS_DESDE_LA_APP == {"recogida", "entrega"}


@pytest.mark.parametrize(
    ("tipo", "destino", "esperado"),
    [
        ("recogida", Estado.RECOGIDO, True),
        ("entrega", Estado.ENTREGADO, True),
        ("recogida", Estado.ENTREGADO, False),
        ("entrega", Estado.RECOGIDO, False),
        ("recogida", Estado.EN_CAMINO, False),
        ("entrega", Estado.NOVEDAD, False),
        ("soporte", Estado.RECOGIDO, False),
    ],
)
def test_la_foto_de_recogida_acompana_al_recogido_y_la_de_entrega_al_entregado(
    tipo, destino, esperado
):
    assert acompana(tipo, destino) is esperado


def test_la_foto_se_enlaza_al_evento_de_su_servicio_su_conductor_y_su_tipo():
    assert se_enlaza(
        foto(), servicio_del_evento="41", conductor_del_evento="3", destino=Estado.RECOGIDO
    )


@pytest.mark.parametrize(
    ("servicio", "conductor", "destino"),
    [
        ("42", "3", Estado.RECOGIDO),  # el evento es de otro servicio
        ("41", "4", Estado.RECOGIDO),  # el evento lo tocó otro conductor
        ("41", None, Estado.RECOGIDO),  # evento del panel, sin conductor
        ("41", "3", Estado.ENTREGADO),  # la foto dice recogida y el evento es de entrega
    ],
)
def test_la_foto_no_se_enlaza_a_un_evento_que_no_le_corresponde(servicio, conductor, destino):
    assert not se_enlaza(
        foto(), servicio_del_evento=servicio, conductor_del_evento=conductor, destino=destino
    )


# --- Mismo id, ¿misma foto? ---------------------------------------------------------------------


def test_la_misma_foto_reenviada_es_la_misma():
    assert misma_foto(foto(), foto())


@pytest.mark.parametrize(
    "cambio",
    [
        {"sha256": "b" * 64},
        {"servicio_id": "42"},
        {"evento_id": "5d1e0c2a-3f7e-4b4e-9d55-0b7f1e2c9a10"},
        {"tipo": "entrega"},
        {"conductor_id": "4"},
    ],
)
def test_el_mismo_id_con_otro_contenido_o_otros_datos_no_es_la_misma_foto(cambio):
    assert not misma_foto(foto(), foto(**cambio))


def test_una_foto_guardada_sin_huella_nunca_es_igual_a_una_que_llega():
    # Evidencias anteriores a la subida por la API no tienen sha256: no se pueden comparar.
    assert not misma_foto(foto(sha256=""), foto(sha256=""))
