"""Pantallas de cobro (1a-16b) contra PostgreSQL: la lista y la línea en la sección Cobros, el
valor digitado o propuesto por tarifa, facturar, pagar y anular con su historial, los servicios
cancelados que se marcan cobrables y quién ve los valores según la configuración."""
from decimal import Decimal

import pytest

from clientes.models import Tarifa
from cobros import operaciones
from cobros.models import AccionCobro, HistorialCobro, LineaCobro
from configuracion.models import configuracion_vigente
from nucleo.cobro import EstadoCobro
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones as op_solicitudes

from .conftest import VALOR

pytestmark = pytest.mark.django_db

C = EstadoCobro


@pytest.fixture
def facturacion(client, crear_usuario):
    usuario = crear_usuario("facturacion", first_name="Laura", last_name="Caja")
    client.force_login(usuario)
    return usuario


def url(linea, accion=""):
    return f"/cobros/{linea.pk}/{accion + '/' if accion else ''}"


def html_de(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    return respuesta.content.decode()


def configurar(**campos):
    c = configuracion_vigente()
    for campo, valor in campos.items():
        setattr(c, campo, valor)
    c.save()


def ultima(linea, accion) -> HistorialCobro:
    return linea.historial.filter(accion=accion).latest("pk")


# --- Lista -------------------------------------------------------------------------------------


def test_la_lista_muestra_las_pendientes_con_su_valor_para_facturacion(
    client, facturacion, linea, crear_servicio
):
    otra = operaciones.crear_linea_al_entregar(crear_servicio(Estado.ENTREGADO))
    operaciones.fijar_valor(otra, VALOR, actor=facturacion)

    html = html_de(client, "/cobros/")
    assert url(linea) in html
    assert url(otra) in html
    assert "$ 180.000" in html
    assert "Sin valor" in html
    assert "Por facturar" in html
    assert 'Pendientes <span class="pestana-cuenta">2</span>' in html


def test_cada_pestana_trae_solo_su_estado(client, facturacion, linea, crear_servicio):
    pagada = operaciones.crear_linea_al_entregar(crear_servicio(Estado.ENTREGADO))
    operaciones.fijar_valor(pagada, VALOR, actor=facturacion)
    operaciones.facturar(pagada, "FE-10", actor=facturacion)
    operaciones.pagar(pagada, actor=facturacion)

    pagadas = html_de(client, "/cobros/?filtro=pagadas")
    assert url(pagada) in pagadas
    assert url(linea) not in pagadas
    pendientes = html_de(client, "/cobros/")
    assert url(linea) in pendientes
    assert url(pagada) not in pendientes


def test_se_busca_por_placa_y_por_numero_de_factura(client, facturacion, linea, crear_servicio):
    otra = operaciones.crear_linea_al_entregar(crear_servicio(Estado.ENTREGADO))
    operaciones.fijar_valor(otra, VALOR, actor=facturacion)
    operaciones.facturar(otra, "FE-777", actor=facturacion)

    por_factura = html_de(client, "/cobros/?filtro=todas&q=fe-777")
    assert url(otra) in por_factura
    assert url(linea) not in por_factura
    placa = linea.servicio.vehiculo.placa
    assert url(linea) in html_de(client, f"/cobros/?filtro=todas&q={placa.lower()}")


def test_logistica_no_entra_a_cobros(client, crear_usuario, linea):
    client.force_login(crear_usuario("logistica"))
    assert client.get("/cobros/").status_code == 403
    assert client.get(url(linea)).status_code == 403
    assert client.post(url(linea, "valor"), {"valor": "1"}).status_code == 403


# --- Valor -------------------------------------------------------------------------------------


def test_digitar_el_valor_lo_deja_por_facturar_con_historial_de_quien(client, facturacion, linea):
    respuesta = client.post(url(linea, "valor"), {"valor": "$ 180.000"})
    assert respuesta.status_code == 302
    linea.refresh_from_db()
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, Decimal(180000))
    registro = ultima(linea, AccionCobro.VALOR)
    assert (registro.usuario, registro.valor_anterior) == (facturacion, None)

    html = html_de(client, url(linea))
    assert "$ 180.000" in html
    assert "Laura Caja" in html
    assert 'sin valor</span> → <span class="dinero">$ 180.000' in html


def test_ajustar_el_valor_guarda_el_anterior_y_se_ve_en_el_historial(client, facturacion, linea):
    client.post(url(linea, "valor"), {"valor": "180000"})
    client.post(url(linea, "valor"), {"valor": "200.000"})
    registro = ultima(linea, AccionCobro.VALOR)
    assert (registro.valor_anterior, registro.valor_nuevo) == (Decimal(180000), Decimal(200000))
    assert "$ 180.000</span> → <span class=\"dinero\">$ 200.000" in html_de(client, url(linea))


def test_un_valor_mal_escrito_no_cambia_nada_y_dice_por_que(client, facturacion, linea):
    respuesta = client.post(url(linea, "valor"), {"valor": "ciento ochenta"})
    assert respuesta.status_code == 200
    assert "Escriba el valor en números" in respuesta.content.decode()
    linea.refresh_from_db()
    assert linea.estado == C.SIN_VALOR
    assert not linea.historial.filter(accion=AccionCobro.VALOR).exists()


def test_cero_no_es_un_valor(client, facturacion, linea):
    respuesta = client.post(url(linea, "valor"), {"valor": "0"}, follow=True)
    assert "No se guardó" in respuesta.content.decode()
    linea.refresh_from_db()
    assert linea.estado == C.SIN_VALOR


def test_la_tarifa_vigente_se_propone_en_el_campo(client, facturacion, linea, cliente):
    """La línea nació sin valor (no había tarifa); la tarifa se creó después."""
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=VALOR)
    html = html_de(client, url(linea))
    assert "Tarifa vigente" in html
    assert "$ 180.000" in html
    assert 'value="180.000"' in html
    linea.refresh_from_db()
    assert linea.estado == C.SIN_VALOR  # proponer no es guardar


def test_la_linea_que_nace_con_tarifa_ya_esta_por_facturar(
    client, facturacion, tarifa_traslado, entregado
):
    nueva = operaciones.crear_linea_al_entregar(entregado)
    assert (nueva.estado, nueva.valor) == (C.POR_FACTURAR, VALOR)
    assert "$ 180.000" in html_de(client, url(nueva))


def test_el_valor_no_cambia_despues_de_facturar(client, facturacion, linea):
    operaciones.fijar_valor(linea, VALOR, actor=facturacion)
    operaciones.facturar(linea, "FE-1", actor=facturacion)
    assert "Guardar valor" not in html_de(client, url(linea))
    respuesta = client.post(url(linea, "valor"), {"valor": "1"}, follow=True)
    assert "No se guardó" in respuesta.content.decode()
    linea.refresh_from_db()
    assert (linea.estado, linea.valor) == (C.FACTURADO, VALOR)


# --- Facturar, pagar y anular ------------------------------------------------------------------


def test_facturar_exige_numero(client, facturacion, linea):
    operaciones.fijar_valor(linea, VALOR, actor=facturacion)
    respuesta = client.post(url(linea, "facturar"), {"numero_factura": "   "})
    assert "Escriba el número de factura" in respuesta.content.decode()
    linea.refresh_from_db()
    assert linea.estado == C.POR_FACTURAR


def test_facturar_pagar_y_todo_queda_en_el_historial(client, facturacion, linea):
    operaciones.fijar_valor(linea, VALOR, actor=facturacion)
    client.post(url(linea, "facturar"), {"numero_factura": " FE-120 "})
    linea.refresh_from_db()
    assert (linea.estado, linea.numero_factura) == (C.FACTURADO, "FE-120")

    client.post(url(linea, "pagar"))
    linea.refresh_from_db()
    assert linea.estado == C.PAGADO
    assert list(linea.historial.values_list("accion", flat=True)) == [
        AccionCobro.CREADA,
        AccionCobro.VALOR,
        AccionCobro.FACTURADA,
        AccionCobro.PAGADA,
    ]
    html = html_de(client, url(linea))
    assert "Pagada" in html
    assert "FE-120" in html
    assert "Marcar pagada" not in html  # ya no hay nada que hacer


def test_no_se_factura_una_linea_sin_valor(client, facturacion, linea):
    respuesta = client.post(url(linea, "facturar"), {"numero_factura": "FE-1"}, follow=True)
    assert "No se guardó" in respuesta.content.decode()
    linea.refresh_from_db()
    assert linea.estado == C.SIN_VALOR


def test_anular_exige_motivo_y_guarda_el_numero_anulado(client, facturacion, linea):
    operaciones.fijar_valor(linea, VALOR, actor=facturacion)
    operaciones.facturar(linea, "FE-9", actor=facturacion)

    sin_motivo = client.post(url(linea, "anular"), {"motivo": " "})
    assert "Escriba por qué se anula" in sin_motivo.content.decode()
    linea.refresh_from_db()
    assert linea.estado == C.FACTURADO

    client.post(url(linea, "anular"), {"motivo": "Se facturó al cliente equivocado"})
    linea.refresh_from_db()
    assert (linea.estado, linea.numero_factura) == (C.POR_FACTURAR, "")
    registro = ultima(linea, AccionCobro.FACTURA_ANULADA)
    assert (registro.numero_factura, registro.usuario) == ("FE-9", facturacion)
    html = html_de(client, url(linea))
    assert "Se facturó al cliente equivocado" in html
    assert "FE-9" in html


def test_las_acciones_solo_aceptan_post(client, facturacion, linea):
    for accion in ("valor", "facturar", "pagar", "anular"):
        assert client.get(url(linea, accion)).status_code == 405


# --- Cancelados --------------------------------------------------------------------------------


def test_un_cancelado_asignado_se_marca_cobrable_y_nace_su_linea(
    client, facturacion, crear_servicio, usuario
):
    asignado = crear_servicio(Estado.ASIGNADO)
    op_solicitudes.cambiar_estado(
        asignado, Estado.CANCELADO, actor=usuario, motivo="El vehículo no estaba"
    )
    sin_asignar = crear_servicio(Estado.PENDIENTE_ASIGNAR)
    op_solicitudes.cambiar_estado(
        sin_asignar, Estado.CANCELADO, actor=usuario, motivo="El cliente desistió"
    )

    html = html_de(client, "/cobros/?filtro=cancelados")
    assert f"/cobros/servicios/{asignado.pk}/cobrable/" in html
    assert "El vehículo no estaba" in html
    assert f"/cobros/servicios/{sin_asignar.pk}/cobrable/" not in html  # nunca salió una grúa

    respuesta = client.post(f"/cobros/servicios/{asignado.pk}/cobrable/")
    linea = LineaCobro.objects.get(servicio=asignado)
    assert respuesta["Location"] == url(linea)
    assert ultima(linea, AccionCobro.MARCADA_COBRABLE).usuario == facturacion
    html = html_de(client, "/cobros/?filtro=cancelados")
    assert f"/cobros/servicios/{asignado.pk}/cobrable/" not in html


def test_un_servicio_que_no_esta_cancelado_no_se_marca_cobrable(
    client, facturacion, crear_servicio
):
    asignado = crear_servicio(Estado.ASIGNADO)
    respuesta = client.post(f"/cobros/servicios/{asignado.pk}/cobrable/", follow=True)
    assert "No se marcó cobrable" in respuesta.content.decode()
    assert not LineaCobro.objects.filter(servicio=asignado).exists()


# --- Quién ve los valores ----------------------------------------------------------------------


def test_logistica_no_ve_valores_en_el_detalle_con_la_configuracion_por_defecto(
    client, crear_usuario, linea
):
    operaciones.fijar_valor(linea, VALOR, actor=None)
    client.force_login(crear_usuario("logistica"))
    html = html_de(client, f"/solicitudes/{linea.servicio.solicitud_id}/")
    assert "Por facturar" in html  # el estado de cobro sí
    assert "180.000" not in html
    assert "180000" not in html
    assert url(linea) not in html  # no entra a Cobros: no hay enlace


def test_logistica_ve_el_valor_si_la_configuracion_lo_permite(client, crear_usuario, linea):
    operaciones.fijar_valor(linea, VALOR, actor=None)
    configurar(ven_valores_logistica=True)
    client.force_login(crear_usuario("logistica"))
    assert "$ 180.000" in html_de(client, f"/solicitudes/{linea.servicio.solicitud_id}/")


def test_el_administrador_ve_el_valor_y_el_enlace_al_cobro_desde_el_detalle(
    client, crear_usuario, linea
):
    operaciones.fijar_valor(linea, VALOR, actor=None)
    client.force_login(crear_usuario("administrador"))
    html = html_de(client, f"/solicitudes/{linea.servicio.solicitud_id}/")
    assert "$ 180.000" in html
    assert url(linea) in html


def test_facturacion_sin_permiso_de_valores_no_los_ve_ni_los_cambia(client, facturacion, linea):
    operaciones.fijar_valor(linea, VALOR, actor=facturacion)
    configurar(ven_valores_facturacion=False)

    for ruta in ("/cobros/", url(linea)):
        html = html_de(client, ruta)
        assert "180.000" not in html, ruta
        assert "180000" not in html, ruta
    assert "Guardar valor" not in html_de(client, url(linea))
    assert client.post(url(linea, "valor"), {"valor": "1"}).status_code == 403
    linea.refresh_from_db()
    assert linea.valor == VALOR

    # Facturar no muestra ni cambia el valor: lo puede hacer.
    client.post(url(linea, "facturar"), {"numero_factura": "FE-5"})
    linea.refresh_from_db()
    assert linea.estado == C.FACTURADO


def test_la_tarifa_no_se_propone_a_quien_no_ve_valores(client, facturacion, linea, cliente):
    Tarifa.objects.create(cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=VALOR)
    configurar(ven_valores_facturacion=False)
    html = html_de(client, url(linea))
    assert "Tarifa vigente" not in html
    assert "180.000" not in html
