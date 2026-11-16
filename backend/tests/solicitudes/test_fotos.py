"""Fotos de evidencia en el detalle de la solicitud (1a-08i) contra PostgreSQL y el disco: se ven
agrupadas por servicio, solo con sesión y rol, y se señala el toque de la app que no trajo foto."""
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.fotos import fotos_de
from solicitudes.models import EventoEstado, Evidencia

from ..conftest import crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado
CONTENIDO = b"\xff\xd8\xff contenido de la foto"


@pytest.fixture(autouse=True)
def media_temporal(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


def tocar(evento_app, servicio, destino, secuencia, **otros) -> EventoEstado:
    datos = evento_app(servicio, destino, secuencia=secuencia, **otros)
    operaciones.aplicar_evento_del_conductor(**datos)
    return EventoEstado.objects.get(pk=datos["id"])


def subir(evento, tipo) -> Evidencia:
    return Evidencia.objects.create(
        id=uuid.uuid4(),
        servicio=evento.servicio,
        evento=evento,
        evento_esperado=evento.pk,
        tipo=tipo,
        archivo=SimpleUploadedFile("x.jpg", CONTENIDO, content_type="image/jpeg"),
        subida_por=evento.conductor,
    )


@pytest.fixture
def entregado_con_fotos(crear_servicio, evento_app):
    """Ana lo recogió (con foto; le entregó Carlos) y lo entregó (con foto; recibió Marta)."""
    servicio = crear_servicio(E.EN_CAMINO)
    recogido = tocar(evento_app, servicio, E.RECOGIDO, 1, nombre_quien="Carlos Ruiz")
    entregado = tocar(evento_app, servicio, E.ENTREGADO, 2, nombre_quien="Marta Gil")
    return servicio, subir(recogido, "recogida"), subir(entregado, "entrega")


def url_foto(evidencia):
    return f"/solicitudes/{evidencia.servicio.solicitud_id}/fotos/{evidencia.pk}/"


def test_el_detalle_muestra_las_fotos_de_cada_servicio_con_quien_y_cuando(
    client, logistica, entregado_con_fotos
):
    servicio, recogida, entrega = entregado_con_fotos
    html = client.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()

    seccion = html[html.index('id="t-fotos"') :]
    assert f"N.º {servicio.pk} · {servicio.vehiculo}" in seccion
    assert seccion.index(url_foto(recogida)) < seccion.index(url_foto(entrega))
    assert "entregó Carlos Ruiz" in seccion  # al recoger, quien entrega el vehículo
    assert "recibió Marta Gil" in seccion  # al entregar, quien lo recibe
    assert str(servicio.conductor) in seccion
    assert "Sin foto de" not in seccion


def test_la_foto_se_ve_con_sesion_de_logistica(client, logistica, entregado_con_fotos):
    _, recogida, _ = entregado_con_fotos
    respuesta = client.get(url_foto(recogida))
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "image/jpeg"
    assert b"".join(respuesta.streaming_content) == CONTENIDO


def test_la_foto_no_tiene_url_publica(client, entregado_con_fotos):
    _, recogida, _ = entregado_con_fotos
    respuesta = client.get(url_foto(recogida))
    assert respuesta.status_code == 302
    assert "/ingresar/" in respuesta["Location"]


def test_facturacion_no_ve_las_fotos_porque_no_ve_el_detalle(
    client, crear_usuario, entregado_con_fotos
):
    _, recogida, _ = entregado_con_fotos
    client.force_login(crear_usuario("facturacion"))
    assert client.get(url_foto(recogida)).status_code == 403


def test_una_foto_no_se_ve_desde_otra_solicitud(client, logistica, cliente, entregado_con_fotos):
    _, recogida, _ = entregado_con_fotos
    otra = crear_solicitud(cliente)
    assert client.get(f"/solicitudes/{otra.pk}/fotos/{recogida.pk}/").status_code == 404


def test_si_el_archivo_no_esta_en_disco_responde_no_encontrada(
    client, logistica, entregado_con_fotos, media_temporal
):
    _, recogida, _ = entregado_con_fotos
    (media_temporal / recogida.archivo.name).unlink()
    assert client.get(url_foto(recogida)).status_code == 404


def test_un_entregado_de_la_app_sin_foto_queda_senalado(
    client, logistica, crear_servicio, evento_app
):
    servicio = crear_servicio(E.EN_CAMINO)
    subir(tocar(evento_app, servicio, E.RECOGIDO, 1), "recogida")
    tocar(evento_app, servicio, E.ENTREGADO, 2)

    [grupo] = fotos_de([servicio])
    assert [(f.tipo, f.evento.destino) for f in grupo.sin_foto] == [("entrega", E.ENTREGADO)]
    html = client.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()
    assert "Sin foto de entrega" in html
    assert "Sin foto de recogida" not in html


def test_un_cambio_hecho_desde_el_panel_no_pide_foto(crear_servicio, usuario):
    servicio = crear_servicio(E.RECOGIDO)
    operaciones.cambiar_estado(servicio, E.ENTREGADO, actor=usuario, nombre_quien="Marta Gil")
    [grupo] = fotos_de([servicio])
    assert grupo.sin_foto == []


def test_la_foto_que_llega_antes_que_su_evento_no_cuenta_como_faltante(
    crear_servicio, evento_app
):
    """La app sube la foto en su propia cola: puede llegar antes que el toque que acompaña."""
    servicio = crear_servicio(E.EN_CAMINO)
    datos = evento_app(servicio, E.RECOGIDO, secuencia=1)
    Evidencia.objects.create(
        id=uuid.uuid4(),
        servicio=servicio,
        evento_esperado=datos["id"],
        tipo="recogida",
        archivo=SimpleUploadedFile("x.jpg", CONTENIDO, content_type="image/jpeg"),
        subida_por=servicio.conductor,
    )
    [grupo] = fotos_de([servicio])
    assert grupo.sin_foto == []
    assert len(grupo.fotos) == 1
    assert grupo.fotos[0].evento is None  # su toque todavía no llega

    operaciones.aplicar_evento_del_conductor(**datos)
    [grupo] = fotos_de([servicio])
    assert grupo.sin_foto == []
    assert grupo.fotos[0].evento.pk == datos["id"]


def test_sin_fotos_el_detalle_lo_dice(client, logistica, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    html = client.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()
    assert "Todavía no hay fotos de esta solicitud." in html


def test_la_foto_nueva_se_guarda_en_la_carpeta_de_su_solicitud_y_servicio(
    entregado_con_fotos, media_temporal
):
    servicio, recogida, entrega = entregado_con_fotos
    solicitud = f"solicitud-{servicio.solicitud_id}"
    carpeta = media_temporal / "evidencias" / solicitud / f"servicio-{servicio.pk}"
    assert sorted(p.name for p in carpeta.iterdir()) == sorted(
        [f"recogida-{recogida.pk}.jpg", f"entrega-{entrega.pk}.jpg"]
    )


def test_la_foto_guardada_con_la_ruta_anterior_se_sigue_viendo(
    client, logistica, entregado_con_fotos, media_temporal
):
    """Las fotos de antes de 1a-08i quedaron en evidencias/<servicio>/<id>.jpg; no se mueven."""
    _, recogida, _ = entregado_con_fotos
    vieja = f"evidencias/{recogida.servicio_id}/{recogida.pk}.jpg"
    (media_temporal / vieja).parent.mkdir(parents=True)
    (media_temporal / recogida.archivo.name).rename(media_temporal / vieja)
    Evidencia.objects.filter(pk=recogida.pk).update(archivo=vieja)
    respuesta = client.get(url_foto(recogida))
    assert respuesta.status_code == 200
    assert b"".join(respuesta.streaming_content) == CONTENIDO


def test_el_detalle_no_hace_una_consulta_por_foto(
    client, logistica, entregado_con_fotos, django_assert_max_num_queries
):
    servicio, _, _ = entregado_con_fotos
    url = f"/solicitudes/{servicio.solicitud_id}/"
    client.get(url)
    with django_assert_max_num_queries(60) as antes:
        client.get(url)
    evento = EventoEstado.objects.filter(servicio=servicio).first()
    for _ in range(3):
        subir(evento, "soporte")
    with django_assert_max_num_queries(len(antes.captured_queries)):
        client.get(url)
