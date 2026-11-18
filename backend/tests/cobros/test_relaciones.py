"""Relación de cobro (1a-17) contra PostgreSQL: qué líneas entran (pagador, estado y fecha de
servicio en hora de Colombia), la reserva de cada línea en una sola relación armada, facturar,
pagar y descartar la relación con el historial de cada línea, el archivo que se descarga y quién
puede verla."""
import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from cobros import operaciones, relaciones
from cobros.exportacion import EXPORTADORES, exportador_configurado
from cobros.models import AccionCobro, LineaEnRelacion, RelacionCobro
from configuracion.models import FormatoExportacion, configuracion_vigente
from nucleo.cobro import CobroInvalido, EstadoCobro
from nucleo.estados import Estado
from nucleo.exportacion import BOM, COLUMNAS
from nucleo.relacion import EstadoRelacion
from solicitudes.models import EventoEstado

from .conftest import VALOR, guardar_linea

pytestmark = pytest.mark.django_db

C, R = EstadoCobro, EstadoRelacion
NOV_1, NOV_15 = date(2026, 11, 1), date(2026, 11, 15)
EL_5_DE_NOVIEMBRE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


@pytest.fixture
def facturacion(client, crear_usuario):
    usuario = crear_usuario("facturacion", first_name="Laura", last_name="Caja")
    client.force_login(usuario)
    return usuario


@pytest.fixture
def por_facturar(crear_servicio, facturacion):
    """Fábrica: un servicio entregado en `momento` (hora del celular) con su línea por facturar del
    pagador de la solicitud, con `valor`."""

    def crear(momento=EL_5_DE_NOVIEMBRE, valor=VALOR, referencia=""):
        servicio = crear_servicio(Estado.ENTREGADO)
        if referencia:
            servicio.referencia_externa = referencia
            servicio.save(update_fields=["referencia_externa"])
        EventoEstado.objects.create(
            servicio=servicio,
            destino=Estado.ENTREGADO.value,
            origen=EventoEstado.Origen.APP,
            resultado=EventoEstado.Resultado.APLICADO,
            conductor=servicio.conductor,
            hora_dispositivo=momento,
        )
        linea = operaciones.crear_linea_al_entregar(servicio)
        if valor is not None:
            operaciones.fijar_valor(linea, valor, actor=facturacion)
        linea.refresh_from_db()
        return linea

    return crear


def armar(cliente, actor, desde=NOV_1, hasta=NOV_15) -> RelacionCobro:
    return relaciones.armar(cliente, desde, hasta, actor=actor)


def estado(linea) -> C:
    linea.refresh_from_db()
    return C(linea.estado)


# --- Qué líneas entran -------------------------------------------------------------------------


def test_entran_las_por_facturar_del_pagador_en_el_rango(
    por_facturar, cliente, otro_cliente, crear_servicio, facturacion
):
    entra = por_facturar()
    sin_valor = por_facturar(valor=None)
    de_octubre = por_facturar(momento=datetime(2026, 10, 20, 15, 0, tzinfo=UTC))
    de_otro = guardar_linea(
        crear_servicio(Estado.ENTREGADO), otro_cliente, valor=VALOR, estado=C.POR_FACTURAR.value
    )

    relacion = armar(cliente, facturacion)

    assert list(relacion.lineas.all()) == [entra]
    assert relacion.estado == R.ARMADA
    assert list(relaciones.sin_valor(cliente, NOV_1, NOV_15)) == [sin_valor]
    assert de_octubre not in relacion.lineas.all()
    assert de_otro not in relacion.lineas.all()


def test_la_fecha_del_servicio_es_la_de_la_entrega_en_hora_de_colombia(
    por_facturar, cliente, facturacion
):
    # 1 de noviembre a las 3:00 UTC son las 22:00 del 31 de octubre en Medellín.
    linea = por_facturar(momento=datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    assert list(relaciones.candidatas(cliente, NOV_1, NOV_15)) == []
    octubre = list(relaciones.candidatas(cliente, date(2026, 10, 31), date(2026, 10, 31)))
    assert octubre == [linea]
    assert octubre[0].fecha_servicio == date(2026, 10, 31)


def test_los_extremos_del_rango_entran(por_facturar, cliente, facturacion):
    primera = por_facturar(momento=datetime(2026, 11, 1, 5, 0, tzinfo=UTC))  # 00:00 en Colombia
    ultima = por_facturar(momento=datetime(2026, 11, 16, 4, 59, tzinfo=UTC))  # 23:59 del 15
    assert set(armar(cliente, facturacion).lineas.all()) == {primera, ultima}


def test_sin_lineas_no_se_arma_y_no_queda_relacion(cliente, facturacion):
    with pytest.raises(CobroInvalido, match="No hay líneas"):
        armar(cliente, facturacion)
    assert not RelacionCobro.objects.exists()


def test_rango_al_reves_no_se_arma(por_facturar, cliente, facturacion):
    por_facturar()
    with pytest.raises(CobroInvalido, match="antes"):
        armar(cliente, facturacion, desde=NOV_15, hasta=NOV_1)


# --- Reserva -------------------------------------------------------------------------------------


def test_una_linea_no_entra_en_dos_relaciones_armadas(por_facturar, cliente, facturacion):
    linea = por_facturar()
    armar(cliente, facturacion)
    with pytest.raises(CobroInvalido, match="No hay líneas"):
        armar(cliente, facturacion)
    assert linea.relaciones.count() == 1


def test_la_base_impide_reservar_una_linea_en_dos_relaciones(por_facturar, cliente, facturacion):
    linea = por_facturar()
    armar(cliente, facturacion)
    otra = RelacionCobro.objects.create(
        pagador=cliente, desde=NOV_1, hasta=NOV_15, estado=R.ARMADA.value, creada_por=facturacion
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        LineaEnRelacion.objects.create(relacion=otra, linea=linea)


def test_una_linea_reservada_no_se_factura_suelta(client, por_facturar, cliente, facturacion):
    linea = por_facturar()
    relacion = armar(cliente, facturacion)

    with pytest.raises(operaciones.LineaReservada, match=f"N.º {relacion.pk}"):
        operaciones.facturar(linea, "FE-1", actor=facturacion)

    html = client.get(f"/cobros/{linea.pk}/").content.decode()
    assert f"/cobros/relaciones/{relacion.pk}/" in html
    assert "Marcar facturada" not in html
    client.post(f"/cobros/{linea.pk}/facturar/", {"numero_factura": "FE-1"})
    assert estado(linea) == C.POR_FACTURAR


# --- Facturar, pagar, descartar ---------------------------------------------------------------


def test_facturar_la_relacion_factura_cada_linea_con_su_historial(
    por_facturar, cliente, facturacion
):
    a, b = por_facturar(), por_facturar(valor=Decimal(95000))
    relacion = relaciones.facturar(armar(cliente, facturacion), " FE-300 ", actor=facturacion)

    assert (relacion.estado, relacion.numero_factura) == (R.FACTURADA, "FE-300")
    assert relacion.cerrada_por == facturacion
    for linea in (a, b):
        assert estado(linea) == C.FACTURADO
        assert linea.numero_factura == "FE-300"
        registro = linea.historial.filter(accion=AccionCobro.FACTURADA).get()
        assert (registro.numero_factura, registro.usuario) == ("FE-300", facturacion)
    assert not LineaEnRelacion.objects.filter(reservada=True).exists()


def test_facturar_exige_numero_y_no_toca_las_lineas(por_facturar, cliente, facturacion):
    linea = por_facturar()
    relacion = armar(cliente, facturacion)
    with pytest.raises(CobroInvalido, match="número"):
        relaciones.facturar(relacion, "  ", actor=facturacion)
    assert estado(linea) == C.POR_FACTURAR
    relacion.refresh_from_db()
    assert relacion.estado == R.ARMADA


def test_pagar_marca_pagadas_las_lineas_y_avisa_la_que_ya_no_tiene_la_factura(
    por_facturar, cliente, facturacion
):
    a, b = por_facturar(), por_facturar()
    relacion = relaciones.facturar(armar(cliente, facturacion), "FE-300", actor=facturacion)
    operaciones.anular_factura(b, "Valor equivocado", actor=facturacion)

    pago = relaciones.pagar(relacion, actor=facturacion)

    assert pago.relacion.estado == R.PAGADA
    assert estado(a) == C.PAGADO
    assert estado(b) == C.POR_FACTURAR
    assert pago.sin_marcar == [b.servicio_id]


def test_solo_se_paga_una_relacion_facturada(por_facturar, cliente, facturacion):
    por_facturar()
    with pytest.raises(CobroInvalido, match="facturada"):
        relaciones.pagar(armar(cliente, facturacion), actor=facturacion)


def test_descartar_exige_motivo_y_libera_las_lineas(por_facturar, cliente, facturacion):
    linea = por_facturar()
    relacion = armar(cliente, facturacion)
    with pytest.raises(CobroInvalido, match="motivo"):
        relaciones.descartar(relacion, "", actor=facturacion)

    relaciones.descartar(relacion, "Fechas equivocadas", actor=facturacion)
    relacion.refresh_from_db()
    assert (relacion.estado, relacion.motivo_descarte) == (R.DESCARTADA, "Fechas equivocadas")
    assert estado(linea) == C.POR_FACTURAR
    # Libre otra vez: entra en una relación nueva, y la descartada la sigue mostrando.
    nueva = armar(cliente, facturacion)
    assert list(nueva.lineas.all()) == [linea]
    assert list(relacion.lineas.all()) == [linea]


def test_una_facturada_no_se_descarta(por_facturar, cliente, facturacion):
    por_facturar()
    relacion = relaciones.facturar(armar(cliente, facturacion), "FE-1", actor=facturacion)
    with pytest.raises(CobroInvalido, match="armada"):
        relaciones.descartar(relacion, "Tarde", actor=facturacion)


def test_si_anulan_la_factura_de_una_linea_puede_entrar_en_otra_relacion(
    por_facturar, cliente, facturacion
):
    linea = por_facturar()
    relaciones.facturar(armar(cliente, facturacion), "FE-1", actor=facturacion)
    operaciones.anular_factura(linea, "Valor equivocado", actor=facturacion)
    assert list(armar(cliente, facturacion).lineas.all()) == [linea]


def test_la_base_exige_numero_en_una_relacion_facturada(cliente, facturacion):
    with pytest.raises(IntegrityError), transaction.atomic():
        RelacionCobro.objects.create(
            pagador=cliente, desde=NOV_1, hasta=NOV_15, estado=R.FACTURADA.value
        )


def test_la_base_exige_rango_en_orden(cliente):
    with pytest.raises(IntegrityError), transaction.atomic():
        RelacionCobro.objects.create(
            pagador=cliente, desde=NOV_15, hasta=NOV_1, estado=R.ARMADA.value
        )


# --- Archivo --------------------------------------------------------------------------------------


def test_cada_formato_de_la_configuracion_tiene_su_exportador():
    assert set(EXPORTADORES) == set(FormatoExportacion.values)
    assert exportador_configurado().extension == "csv"


def leer_csv(contenido: bytes) -> list[list[str]]:
    texto = contenido.decode("utf-8")
    assert texto.startswith(BOM)
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


def test_el_archivo_trae_cada_linea_con_numero_de_caso_y_el_total(
    client, por_facturar, cliente, facturacion
):
    a = por_facturar(referencia="SIN-889")
    b = por_facturar(valor=Decimal("95000.50"), momento=datetime(2026, 11, 7, 15, tzinfo=UTC))
    relacion = armar(cliente, facturacion)

    respuesta = client.get(f"/cobros/relaciones/{relacion.pk}/descargar/")

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "text/csv; charset=utf-8"
    assert f'filename="relacion-{relacion.pk}-' in respuesta["Content-Disposition"]
    filas = leer_csv(respuesta.content)
    assert filas[0] == list(COLUMNAS)
    columna = {nombre: i for i, nombre in enumerate(COLUMNAS)}
    primera, segunda = filas[1], filas[2]
    assert primera[columna["Servicio"]] == str(a.servicio_id)
    assert primera[columna["Número de caso"]] == "SIN-889"
    assert primera[columna["Fecha del servicio"]] == "05/11/2026"
    assert primera[columna["Pagador"]] == cliente.nombre
    assert primera[columna["Placa"]] == a.servicio.vehiculo.placa
    assert primera[columna["Valor"]] == "180000"
    assert segunda[columna["Servicio"]] == str(b.servicio_id)
    assert segunda[columna["Valor"]] == "95000,50"
    assert filas[3][0] == "Total"
    assert filas[3][-1] == "275000,50"


def test_el_archivo_de_una_facturada_lleva_el_numero_de_factura(
    client, por_facturar, cliente, facturacion
):
    por_facturar()
    relacion = relaciones.facturar(armar(cliente, facturacion), "FE-300", actor=facturacion)
    filas = leer_csv(client.get(f"/cobros/relaciones/{relacion.pk}/descargar/").content)
    assert filas[1][COLUMNAS.index("Factura")] == "FE-300"


# --- Pantallas ------------------------------------------------------------------------------------


def test_la_vista_previa_muestra_las_lineas_el_total_y_las_que_quedan_por_fuera(
    client, por_facturar, cliente, facturacion
):
    entra = por_facturar(referencia="SIN-889")
    sin_valor = por_facturar(valor=None)
    respuesta = client.get(
        "/cobros/relaciones/",
        {"pagador": cliente.pk, "desde": "2026-11-01", "hasta": "2026-11-15"},
    )
    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert f"/cobros/{entra.pk}/" in html
    assert "SIN-889" in html
    assert "$ 180.000" in html
    assert "Quedan por fuera" in html
    assert f"/cobros/{sin_valor.pk}/" in html
    assert not RelacionCobro.objects.exists()  # ver no arma


def test_armar_facturar_y_pagar_desde_el_panel(client, por_facturar, cliente, facturacion):
    linea = por_facturar()
    respuesta = client.post(
        "/cobros/relaciones/armar/",
        {"pagador": cliente.pk, "desde": "2026-11-01", "hasta": "2026-11-15"},
    )
    relacion = RelacionCobro.objects.get()
    assert respuesta.status_code == 302
    assert respuesta["Location"] == f"/cobros/relaciones/{relacion.pk}/"
    html = client.get(respuesta["Location"]).content.decode()
    assert "Armada" in html
    assert "$ 180.000" in html

    client.post(f"/cobros/relaciones/{relacion.pk}/facturar/", {"numero_factura": "FE-9"})
    assert estado(linea) == C.FACTURADO
    client.post(f"/cobros/relaciones/{relacion.pk}/pagar/")
    assert estado(linea) == C.PAGADO
    relacion.refresh_from_db()
    assert relacion.estado == R.PAGADA
    assert "FE-9" in client.get("/cobros/relaciones/").content.decode()


def test_descartar_sin_motivo_desde_el_panel_no_descarta(client, por_facturar, cliente, facturacion):
    por_facturar()
    relacion = armar(cliente, facturacion)
    respuesta = client.post(f"/cobros/relaciones/{relacion.pk}/descartar/", {"motivo": ""})
    assert respuesta.status_code == 200
    relacion.refresh_from_db()
    assert relacion.estado == R.ARMADA


def test_quien_no_ve_valores_no_entra_a_las_relaciones(client, por_facturar, cliente, facturacion):
    por_facturar()
    relacion = armar(cliente, facturacion)
    c = configuracion_vigente()
    c.ven_valores_facturacion = False
    c.save()

    for ruta in (
        "/cobros/relaciones/",
        f"/cobros/relaciones/{relacion.pk}/",
        f"/cobros/relaciones/{relacion.pk}/descargar/",
    ):
        assert client.get(ruta).status_code == 403, ruta
    assert client.post(
        f"/cobros/relaciones/{relacion.pk}/facturar/", {"numero_factura": "FE-1"}
    ).status_code == 403
    assert "Relaciones de cobro" not in client.get("/cobros/").content.decode()


def test_logistica_no_entra_a_las_relaciones(client, crear_usuario):
    client.force_login(crear_usuario("logistica"))
    assert client.get("/cobros/relaciones/").status_code == 403
