"""Los roles existen como grupos de Django después de migrar."""
import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import Group

pytestmark = pytest.mark.django_db

ROLES = {"administrador", "logistica", "facturacion", "conductor"}
migracion = importlib.import_module("flota.migrations.0002_roles")


def test_los_cuatro_roles_existen_tras_migrar():
    assert set(Group.objects.filter(name__in=ROLES).values_list("name", flat=True)) == ROLES


def test_crear_los_roles_dos_veces_no_los_duplica():
    migracion.crear_roles(apps, None)
    migracion.crear_roles(apps, None)
    assert Group.objects.filter(name__in=ROLES).count() == 4


def test_la_migracion_de_roles_es_reversible():
    migracion.quitar_roles(apps, None)
    assert not Group.objects.filter(name__in=ROLES).exists()
    migracion.crear_roles(apps, None)
    assert Group.objects.filter(name__in=ROLES).count() == 4
