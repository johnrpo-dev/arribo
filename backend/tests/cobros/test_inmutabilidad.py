"""Estado, valor y factura de una línea solo cambian con las operaciones; el historial es de solo
agregar y nada de cobros se borra.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from cobros import operaciones
from cobros.models import (
    AccionCobro,
    CambioDeCobroNoPermitido,
    HistorialCobro,
    HistorialInmutable,
    LineaCobro,
)
from nucleo.cobro import EstadoCobro

pytestmark = pytest.mark.django_db

C = EstadoCobro
D = Decimal


@pytest.fixture
def por_facturar(linea, usuario):
    operaciones.fijar_valor(linea, D("250000"), actor=usuario)
    return linea


def sin_cambios(linea):
    guardada = LineaCobro.objects.get(pk=linea.pk)
    assert (guardada.estado, guardada.valor, guardada.numero_factura) == (
        C.POR_FACTURAR,
        D("250000"),
        "",
    )
    assert guardada.historial.count() == 2


# --- La línea solo cambia con las operaciones --------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("estado", C.PAGADO),
        ("estado", C.NO_COBRABLE),
        ("valor", D("300000")),
        ("numero_factura", "FE-9"),
    ],
)
def test_cambiar_estado_valor_o_factura_guardando_el_modelo_falla_y_no_deja_historial(
    por_facturar, campo, valor
):
    setattr(por_facturar, campo, valor)
    with pytest.raises(CambioDeCobroNoPermitido, match="solo cambian con las operaciones"):
        por_facturar.save()
    sin_cambios(por_facturar)


def test_tampoco_con_update_fields(por_facturar):
    por_facturar.valor = D("1")
    with pytest.raises(CambioDeCobroNoPermitido):
        por_facturar.save(update_fields=["valor"])
    sin_cambios(por_facturar)


def test_guardar_la_linea_sin_tocar_el_cobro_si_se_puede(por_facturar):
    por_facturar.save()
    sin_cambios(por_facturar)


def test_guardar_una_copia_vieja_no_pisa_un_cambio_hecho_por_las_operaciones(
    por_facturar, usuario
):
    copia_vieja = LineaCobro.objects.get(pk=por_facturar.pk)
    operaciones.facturar(por_facturar, "FE-1", actor=usuario)
    with pytest.raises(CambioDeCobroNoPermitido):
        copia_vieja.save()
    assert LineaCobro.objects.get(pk=por_facturar.pk).estado == C.FACTURADO


def test_una_linea_con_historial_no_se_borra_ni_su_servicio(linea, entregado):
    with pytest.raises(ProtectedError):
        linea.delete()
    with pytest.raises(ProtectedError):
        entregado.delete()
    assert LineaCobro.objects.filter(pk=linea.pk).exists()


# --- Historial de solo agregar -----------------------------------------------------------------


def test_modificar_un_registro_del_historial_falla(por_facturar):
    registro = por_facturar.historial.last()
    registro.valor_nuevo = D("1")
    with pytest.raises(HistorialInmutable, match="solo agregar"):
        registro.save()
    leido = HistorialCobro.objects.get(pk=registro.pk)
    leido.motivo = "otro"
    with pytest.raises(HistorialInmutable):
        leido.save(update_fields=["motivo"])
    assert HistorialCobro.objects.get(pk=registro.pk).valor_nuevo == D("250000")


def test_borrar_un_registro_del_historial_falla(por_facturar):
    registro = por_facturar.historial.last()
    with pytest.raises(HistorialInmutable, match="no se modifica ni se borra"):
        registro.delete()
    assert por_facturar.historial.count() == 2


def test_modificar_o_borrar_el_historial_en_lote_falla(por_facturar):
    registro = por_facturar.historial.last()
    with pytest.raises(HistorialInmutable):
        HistorialCobro.objects.filter(pk=registro.pk).update(valor_nuevo=D("1"))
    with pytest.raises(HistorialInmutable):
        HistorialCobro.objects.all().delete()
    with pytest.raises(HistorialInmutable):
        por_facturar.historial.all().delete()
    registro.motivo = "x"
    # bulk_update abre su transacción sin punto de guardado: se aísla para poder seguir consultando.
    with pytest.raises(HistorialInmutable), transaction.atomic():
        HistorialCobro.objects.bulk_update([registro], ["motivo"])
    assert por_facturar.historial.count() == 2
    assert HistorialCobro.objects.get(pk=registro.pk).valor_nuevo == D("250000")


@pytest.mark.parametrize(
    ("datos", "restriccion"),
    [
        ({"accion": "borrada"}, "historial_cobro_accion_valida"),
        ({"accion": AccionCobro.FACTURA_ANULADA, "motivo": "  "}, "historial_cobro_anulacion_con_motivo"),
        ({"accion": AccionCobro.VALOR, "valor_nuevo": None}, "historial_cobro_cambio_de_valor_con_valor"),
    ],
)
def test_la_base_rechaza_registros_de_historial_incoherentes(linea, datos, restriccion):
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        HistorialCobro.objects.create(linea=linea, **datos)
