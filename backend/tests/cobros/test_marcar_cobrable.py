"""Un servicio cancelado no tiene línea de cobro; `marcar_cobrable` se la crea, una sola vez, para el
caso "la grúa se desplazó y el vehículo no estaba".
"""
from decimal import Decimal

import pytest

from cobros import operaciones
from cobros.models import AccionCobro, HistorialCobro, LineaCobro
from cobros.operaciones import EstadoNoCobrable
from nucleo.cobro import EstadoCobro
from nucleo.estados import Estado
from solicitudes import operaciones as op_solicitudes

from .conftest import VALOR

pytestmark = pytest.mark.django_db

E = Estado
C = EstadoCobro


@pytest.fixture
def cancelado(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    op_solicitudes.asignar(servicio, ana, actor=usuario)
    op_solicitudes.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    op_solicitudes.cambiar_estado(
        servicio, E.CANCELADO, actor=usuario, motivo="El vehículo no estaba en el sitio"
    )
    return servicio


def test_un_servicio_cancelado_no_tiene_linea(cancelado):
    assert not LineaCobro.objects.filter(servicio=cancelado).exists()


def test_marcar_cobrable_crea_la_linea_inicial_y_su_historial(cancelado, cliente, usuario):
    linea = operaciones.marcar_cobrable(cancelado, actor=usuario)

    assert (linea.servicio, linea.pagador, linea.posicion) == (cancelado, cliente, 1)
    assert (linea.estado, linea.valor, linea.numero_factura) == (C.SIN_VALOR, None, "")
    registro = linea.historial.get()
    assert (registro.accion, registro.usuario) == (AccionCobro.MARCADA_COBRABLE, usuario)


def test_marcar_cobrable_con_tarifa_nace_por_facturar(cancelado, tarifa_traslado, usuario):
    linea = operaciones.marcar_cobrable(cancelado, actor=usuario)
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, VALOR)
    assert linea.historial.get().valor_nuevo == VALOR


def test_marcar_cobrable_dos_veces_crea_una_sola_linea(cancelado, usuario):
    primera = operaciones.marcar_cobrable(cancelado, actor=usuario)
    segunda = operaciones.marcar_cobrable(cancelado, actor=usuario)
    assert primera == segunda
    assert LineaCobro.objects.filter(servicio=cancelado).count() == 1
    assert HistorialCobro.objects.count() == 1


def test_la_linea_de_un_cancelado_cobrable_sigue_el_ciclo_normal(cancelado, usuario):
    linea = operaciones.marcar_cobrable(cancelado, actor=usuario)
    operaciones.fijar_valor(linea, Decimal(60000), actor=usuario)
    operaciones.facturar(linea, "FE-2001", actor=usuario)
    operaciones.pagar(linea, actor=usuario)
    assert linea.estado == C.PAGADO
    assert linea.historial.count() == 4


@pytest.mark.parametrize("estado", [e for e in Estado if e != E.CANCELADO])
def test_marcar_cobrable_un_servicio_no_cancelado_se_rechaza(crear_servicio, usuario, estado):
    servicio = crear_servicio(estado)
    with pytest.raises(EstadoNoCobrable, match="Solo un servicio cancelado"):
        operaciones.marcar_cobrable(servicio, actor=usuario)
    assert not LineaCobro.objects.exists()
    assert not HistorialCobro.objects.exists()
