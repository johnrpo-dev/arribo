"""Datos de las pruebas de "Personal y grúas", siempre contra PostgreSQL. Ana (GRU001) y Beto
(GRU002) vienen de `tests/conftest.py`; los usuarios del panel y la app, de sus carpetas."""
import pytest

# Fixtures de otras carpetas: usuarios del panel y el acceso de Ana a la app.
from tests.api.conftest import ana_app, api, dar_acceso, hash_rapido, sesion  # noqa: F401
from tests.panel.conftest import crear_usuario  # noqa: F401


@pytest.fixture
def administrador(client, crear_usuario):  # noqa: F811
    usuario = crear_usuario("administrador", first_name="Olga")
    client.force_login(usuario)
    return usuario
