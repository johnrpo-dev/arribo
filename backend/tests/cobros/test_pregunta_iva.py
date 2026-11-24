"""La pregunta "¿Lleva IVA?" en Cobros, contra PostgreSQL.

Se pregunta al armar una relación y al facturar una línea suelta, sin respuesta por defecto. Si no
lleva IVA, la relación guarda IVA cero y el total a facturar es el subtotal.
"""
from decimal import Decimal

import pytest

from cobros import facturacion
from cobros.models import RelacionCobro
from configuracion.models import configuracion_vigente
from nucleo.cobro import EstadoCobro
from nucleo.facturacion import FacturaNoCuadra
from nucleo.relacion import EstadoRelacion

from .test_relaciones import estado

pytestmark = pytest.mark.django_db

C, R = EstadoCobro, EstadoRelacion
D = Decimal
ARMAR = "/cobros/relaciones/armar/"
RANGO = {"pagador": None, "desde": "2026-11-01", "hasta": "2026-11-15"}


@pytest.fixture
def facturador(facturacion):
    return facturacion


def rango(cliente, **mas):
    return {**RANGO, "pagador": cliente.pk, **mas}


# --- Relación ------------------------------------------------------------------------------------


def test_la_vista_previa_pregunta_si_lleva_iva_con_el_total_de_cada_caso(
    client, por_facturar, cliente, facturador
):
    por_facturar()
    html = client.get("/cobros/relaciones/", rango(cliente)).content.decode()
    assert "¿Lleva IVA?" in html
    assert "Sí, lleva IVA del 19 %: total $ 214.200" in html
    assert "No lleva IVA: total $ 180.000" in html
    assert 'name="lleva_iva" value="si"' in html
    assert "checked" not in html  # no hay respuesta por defecto


def test_sin_responder_si_lleva_iva_no_se_arma_la_relacion(
    client, por_facturar, cliente, facturador
):
    por_facturar()
    respuesta = client.post(ARMAR, rango(cliente))
    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Responda si lleva IVA." in html
    assert "Armar la relación" in html  # sigue viendo las líneas para responder
    assert not RelacionCobro.objects.exists()


def test_una_relacion_sin_iva_se_factura_por_el_subtotal(
    client, por_facturar, cliente, facturador
):
    linea = por_facturar()
    client.post(ARMAR, rango(cliente, lleva_iva="no"))
    relacion = RelacionCobro.objects.get()
    assert relacion.porcentaje_iva == D("0")

    with pytest.raises(FacturaNoCuadra):
        facturacion.facturar_relacion(relacion, "FE-1", D("214200"), actor=facturador)
    facturacion.facturar_relacion(relacion, "FE-1", D("180000"), actor=facturador)
    assert estado(linea) == C.FACTURADO


def test_una_relacion_con_iva_suma_el_de_la_configuracion(
    client, por_facturar, cliente, facturador
):
    por_facturar()
    client.post(ARMAR, rango(cliente, lleva_iva="si"))
    relacion = RelacionCobro.objects.get()
    assert relacion.porcentaje_iva == D("19")
    facturacion.facturar_relacion(relacion, "FE-2", D("214200"), actor=facturador)
    relacion.refresh_from_db()
    assert relacion.estado == R.FACTURADA


def test_la_relacion_la_orden_y_el_archivo_dicen_sin_iva(client, por_facturar, cliente, facturador):
    por_facturar()
    client.post(ARMAR, rango(cliente, lleva_iva="no"))
    relacion = RelacionCobro.objects.get()
    base = f"/cobros/relaciones/{relacion.pk}/"

    for html in (client.get(base).content.decode(), client.get(base + "orden/").content.decode()):
        assert "Sin IVA" in html
        assert "IVA 19 %" not in html
        assert "214.200" not in html
    archivo = client.get(base + "descargar/").content.decode("utf-8-sig")
    assert "Sin IVA;" in archivo


def test_la_respuesta_queda_aunque_despues_cambie_la_configuracion(
    client, por_facturar, cliente, facturador
):
    por_facturar()
    client.post(ARMAR, rango(cliente, lleva_iva="no"))
    c = configuracion_vigente()
    c.porcentaje_iva = D("5")
    c.save()
    relacion = RelacionCobro.objects.get()
    facturacion.facturar_relacion(relacion, "FE-3", D("180000"), actor=facturador)


# --- Línea suelta ----------------------------------------------------------------------------------


def test_sin_responder_si_lleva_iva_no_se_factura_la_linea(client, por_facturar, facturador):
    linea = por_facturar()
    respuesta = client.post(
        f"/cobros/{linea.pk}/facturar/", {"numero_factura": "FE-4", "total_factura": "214.200"}
    )
    assert "Responda si lleva IVA." in respuesta.content.decode()
    assert estado(linea) == C.POR_FACTURAR


def test_una_linea_sin_iva_se_factura_por_su_valor(client, por_facturar, facturador):
    linea = por_facturar()
    respuesta = client.post(
        f"/cobros/{linea.pk}/facturar/",
        {"numero_factura": "FE-5", "total_factura": "180.000", "lleva_iva": "no"},
        follow=True,
    )
    assert "Facturada con el número FE-5 (sin IVA)" in respuesta.content.decode()
    assert estado(linea) == C.FACTURADO


def test_una_linea_sin_iva_no_acepta_el_total_con_iva(client, por_facturar, facturador):
    linea = por_facturar()
    respuesta = client.post(
        f"/cobros/{linea.pk}/facturar/",
        {"numero_factura": "FE-6", "total_factura": "214.200", "lleva_iva": "no"},
        follow=True,
    )
    assert "$ 34.200 de más" in respuesta.content.decode()
    assert estado(linea) == C.POR_FACTURAR


def test_una_linea_con_iva_se_factura_por_el_total_con_iva(por_facturar, facturador):
    linea = por_facturar()
    with pytest.raises(FacturaNoCuadra):
        facturacion.facturar_linea(linea, "FE-7", D("180000"), actor=facturador, lleva_iva=True)
    facturacion.facturar_linea(linea, "FE-7", D("214200"), actor=facturador, lleva_iva=True)
    assert estado(linea) == C.FACTURADO


def test_quien_no_ve_valores_ve_la_pregunta_sin_cifras(client, por_facturar, facturador):
    linea = por_facturar()
    c = configuracion_vigente()
    c.ven_valores_facturacion = False
    c.save()
    html = client.get(f"/cobros/{linea.pk}/").content.decode()
    assert "Sí, lleva IVA del 19 %" in html
    assert "No lleva IVA" in html
    assert "214.200" not in html
    assert "180.000" not in html
