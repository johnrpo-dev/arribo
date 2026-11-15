"""El admin de la flota abre, no deja borrar y muestra los traslapes en español en vez de fallar."""

import pytest

from flota.models import Grua

pytestmark = pytest.mark.django_db

MODELOS = ["grua", "conductor", "asignacionconductorgrua"]


@pytest.mark.parametrize("modelo", MODELOS)
def test_el_admin_abre_la_lista_pero_no_deja_agregar(admin_client, modelo):
    assert admin_client.get(f"/admin/flota/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/flota/{modelo}/add/").status_code == 403


@pytest.mark.parametrize("modelo", ["grua", "conductor"])
def test_la_marca_de_demostracion_no_se_edita_en_el_admin(admin_client, modelo):
    assert 'name="es_demo"' not in admin_client.get(f"/admin/flota/{modelo}/add/").content.decode()


def test_el_admin_no_deja_borrar(admin_client):
    grua = Grua.objects.create(placa="GRU001", capacidad=1)
    assert admin_client.get(f"/admin/flota/grua/{grua.pk}/delete/").status_code == 403
    assert Grua.objects.filter(pk=grua.pk).exists()

