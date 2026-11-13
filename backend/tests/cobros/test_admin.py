"""En el admin las líneas de cobro y su historial se consultan, pero no se agregan, editan ni borran."""
from decimal import Decimal

import pytest

from cobros import operaciones
from cobros.models import LineaCobro

pytestmark = pytest.mark.django_db

LISTA = "/admin/cobros/lineacobro/"


@pytest.fixture
def con_historial(linea, usuario):
    operaciones.fijar_valor(linea, Decimal(250000), actor=usuario)
    return linea


def test_la_lista_de_lineas_abre(admin_client, con_historial):
    assert admin_client.get(LISTA).status_code == 200


def test_no_se_agregan_lineas_en_el_admin(admin_client):
    assert admin_client.get(f"{LISTA}add/").status_code == 403


def test_la_linea_y_su_historial_se_ven_pero_no_se_editan(admin_client, con_historial):
    url = f"{LISTA}{con_historial.pk}/change/"
    respuesta = admin_client.get(url)
    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    for campo in ("estado", "valor", "numero_factura", "pagador"):
        assert f'name="{campo}"' not in contenido
    assert "Por facturar" in contenido
    assert "Creada al entregar" in contenido and "Cambio de valor" in contenido

    assert admin_client.post(url, {"valor": "1", "estado": "pagado"}).status_code == 403
    guardada = LineaCobro.objects.get(pk=con_historial.pk)
    assert (guardada.estado, guardada.valor) == ("por_facturar", Decimal(250000))


def test_no_se_borran_lineas_en_el_admin(admin_client, con_historial):
    assert admin_client.get(f"{LISTA}{con_historial.pk}/delete/").status_code == 403
    assert LineaCobro.objects.filter(pk=con_historial.pk).exists()


def test_el_historial_no_tiene_pantalla_propia_para_editarlo(admin_client):
    assert admin_client.get("/admin/cobros/historialcobro/").status_code == 404
