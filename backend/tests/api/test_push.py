"""Avisos push al conductor (1a-14) contra PostgreSQL: la tabla de salida en la transacción de la
asignación, el envío después de confirmar, los reintentos acotados, el comando de reenvío y los
tokens que FCM ya no reconoce.

El envío real se prueba con un cliente HTTP falso (`FcmFalso`) y credenciales falsas: ninguna
prueba toca la red ni lee la cuenta de servicio real (`tests/conftest.py` deja vacía
`ARRIBO_FIREBASE_CREDENCIALES`).
"""
import json
import logging
import threading
import time
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
import requests
from django.core.management import call_command
from django.db import IntegrityError, transaction

from api import notificaciones, push
from api.models import EstadoNotificacion, NotificacionPush, TokenDispositivo
from api.push import EnviadorFCM
from clientes.models import Cliente, Contacto, Tarifa, TipoCliente
from cobros.models import LineaCobro
from flota.models import Conductor
from nucleo.estados import Estado, Resolucion
from nucleo.push import MAXIMO_INTENTOS
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import Servicio

from ..conftest import crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado
PENDIENTE = EstadoNotificacion.PENDIENTE
ENVIADA = EstadoNotificacion.ENVIADA
FALLIDA = EstadoNotificacion.FALLIDA
URL_FCM = "https://fcm.googleapis.com/v1/projects/arribo-prueba/messages:send"


# --- Dobles de prueba ----------------------------------------------------------------------------


class CredencialesFalsas:
    """Lo que `EnviadorFCM` usa de la cuenta de servicio, sin llave ni red."""

    project_id = "arribo-prueba"

    def __init__(self):
        self.token = "acceso-falso"
        self.valid = True
        self.renovaciones = 0

    def refresh(self, request):
        self.renovaciones += 1
        self.token = f"acceso-renovado-{self.renovaciones}"
        self.valid = True


class RespuestaFalsa:
    def __init__(self, estado, cuerpo=None):
        self.status_code = estado
        self._cuerpo = cuerpo

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin cuerpo JSON")
        return self._cuerpo


def ok():
    return RespuestaFalsa(200, {"name": "projects/arribo-prueba/messages/0:1"})


def error_fcm(estado, codigo=None, estado_texto="ERROR"):
    error = {"code": estado, "message": "Algo pasó en FCM.", "status": estado_texto}
    if codigo:
        error["details"] = [
            {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": codigo}
        ]
    return RespuestaFalsa(estado, {"error": error})


class FcmFalso:
    """Cliente HTTP falso: anota cada POST y responde lo que haya en `respuestas`, en orden (la
    última se repite). Una excepción en la lista se lanza en vez de responder."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas) or [ok()]
        self.envios = []

    def responder(self, *respuestas):
        self.respuestas = list(respuestas)

    def post(self, url, json=None, headers=None, timeout=None):
        self.envios.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(respuesta, BaseException):
            raise respuesta
        return respuesta

    def close(self):
        pass

    @property
    def tokens(self):
        return [envio["json"]["message"]["token"] for envio in self.envios]


@pytest.fixture
def credenciales():
    return CredencialesFalsas()


@pytest.fixture
def fcm(monkeypatch, credenciales):
    """El push queda "configurado" con credenciales y cliente HTTP falsos."""
    falso = FcmFalso()
    enviador = EnviadorFCM(credenciales, http=falso)
    monkeypatch.setattr(push, "enviador_configurado", lambda: enviador)
    return falso


@pytest.fixture
def celular_con_push():
    """Una sesión de la app (token de celular) con su token de push registrado."""

    def crear(conductor, token_push, dispositivo_id=None):
        token, _ = TokenDispositivo.emitir(conductor, dispositivo_id or f"celular-{token_push}")
        notificaciones.registrar_token_push(token, token_push)
        token.refresh_from_db()
        return token

    return crear


@pytest.fixture
def pendiente(crear_servicio):
    return crear_servicio(E.PENDIENTE_ASIGNAR)


def estados(*notificaciones_):
    return [NotificacionPush.objects.get(pk=n.pk).estado for n in notificaciones_]


# --- La tabla de salida va en la transacción de la asignación -----------------------------------


def test_asignar_encola_una_notificacion_en_la_misma_transaccion(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular = celular_con_push(ana, "push-ana")

    with django_capture_on_commit_callbacks() as al_confirmar, transaction.atomic():
        operaciones.asignar(pendiente, ana, actor=usuario)
        # Todavía dentro de la transacción: el aviso ya está en la tabla de salida, sin enviar.
        aviso = NotificacionPush.objects.get()
        assert (aviso.dispositivo, aviso.servicio, aviso.tipo) == (celular, pendiente, "asignado")
        assert aviso.estado == PENDIENTE
        assert fcm.envios == []

    assert len(al_confirmar) == 1  # el envío espera a que se confirme la asignación


def test_el_aviso_se_envia_despues_de_confirmar_la_asignacion(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    aviso = NotificacionPush.objects.get()
    assert aviso.estado == ENVIADA
    assert aviso.enviada_en is not None
    assert aviso.intentos == 1
    assert fcm.tokens == ["push-ana"]


def test_si_la_asignacion_se_revierte_no_queda_notificacion(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")

    class Revertir(Exception):
        pass

    with (
        django_capture_on_commit_callbacks(execute=True) as al_confirmar,
        pytest.raises(Revertir),
        transaction.atomic(),
    ):
        operaciones.asignar(pendiente, ana, actor=usuario)
        assert NotificacionPush.objects.count() == 1
        raise Revertir

    assert not NotificacionPush.objects.exists()
    assert al_confirmar == []
    assert fcm.envios == []
    pendiente.refresh_from_db()
    assert pendiente.estado == E.PENDIENTE_ASIGNAR


def test_una_asignacion_rechazada_no_encola_nada(
    pendiente, grua1, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    sin_grua = Conductor.objects.create(nombre="Carla", celular="3000000003")
    celular_con_push(sin_grua, "push-carla")

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(operaciones.ConductorBloqueado),
    ):
        operaciones.asignar(pendiente, sin_grua, actor=usuario)

    assert not NotificacionPush.objects.exists()
    assert fcm.envios == []


def test_un_conductor_sin_celular_con_push_no_recibe_aviso_y_la_asignacion_sigue(
    pendiente, ana, usuario, fcm, django_capture_on_commit_callbacks
):
    TokenDispositivo.emitir(ana, "celular-sin-push")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    pendiente.refresh_from_db()
    assert pendiente.estado == E.ASIGNADO
    assert not NotificacionPush.objects.exists()
    assert fcm.envios == []


def test_cada_celular_con_sesion_del_conductor_recibe_su_aviso(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-celular-1")
    celular_con_push(ana, "push-celular-2")
    revocado = celular_con_push(ana, "push-celular-viejo")
    TokenDispositivo.objects.filter(pk=revocado.pk).update(revocado_en=revocado.creado_en,
                                                         push_token="")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    assert sorted(fcm.tokens) == ["push-celular-1", "push-celular-2"]


# --- Un fallo del push nunca tumba ni revierte la asignación -------------------------------------


def test_un_fallo_de_envio_no_revierte_la_asignacion(
    client, logistica, pendiente, ana, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")
    fcm.responder(requests.ConnectionError("FCM no responde"))

    with django_capture_on_commit_callbacks(execute=True):
        respuesta = client.post(url_asignar(pendiente), {f"s{pendiente.pk}-conductor": ana.pk})

    assert respuesta.status_code == 302
    pendiente.refresh_from_db()
    assert pendiente.estado == E.ASIGNADO
    assert pendiente.conductor == ana
    aviso = NotificacionPush.objects.get()
    assert aviso.estado == PENDIENTE
    assert aviso.intentos == 1
    assert "Sin conexión con FCM" in aviso.error


def test_un_error_inesperado_al_enviar_no_revierte_la_asignacion(
    client, logistica, pendiente, ana, celular_con_push, monkeypatch, caplog,
    django_capture_on_commit_callbacks,
):
    celular_con_push(ana, "push-ana")

    def explota(_):
        raise RuntimeError("falla que nadie esperaba")

    monkeypatch.setattr(notificaciones, "enviar", explota)

    with caplog.at_level(logging.ERROR), django_capture_on_commit_callbacks(execute=True):
        respuesta = client.post(url_asignar(pendiente), {f"s{pendiente.pk}-conductor": ana.pk})

    assert respuesta.status_code == 302
    pendiente.refresh_from_db()
    assert pendiente.estado == E.ASIGNADO
    assert NotificacionPush.objects.get().estado == PENDIENTE  # el comando la reenvía
    assert "queda pendiente" in caplog.text


def test_un_fallo_al_encolar_no_revierte_la_asignacion(
    pendiente, ana, usuario, celular_con_push, monkeypatch, caplog
):
    celular_con_push(ana, "push-ana")
    original = notificaciones.encolar_avisos_de_asignacion

    def encola_y_falla(servicio, conductor_anterior=None):
        original(servicio, conductor_anterior)
        raise IntegrityError("falla de la base al encolar")

    monkeypatch.setattr(notificaciones, "encolar_avisos_de_asignacion", encola_y_falla)

    with caplog.at_level(logging.ERROR):
        operaciones.asignar(pendiente, ana, actor=usuario)

    pendiente.refresh_from_db()
    assert pendiente.estado == E.ASIGNADO
    assert pendiente.eventos.filter(destino=E.ASIGNADO).count() == 1
    assert not NotificacionPush.objects.exists()  # se deshizo solo lo del aviso
    assert "la asignación sigue" in caplog.text


def test_un_error_inesperado_del_enviador_cuenta_como_intento(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")
    fcm.responder(RuntimeError("el cliente HTTP falló de una forma rara"))

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    aviso = NotificacionPush.objects.get()
    assert (aviso.estado, aviso.intentos) == (PENDIENTE, 1)
    assert "RuntimeError" in aviso.error


# --- Reasignar avisa a los dos conductores -------------------------------------------------------


def test_reasignar_avisa_a_los_dos_conductores(
    crear_servicio, ana, beto, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    servicio = crear_servicio(E.ASIGNADO, conductor=ana)
    celular_con_push(ana, "push-ana")
    celular_con_push(beto, "push-beto")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.reasignar(servicio, beto, actor=usuario, motivo="Ana pinchó")

    avisos = {n.dispositivo.conductor.nombre: n for n in NotificacionPush.objects.all()}
    assert avisos["Beto"].tipo == "asignado"
    assert avisos["Ana"].tipo == "retirado"
    assert {n.estado for n in avisos.values()} == {ENVIADA}
    por_token = {envio["json"]["message"]["token"]: envio["json"]["message"] for envio in fcm.envios}
    assert por_token["push-beto"]["data"] == {"tipo": "asignado", "servicio_id": str(servicio.pk)}
    assert por_token["push-ana"]["data"] == {"tipo": "retirado", "servicio_id": str(servicio.pk)}
    assert "ya no está a su cargo" in por_token["push-ana"]["notification"]["body"]


def test_un_aviso_que_ya_no_aplica_no_se_envia(
    pendiente, ana, beto, usuario, celular_con_push, fcm, reloj,
    django_capture_on_commit_callbacks,
):
    celular_con_push(ana, "push-ana")
    fcm.responder(error_fcm(503, estado_texto="UNAVAILABLE"))
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    asignado = NotificacionPush.objects.get()
    assert asignado.estado == PENDIENTE

    fcm.responder(ok())
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.reasignar(pendiente, beto, actor=usuario)
    reloj.avanzar(minutes=1)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())

    asignado.refresh_from_db()
    assert asignado.estado == FALLIDA
    assert "Ya no aplica" in asignado.error
    retirado = NotificacionPush.objects.get(tipo="retirado")
    assert retirado.estado == ENVIADA
    # Al celular de Ana solo le llegó el "retirado": el "asignado" vencido no salió.
    assert [e["json"]["message"]["data"]["tipo"] for e in fcm.envios[1:]] == ["retirado"]


# --- El mensaje que sale hacia FCM ---------------------------------------------------------------


def test_el_envio_usa_la_api_http_v1_de_fcm_con_el_token_de_acceso(
    pendiente, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    (envio,) = fcm.envios
    assert envio["url"] == URL_FCM
    assert envio["headers"] == {"Authorization": "Bearer acceso-falso"}
    assert envio["timeout"] is not None
    assert envio["json"] == {
        "message": {
            "token": "push-ana",
            "notification": {
                "title": "Nuevo servicio asignado",
                "body": f"Servicio N.º {pendiente.pk}. Abra Arribo para ver el detalle.",
            },
            "data": {"tipo": "asignado", "servicio_id": str(pendiente.pk)},
            "android": {"priority": "HIGH"},
        }
    }


def test_el_cuerpo_de_la_notificacion_no_lleva_valores_de_cobro_ni_datos_personales(
    cliente, ana, usuario, nuevo_vehiculo, celular_con_push, fcm,
    django_capture_on_commit_callbacks,
):
    pagador = Cliente.objects.create(
        nombre="Aseguradora Pagadora Única", tipo=TipoCliente.ASEGURADORA
    )
    Tarifa.objects.create(
        cliente=pagador, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal("876543.21")
    )
    contacto = Contacto.objects.create(nombre="Portería Torre Norte", telefono="604 444 5566")
    solicitud = crear_solicitud(
        cliente, pagador=pagador, contacto_origen=contacto, origen="Calle Secreta # 1-23"
    )
    servicio = Servicio.objects.create(
        solicitud=solicitud,
        vehiculo=nuevo_vehiculo(placa="QWE987", marca="Mazda"),
        referencia_externa="CASO-77",
    )
    LineaCobro.objects.create(
        servicio=servicio, pagador=pagador, estado="por_facturar", valor=Decimal("987654.32")
    )
    celular_con_push(ana, "push-ana")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(servicio, ana, actor=usuario)

    (envio,) = fcm.envios
    mensaje = envio["json"]["message"]
    assert set(mensaje["data"]) == {"tipo", "servicio_id"}
    texto = json.dumps(envio["json"], ensure_ascii=False)
    for prohibido in (
        "876543", "987654", "Aseguradora", "Autos del Valle", "Portería", "4445566",
        "Calle Secreta", "QWE987", "Mazda", "CASO-77", "Ana", "valor", "tarifa", "pagador",
        "factura",
    ):
        assert prohibido not in texto, prohibido
    aviso = NotificacionPush.objects.get()
    assert (aviso.titulo, aviso.cuerpo) == (
        mensaje["notification"]["title"], mensaje["notification"]["body"]
    )


def test_un_401_de_fcm_renueva_el_token_de_acceso_en_el_siguiente_intento(
    pendiente, ana, usuario, celular_con_push, fcm, credenciales, reloj,
    django_capture_on_commit_callbacks,
):
    celular_con_push(ana, "push-ana")
    fcm.responder(error_fcm(401, estado_texto="UNAUTHENTICATED"), ok())

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    reloj.avanzar(minutes=1)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())

    assert credenciales.renovaciones == 1
    assert fcm.envios[1]["headers"] == {"Authorization": "Bearer acceso-renovado-1"}
    assert NotificacionPush.objects.get().estado == ENVIADA


# --- Reintentos acotados y comando de reenvío ----------------------------------------------------


def test_reintento_acotado_con_esperas_crecientes(
    pendiente, ana, usuario, celular_con_push, fcm, reloj, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")
    fcm.responder(error_fcm(503, "UNAVAILABLE", "UNAVAILABLE"))
    inicio = reloj.ahora

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    aviso = NotificacionPush.objects.get()
    assert (aviso.estado, aviso.intentos) == (PENDIENTE, 1)
    assert "503" in aviso.error

    # Antes de su hora, el comando no lo toca.
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())
    assert len(fcm.envios) == 1

    for minutos, intentos in ((1, 2), (5, 3), (15, 4)):
        reloj.avanzar(minutes=minutos)
        call_command("enviar_notificaciones_pendientes", stdout=StringIO())
        aviso.refresh_from_db()
        assert (aviso.estado, aviso.intentos) == (PENDIENTE, intentos)

    reloj.avanzar(minutes=30)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())
    aviso.refresh_from_db()
    assert (aviso.estado, aviso.intentos) == (FALLIDA, MAXIMO_INTENTOS)
    assert f"Se agotaron los {MAXIMO_INTENTOS} intentos" in aviso.error

    reloj.avanzar(hours=5)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())
    assert len(fcm.envios) == MAXIMO_INTENTOS  # agotado, nadie lo vuelve a intentar
    assert aviso.proximo_intento - inicio < timedelta(hours=1)


def test_el_comando_reenvia_las_que_quedaron_pendientes(
    pendiente, ana, usuario, celular_con_push, fcm, reloj, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")
    fcm.responder(requests.Timeout("se agotó el tiempo"))
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    assert NotificacionPush.objects.get().estado == PENDIENTE

    fcm.responder(ok())
    salida = StringIO()
    call_command("enviar_notificaciones_pendientes", stdout=salida)
    assert "0 enviados" in salida.getvalue()
    assert "próximo reintento" in salida.getvalue()

    reloj.avanzar(minutes=1)
    salida = StringIO()
    call_command("enviar_notificaciones_pendientes", stdout=salida)

    assert "1 enviados, 0 por reintentar, 0 fallidos" in salida.getvalue()
    aviso = NotificacionPush.objects.get()
    assert (aviso.estado, aviso.intentos, aviso.error) == (ENVIADA, 2, "")


def test_una_notificacion_enviada_o_fallida_no_se_vuelve_a_enviar(
    pendiente, ana, usuario, celular_con_push, fcm, reloj, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    aviso = NotificacionPush.objects.get()

    assert notificaciones.enviar(aviso.pk) is None
    reloj.avanzar(hours=1)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())

    assert len(fcm.envios) == 1


# --- Tokens que FCM ya no reconoce ---------------------------------------------------------------


def test_un_token_no_registrado_se_desactiva(
    crear_servicio, ana, usuario, celular_con_push, fcm, caplog,
    django_capture_on_commit_callbacks,
):
    celular = celular_con_push(ana, "push-desinstalada")
    fcm.responder(error_fcm(404, "UNREGISTERED", "NOT_FOUND"))

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(crear_servicio(), ana, actor=usuario)

    aviso = NotificacionPush.objects.get()
    assert (aviso.estado, aviso.intentos) == (FALLIDA, 1)
    assert "UNREGISTERED" in aviso.error
    celular.refresh_from_db()
    assert celular.push_token == ""
    assert celular.push_desactivado_en is not None
    assert celular.vigente  # la sesión sigue: solo deja de recibir push
    assert "se desactivó" in caplog.text

    # La siguiente asignación ya no intenta ese token.
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(crear_servicio(), ana, actor=usuario)
    assert NotificacionPush.objects.count() == 1
    assert len(fcm.envios) == 1


def test_desactivar_un_token_no_borra_el_nuevo_que_registro_la_app(
    pendiente, ana, usuario, celular_con_push, fcm, monkeypatch,
    django_capture_on_commit_callbacks,
):
    """Si la app registra otro token mientras FCM responde que el viejo no existe, el nuevo se
    conserva."""
    celular = celular_con_push(ana, "push-viejo")

    def responde_y_la_app_cambia_de_token(url, json=None, headers=None, timeout=None):
        notificaciones.registrar_token_push(celular, "push-nuevo")
        return error_fcm(404, "UNREGISTERED", "NOT_FOUND")

    monkeypatch.setattr(fcm, "post", responde_y_la_app_cambia_de_token)

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    celular.refresh_from_db()
    assert celular.push_token == "push-nuevo"


def test_un_mensaje_que_fcm_rechaza_falla_sin_reintentar(
    pendiente, ana, usuario, celular_con_push, fcm, reloj, django_capture_on_commit_callbacks
):
    celular = celular_con_push(ana, "push-ana")
    fcm.responder(error_fcm(400, "INVALID_ARGUMENT", "INVALID_ARGUMENT"))

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)
    reloj.avanzar(hours=1)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())

    aviso = NotificacionPush.objects.get()
    assert (aviso.estado, aviso.intentos) == (FALLIDA, 1)
    assert "INVALID_ARGUMENT" in aviso.error
    celular.refresh_from_db()
    assert celular.push_token == "push-ana"  # no es culpa del token


def test_una_sesion_cerrada_antes_del_envio_no_recibe_el_aviso(
    pendiente, ana, usuario, celular_con_push, fcm, reloj, django_capture_on_commit_callbacks
):
    celular = celular_con_push(ana, "push-ana")
    fcm.responder(requests.ConnectionError("sin red"))
    with django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    from api.ingreso import cerrar_sesion

    cerrar_sesion(celular)
    fcm.responder(ok())
    reloj.avanzar(minutes=1)
    call_command("enviar_notificaciones_pendientes", stdout=StringIO())

    aviso = NotificacionPush.objects.get()
    assert aviso.estado == FALLIDA
    assert "ya no tiene sesión" in aviso.error
    assert len(fcm.envios) == 1


# --- Sin credenciales: el servidor sigue igual ---------------------------------------------------


def test_sin_credenciales_no_se_envia_y_queda_un_aviso_en_el_registro(
    pendiente, ana, usuario, celular_con_push, caplog, django_capture_on_commit_callbacks
):
    celular_con_push(ana, "push-ana")

    with caplog.at_level(logging.WARNING), django_capture_on_commit_callbacks(execute=True):
        operaciones.asignar(pendiente, ana, actor=usuario)

    pendiente.refresh_from_db()
    assert pendiente.estado == E.ASIGNADO
    aviso = NotificacionPush.objects.get()
    assert aviso.estado == FALLIDA
    assert "no está configurado" in aviso.error
    assert "ARRIBO_FIREBASE_CREDENCIALES" in caplog.text


def test_las_pruebas_no_leen_la_cuenta_de_servicio_real(settings):
    assert settings.ARRIBO_FIREBASE_CREDENCIALES == ""
    assert push.enviador_configurado() is None


def test_una_cuenta_de_servicio_ilegible_no_tumba_nada_ni_se_copia_al_registro(
    settings, tmp_path, caplog
):
    archivo = tmp_path / "cuenta.json"
    archivo.write_text('{"type": "service_account", "private_key": "secreto-de-prueba"', "utf-8")
    settings.ARRIBO_FIREBASE_CREDENCIALES = str(archivo)

    with caplog.at_level(logging.ERROR):
        assert push.enviador_configurado() is None

    assert str(archivo) in caplog.text
    assert "secreto-de-prueba" not in caplog.text


# --- Dos envíos a la vez no mandan el mismo aviso dos veces --------------------------------------


@pytest.mark.django_db(transaction=True)
def test_dos_envios_simultaneos_del_mismo_aviso_lo_mandan_una_sola_vez(
    pendiente, ana, usuario, celular_con_push, monkeypatch, credenciales
):
    from ..solicitudes.test_concurrencia import en_paralelo

    celular_con_push(ana, "push-ana")
    operaciones.asignar(pendiente, ana, actor=usuario)  # sin push configurado: queda fallida
    aviso = NotificacionPush.objects.get()
    NotificacionPush.objects.filter(pk=aviso.pk).update(estado=PENDIENTE, error="")

    envios = []
    candado = threading.Lock()

    class FcmLento(FcmFalso):
        def post(self, *args, **kwargs):
            with candado:
                envios.append(1)
            time.sleep(0.3)  # el otro hilo llega mientras este todavía envía
            return ok()

    enviador = EnviadorFCM(credenciales, http=FcmLento())
    monkeypatch.setattr(push, "enviador_configurado", lambda: enviador)

    salidas = en_paralelo(lambda: notificaciones.enviar(aviso.pk),
                          lambda: notificaciones.enviar(aviso.pk))

    assert sorted(salidas, key=str) == [ENVIADA, None] or sorted(salidas, key=str) == [None,
                                                                                      ENVIADA]
    assert len(envios) == 1
    assert NotificacionPush.objects.get().estado == ENVIADA


# --- Apoyo ---------------------------------------------------------------------------------------


def url_asignar(servicio):
    return f"/solicitudes/{servicio.solicitud_id}/servicios/{servicio.pk}/asignar/"


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


def test_resolver_una_novedad_devolviendola_a_la_cola_no_envia_aviso(
    crear_servicio, ana, usuario, celular_con_push, fcm, django_capture_on_commit_callbacks
):
    """Fuera del alcance de la 1a-14 (anotado en QUESTIONS.md): solo asignar y reasignar avisan."""
    servicio = crear_servicio(E.NOVEDAD, previo=E.ASIGNADO)
    celular_con_push(ana, "push-ana")

    with django_capture_on_commit_callbacks(execute=True):
        operaciones.resolver_novedad(servicio, Resolucion.REASIGNAR, actor=usuario)

    assert not NotificacionPush.objects.exists()
