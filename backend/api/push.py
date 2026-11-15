"""Envío de un aviso push con la API HTTP v1 de Firebase Cloud Messaging (FCM).

Sin `firebase-admin` (arrastra los clientes de Firestore, Storage y gRPC): con la cuenta de
servicio, `google-auth` obtiene el token de acceso de OAuth 2 (y lo renueva antes de que venza, cada
hora) y `requests` hace el POST a `projects/<proyecto>/messages:send`.

La cuenta de servicio es una credencial: su ruta llega por `ARRIBO_FIREBASE_CREDENCIALES` (fuera del
repositorio) y nunca se escribe su contenido en el registro, en la base ni en un error. Sin la
variable, o si el archivo no se puede leer, `enviador_configurado()` devuelve None y el servidor
sigue igual, solo que sin avisos push.

Qué hacer con cada respuesta de FCM lo decide `nucleo.push.clasificar`.
"""
import logging
import threading
from dataclasses import dataclass

import requests
from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request

from nucleo.push import Contenido, Desenlace, clasificar

registro = logging.getLogger(__name__)

ALCANCE = "https://www.googleapis.com/auth/firebase.messaging"
URL_DE_ENVIO = "https://fcm.googleapis.com/v1/projects/{proyecto}/messages:send"
# Segundos para conectar y para leer la respuesta. El primer envío corre al terminar la petición
# del panel que asignó: con FCM caído, el panel no espera más que esto.
TIEMPO_MAXIMO = (5, 10)
LARGO_MAXIMO_DEL_DETALLE = 300


@dataclass(frozen=True)
class Envio:
    desenlace: Desenlace
    # Por qué no se envió, para el registro del servidor y la columna "último error".
    detalle: str = ""


def mensaje(token_push: str, contenido: Contenido) -> dict:
    """El cuerpo de `messages:send`. La parte `notification` la muestra Android solo cuando la
    app no está a la vista (tocarla abre la app); `data` la lee la app. Prioridad alta para que
    llegue aunque el celular esté en reposo (Doze)."""
    return {
        "message": {
            "token": token_push,
            "notification": {"title": contenido.titulo, "body": contenido.cuerpo},
            "data": dict(contenido.datos),
            "android": {"priority": "HIGH"},
        }
    }


class EnviadorFCM:
    """`credenciales`: las de la cuenta de servicio (`google.oauth2.service_account`), o una falsa
    en las pruebas (con `project_id`, `token`, `valid` y `refresh`). `http`: una sesión de
    `requests`, o un cliente falso en las pruebas (ninguna prueba toca la red)."""

    def __init__(self, credenciales, http=None):
        self._credenciales = credenciales
        self._http = http if http is not None else requests.Session()
        # Una sola petición a la vez: la sesión de requests y la renovación del token de acceso
        # no se comparten entre hilos (runserver atiende cada petición en un hilo).
        self._candado = threading.Lock()
        self._renovar = False
        # Una sola, para toda la vida del enviador: al destruirse, la de google-auth cierra la
        # sesión HTTP que recibe.
        self._peticion_de_token = Request(session=self._http)

    @property
    def proyecto(self) -> str:
        return self._credenciales.project_id

    def enviar(self, token_push: str, contenido: Contenido) -> Envio:
        with self._candado:
            try:
                acceso = self._token_de_acceso()
            except (GoogleAuthError, requests.RequestException) as error:
                return Envio(
                    Desenlace.REINTENTAR,
                    f"No se pudo obtener el token de acceso de Google ({type(error).__name__}).",
                )
            try:
                respuesta = self._http.post(
                    URL_DE_ENVIO.format(proyecto=self.proyecto),
                    json=mensaje(token_push, contenido),
                    headers={"Authorization": f"Bearer {acceso}"},
                    timeout=TIEMPO_MAXIMO,
                )
            except requests.RequestException as error:
                return Envio(Desenlace.REINTENTAR, f"Sin conexión con FCM ({type(error).__name__}).")
            if respuesta.status_code == 401:
                self._renovar = True  # el token de acceso ya no sirve: se pide otro la próxima vez
        codigo, texto = _error_de_fcm(respuesta)
        desenlace = clasificar(respuesta.status_code, codigo)
        if desenlace == Desenlace.ENVIADO:
            return Envio(desenlace)
        detalle = f"FCM respondió {respuesta.status_code}"
        if codigo:
            detalle += f" {codigo}"
        if texto:
            detalle += f": {texto}"
        return Envio(desenlace, detalle[:LARGO_MAXIMO_DEL_DETALLE])

    def _token_de_acceso(self) -> str:
        if self._renovar or not self._credenciales.valid:
            self._credenciales.refresh(self._peticion_de_token)
            self._renovar = False
        return self._credenciales.token


def _error_de_fcm(respuesta) -> tuple[str | None, str]:
    """(errorCode de FCM, mensaje) de una respuesta de error de la API v1, si la trae:
    {"error": {"code": 404, "message": "...", "status": "NOT_FOUND",
               "details": [{"@type": "...FcmError", "errorCode": "UNREGISTERED"}]}}"""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return None, ""
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    if not isinstance(error, dict):
        return None, ""
    codigo = None
    for detalle in error.get("details") or []:
        if isinstance(detalle, dict) and isinstance(detalle.get("errorCode"), str):
            codigo = detalle["errorCode"]
            break
    texto = error.get("message")
    return codigo, texto if isinstance(texto, str) else ""


_enviadores: dict[str, EnviadorFCM] = {}
_candado_de_carga = threading.Lock()


def enviador_configurado() -> EnviadorFCM | None:
    """El enviador con la cuenta de servicio de `ARRIBO_FIREBASE_CREDENCIALES`, o None si la
    variable está vacía o el archivo no se puede leer. Se lee una vez por proceso; si el archivo
    estaba mal, se vuelve a intentar en el siguiente aviso (corregirlo no exige reiniciar)."""
    ruta = settings.ARRIBO_FIREBASE_CREDENCIALES
    if not ruta:
        return None
    with _candado_de_carga:
        enviador = _enviadores.get(ruta)
        if enviador is None:
            enviador = _cargar(ruta)
            if enviador is not None:
                _enviadores[ruta] = enviador
    return enviador


def _cargar(ruta: str) -> EnviadorFCM | None:
    from google.oauth2 import service_account

    try:
        credenciales = service_account.Credentials.from_service_account_file(
            ruta, scopes=[ALCANCE]
        )
    # Solo el tipo de error y la ruta: el mensaje podría citar parte del archivo.
    except Exception as error:  # noqa: BLE001
        registro.error(
            "No se pudo leer la cuenta de servicio de Firebase en %s (%s): no se envían avisos "
            "push hasta corregirlo.",
            ruta,
            type(error).__name__,
        )
        return None
    if not credenciales.project_id:
        registro.error(
            "La cuenta de servicio de Firebase en %s no dice de qué proyecto es: no se envían "
            "avisos push.",
            ruta,
        )
        return None
    return EnviadorFCM(credenciales)
