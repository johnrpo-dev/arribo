"""Visto por el conductor (1a-14): un servicio queda visto la primera vez que la app del conductor lo
baja (lista o detalle, también con 304) y vuelve a "sin ver" al cambiar de conductor o volver a la
cola. Logística lo ve en el detalle de la solicitud. Contra PostgreSQL."""
import pytest
from django.db import IntegrityError, transaction

from nucleo.estados import Estado, Resolucion
from solicitudes import operaciones
from solicitudes.models import Servicio

from ..conftest import BOGOTA
from .conftest import URL_ASIGNACIONES, cliente_con

pytestmark = pytest.mark.django_db

E = Estado


def url_detalle(servicio):
    return f"{URL_ASIGNACIONES}{servicio.pk}/"


def visto(servicio):
    return Servicio.objects.get(pk=servicio.pk).visto_por_conductor_en


@pytest.fixture
def asignado(crear_servicio, ana_app, usuario):
    """Un servicio que logística le acaba de asignar a Ana desde el panel (todavía sin ver)."""
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana_app, actor=usuario)
    return servicio


@pytest.fixture
def sesion_beto(beto_app):
    from api.models import TokenDispositivo

    _, clave = TokenDispositivo.emitir(beto_app, "celular-de-beto")
    return cliente_con(clave)


def test_un_servicio_recien_asignado_esta_sin_ver(asignado):
    assert visto(asignado) is None


def test_bajar_la_lista_marca_vistos_sus_servicios_y_no_cambia_la_hora_despues(
    sesion, asignado, reloj
):
    primera = reloj.ahora

    assert sesion.get(URL_ASIGNACIONES).status_code == 200
    assert visto(asignado) == primera

    reloj.avanzar(minutes=10)
    sesion.get(URL_ASIGNACIONES)
    assert visto(asignado) == primera  # la hora es la de la primera vez


def test_la_lista_no_le_muestra_al_conductor_la_hora_de_visto(sesion, asignado):
    sesion.get(URL_ASIGNACIONES)

    (servicio,) = sesion.get(URL_ASIGNACIONES).json()["servicios"]
    assert not any("visto" in clave for clave in servicio)


def test_abrir_el_detalle_marca_visto_el_servicio(sesion, asignado, reloj):
    assert sesion.get(url_detalle(asignado)).status_code == 200

    assert visto(asignado) == reloj.ahora


def test_un_304_tambien_cuenta_como_visto(sesion, asignado, reloj):
    """La app ya tenía la lista (por ejemplo, la bajó antes de la 1a-14): aunque el servidor
    responda 304 sin cuerpo, el conductor la tiene en pantalla."""
    etag = sesion.get(URL_ASIGNACIONES)["ETag"]
    Servicio.objects.filter(pk=asignado.pk).update(visto_por_conductor_en=None)
    reloj.avanzar(minutes=3)

    respuesta = sesion.get(URL_ASIGNACIONES, HTTP_IF_NONE_MATCH=etag)

    assert respuesta.status_code == 304
    assert visto(asignado) == reloj.ahora


def test_el_visto_no_cambia_el_etag_de_la_lista(sesion, asignado):
    primera = sesion.get(URL_ASIGNACIONES)["ETag"]

    assert sesion.get(URL_ASIGNACIONES, HTTP_IF_NONE_MATCH=primera).status_code == 304


def test_otro_conductor_no_marca_visto_un_servicio_ajeno(sesion_beto, asignado):
    assert sesion_beto.get(URL_ASIGNACIONES).json()["servicios"] == []
    assert sesion_beto.get(url_detalle(asignado)).status_code == 404

    assert visto(asignado) is None


def test_un_servicio_terminado_no_se_marca(sesion, crear_servicio, ana_app):
    entregado = crear_servicio(E.ENTREGADO, conductor=ana_app)

    sesion.get(URL_ASIGNACIONES)
    assert operaciones.marcar_vistos(ana_app, [entregado.pk]) == 0

    assert visto(entregado) is None


def test_reasignar_deja_el_servicio_sin_ver_para_el_nuevo_conductor(
    sesion, sesion_beto, asignado, beto, usuario, reloj
):
    sesion.get(URL_ASIGNACIONES)
    assert visto(asignado) is not None

    operaciones.reasignar(asignado, beto, actor=usuario, motivo="Ana pinchó")
    assert visto(asignado) is None

    reloj.avanzar(minutes=2)
    sesion_beto.get(URL_ASIGNACIONES)
    assert visto(asignado) == reloj.ahora


def test_volver_a_la_cola_deja_el_servicio_sin_ver(sesion, crear_servicio, ana_app, usuario):
    servicio = crear_servicio(E.ASIGNADO, conductor=ana_app)
    sesion.get(URL_ASIGNACIONES)
    operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo="Llanta pinchada")
    assert visto(servicio) is not None  # la novedad no cambia de conductor

    operaciones.resolver_novedad(servicio, Resolucion.REASIGNAR, actor=usuario)

    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor, servicio.visto_por_conductor_en) == (
        E.PENDIENTE_ASIGNAR,
        None,
        None,
    )


def test_la_base_no_acepta_visto_sin_conductor(crear_servicio):
    pendiente = crear_servicio()

    with pytest.raises(IntegrityError), transaction.atomic():
        Servicio.objects.filter(pk=pendiente.pk).update(
            visto_por_conductor_en="2026-11-15T10:00:00Z"
        )


# --- Lo que ve logística en el detalle de la solicitud ---------------------------------------------


@pytest.fixture
def panel(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    return client


def fila_del_servicio(panel, servicio):
    html = panel.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()
    inicio = html.index(f'<td class="cifra">{servicio.pk}</td>')
    return html[inicio : html.index("</tr>", inicio)]


def test_el_detalle_muestra_sin_ver_mientras_la_app_no_lo_baje(panel, asignado):
    assert "Sin ver" in fila_del_servicio(panel, asignado)


def test_el_detalle_muestra_la_hora_en_que_el_conductor_lo_vio(panel, sesion, asignado, reloj):
    sesion.get(URL_ASIGNACIONES)

    fila = fila_del_servicio(panel, asignado)

    assert "Sin ver" not in fila
    assert reloj.ahora.astimezone(BOGOTA).strftime("%d/%m/%Y %H:%M") in fila


def test_el_detalle_no_muestra_visto_en_un_servicio_sin_conductor(panel, crear_servicio):
    pendiente = crear_servicio()

    fila = fila_del_servicio(panel, pendiente)

    assert "Sin ver" not in fila
    assert "—" in fila
