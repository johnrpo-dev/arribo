"""Registro único de configuración: valores por defecto y restricciones en PostgreSQL."""
from datetime import time

import pytest
from django.db import IntegrityError, transaction

from configuracion.models import (
    COSTO_MENSUAL_RETENCION,
    Configuracion,
    FormatoExportacion,
    MomentoPlacaVin,
    RetencionFotos,
    configuracion_vigente,
)

pytestmark = pytest.mark.django_db


def test_valores_por_defecto_son_los_de_la_arquitectura():
    c = configuracion_vigente()
    assert c.momento_placa_vin == MomentoPlacaVin.AL_RECOGER
    assert c.minimo_fotos == 4
    assert c.ven_valores_administrador is True
    assert c.ven_valores_facturacion is True
    assert c.ven_valores_logistica is False
    assert c.retencion_fotos == RetencionFotos.DOCE_MESES
    assert c.meses_retencion == 12
    assert c.alerta_sin_asignar_minutos == 10
    assert c.alerta_programado_sin_asignar_horas == 2
    assert c.alerta_sin_en_camino_minutos == 15
    assert c.alerta_recogido_sin_entregado_horas == 4
    assert c.alerta_sin_facturar_dias == 5
    assert c.alerta_sin_pagar_dias == 30
    assert c.nocturno_inicio == time(19, 0)
    assert c.nocturno_fin == time(6, 0)
    assert c.formato_exportacion == FormatoExportacion.CSV_GENERICO


def test_configuracion_vigente_crea_el_registro_una_sola_vez():
    assert Configuracion.objects.count() == 0
    primera = configuracion_vigente()
    segunda = configuracion_vigente()
    assert primera.pk == segunda.pk
    assert Configuracion.objects.count() == 1


def test_solo_puede_existir_un_registro_en_la_base():
    configuracion_vigente()
    with pytest.raises(IntegrityError), transaction.atomic():
        Configuracion.objects.create()
    assert Configuracion.objects.count() == 1


def test_la_base_no_acepta_un_registro_con_unico_falso():
    with pytest.raises(IntegrityError, match="configuracion_unico_siempre_verdadero"), transaction.atomic():
        Configuracion.objects.create(unico=False)


@pytest.mark.parametrize("valor", [-1, 21, 100])
def test_la_base_rechaza_minimo_de_fotos_fuera_de_rango(valor):
    c = configuracion_vigente()
    with pytest.raises(IntegrityError), transaction.atomic():
        Configuracion.objects.filter(pk=c.pk).update(minimo_fotos=valor)


@pytest.mark.parametrize("valor", [0, 20])
def test_la_base_acepta_minimo_de_fotos_en_los_extremos(valor):
    c = configuracion_vigente()
    Configuracion.objects.filter(pk=c.pk).update(minimo_fotos=valor)
    c.refresh_from_db()
    assert c.minimo_fotos == valor


def test_la_base_no_deja_quitar_al_administrador_de_los_que_ven_valores():
    c = configuracion_vigente()
    with pytest.raises(IntegrityError, match="configuracion_administrador_ve_valores"), transaction.atomic():
        Configuracion.objects.filter(pk=c.pk).update(ven_valores_administrador=False)


def test_la_base_rechaza_horario_nocturno_con_inicio_igual_al_fin():
    c = configuracion_vigente()
    with pytest.raises(IntegrityError, match="configuracion_horario_nocturno_distinto"), transaction.atomic():
        Configuracion.objects.filter(pk=c.pk).update(nocturno_fin=time(19, 0))


@pytest.mark.parametrize(
    "campo",
    [
        "alerta_sin_asignar_minutos",
        "alerta_programado_sin_asignar_horas",
        "alerta_sin_en_camino_minutos",
        "alerta_recogido_sin_entregado_horas",
        "alerta_sin_facturar_dias",
        "alerta_sin_pagar_dias",
    ],
)
def test_la_base_rechaza_umbrales_de_alerta_en_cero(campo):
    c = configuracion_vigente()
    with pytest.raises(IntegrityError, match="configuracion_umbrales_positivos"), transaction.atomic():
        Configuracion.objects.filter(pk=c.pk).update(**{campo: 0})


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("momento_placa_vin", "nunca"),
        ("retencion_fotos", "3"),
        ("formato_exportacion", "siigo"),
    ],
)
def test_la_base_rechaza_opciones_desconocidas(campo, valor):
    c = configuracion_vigente()
    with pytest.raises(IntegrityError), transaction.atomic():
        Configuracion.objects.filter(pk=c.pk).update(**{campo: valor})


def test_retencion_indefinida_no_tiene_meses():
    c = Configuracion(retencion_fotos=RetencionFotos.INDEFINIDA)
    assert c.meses_retencion is None
    assert Configuracion(retencion_fotos=RetencionFotos.SEIS_MESES).meses_retencion == 6


def test_cada_opcion_de_retencion_tiene_su_costo_de_la_arquitectura():
    assert COSTO_MENSUAL_RETENCION == {
        RetencionFotos.SEIS_MESES: "COP 700 al mes",
        RetencionFotos.DOCE_MESES: "COP 1.900 al mes",
        RetencionFotos.VEINTICUATRO_MESES: "COP 4.200 al mes",
        RetencionFotos.INDEFINIDA: "sube unos COP 200 cada mes",
    }
