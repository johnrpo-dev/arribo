"""Datos de las pruebas de documentos, siempre contra PostgreSQL. Los tipos SOAT, Tecnomecánica y
Licencia de conducción los siembra la migración; Ana (GRU001) y Beto (GRU002) vienen de
`tests/conftest.py`."""
from datetime import timedelta

import pytest

from documentos.consultas import dia_local
from documentos.models import TipoDocumento
from documentos.operaciones import registrar_documento

# Fixtures de otras carpetas: usuarios del panel y la sesión de Ana en la app.
from tests.api.conftest import ana_app, dar_acceso, hash_rapido, sesion  # noqa: F401
from tests.panel.conftest import crear_usuario  # noqa: F401


@pytest.fixture
def soat():
    return TipoDocumento.objects.get(nombre="SOAT")


@pytest.fixture
def tecnomecanica():
    return TipoDocumento.objects.get(nombre="Tecnomecánica")


@pytest.fixture
def licencia():
    return TipoDocumento.objects.get(nombre="Licencia de conducción")


@pytest.fixture
def quien(django_user_model):
    return django_user_model.objects.create_user("administrador-docs")


def en_dias(dias: int):
    """El día de hoy en Medellín más `dias`."""
    return dia_local() + timedelta(days=dias)


@pytest.fixture
def registrar(quien):
    """Registra un documento que vence en `vence_en` días desde hoy (o que aplica desde
    `aplica_desde_en` días), a nombre del usuario `quien`."""

    def registrar_(tipo, sujeto, *, vence_en=None, aplica_desde_en=None, **otros):
        return registrar_documento(
            tipo=tipo,
            sujeto=sujeto,
            por=quien,
            vence=None if vence_en is None else en_dias(vence_en),
            aplica_desde=None if aplica_desde_en is None else en_dias(aplica_desde_en),
            **otros,
        )

    return registrar_
