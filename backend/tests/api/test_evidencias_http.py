"""La subida de fotos por HTTP de verdad: el servidor de pruebas de Django escuchando en un puerto
y un cliente que manda el `multipart/form-data` por la red, como lo hará el celular.

Lo que el cliente de pruebas no ejerce: el cuerpo leído del socket por partes, y que una foto
demasiado grande reciba su 413 (y no una conexión cortada, que la app reintentaría sin fin).
"""
import hashlib
import http.client
import json
import uuid
from urllib.parse import urlparse

import pytest

from api.models import TokenDispositivo
from nucleo.estados import Estado
from nucleo.evidencia import TAMANO_MAXIMO_FOTO
from solicitudes.models import Evidencia

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("media_temporal")]


def jpeg_de(tamano: int) -> bytes:
    relleno = bytes(range(256)) * (tamano // 256 + 1)
    return (b"\xff\xd8\xff\xe0" + relleno)[:tamano]


def put_foto(servidor, clave, evidencia_id, servicio, contenido, evento_id=None):
    """PUT real por la red; devuelve (estado HTTP, cuerpo JSON)."""
    limite = "arribo" + uuid.uuid4().hex
    campos = {
        "servicio_id": servicio.pk,
        "evento_id": evento_id or uuid.uuid4(),
        "tipo": "recogida",
    }
    partes = [
        f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"\r\n\r\n{valor}\r\n'.encode()
        for nombre, valor in campos.items()
    ]
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="archivo"; filename="IMG_1.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n".encode() + contenido + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    url = urlparse(servidor.url)
    conexion = http.client.HTTPConnection(url.hostname, url.port, timeout=60)
    try:
        conexion.request(
            "PUT",
            f"/api/v1/evidencias/{evidencia_id}/",
            body=b"".join(partes),
            headers={
                "Authorization": f"Bearer {clave}",
                "Content-Type": f"multipart/form-data; boundary={limite}",
            },
        )
        respuesta = conexion.getresponse()
        return respuesta.status, json.loads(respuesta.read())
    finally:
        conexion.close()


@pytest.fixture
def clave(ana_app):
    return TokenDispositivo.emitir(ana_app, "celular-de-ana", "Moto G de Ana")[1]


def test_una_foto_de_varios_trozos_llega_entera_por_http_y_repetirla_no_la_duplica(
    live_server, clave, crear_servicio, media_temporal
):
    servicio = crear_servicio(Estado.EN_CAMINO)
    contenido = jpeg_de(700 * 1024)  # como una foto comprimida: más de diez trozos de 64 KB
    evidencia_id, evento_id = uuid.uuid4(), uuid.uuid4()

    primera = put_foto(live_server, clave, evidencia_id, servicio, contenido, evento_id)
    evidencia = Evidencia.objects.get(pk=evidencia_id)
    en_disco = (media_temporal / evidencia.archivo.name).read_bytes()
    segunda = put_foto(live_server, clave, evidencia_id, servicio, contenido, evento_id)
    distinta = put_foto(live_server, clave, evidencia_id, servicio, contenido[:-1], evento_id)

    assert primera[0] == 201 and primera[1]["resultado"] == "guardada"
    assert en_disco == contenido
    assert (evidencia.tamano, evidencia.sha256) == (
        len(contenido),
        hashlib.sha256(contenido).hexdigest(),
    )
    assert primera[1]["enlazada"] is False  # el evento que acompaña aún no llegó
    assert segunda[0] == 200 and segunda[1]["resultado"] == "repetida"
    assert distinta[0] == 409 and distinta[1]["error"] == "evidencia_distinta"
    assert Evidencia.objects.count() == 1
    assert [r.name for r in media_temporal.rglob("*.jpg")] == [f"{evidencia_id}.jpg"]


@pytest.mark.parametrize("sobra", [1, 1024 * 1024])
def test_una_foto_demasiado_grande_recibe_su_413_por_http_y_no_deja_nada_en_disco(
    live_server, clave, crear_servicio, media_temporal, sobra
):
    servicio = crear_servicio(Estado.EN_CAMINO)

    estado, cuerpo = put_foto(
        live_server, clave, uuid.uuid4(), servicio, jpeg_de(TAMANO_MAXIMO_FOTO + sobra)
    )

    assert (estado, cuerpo["error"], cuerpo["maximo_bytes"]) == (
        413,
        "foto_demasiado_grande",
        TAMANO_MAXIMO_FOTO,
    )
    assert not Evidencia.objects.exists()
    assert [r for r in media_temporal.rglob("*") if r.is_file()] == []
