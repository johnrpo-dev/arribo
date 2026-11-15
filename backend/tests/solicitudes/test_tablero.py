"""Tablero de inicio de logística y del administrador (1a-08c, adelanto mínimo de la 1a-18) contra
PostgreSQL: por asignar en orden, borradores con lo que les falta, alertas abiertas y lo que está
en curso por conductor."""
from datetime import timedelta

import pytest
from django.utils import timezone

from alertas.models import TipoAlerta
from alertas.operaciones import abrir_alerta, resolver_alerta
from nucleo.estados import Estado
from solicitudes import consultas, operaciones
from solicitudes.models import EstadoRegistro
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica", first_name="Lina")
    client.force_login(usuario)
    return usuario


@pytest.mark.parametrize("ruta", ["/", "/tablero/"])
def test_el_inicio_y_el_tablero_muestran_lo_que_requiere_accion(client, logistica, ruta):
    html = client.get(ruta).content.decode()
    assert 'href="/solicitudes/nueva/"' in html
    assert 'name="q"' in html  # la búsqueda
    for titulo in ("Por asignar", "Borradores", "Alertas sin resolver", "En curso por conductor"):
        assert titulo in html
    assert html.index("Por asignar") < html.index("Borradores") < html.index(
        "Alertas sin resolver"
    ) < html.index("En curso por conductor")


def test_el_administrador_tambien_ve_el_tablero_en_el_inicio(client, crear_usuario):
    client.force_login(crear_usuario("administrador"))
    assert "En curso por conductor" in client.get("/").content.decode()


def test_facturacion_no_ve_el_tablero(client, crear_usuario):
    client.force_login(crear_usuario("facturacion"))
    html = client.get("/").content.decode()
    assert "Por asignar" not in html
    assert client.get("/tablero/").status_code == 403


def test_por_asignar_inmediatos_primero_y_luego_programados_por_hora(
    cliente, crear_servicio, client, logistica
):
    ahora = timezone.now()
    programada_tarde = crear_solicitud(cliente, programada_para=ahora + timedelta(hours=6))
    programada_pronto = crear_solicitud(cliente, programada_para=ahora + timedelta(hours=1))
    inmediata_vieja = crear_solicitud(cliente)
    inmediata_nueva = crear_solicitud(cliente)
    orden = [inmediata_vieja, inmediata_nueva, programada_pronto, programada_tarde]
    for solicitud in reversed(orden):
        crear_servicio(solicitud_de=solicitud)
    borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    crear_servicio(solicitud_de=borrador)  # un borrador no se asigna: no sale aquí
    crear_servicio(Estado.ASIGNADO, solicitud_de=inmediata_vieja)  # ya asignado: tampoco

    assert [s.solicitud_id for s in consultas.por_asignar()] == [s.pk for s in orden]
    html = client.get("/").content.decode()
    for solicitud in orden:
        assert f'href="/solicitudes/{solicitud.pk}/#t-asignar"' in html


def test_los_borradores_dicen_que_les_falta(client, logistica, cliente, crear_servicio):
    incompleto = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR, destino="")
    crear_servicio(solicitud_de=incompleto)
    completo = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    crear_servicio(solicitud_de=completo)

    html = client.get("/").content.decode()

    assert "Falta el destino" in html
    assert "lista para abrir" in html
    assert f'href="/solicitudes/{incompleto.pk}/"' in html


def test_las_alertas_abiertas_salen_con_su_solicitud(
    client, logistica, solicitud, crear_servicio, ana
):
    evento = operaciones.asignar(crear_servicio(), ana, actor=logistica)
    abrir_alerta(TipoAlerta.CONFLICTO_SINCRONIZACION, evento, "El toque no encajó.")
    abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "Evento sin guardar de Ana.")
    resuelta = abrir_alerta(TipoAlerta.CAPACIDAD_EXCEDIDA, evento, "Ya resuelta.")
    resolver_alerta(resuelta, por=logistica)

    html = client.get("/").content.decode()

    assert "El toque no encajó." in html
    assert "Evento sin guardar de Ana." in html
    assert "Ya resuelta." not in html
    assert f'<a href="/solicitudes/{solicitud.pk}/">{solicitud.pk}</a>' in html


def test_en_curso_agrupado_por_conductor_sin_pendientes_ni_terminados(
    client, logistica, cliente, crear_servicio, beto, nuevo_vehiculo
):
    solicitud = crear_solicitud(cliente)
    crear_servicio(Estado.ASIGNADO, solicitud_de=solicitud, vehiculo=nuevo_vehiculo(placa="AAA111"))
    crear_servicio(Estado.NOVEDAD, solicitud_de=solicitud, vehiculo=nuevo_vehiculo(placa="BBB222"))
    crear_servicio(
        Estado.RECOGIDO, solicitud_de=solicitud, conductor=beto,
        vehiculo=nuevo_vehiculo(placa="CCC333"),
    )
    crear_servicio(Estado.ENTREGADO, solicitud_de=solicitud, vehiculo=nuevo_vehiculo(placa="DDD444"))

    rondas = consultas.en_curso()

    assert [(r.conductor.nombre, len(r.servicios)) for r in rondas] == [("Ana", 2), ("Beto", 1)]
    html = client.get("/").content.decode()
    seccion = html[html.index("En curso por conductor"):]
    for texto in ("Ana", "Beto", "AAA111", "BBB222", "CCC333", "Novedad", "Recogido"):
        assert texto in seccion, texto
    assert "DDD444" not in seccion


def test_el_tablero_no_hace_una_consulta_por_fila(
    client, logistica, cliente, crear_servicio, beto, django_assert_max_num_queries
):
    for numero in range(8):
        abierta = crear_solicitud(cliente)
        crear_servicio(solicitud_de=abierta)
        crear_servicio(Estado.EN_CAMINO, solicitud_de=abierta, conductor=beto)
        borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR, origen="")
        crear_servicio(solicitud_de=borrador)
    with django_assert_max_num_queries(14):
        client.get("/")
