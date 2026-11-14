"""Estado de los documentos contra PostgreSQL: el vigente es el más reciente, días de anticipación
por tipo, borde del día en Medellín y documentos por vencer (para la alerta de la 1a-18)."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from documentos.consultas import (
    dia_local,
    documentos_por_vencer,
    estados_de,
    vencidos_para_asignar,
)
from documentos.operaciones import registrar_documento
from flota.models import Grua
from nucleo.documentos import EstadoDocumento

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")
E = EstadoDocumento


def estado(sujeto, tipo, hoy=None):
    return next(e for e in estados_de(sujeto, hoy) if e.tipo == tipo).estado


# --- El vigente es el más reciente ---------------------------------------------------------------


def test_el_vigente_es_el_mas_reciente_aunque_el_anterior_venza_despues(soat, grua1, registrar):
    registrar(soat, grua1, vence_en=300)
    nuevo = registrar(soat, grua1, vence_en=-1)
    vigente = next(e for e in estados_de(grua1) if e.tipo == soat)
    assert vigente.documento == nuevo
    assert vigente.estado == E.VENCIDO


def test_renovar_un_documento_vencido_lo_deja_vigente(soat, grua1, registrar):
    registrar(soat, grua1, vence_en=-10)
    registrar(soat, grua1, vence_en=365)
    assert estado(grua1, soat) == E.VIGENTE


def test_los_documentos_de_otra_grua_no_cuentan(soat, grua1, grua2, registrar):
    registrar(soat, grua2, vence_en=-1)
    assert estado(grua1, soat) == E.FALTA
    assert estado(grua2, soat) == E.VENCIDO


def test_un_tipo_sin_documento_falta(licencia, ana):
    assert estado(ana, licencia) == E.FALTA


def test_un_tipo_inactivo_no_aparece_ni_bloquea(soat, grua1, ana, registrar):
    registrar(soat, grua1, vence_en=-1)
    soat.activo = False
    soat.save()
    assert soat not in [e.tipo for e in estados_de(grua1)]
    assert vencidos_para_asignar(ana, grua1) == ()


# --- Días de anticipación por tipo ---------------------------------------------------------------


def test_los_dias_de_anticipacion_son_de_cada_tipo(soat, tecnomecanica, grua1, registrar):
    soat.dias_anticipacion = 10
    soat.save()
    registrar(soat, grua1, vence_en=15)
    registrar(tecnomecanica, grua1, vence_en=15)
    assert estado(grua1, soat) == E.VIGENTE
    assert estado(grua1, tecnomecanica) == E.POR_VENCER


def test_cambiar_los_dias_de_anticipacion_cambia_el_estado(soat, grua1, registrar):
    registrar(soat, grua1, vence_en=45)
    assert estado(grua1, soat) == E.VIGENTE
    soat.dias_anticipacion = 60
    soat.save()
    assert estado(grua1, soat) == E.POR_VENCER


# --- El día se cuenta en Medellín ----------------------------------------------------------------


def test_el_dia_local_es_el_de_medellin_y_no_el_de_utc():
    # 3 a. m. UTC del 14 son las 10 p. m. del 13 en Medellín.
    assert dia_local(datetime(2026, 11, 14, 3, 0, tzinfo=UTC)) == date(2026, 11, 13)
    assert dia_local(datetime(2026, 11, 14, 5, 0, tzinfo=UTC)) == date(2026, 11, 14)


def test_un_soat_que_vence_hoy_sirve_hasta_la_medianoche_de_medellin(soat, grua1, quien):
    registrar_documento(tipo=soat, sujeto=grua1, por=quien, vence=date(2026, 11, 13))
    ultimo_minuto = datetime(2026, 11, 13, 23, 59, tzinfo=BOGOTA)  # ya es el 14 en UTC
    medianoche = datetime(2026, 11, 14, 0, 0, tzinfo=BOGOTA)
    assert ultimo_minuto.astimezone(UTC).date() == date(2026, 11, 14)
    assert estado(grua1, soat, dia_local(ultimo_minuto)) == E.POR_VENCER
    assert estado(grua1, soat, dia_local(medianoche)) == E.VENCIDO


# --- Aún no aplica -------------------------------------------------------------------------------


def test_aun_no_aplica_hasta_la_fecha_y_desde_ese_dia_cuenta_como_vencido(
    tecnomecanica, grua1, quien
):
    registrar_documento(
        tipo=tecnomecanica, sujeto=grua1, por=quien, aplica_desde=date(2026, 12, 1)
    )
    assert estado(grua1, tecnomecanica, date(2026, 11, 30)) == E.AUN_NO_APLICA
    assert estado(grua1, tecnomecanica, date(2026, 12, 1)) == E.VENCIDO


# --- Documentos por vencer -----------------------------------------------------------------------


def test_documentos_por_vencer_trae_solo_los_que_hay_que_avisar(
    soat, tecnomecanica, licencia, grua1, grua2, ana, beto, registrar
):
    por_vencer = registrar(soat, grua1, vence_en=30)
    registrar(soat, grua2, vence_en=31)  # vigente
    registrar(tecnomecanica, grua1, vence_en=-1)  # vencido: no es "por vencer"
    empieza_pronto = registrar(tecnomecanica, grua2, aplica_desde_en=20)
    registrar(licencia, beto, aplica_desde_en=200)  # aún no aplica, lejos
    licencia_hoy = registrar(licencia, ana, vence_en=0)
    # Ana sin nada más; Beto sin licencia vigente: "falta" no es "por vencer".

    avisos = documentos_por_vencer(dia_local())

    assert [a.documento for a in avisos] == [licencia_hoy, empieza_pronto, por_vencer]
    assert {a.descripcion for a in avisos} == {
        "SOAT de la grúa GRU001",
        "Tecnomecánica de la grúa GRU002",
        "Licencia de conducción de Ana",
    }


def test_documentos_por_vencer_usa_la_fecha_que_se_le_pasa(soat, grua1, quien):
    registrar_documento(tipo=soat, sujeto=grua1, por=quien, vence=date(2027, 1, 31))
    assert documentos_por_vencer(date(2026, 12, 31)) == []
    assert len(documentos_por_vencer(date(2027, 1, 1))) == 1


def test_documentos_por_vencer_ignora_gruas_inactivas(soat, quien):
    inactiva = Grua.objects.create(placa="GRU009", capacidad=1, activa=False)
    registrar_documento(tipo=soat, sujeto=inactiva, por=quien, vence=dia_local())
    assert documentos_por_vencer(dia_local()) == []
