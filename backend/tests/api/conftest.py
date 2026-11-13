"""Datos de las pruebas de la API, siempre contra PostgreSQL. Usa los de `tests/conftest.py`: Ana
(celular 3000000001) maneja la grúa GRU001 y Beto (3000000002) la GRU002.

Hash rápido: cada ingreso calcula un hash del PIN y el de producción (PBKDF2 con un millón de
vueltas) tarda casi un segundo, así que aquí se usa MD5 para no alargar la suite. Ninguna prueba
depende del algoritmo, salvo `test_el_pin_se_guarda_con_el_hash_de_django_nunca_en_claro`, que
vuelve a poner el de producción.
"""
from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Group
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
