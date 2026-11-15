"""Tablero de inicio de logística y del administrador (1a-08c, visual desde la 1a-08e) contra
PostgreSQL: cifras del día, por asignar en orden con su espera y asignación ahí mismo, borradores
con lo que les falta, alertas abiertas que se resuelven ahí y una tarjeta por conductor."""
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from alertas.models import TipoAlerta
from alertas.operaciones import abrir_alerta, resolver_alerta
from configuracion.models import configuracion_vigente
from flota.models import Conductor
from nucleo.estados import Estado
from panel.tablero import datos_del_tablero, entregados_hoy
from solicitudes import consultas, operaciones
from solicitudes.models import EstadoRegistro, Solicitud
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db

RUTA_ASIGNAR = "/solicitudes/{}/servicios/{}/asignar/"


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
    for titulo in ("Por asignar", "Borradores", "Alertas sin resolver", "Conductores"):
        assert titulo in html
    assert html.index('id="t-por-asignar"') < html.index('id="t-borradores"') < html.index(
        'id="t-alertas"'
    ) < html.index('id="t-conductores"')
    assert 'hx-trigger="every 60s' in html  # se actualiza solo


def test_el_administrador_tambien_ve_el_tablero_en_el_inicio(client, crear_usuario):
    client.force_login(crear_usuario("administrador"))
    assert 'id="t-conductores"' in client.get("/").content.decode()


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
    assert f'href="/solicitudes/{solicitud.pk}/">Ver solicitud {solicitud.pk}</a>' in html


def test_cada_conductor_muestra_su_ronda_sin_pendientes_ni_terminados(
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
    seccion = html[html.index('id="t-conductores"'):]
    for texto in ("Ana", "Beto", "AAA111", "BBB222", "CCC333", "Novedad", "Recogido"):
        assert texto in seccion, texto
    assert "DDD444" not in seccion


def test_el_tablero_no_hace_una_consulta_por_fila(client, logistica, cliente, crear_servicio, beto):
    """Las consultas no crecen con las filas: las mismas con 2 que con 8 de cada cosa. 20 fijas:
    sesión y usuario, configuración, disponibilidad de la flota con sus documentos, por asignar,
    borradores, en curso, alertas y entregados de hoy."""

    def crear(cantidad):
        for _ in range(cantidad):
            abierta = crear_solicitud(cliente)
            crear_servicio(solicitud_de=abierta)
            crear_servicio(Estado.EN_CAMINO, solicitud_de=abierta, conductor=beto)
            borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR, origen="")
            crear_servicio(solicitud_de=borrador)

    def consultas_del_tablero():
        with CaptureQueriesContext(connection) as capturadas:
            assert client.get("/").status_code == 200
        return len(capturadas)

    crear(2)
    consultas_del_tablero()  # la primera llena cachés de Django (tipos de contenido)
    con_pocas = consultas_del_tablero()
    crear(6)
    assert consultas_del_tablero() == con_pocas
    assert con_pocas <= 20


# --- Tablero visual (1a-08e) -------------------------------------------------------------------


def test_un_inmediato_que_espera_mas_del_umbral_sale_urgente(
    client, logistica, cliente, crear_servicio
):
    vieja = crear_solicitud(cliente)
    Solicitud.objects.filter(pk=vieja.pk).update(creada_en=timezone.now() - timedelta(minutes=25))
    crear_servicio(solicitud_de=vieja)
    crear_servicio(solicitud_de=crear_solicitud(cliente))  # recién llegada

    datos = datos_del_tablero()

    esperas = [(f.servicio.solicitud_id, f.urgente, f.espera) for f in datos["por_asignar"]]
    assert esperas[0] == (vieja.pk, True, "25 min")
    assert esperas[1][1] is False
    assert datos["cifras"]["por_asignar"] == 2
    assert datos["cifras"]["urgentes"] == 1
    assert "esperando de más" in client.get("/").content.decode()


def test_el_umbral_de_urgencia_sale_de_la_configuracion(logistica, cliente, crear_servicio):
    configuracion = configuracion_vigente()
    configuracion.alerta_sin_asignar_minutos = 30
    configuracion.save()
    vieja = crear_solicitud(cliente)
    Solicitud.objects.filter(pk=vieja.pk).update(creada_en=timezone.now() - timedelta(minutes=25))
    crear_servicio(solicitud_de=vieja)

    assert datos_del_tablero()["por_asignar"][0].urgente is False


def test_un_programado_sale_urgente_cuando_se_acerca_su_hora(logistica, cliente, crear_servicio):
    ahora = timezone.now()
    crear_servicio(solicitud_de=crear_solicitud(cliente, programada_para=ahora + timedelta(hours=1)))
    crear_servicio(solicitud_de=crear_solicitud(cliente, programada_para=ahora + timedelta(hours=5)))

    assert [f.urgente for f in datos_del_tablero()["por_asignar"]] == [True, False]


def test_asignar_desde_el_tablero_vuelve_al_tablero(
    client, logistica, solicitud, crear_servicio, ana
):
    servicio = crear_servicio()
    html = client.get("/").content.decode()
    assert f'name="s{servicio.pk}-conductor"' in html

    respuesta = client.post(
        RUTA_ASIGNAR.format(solicitud.pk, servicio.pk),
        {f"s{servicio.pk}-conductor": ana.pk, "volver": "tablero"},
    )

    assert respuesta.status_code == 302
    assert respuesta["Location"] == "/"
    servicio.refresh_from_db()
    assert servicio.estado == Estado.ASIGNADO
    assert servicio.conductor == ana


def test_asignar_desde_la_solicitud_sigue_volviendo_a_la_solicitud(
    client, logistica, solicitud, crear_servicio, ana
):
    servicio = crear_servicio()
    respuesta = client.post(
        RUTA_ASIGNAR.format(solicitud.pk, servicio.pk), {f"s{servicio.pk}-conductor": ana.pk}
    )
    assert respuesta["Location"] == f"/solicitudes/{solicitud.pk}/"


def test_resolver_una_alerta_desde_el_tablero(client, logistica, ana):
    alerta = abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "Evento sin guardar de Ana.")

    respuesta = client.post(f"/alertas/{alerta.pk}/resolver/")

    assert respuesta.status_code == 302
    alerta.refresh_from_db()
    assert alerta.resuelta_por == logistica
    assert "Evento sin guardar de Ana." not in client.get("/").content.decode()


def test_resolver_alerta_solo_por_post_y_no_para_facturacion(client, crear_usuario, ana):
    alerta = abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "x")
    client.force_login(crear_usuario("logistica"))
    assert client.get(f"/alertas/{alerta.pk}/resolver/").status_code == 405
    client.force_login(crear_usuario("facturacion"))
    assert client.post(f"/alertas/{alerta.pk}/resolver/").status_code == 403
    alerta.refresh_from_db()
    assert alerta.abierta


def test_la_tarjeta_del_conductor_dice_si_esta_libre_o_lleno(logistica, crear_servicio, ana, beto):
    crear_servicio(Estado.RECOGIDO)  # Ana: grúa de 1 puesto, llena
    datos = datos_del_tablero()
    tarjetas = {t.conductor.nombre: t for t in datos["conductores"]}

    assert tarjetas["Ana"].situacion == "lleno"
    assert tarjetas["Ana"].ocupacion == 100
    assert tarjetas["Beto"].situacion == "libre"
    assert datos["cifras"]["libres"] == 1
    assert datos["cifras"]["en_curso"] == 1


def test_un_conductor_inactivo_no_sale_en_el_tablero(logistica, beto):
    beto.activo = False
    beto.save()
    assert "Beto" not in [t.conductor.nombre for t in datos_del_tablero()["conductores"]]


def test_un_conductor_sin_grua_sale_bloqueado(logistica):
    sin_grua = Conductor.objects.create(nombre="Carla", celular="3005550000")
    tarjeta = next(t for t in datos_del_tablero()["conductores"] if t.conductor == sin_grua)
    assert tarjeta.situacion == "bloqueado"


def test_entregados_hoy_cuenta_los_servicios_entregados_desde_la_medianoche(
    logistica, crear_servicio, usuario
):
    servicio = crear_servicio(Estado.RECOGIDO)
    operaciones.cambiar_estado(servicio, Estado.ENTREGADO, actor=usuario, nombre_quien="Pedro")

    assert entregados_hoy() == 1
    assert entregados_hoy(timezone.now() + timedelta(days=1)) == 0
