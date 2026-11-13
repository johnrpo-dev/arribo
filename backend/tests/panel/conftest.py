"""Usuarios del panel para las pruebas. Los grupos ya existen: los crea la migración de `flota`."""
import itertools

import pytest
from django.contrib.auth.models import Group

CLAVE = "clave-de-prueba-123"


@pytest.fixture
def crear_usuario(django_user_model):
    """Fábrica de usuarios con los roles pedidos (nombres de grupo) y la clave CLAVE."""
    numeros = itertools.count(1)

    def crear(*roles, superusuario=False, **datos):
        datos.setdefault("username", f"usuario{next(numeros)}")
        if superusuario:
            usuario = django_user_model.objects.create_superuser(password=CLAVE, **datos)
        else:
            usuario = django_user_model.objects.create_user(password=CLAVE, **datos)
        for rol in roles:
            usuario.groups.add(Group.objects.get(name=rol))
        return usuario

    return crear
