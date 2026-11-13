"""Datos de las pruebas de la API, siempre contra PostgreSQL. Usa los de `tests/conftest.py`: Ana
(celular 3000000001) maneja la grúa GRU001 y Beto (3000000002) la GRU002.

Hash rápido: cada ingreso calcula un hash del PIN y el de producción (PBKDF2 con un millón de
vueltas) tarda casi un segundo, así que aquí se usa MD5 para no alargar la suite. Ninguna prueba
depende del algoritmo, salvo `test_el_pin_se_guarda_con_el_hash_de_django_nunca_en_claro`, que
vuelve a poner el de producción.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import TokenDispositivo

PIN = "482913"
OTRO_PIN = "135790"
CELULAR_ANA = "3000000001"
CELULAR_DE_NADIE = "3109999999"
URL_INGRESO = "/api/v1/ingresar/"
URL_SALIDA = "/api/v1/salir/"
URL_ASIGNACIONES = "/api/v1/asignaciones/"


@pytest.fixture(autouse=True)
def hash_rapido(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def dar_acceso(django_user_model):
    """Le da a un conductor lo que necesita para entrar a la app: un usuario del grupo conductor
    (sin contraseña: no entra al panel) y el PIN."""

    def dar(conductor, pin=PIN):
        usuario = django_user_model.objects.create_user(username=f"conductor{conductor.pk}")
        # get_or_create: las pruebas transaccionales vacían las tablas, también los grupos que
        # crea la migración de flota.
        usuario.groups.add(Group.objects.get_or_create(name="conductor")[0])
        conductor.usuario = usuario
        conductor.fijar_pin(pin)
        conductor.save()
        return conductor

    return dar


@pytest.fixture
def ana_app(ana, dar_acceso):
    return dar_acceso(ana)


@pytest.fixture
def beto_app(beto, dar_acceso):
    return dar_acceso(beto)


@pytest.fixture
def api():
    return APIClient()


def ingresar(api, celular=CELULAR_ANA, pin=PIN, dispositivo_id="celular-de-ana", **otros):
    datos = {"celular": celular, "pin": pin, "dispositivo_id": dispositivo_id, **otros}
    return api.post(URL_INGRESO, datos, format="json")


def cliente_con(clave: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {clave}")
    return cliente


@pytest.fixture
def sesion(ana_app):
    """Cliente con el token de Ana en su celular: el registro en `sesion.token`, la clave en claro
    en `sesion.clave`."""
    token, clave = TokenDispositivo.emitir(ana_app, "celular-de-ana", "Moto G de Ana")
    cliente = cliente_con(clave)
    cliente.token, cliente.clave = token, clave
    return cliente


class Reloj:
    def __init__(self, ahora: datetime):
        self.ahora = ahora

    def avanzar(self, **tiempo):
        self.ahora += timedelta(**tiempo)


@pytest.fixture
def reloj(monkeypatch):
    """Detiene `timezone.now()` (y lo que de él depende) en la hora actual sin fracciones de
    segundo; solo avanza con `reloj.avanzar(minutes=...)`."""
    reloj = Reloj(timezone.now().replace(microsecond=0))
    monkeypatch.setattr(timezone, "now", lambda: reloj.ahora)
    return reloj


# --- Sincronización (1a-10) ----------------------------------------------------------------------

URL_EVENTOS = "/api/v1/eventos/"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"foto de prueba " * 40 + b"\xff\xd9"


def evento_json(servicio, destino, *, secuencia=1, **otros) -> dict:
    """Un evento como lo manda el celular (id nuevo en cada llamada, salvo que se pase)."""
    base = {
        "id": str(uuid.uuid4()),
        "servicio_id": getattr(servicio, "pk", servicio),
        "destino": getattr(destino, "value", destino),
        "secuencia": secuencia,
        "hora_dispositivo": f"2026-11-20T13:{secuencia % 60:02d}:00Z",
    }
    base.update(otros)
    return base


def enviar(cliente, *eventos):
    """POST del lote; devuelve la lista de resultados (uno por evento, en el orden enviado)."""
    respuesta = cliente.post(URL_EVENTOS, {"eventos": list(eventos)}, format="json")
    assert respuesta.status_code == 200, respuesta.content
    cuerpo = respuesta.json()
    assert cuerpo["version"] == 1
    assert len(cuerpo["resultados"]) == len(eventos)
    return cuerpo["resultados"]


def url_evidencia(evidencia_id) -> str:
    return f"/api/v1/evidencias/{evidencia_id}/"


def subir(cliente, servicio, evento_id, *, evidencia_id=None, tipo="recogida", contenido=JPEG,
          nombre="IMG_0001.jpg", **otros):
    """PUT de una foto en multipart; devuelve (respuesta, id de la evidencia)."""
    evidencia_id = evidencia_id or uuid.uuid4()
    datos = {
        "servicio_id": getattr(servicio, "pk", servicio),
        "evento_id": str(evento_id),
        "tipo": tipo,
        "archivo": SimpleUploadedFile(nombre, contenido, content_type="image/jpeg"),
    }
    datos.update(otros)
    datos = {clave: valor for clave, valor in datos.items() if valor is not None}
    return cliente.put(url_evidencia(evidencia_id), datos, format="multipart"), evidencia_id


@pytest.fixture
def sesion_beto(beto_app):
    token, clave = TokenDispositivo.emitir(beto_app, "celular-de-beto", "Moto G de Beto")
    cliente = cliente_con(clave)
    cliente.token, cliente.clave = token, clave
    return cliente


@pytest.fixture
def media_temporal(settings, tmp_path):
    """Las fotos de la prueba van a una carpeta temporal, no a `backend/media/`."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path
