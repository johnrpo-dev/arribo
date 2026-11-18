"""Lista de solicitudes (1a-08c) contra PostgreSQL: filtros por estado derivado, búsqueda, páginas
y una cota de consultas."""
import itertools
from datetime import UTC, date, datetime, timedelta

import pytest
from django.utils import timezone

from clientes.models import Cliente, TelefonoCliente, TipoCliente
from nucleo.estados import Estado
from solicitudes import consultas
from solicitudes.models import EstadoRegistro, Solicitud
from tests.conftest import VIN, crear_solicitud

pytestmark = pytest.mark.django_db

RUTA = "/solicitudes/"


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


def ids(filtro, texto=""):
    return {s.pk for s in consultas.lista(filtro, texto)}


# --- Estado derivado -----------------------------------------------------------------------------


def test_el_filtro_coincide_con_el_estado_del_nucleo_en_todas_las_combinaciones(
    cliente, crear_servicio
):
    """Activas = abierta o en curso; Terminadas = completada o cancelada, según
    `nucleo.estados.estado_solicitud`, para cero, uno o dos servicios en cualquier estado."""
    combinaciones = [()]
    combinaciones += [(e,) for e in Estado]
    combinaciones += list(itertools.combinations_with_replacement(list(Estado), 2))
    for estados in combinaciones:
        solicitud = crear_solicitud(cliente)
        for estado in estados:
            crear_servicio(estado, solicitud_de=solicitud)

    activas, terminadas = ids("activas"), ids("terminadas")
    for solicitud in Solicitud.objects.all():
        estado = solicitud.estado  # deriva con nucleo.estados.estado_solicitud
        if estado in ("abierta", "en_curso"):
            assert solicitud.pk in activas and solicitud.pk not in terminadas, estado
        else:
            assert estado in ("completada", "cancelada")
            assert solicitud.pk in terminadas and solicitud.pk not in activas, estado
    assert len(activas) + len(terminadas) == Solicitud.objects.count()


def test_borrador_es_activa_y_no_concretada_es_terminada(cliente, crear_servicio, solicitud):
    """`solicitud` es la abierta sin servicios que trae `crear_servicio`."""
    borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    cerrada = crear_solicitud(
        cliente, estado_registro=EstadoRegistro.NO_CONCRETADA, motivo_no_concretada="precio"
    )
    crear_servicio(solicitud_de=cerrada)  # pendiente, pero la solicitud no se concretó
    assert ids("activas") == {borrador.pk, solicitud.pk}
    assert ids("borradores") == {borrador.pk}
    assert ids("terminadas") == {cerrada.pk}
    assert ids("por_asignar") == set()
    assert ids("todas") == {borrador.pk, cerrada.pk, solicitud.pk}


def test_por_asignar_son_las_abiertas_con_algun_servicio_pendiente(cliente, crear_servicio):
    con_pendiente = crear_solicitud(cliente)
    crear_servicio(solicitud_de=con_pendiente)
    crear_servicio(Estado.ASIGNADO, solicitud_de=con_pendiente)
    toda_asignada = crear_solicitud(cliente)
    crear_servicio(Estado.ASIGNADO, solicitud_de=toda_asignada)
    borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    crear_servicio(solicitud_de=borrador)
    assert ids("por_asignar") == {con_pendiente.pk}


def test_programadas_son_las_activas_con_hora_en_orden_de_hora(cliente, crear_servicio):
    ahora = timezone.now()
    tarde = crear_solicitud(cliente, programada_para=ahora + timedelta(hours=5))
    temprano = crear_solicitud(cliente, programada_para=ahora + timedelta(hours=1))
    crear_solicitud(cliente)  # inmediata
    entregada = crear_solicitud(cliente, programada_para=ahora + timedelta(hours=2))
    crear_servicio(Estado.ENTREGADO, solicitud_de=entregada)
    assert [s.pk for s in consultas.lista("programadas")] == [temprano.pk, tarde.pk]


def test_un_filtro_desconocido_muestra_activas(client, logistica, cliente):
    crear_solicitud(cliente)
    html = client.get(RUTA, {"filtro": "inventado"}).content.decode()
    assert 'aria-current="page">Activas</a>' in html


# --- Búsqueda ------------------------------------------------------------------------------------


@pytest.fixture
def para_buscar(cliente, crear_servicio, nuevo_vehiculo):
    """Una solicitud con teléfono, placa, VIN y referencia conocidos, y otra que no coincide (además
    de la que trae `crear_servicio`, sin vehículos ni teléfono)."""
    aseguradora = Cliente.objects.create(nombre="Seguros Andinos", tipo=TipoCliente.ASEGURADORA)
    quien_llama = Cliente.objects.create(nombre="Transportes Cumbre", tipo=TipoCliente.PARTICULAR)
    TelefonoCliente.objects.create(cliente=quien_llama, numero="3001234567")
    buscada = crear_solicitud(quien_llama, pagador=aseguradora)
    servicio = crear_servicio(
        solicitud_de=buscada, vehiculo=nuevo_vehiculo(placa="KLM456", vin=VIN)
    )
    servicio.referencia_externa = "SIN-2026-0099"
    servicio.save(update_fields=["referencia_externa"])
    otro = Cliente.objects.create(nombre="Pedro Pérez", tipo=TipoCliente.PARTICULAR)
    otra = crear_solicitud(otro)
    crear_servicio(solicitud_de=otra, vehiculo=nuevo_vehiculo(placa="ZZZ999"))
    return buscada, otra


@pytest.mark.parametrize(
    "texto",
    [
        "300 123 4567",  # teléfono completo con espacios
        "+57 3001234567",  # con el indicativo
        "1234567",  # parte del teléfono
        "transportes cum",  # nombre del solicitante, sin importar mayúsculas
        "andinos",  # nombre del pagador
        "klm-456",  # placa como se digita
        "klm",  # parte de la placa
        "1hg-cm826 33a004352",  # VIN como se digita
        "sin-2026",  # referencia externa
    ],
)
def test_buscar_por_cliente_vehiculo_o_referencia(para_buscar, texto):
    buscada, _ = para_buscar
    assert ids("todas", texto) == {buscada.pk}


def test_buscar_por_numero_de_solicitud(para_buscar):
    _, otra = para_buscar
    assert otra.pk in ids("todas", str(otra.pk))
    assert otra.pk in ids("todas", f"#{otra.pk}")


def test_la_busqueda_respeta_el_filtro(para_buscar):
    buscada, _ = para_buscar
    assert ids("borradores", "klm") == set()
    assert ids("activas", "klm") == {buscada.pk}


@pytest.fixture
def atendida(cliente, crear_servicio, beto):
    """Una solicitud atendida por Beto (grúa GRU002) con su línea facturada FE-7788, y otra
    atendida por Ana (GRU001) sin factura."""
    from cobros.models import LineaCobro

    de_beto = crear_solicitud(cliente)
    servicio = crear_servicio(Estado.ENTREGADO, solicitud_de=de_beto, conductor=beto)
    LineaCobro.objects.create(
        servicio=servicio, pagador=cliente, posicion=1, valor=1000, estado="facturado",
        numero_factura="FE-7788",
    )
    de_ana = crear_solicitud(cliente)
    crear_servicio(Estado.ASIGNADO, solicitud_de=de_ana)
    return de_beto, de_ana


@pytest.mark.parametrize("texto", ["beto", "gru002", "GRU-002", "fe-7788"])
def test_buscar_por_conductor_grua_o_factura(atendida, texto):
    de_beto, _ = atendida
    assert ids("todas", texto) == {de_beto.pk}


def test_buscar_por_factura_es_el_numero_exacto(atendida):
    assert ids("todas", "FE-77") == set()


def test_buscar_por_fecha_registrada_o_programada_en_hora_de_colombia(cliente):
    # 19/11 a las 2:00 UTC son las 21:00 del 18/11 en Medellín.
    registrada = crear_solicitud(cliente)
    Solicitud.objects.filter(pk=registrada.pk).update(
        creada_en=datetime(2026, 11, 19, 2, 0, tzinfo=UTC)
    )
    programada = crear_solicitud(
        cliente, programada_para=datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
    )
    for texto in ("18/11/2026", "18-11-2026", "2026-11-18"):
        assert ids("todas", texto) == {registrada.pk, programada.pk}, texto
    assert registrada.pk not in ids("todas", "19/11/2026")


@pytest.mark.parametrize(
    ("texto", "fecha"),
    [("18/11/2026", (2026, 11, 18)), ("5/1", (2026, 1, 5)), ("2026-02-03", (2026, 2, 3)),
     ("31/02/2026", None), ("abc", None), ("123", None)],
)
def test_leer_fecha(texto, fecha):
    esperado = date(*fecha) if fecha else None
    assert consultas.leer_fecha(texto, date(2026, 11, 18)) == esperado


def test_la_busqueda_del_tablero_sin_filtro_busca_en_todas(client, logistica, para_buscar):
    buscada, _ = para_buscar
    cerrada = crear_solicitud(
        buscada.solicitante,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
        motivo_no_concretada="precio",
    )
    html = client.get(RUTA, {"q": "transportes cumbre"}).content.decode()
    assert f'href="/solicitudes/{cerrada.pk}/"' in html
    assert f'href="/solicitudes/{buscada.pk}/"' in html
    assert 'aria-current="page">Todas</a>' in html


# --- Pantalla ------------------------------------------------------------------------------------


def test_la_fila_muestra_cliente_vehiculo_conductor_estado_y_enlace(
    client, logistica, cliente, crear_servicio, nuevo_vehiculo, ana
):
    solicitud = crear_solicitud(cliente, programada_para=timezone.now() + timedelta(days=1))
    crear_servicio(Estado.EN_CAMINO, solicitud_de=solicitud, vehiculo=nuevo_vehiculo(placa="QWE321"))
    crear_servicio(solicitud_de=solicitud, vehiculo=nuevo_vehiculo(vin=VIN))
    html = client.get(RUTA).content.decode()
    assert f'href="/solicitudes/{solicitud.pk}/"' in html
    for texto in ("Autos del Valle", "Traslado", "QWE321", VIN, "Ana", "En curso", "Programada"):
        assert texto in html, texto


def test_la_lista_es_paginada(client, logistica, cliente):
    for _ in range(consultas.POR_PAGINA + 3):
        crear_solicitud(cliente)
    primera = client.get(RUTA).content.decode()
    assert "Página 1 de 2" in primera
    assert "pagina=2" in primera
    segunda = client.get(RUTA, {"pagina": 2}).content.decode()
    assert segunda.count('aria-label="Abrir la solicitud') == 3


def test_la_lista_no_hace_una_consulta_por_solicitud(
    client, logistica, cliente, crear_servicio, beto, django_assert_max_num_queries
):
    for _ in range(12):
        solicitud = crear_solicitud(cliente)
        crear_servicio(Estado.ASIGNADO, solicitud_de=solicitud)
        crear_servicio(Estado.RECOGIDO, solicitud_de=solicitud, conductor=beto)
    # Sesión, usuario y grupos; conteo de la página; solicitudes; servicios precargados.
    with django_assert_max_num_queries(8):
        respuesta = client.get(RUTA)
    filas = respuesta.content.decode().count('aria-label="Abrir la solicitud')
    assert filas == Solicitud.objects.count() == 13  # las 12 y la que trae crear_servicio


def test_facturacion_no_entra_a_la_lista(client, crear_usuario):
    client.force_login(crear_usuario("facturacion"))
    assert client.get(RUTA).status_code == 403
