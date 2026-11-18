"""Alertas por umbral (1a-18) contra PostgreSQL, con el reloj controlado (`evaluar(ahora=...)`):
sin asignar (inmediato y programado), Recogido sin Entregado y documento por vencer o vencido. Se
abren una vez, se cierran solas cuando la condición deja de cumplirse y siguen los umbrales de la
configuración. El tablero las evalúa al cargarse y no deja marcarlas resueltas a mano."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from alertas.evaluacion import evaluar
from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import abrir_alerta, alertas_abiertas
from configuracion.models import configuracion_vigente
from documentos.consultas import dia_local
from documentos.models import TipoDocumento
from documentos.operaciones import registrar_documento
from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import EstadoRegistro, Solicitud
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db

SIN_ASIGNAR = TipoAlerta.SIN_ASIGNAR
RECOGIDO = TipoAlerta.RECOGIDO_SIN_ENTREGADO
DOCUMENTO = TipoAlerta.DOCUMENTO_POR_VENCER


def configurar(**campos):
    c = configuracion_vigente()
    for campo, valor in campos.items():
        setattr(c, campo, valor)
    c.save()


def abiertas(tipo, registro=None):
    return list(alertas_abiertas(registro=registro, tipo=tipo))


def registrada_hace(servicio, delta):
    Solicitud.objects.filter(pk=servicio.solicitud_id).update(creada_en=timezone.now() - delta)


# --- Sin asignar ---------------------------------------------------------------------------------


def test_inmediato_sin_asignar_alerta_al_pasar_el_umbral(crear_servicio):
    servicio = crear_servicio()
    creada = servicio.solicitud.creada_en

    evaluar(ahora=creada + timedelta(minutes=9))
    assert abiertas(SIN_ASIGNAR) == []

    resumen = evaluar(ahora=creada + timedelta(minutes=10))
    [alerta] = abiertas(SIN_ASIGNAR, servicio)
    assert resumen.abiertas[SIN_ASIGNAR] == 1
    assert f"Servicio N.º {servicio.pk}" in alerta.mensaje
    assert "sigue sin asignar" in alerta.mensaje
    assert "10 min" in alerta.mensaje


def test_cambiar_el_umbral_hace_aparecer_la_alerta(crear_servicio):
    servicio = crear_servicio()
    ahora = servicio.solicitud.creada_en + timedelta(minutes=6)
    evaluar(ahora=ahora)
    assert abiertas(SIN_ASIGNAR) == []

    configurar(alerta_sin_asignar_minutos=5)
    evaluar(ahora=ahora)
    assert len(abiertas(SIN_ASIGNAR, servicio)) == 1


def test_evaluar_dos_veces_no_abre_otra(crear_servicio):
    servicio = crear_servicio()
    ahora = servicio.solicitud.creada_en + timedelta(hours=1)
    evaluar(ahora=ahora)
    resumen = evaluar(ahora=ahora + timedelta(minutes=1))
    assert resumen.total_abiertas == 0
    assert Alerta.objects.filter(tipo=SIN_ASIGNAR).count() == 1


def test_al_asignarlo_la_alerta_se_cierra_sola(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    ahora = servicio.solicitud.creada_en + timedelta(minutes=30)
    evaluar(ahora=ahora)
    operaciones.asignar(servicio, ana, actor=usuario)

    resumen = evaluar(ahora=ahora + timedelta(minutes=1))

    assert resumen.cerradas[SIN_ASIGNAR] == 1
    alerta = Alerta.objects.get(tipo=SIN_ASIGNAR)
    assert alerta.resuelta_en == ahora + timedelta(minutes=1)
    assert alerta.resuelta_por is None  # la cerró el sistema


def test_programado_alerta_desde_horas_antes_de_su_hora(cliente, crear_servicio):
    hora = timezone.now() + timedelta(days=2)
    servicio = crear_servicio(solicitud_de=crear_solicitud(cliente, programada_para=hora))

    evaluar(ahora=hora - timedelta(hours=2, minutes=1))
    assert abiertas(SIN_ASIGNAR) == []
    evaluar(ahora=hora - timedelta(hours=2))
    [alerta] = abiertas(SIN_ASIGNAR, servicio)
    assert "programado para el" in alerta.mensaje


def test_un_borrador_no_alerta(cliente, crear_servicio):
    borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    crear_servicio(solicitud_de=borrador)
    evaluar(ahora=timezone.now() + timedelta(days=1))
    assert abiertas(SIN_ASIGNAR) == []


# --- Recogido sin Entregado ---------------------------------------------------------------------


@pytest.fixture
def recogido(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(servicio, Estado.EN_CAMINO, actor=usuario)
    evento = operaciones.cambiar_estado(servicio, Estado.RECOGIDO, actor=usuario)
    return servicio, evento.hora_sincronizacion


def test_recogido_sin_entregado_alerta_al_pasar_las_horas(recogido):
    servicio, momento = recogido
    evaluar(ahora=momento + timedelta(hours=3, minutes=59))
    assert abiertas(RECOGIDO) == []

    evaluar(ahora=momento + timedelta(hours=4))
    [alerta] = abiertas(RECOGIDO, servicio)
    assert "sin marcarse Entregado" in alerta.mensaje
    assert "Ana" in alerta.mensaje


def test_cambiar_el_umbral_de_recogido(recogido):
    servicio, momento = recogido
    configurar(alerta_recogido_sin_entregado_horas=1)
    evaluar(ahora=momento + timedelta(hours=1))
    assert len(abiertas(RECOGIDO, servicio)) == 1


def test_al_entregarlo_la_alerta_se_cierra_sola(recogido, usuario):
    servicio, momento = recogido
    evaluar(ahora=momento + timedelta(hours=5))
    assert len(abiertas(RECOGIDO)) == 1
    servicio.refresh_from_db()
    operaciones.cambiar_estado(servicio, Estado.ENTREGADO, actor=usuario, nombre_quien="Pedro")
    evaluar(ahora=momento + timedelta(hours=5, minutes=1))
    assert abiertas(RECOGIDO) == []


# --- Documentos ----------------------------------------------------------------------------------


@pytest.fixture
def soat():
    return TipoDocumento.objects.get(nombre="SOAT")


def registrar(tipo, sujeto, por, vence_en):
    return registrar_documento(
        tipo=tipo, sujeto=sujeto, por=por, vence=dia_local() + timedelta(days=vence_en)
    )


def test_documento_por_vencer_alerta_y_al_renovarlo_se_cierra(soat, grua1, usuario):
    documento = registrar(soat, grua1, usuario, vence_en=10)
    evaluar()
    [alerta] = abiertas(DOCUMENTO, documento)
    assert f"SOAT de la grúa {grua1.placa} vence el" in alerta.mensaje

    registrar(soat, grua1, usuario, vence_en=365)
    resumen = evaluar()
    assert abiertas(DOCUMENTO) == []
    assert resumen.cerradas[DOCUMENTO] == 1


def test_documento_vigente_no_alerta_y_vencido_si(soat, grua1, grua2, usuario):
    registrar(soat, grua1, usuario, vence_en=200)
    vencido = registrar(soat, grua2, usuario, vence_en=-1)
    evaluar()
    [alerta] = abiertas(DOCUMENTO)
    assert alerta.registro == vencido
    assert "vencido" in alerta.mensaje


def test_los_dias_de_anticipacion_del_tipo_mandan(soat, grua1, usuario):
    registrar(soat, grua1, usuario, vence_en=40)
    evaluar()
    assert abiertas(DOCUMENTO) == []
    soat.dias_anticipacion = 45
    soat.save()
    evaluar()
    assert len(abiertas(DOCUMENTO)) == 1


def test_la_grua_inactiva_no_alerta(soat, grua1, usuario):
    registrar(soat, grua1, usuario, vence_en=-5)
    grua1.activa = False
    grua1.save()
    evaluar()
    assert abiertas(DOCUMENTO) == []


# --- Conflicto, comando y tablero ---------------------------------------------------------------


def test_evaluar_no_toca_las_alertas_de_conflicto(crear_servicio, ana, usuario):
    evento = operaciones.asignar(crear_servicio(), ana, actor=usuario)
    conflicto = abrir_alerta(TipoAlerta.CONFLICTO_SINCRONIZACION, evento, "No encajó.")
    evaluar(ahora=timezone.now() + timedelta(days=1))
    conflicto.refresh_from_db()
    assert conflicto.abierta


def test_el_comando_evalua_y_dice_cuantas(crear_servicio):
    servicio = crear_servicio()
    registrada_hace(servicio, timedelta(hours=1))
    salida = StringIO()
    call_command("evaluar_alertas", stdout=salida)
    assert "Servicio sin asignar: 1 nuevas, 0 cerradas." in salida.getvalue()
    assert len(abiertas(SIN_ASIGNAR, servicio)) == 1


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica", first_name="Lina")
    client.force_login(usuario)
    return usuario


def test_el_tablero_evalua_al_cargarse_y_lleva_a_la_solicitud(client, logistica, crear_servicio):
    servicio = crear_servicio()
    registrada_hace(servicio, timedelta(minutes=30))
    html = client.get("/").content.decode()
    alerta = Alerta.objects.get(tipo=SIN_ASIGNAR)
    assert "Servicio sin asignar" in html
    assert f"Servicio N.º {servicio.pk}" in html
    assert f'href="/solicitudes/{servicio.solicitud_id}/"' in html
    assert "Se cierra sola cuando se atiende." in html
    assert f'action="/alertas/{alerta.pk}/resolver/"' not in html


def test_una_alerta_por_condicion_no_se_resuelve_a_mano(client, logistica, crear_servicio):
    alerta = abrir_alerta(SIN_ASIGNAR, crear_servicio(), "Sin asignar.")
    client.post(f"/alertas/{alerta.pk}/resolver/")
    alerta.refresh_from_db()
    assert alerta.abierta


def test_el_administrador_ve_el_enlace_al_documento(client, crear_usuario, soat, grua1, usuario):
    registrar(soat, grua1, usuario, vence_en=5)
    client.force_login(crear_usuario("administrador"))
    html = client.get("/").content.decode()
    assert f'href="/flota/gruas/{grua1.pk}/documentos/{soat.pk}/"' in html


def test_logistica_ve_la_alerta_del_documento_sin_enlace_a_flota(
    client, logistica, soat, grua1, usuario
):
    registrar(soat, grua1, usuario, vence_en=5)
    html = client.get("/").content.decode()
    assert "Documento por vencer o vencido" in html
    assert "/flota/gruas/" not in html
