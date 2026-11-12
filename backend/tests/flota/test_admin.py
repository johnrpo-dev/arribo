"""El admin de la flota abre, no deja borrar y muestra los traslapes en español en vez de fallar."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from flota.models import AsignacionConductorGrua, Conductor, Grua

pytestmark = pytest.mark.django_db

MODELOS = ["grua", "conductor", "asignacionconductorgrua"]


@pytest.mark.parametrize("modelo", MODELOS)
def test_el_admin_abre_la_lista_y_el_formulario(admin_client, modelo):
    assert admin_client.get(f"/admin/flota/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/flota/{modelo}/add/").status_code == 200


def test_el_admin_no_deja_borrar(admin_client):
    grua = Grua.objects.create(placa="GRU001", capacidad=1)
    assert admin_client.get(f"/admin/flota/grua/{grua.pk}/delete/").status_code == 403
    assert Grua.objects.filter(pk=grua.pk).exists()


def test_el_admin_muestra_el_traslape_en_espanol(admin_client):
    ana = Conductor.objects.create(nombre="Ana", celular="3000000001")
    grua1 = Grua.objects.create(placa="GRU001", capacidad=2)
    grua2 = Grua.objects.create(placa="GRU002", capacidad=1)
    AsignacionConductorGrua.objects.create(
        conductor=ana, grua=grua1, inicio=datetime(2026, 11, 1, 8, tzinfo=ZoneInfo("America/Bogota"))
    )

    respuesta = admin_client.post(
        "/admin/flota/asignacionconductorgrua/add/",
        {
            "conductor": ana.pk,
            "grua": grua2.pk,
            "inicio_0": "2026-11-05",
            "inicio_1": "08:00:00",
            "fin_0": "",
            "fin_1": "",
            "motivo": "",
        },
    )

    assert respuesta.status_code == 200  # vuelve al formulario con el error, no un 500
    assert "Ana ya tiene asignada la grúa GRU001" in respuesta.content.decode()
    assert AsignacionConductorGrua.objects.count() == 1
