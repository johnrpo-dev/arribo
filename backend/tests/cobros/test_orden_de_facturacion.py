"""Orden de facturación (1a-19b), contra PostgreSQL: el total con IVA, la verificación del total y
del número al registrar la factura, el IVA congelado en la relación, los datos de facturación del
pagador y la orden imprimible."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from cobros import facturacion, operaciones
from cobros.models import RelacionCobro
from configuracion.models import configuracion_vigente
from nucleo.cobro import CobroInvalido, EstadoCobro
from nucleo.facturacion import FacturaNoCuadra, FacturaRepetida
from nucleo.relacion import EstadoRelacion

from .test_relaciones import armar, estado

pytestmark = pytest.mark.django_db

C, R = EstadoCobro, EstadoRelacion
D = Decimal
CON_IVA = D("214200")  # 180.000 + 19 %


@pytest.fixture
def facturador(facturacion):
    return facturacion


def configurar(**campos):
    c = configuracion_vigente()
    for nombre, valor in campos.items():
        setattr(c, nombre, valor)
    c.save()


def relacion_url(relacion, accion=""):
    return f"/cobros/relaciones/{relacion.pk}/" + (f"{accion}/" if accion else "")


# --- Total con IVA -------------------------------------------------------------------------------


def test_la_relacion_muestra_subtotal_iva_y_total(client, por_facturar, cliente, facturador):
    por_facturar()
    por_facturar(valor=D("150000"))
    relacion = armar(cliente, facturador)
    html = client.get(relacion_url(relacion)).content.decode()
    assert "$ 330.000" in html
    assert "IVA 19 %" in html
    assert "$ 62.700" in html
    assert "$ 392.700" in html


def test_el_iva_queda_congelado_al_armar_la_relacion(por_facturar, cliente, facturador):
    linea = por_facturar()
    relacion = armar(cliente, facturador)
    assert relacion.porcentaje_iva == D("19")
    configurar(porcentaje_iva=D("5"))

    with pytest.raises(FacturaNoCuadra):
        facturacion.facturar_relacion(relacion, "FE-1", D("189000"), actor=facturador)
    facturacion.facturar_relacion(relacion, "FE-1", CON_IVA, actor=facturador)
    assert estado(linea) == C.FACTURADO


def test_una_linea_suelta_usa_el_iva_vigente(client, por_facturar, facturador):
    linea = por_facturar()
    configurar(porcentaje_iva=D("0"))
    facturacion.facturar_linea(linea, "FE-2", D("180000"), actor=facturador)
    assert estado(linea) == C.FACTURADO


def test_la_base_no_acepta_un_iva_fuera_de_rango():
    c = configuracion_vigente()
    c.porcentaje_iva = D("150")
    with pytest.raises(IntegrityError), transaction.atomic():
        c.save()


# --- Verificar el total ----------------------------------------------------------------------------


def test_un_total_mal_digitado_no_factura_la_relacion(client, por_facturar, cliente, facturador):
    linea = por_facturar()
    relacion = armar(cliente, facturador)

    respuesta = client.post(
        relacion_url(relacion, "facturar"),
        {"numero_factura": "FE-9", "total_factura": "241.200"},
        follow=True,
    )

    html = respuesta.content.decode()
    assert "No se facturó" in html
    assert "$ 27.000 de más" in html
    relacion.refresh_from_db()
    assert relacion.estado == R.ARMADA
    assert estado(linea) == C.POR_FACTURAR


def test_el_total_exacto_factura_todas_las_lineas_con_el_mismo_numero(
    client, por_facturar, cliente, facturador
):
    a, b = por_facturar(), por_facturar()
    relacion = armar(cliente, facturador)

    client.post(
        relacion_url(relacion, "facturar"), {"numero_factura": "FE-9", "total_factura": "428.400"}
    )

    for linea in (a, b):
        linea.refresh_from_db()
        assert (linea.estado, linea.numero_factura) == (C.FACTURADO, "FE-9")


def test_un_total_mal_digitado_no_factura_la_linea(client, por_facturar, facturador):
    linea = por_facturar()
    respuesta = client.post(
        f"/cobros/{linea.pk}/facturar/",
        {"numero_factura": "FE-3", "total_factura": "180.000", "lleva_iva": "si"},
        follow=True,
    )
    assert "no coincide con el de la orden" in respuesta.content.decode()
    assert estado(linea) == C.POR_FACTURAR


def test_la_linea_muestra_lo_que_hay_que_facturar(client, por_facturar, facturador):
    linea = por_facturar()
    html = client.get(f"/cobros/{linea.pk}/").content.decode()
    assert "¿Lleva IVA?" in html
    assert "Sí, lleva IVA del 19 %: total $ 214.200" in html
    assert "No lleva IVA: total $ 180.000" in html
    assert "Total de la factura" in html


def test_quien_no_ve_valores_factura_sin_que_el_aviso_muestre_cifras(
    client, por_facturar, facturador
):
    linea = por_facturar()
    configurar(ven_valores_facturacion=False)
    respuesta = client.post(
        f"/cobros/{linea.pk}/facturar/",
        {"numero_factura": "FE-4", "total_factura": "100.000", "lleva_iva": "si"},
        follow=True,
    )
    html = respuesta.content.decode()
    assert "no coincide con el de la orden" in html
    assert "214.200" not in html
    assert "180.000" not in html


# --- Número repetido -------------------------------------------------------------------------------


def test_un_numero_ya_registrado_no_se_repite_y_dice_donde(por_facturar, facturador):
    primera, segunda = por_facturar(), por_facturar()
    facturacion.facturar_linea(primera, "FE-7", CON_IVA, actor=facturador)

    with pytest.raises(FacturaRepetida, match=f"servicio N.º {primera.servicio_id}"):
        facturacion.facturar_linea(segunda, " fe-7 ", CON_IVA, actor=facturador)
    assert estado(segunda) == C.POR_FACTURAR


def test_un_numero_de_una_linea_ya_pagada_tampoco_se_repite(por_facturar, cliente, facturador):
    pagada = por_facturar()
    facturacion.facturar_linea(pagada, "FE-8", CON_IVA, actor=facturador)
    operaciones.pagar(pagada, actor=facturador)
    por_facturar()
    relacion = armar(cliente, facturador)

    with pytest.raises(FacturaRepetida):
        facturacion.facturar_relacion(relacion, "FE-8", CON_IVA, actor=facturador)
    relacion.refresh_from_db()
    assert relacion.estado == R.ARMADA


def test_el_numero_de_una_factura_anulada_queda_libre(por_facturar, facturador):
    primera, segunda = por_facturar(), por_facturar()
    facturacion.facturar_linea(primera, "FE-10", CON_IVA, actor=facturador)
    operaciones.anular_factura(primera, "Se registró en el servicio equivocado", actor=facturador)

    facturacion.facturar_linea(segunda, "FE-10", CON_IVA, actor=facturador)
    assert estado(segunda) == C.FACTURADO


def test_solo_se_factura_lo_que_esta_por_facturar(por_facturar, facturador):
    linea = por_facturar(valor=None)
    with pytest.raises(CobroInvalido):
        facturacion.facturar_linea(linea, "FE-11", CON_IVA, actor=facturador)


# --- Datos de facturación del pagador y orden imprimible ----------------------------------------


def test_la_relacion_avisa_que_le_falta_al_pagador_y_los_guarda_en_el_cliente(
    client, por_facturar, cliente, facturador
):
    por_facturar()
    relacion = armar(cliente, facturador)
    html = client.get(relacion_url(relacion)).content.decode()
    assert "le falta: NIT o documento, dirección, ciudad" in html

    respuesta = client.post(
        relacion_url(relacion, "pagador"),
        {
            "razon_social": "Concesionario Los Andes S.A.S.",
            "documento": "900555111-2",
            "direccion": "Cra 50 # 10-20",
            "ciudad": "Medellín",
            "correo_facturacion": "facturas@losandes.example",
        },
    )

    assert respuesta.status_code == 302
    cliente.refresh_from_db()
    assert cliente.documento == "900555111-2"
    assert cliente.nombre_para_facturar == "Concesionario Los Andes S.A.S."
    assert "le falta" not in client.get(relacion_url(relacion)).content.decode()


def test_un_correo_mal_escrito_no_se_guarda(client, por_facturar, cliente, facturador):
    por_facturar()
    relacion = armar(cliente, facturador)
    respuesta = client.post(relacion_url(relacion, "pagador"), {"correo_facturacion": "no-es-correo"})
    assert respuesta.status_code == 200
    cliente.refresh_from_db()
    assert cliente.correo_facturacion == ""


def test_la_orden_trae_empresa_pagador_servicios_y_totales(client, por_facturar, cliente, facturador):
    configurar(empresa_nombre="Grúas del Valle S.A.S.", empresa_nit="901000222-3")
    cliente.documento = "900555111-2"
    cliente.direccion = "Cra 50 # 10-20"
    cliente.ciudad = "Medellín"
    cliente.save()
    linea = por_facturar(referencia="SIN-889")
    relacion = armar(cliente, facturador)

    html = client.get(relacion_url(relacion, "orden")).content.decode()

    assert f"Orden de facturación N.º {relacion.pk}" in html
    assert "No es una factura" in html
    assert "Grúas del Valle S.A.S." in html
    assert "NIT 901000222-3" in html
    assert "900555111-2" in html
    assert "Cra 50 # 10-20, Medellín" in html
    assert f"N.º {linea.servicio_id}" in html
    assert "SIN-889" in html
    assert linea.servicio.vehiculo.placa in html
    assert "$ 180.000" in html
    assert "IVA 19 %" in html
    assert "$ 214.200" in html
    assert "le falta" not in html


def test_sin_datos_de_la_empresa_la_orden_lo_dice(client, por_facturar, cliente, facturador):
    por_facturar()
    relacion = armar(cliente, facturador)
    html = client.get(relacion_url(relacion, "orden")).content.decode()
    assert "Datos de la empresa sin configurar" in html
    assert "Al pagador le falta" in html


def test_la_orden_solo_la_ve_quien_ve_valores(client, por_facturar, cliente, facturador, crear_usuario):
    por_facturar()
    relacion = armar(cliente, facturador)
    configurar(ven_valores_facturacion=False)
    assert client.get(relacion_url(relacion, "orden")).status_code == 403
    assert client.post(relacion_url(relacion, "pagador"), {}).status_code == 403
    client.force_login(crear_usuario("logistica"))
    assert client.get(relacion_url(relacion, "orden")).status_code == 403


def test_la_relacion_armada_guarda_el_iva_y_las_anteriores_usan_el_vigente(
    por_facturar, cliente, facturador
):
    por_facturar()
    relacion = armar(cliente, facturador)
    RelacionCobro.objects.filter(pk=relacion.pk).update(porcentaje_iva=None)  # armada antes del IVA
    relacion.refresh_from_db()
    configurar(porcentaje_iva=D("10"))
    facturacion.facturar_relacion(relacion, "FE-12", D("198000"), actor=facturador)
    relacion.refresh_from_db()
    assert relacion.estado == R.FACTURADA


def test_el_iva_es_19_por_defecto_y_cambiarlo_deja_historial(client, crear_usuario):
    from configuracion.models import HistorialConfiguracion
    from tests.configuracion.test_pantalla import RUTA, datos_validos

    assert configuracion_vigente().porcentaje_iva == D("19")
    client.force_login(crear_usuario("administrador"))
    client.post(RUTA, datos_validos(porcentaje_iva="16", empresa_nombre="Grúas del Valle"))

    assert configuracion_vigente().porcentaje_iva == D("16")
    cambio = HistorialConfiguracion.objects.get(campo="porcentaje_iva")
    assert (cambio.valor_anterior, cambio.valor_nuevo) == ("19.00", "16")
    assert HistorialConfiguracion.objects.filter(campo="empresa_nombre").exists()


def test_el_numero_de_bodega_sale_en_la_orden_el_archivo_y_la_busqueda(
    client, por_facturar, cliente, facturador
):
    from nucleo.exportacion import COLUMNAS

    from .test_relaciones import leer_csv

    linea = por_facturar()
    vehiculo = linea.servicio.vehiculo
    vehiculo.placa, vehiculo.numero_bodega = "", "B-512"
    vehiculo.save()
    relacion = armar(cliente, facturador)

    assert "bodega B-512" in client.get(relacion_url(relacion, "orden")).content.decode()
    filas = leer_csv(client.get(relacion_url(relacion, "descargar")).content)
    assert filas[1][COLUMNAS.index("Número de bodega")] == "B-512"
    assert "bodega B-512" in client.get("/cobros/", {"q": "b-512"}).content.decode()
