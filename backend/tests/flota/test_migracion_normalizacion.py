"""La migración 0003 de flota normaliza placas y celulares ya guardados antes de exigir el formato."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ANTES = [("flota", "0002_roles")]
DESPUES = [("flota", "0003_placa_y_celular_normalizados_y_es_demo")]


def _migrar(destino):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(destino)
    return executor.loader.project_state(destino).apps


def _volver_a_la_ultima():
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.fixture
def antes_de_la_0003(transactional_db):
    apps = _migrar(ANTES)
    yield apps
    _volver_a_la_ultima()


def test_la_migracion_normaliza_placas_y_celulares_existentes(antes_de_la_0003):
    apps = antes_de_la_0003
    apps.get_model("flota", "Grua").objects.create(placa="ABC-123", capacidad=1)
    apps.get_model("flota", "Conductor").objects.create(nombre="Ana", celular="+57 300 123 4567")
    apps.get_model("flota", "Conductor").objects.create(nombre="Beto", celular="300 12")

    apps = _migrar(DESPUES)

    assert list(apps.get_model("flota", "Grua").objects.values_list("placa", flat=True)) == [
        "ABC123"
    ]
    celulares = dict(apps.get_model("flota", "Conductor").objects.values_list("nombre", "celular"))
    # Un celular corto no se puede validar, pero al menos queda solo con dígitos.
    assert celulares == {"Ana": "3001234567", "Beto": "30012"}
    assert not apps.get_model("flota", "Grua").objects.get().es_demo


def test_la_migracion_se_detiene_si_dos_placas_quedan_iguales(antes_de_la_0003):
    Grua = antes_de_la_0003.get_model("flota", "Grua")
    Grua.objects.create(placa="ABC-123", capacidad=1)
    Grua.objects.create(placa="ABC123", capacidad=2)

    with pytest.raises(RuntimeError, match="quedan iguales al normalizar"):
        _migrar(DESPUES)
    assert sorted(Grua.objects.values_list("placa", flat=True)) == ["ABC-123", "ABC123"]
    Grua.objects.all().delete()  # solo para poder volver a migrar al final de la prueba
