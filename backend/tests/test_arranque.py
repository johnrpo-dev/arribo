"""El esqueleto arranca y el núcleo sigue sin depender de Django."""
import ast
from pathlib import Path

NUCLEO = Path(__file__).resolve().parent.parent / "nucleo"


def test_salud_responde(client):
    respuesta = client.get("/salud/")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_las_pruebas_corren_sobre_postgresql(db):
    from django.db import connection

    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("select current_database()")
        base = cursor.fetchone()[0]
    assert base.startswith("test_"), f"Las pruebas deben usar su propia base, no {base}"


def test_zona_horaria_es_bogota(settings):
    assert settings.TIME_ZONE == "America/Bogota"
    assert settings.USE_TZ is True


def test_el_nucleo_no_importa_django():
    for archivo in NUCLEO.glob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            modulos = []
            if isinstance(nodo, ast.Import):
                modulos = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                modulos = [nodo.module or ""]
            for modulo in modulos:
                assert not modulo.startswith(("django", "rest_framework", "config")), (
                    f"{archivo.name} importa {modulo}: el núcleo debe ser Python puro"
                )
