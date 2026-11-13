"""En el admin las alertas se consultan y se marcan como resueltas; no se agregan, editan ni borran."""
import pytest

from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import abrir_alerta

pytestmark = pytest.mark.django_db

LISTA = "/admin/alertas/alerta/"


@pytest.fixture
def alerta(ana):
    return abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "La app de Ana envió algo ilegible.")


def test_la_lista_de_alertas_abre_y_muestra_el_mensaje(admin_client, alerta):
    respuesta = admin_client.get(LISTA)
    assert respuesta.status_code == 200
    assert "La app de Ana envió algo ilegible." in respuesta.content.decode()


def test_no_se_agregan_ni_se_borran_alertas_en_el_admin(admin_client, alerta):
    assert admin_client.get(f"{LISTA}add/").status_code == 403
    assert admin_client.get(f"{LISTA}{alerta.pk}/delete/").status_code == 403
    assert Alerta.objects.filter(pk=alerta.pk).exists()


def test_la_alerta_se_ve_pero_no_se_edita(admin_client, alerta):
    url = f"{LISTA}{alerta.pk}/change/"
    assert admin_client.get(url).status_code == 200
    assert admin_client.post(url, {"mensaje": "otro"}).status_code == 403
    assert Alerta.objects.get(pk=alerta.pk).mensaje == "La app de Ana envió algo ilegible."


def test_la_accion_del_admin_marca_las_alertas_como_resueltas(admin_client, admin_user, alerta):
    respuesta = admin_client.post(
        LISTA, {"action": "resolver", "_selected_action": [alerta.pk]}, follow=True
    )

    assert respuesta.status_code == 200
    assert "Alertas resueltas: 1." in respuesta.content.decode()
    alerta.refresh_from_db()
    assert not alerta.abierta
    assert alerta.resuelta_por == admin_user
