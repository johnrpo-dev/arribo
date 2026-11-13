"""La línea de cobro nace cuando el servicio queda Entregado, desde el panel o desde la app, en la
misma transacción del cambio de estado. Una sola vez, con el pagador de la solicitud y la tarifa.
"""
import ast
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import IntegrityError

from clientes.models import Tarifa
from cobros import operaciones
from cobros.models import AccionCobro, HistorialCobro, LineaCobro
from cobros.operaciones import EstadoNoCobrable
from nucleo.cobro import EstadoCobro
from nucleo.cobro import LineaCobro as LineaNucleo
from nucleo.estados import Estado
from nucleo.sincronizacion import Resultado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones as op_solicitudes
from solicitudes.models import EventoEstado, Servicio
from solicitudes.operaciones import aplicar_evento_del_conductor, aplicar_lote_del_conductor
from solicitudes.senales import servicio_entregado

from ..conftest import crear_solicitud
from .conftest import VALOR

pytestmark = pytest.mark.django_db

E = Estado
C = EstadoCobro
D = Decimal
SOLICITUDES = Path(__file__).resolve().parents[2] / "solicitudes"


def unica_linea(servicio) -> LineaCobro:
    lineas = list(LineaCobro.objects.filter(servicio=servicio))
    assert len(lineas) == 1, f"Se esperaba una línea y hay {len(lineas)}"
    return lineas[0]


def entregar_desde_el_panel(servicio, actor):
    return op_solicitudes.cambiar_estado(servicio, E.ENTREGADO, actor=actor, nombre_quien="Portería")


# --- Desde el panel ----------------------------------------------------------------------------


def test_al_entregar_desde_el_panel_nace_la_linea_sin_valor(crear_servicio, cliente, usuario):
    servicio = crear_servicio(E.RECOGIDO)
    entregar_desde_el_panel(servicio, usuario)

    linea = unica_linea(servicio)
    assert (linea.pagador, linea.posicion) == (cliente, 1)
    assert (linea.estado, linea.valor, linea.numero_factura) == (C.SIN_VALOR, None, "")
    registro = linea.historial.get()
    assert registro.accion == AccionCobro.CREADA
    assert (registro.valor_anterior, registro.valor_nuevo, registro.usuario) == (None, None, usuario)


def test_con_tarifa_vigente_la_linea_nace_por_facturar_con_ese_valor(
    crear_servicio, tarifa_traslado, usuario
):
    servicio = crear_servicio(E.RECOGIDO)
    entregar_desde_el_panel(servicio, usuario)

    linea = unica_linea(servicio)
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, VALOR)
    assert linea.historial.get().valor_nuevo == VALOR


def test_la_linea_es_del_pagador_de_la_solicitud_con_su_tarifa(
    crear_servicio, cliente, otro_cliente, tarifa_traslado, usuario
):
    """El solicitante tiene tarifa, pero paga otro cliente: cuenta la tarifa del pagador."""
    Tarifa.objects.create(cliente=otro_cliente, tipo_servicio=TipoServicio.TRASLADO, valor=D("95000"))
    solicitud = crear_solicitud(cliente, pagador=otro_cliente)
    servicio = crear_servicio(E.RECOGIDO, solicitud_de=solicitud)
    entregar_desde_el_panel(servicio, usuario)

    linea = unica_linea(servicio)
    assert (linea.pagador, linea.estado, linea.valor) == (otro_cliente, C.POR_FACTURAR, D("95000"))


def test_sin_tarifa_del_pagador_la_linea_nace_sin_valor(
    crear_servicio, cliente, otro_cliente, tarifa_traslado, usuario
):
    solicitud = crear_solicitud(cliente, pagador=otro_cliente)
    servicio = crear_servicio(E.RECOGIDO, solicitud_de=solicitud)
    entregar_desde_el_panel(servicio, usuario)
    assert unica_linea(servicio).estado == C.SIN_VALOR


@pytest.mark.parametrize(
    "tarifa",
    [
        {"tipo_servicio": TipoServicio.DESVARE, "vigente": True},
        {"tipo_servicio": TipoServicio.TRASLADO, "vigente": False},
    ],
    ids=["de_otro_tipo", "no_vigente"],
)
def test_una_tarifa_de_otro_tipo_o_no_vigente_no_se_propone(
    crear_servicio, cliente, usuario, tarifa
):
    Tarifa.objects.create(cliente=cliente, valor=VALOR, **tarifa)
    servicio = crear_servicio(E.RECOGIDO)
    entregar_desde_el_panel(servicio, usuario)
    assert unica_linea(servicio).estado == C.SIN_VALOR


def test_ningun_otro_cambio_de_estado_crea_linea(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    op_solicitudes.asignar(servicio, ana, actor=usuario)
    op_solicitudes.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    op_solicitudes.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo="Llanta pinchada")
    op_solicitudes.resolver_novedad(servicio, "reanudar", actor=usuario)
    op_solicitudes.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert not LineaCobro.objects.exists()

    entregar_desde_el_panel(servicio, usuario)
    assert unica_linea(servicio).posicion == 1


# --- Desde la app del conductor ----------------------------------------------------------------


def test_al_entregar_desde_la_app_nace_la_linea_sin_usuario(
    crear_servicio, evento_app, tarifa_traslado
):
    servicio = crear_servicio(E.RECOGIDO)
    assert aplicar_evento_del_conductor(**evento_app(servicio, E.ENTREGADO)) == Resultado.APLICADO

    linea = unica_linea(servicio)
    assert (linea.estado, linea.valor) == (C.POR_FACTURAR, VALOR)
    registro = linea.historial.get()
    assert (registro.accion, registro.usuario) == (AccionCobro.CREADA, None)


def test_un_evento_de_entregado_duplicado_crea_una_sola_linea(crear_servicio, evento_app):
    servicio = crear_servicio(E.RECOGIDO)
    datos = evento_app(servicio, E.ENTREGADO)
    assert aplicar_evento_del_conductor(**datos) == Resultado.APLICADO
    assert aplicar_evento_del_conductor(**datos) == Resultado.DUPLICADO
    assert aplicar_lote_del_conductor([datos]) == [(str(datos["id"]), Resultado.DUPLICADO)]

    assert unica_linea(servicio).historial.count() == 1
    assert HistorialCobro.objects.count() == 1


def test_un_lote_que_termina_en_entregado_crea_una_sola_linea(crear_servicio, evento_app):
    servicio = crear_servicio(E.ASIGNADO)
    lote = [
        evento_app(servicio, E.ENTREGADO, secuencia=3),
        evento_app(servicio, E.EN_CAMINO, secuencia=1),
        evento_app(servicio, E.RECOGIDO, secuencia=2),
    ]
    resultados = [resultado for _, resultado in aplicar_lote_del_conductor(lote)]
    assert resultados == [Resultado.APLICADO] * 3
    unica_linea(servicio)


def test_un_entregado_de_otro_conductor_es_conflicto_y_no_crea_linea(
    crear_servicio, evento_app, beto
):
    servicio = crear_servicio(E.RECOGIDO)  # asignado a Ana
    datos = evento_app(servicio, E.ENTREGADO, conductor=beto)
    assert aplicar_evento_del_conductor(**datos) == Resultado.CONFLICTO
    assert EventoEstado.objects.get(pk=datos["id"]).resultado == EventoEstado.Resultado.CONFLICTO
    assert not LineaCobro.objects.exists()


def test_un_entregado_sobre_un_servicio_cancelado_es_conflicto_y_no_crea_linea(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.CANCELADO)
    assert aplicar_evento_del_conductor(**evento_app(servicio, E.ENTREGADO)) == Resultado.CONFLICTO
    assert not LineaCobro.objects.exists()


# --- Misma transacción: si la línea falla, el servicio no queda Entregado ----------------------


def test_si_la_linea_falla_desde_el_panel_el_servicio_no_queda_entregado(
    monkeypatch, crear_servicio, usuario
):
    def tarifa_que_falla(*args, **kwargs):
        raise RuntimeError("No se pudo leer la tarifa")

    monkeypatch.setattr(operaciones, "tarifa_propuesta", tarifa_que_falla)
    servicio = crear_servicio(E.RECOGIDO)

    with pytest.raises(RuntimeError, match="No se pudo leer la tarifa"):
        entregar_desde_el_panel(servicio, usuario)

    servicio.refresh_from_db()
    assert servicio.estado == E.RECOGIDO
    assert not EventoEstado.objects.exists()
    assert not LineaCobro.objects.exists()
    assert not HistorialCobro.objects.exists()


def test_si_la_base_rechaza_la_linea_desde_la_app_el_servicio_no_queda_entregado(
    monkeypatch, crear_servicio, evento_app
):
    """Un núcleo que devolviera una línea por facturar sin valor: la base la rechaza y el evento
    del conductor se deshace entero (el celular lo reenviará)."""
    monkeypatch.setattr(
        operaciones.cobro, "linea_inicial", lambda valor: LineaNucleo(C.POR_FACTURAR)
    )
    servicio = crear_servicio(E.RECOGIDO)
    datos = evento_app(servicio, E.ENTREGADO)

    with pytest.raises(IntegrityError, match="linea_cobro_por_facturar_coherente"):
        aplicar_evento_del_conductor(**datos)

    servicio.refresh_from_db()
    assert servicio.estado == E.RECOGIDO
    assert not EventoEstado.objects.filter(pk=datos["id"]).exists()
    assert not LineaCobro.objects.exists()


# --- crear_linea_al_entregar directamente ------------------------------------------------------


def test_crear_la_linea_dos_veces_no_crea_otra_ni_cambia_la_existente(linea, entregado, usuario):
    operaciones.fijar_valor(linea, D("250000"), actor=usuario)
    otra_vez = operaciones.crear_linea_al_entregar(entregado, actor=usuario)

    assert otra_vez == linea
    assert unica_linea(entregado).valor == D("250000")
    assert linea.historial.count() == 2  # creada y valor; la segunda llamada no deja nada


@pytest.mark.parametrize("estado", [e for e in Estado if e != E.ENTREGADO])
def test_solo_un_servicio_entregado_crea_su_linea_al_entregar(crear_servicio, estado):
    servicio = crear_servicio(estado)
    with pytest.raises(EstadoNoCobrable, match="queda Entregado"):
        operaciones.crear_linea_al_entregar(servicio)
    assert not LineaCobro.objects.exists()


# --- Enganche ----------------------------------------------------------------------------------


def test_cobros_escucha_la_senal_de_servicio_entregado():
    assert servicio_entregado.has_listeners(sender=Servicio)


def test_solicitudes_no_importa_cobros():
    for archivo in SOLICITUDES.rglob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            modulos = []
            if isinstance(nodo, ast.Import):
                modulos = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                modulos = [nodo.module or ""]
            for modulo in modulos:
                assert not modulo.startswith("cobros"), f"{archivo.name} importa {modulo}"
