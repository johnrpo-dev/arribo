"""Guardar la configuración deja historial de solo agregar, y quién ve los valores de cobro."""
from datetime import time

import pytest

from configuracion.models import (
    HistorialConfiguracion,
    HistorialInmutable,
    configuracion_vigente,
)
from configuracion.operaciones import guardar_configuracion, puede_ver_valores

pytestmark = pytest.mark.django_db


def test_guardar_deja_un_registro_por_campo_cambiado(crear_usuario):
    admin = crear_usuario("administrador")
    c = configuracion_vigente()
    c.minimo_fotos = 6
    c.ven_valores_logistica = True
    c.nocturno_inicio = time(20, 30)
    historial = guardar_configuracion(c, usuario=admin)

    assert {(h.campo, h.valor_anterior, h.valor_nuevo) for h in historial} == {
        ("minimo_fotos", "4", "6"),
        ("ven_valores_logistica", "No", "Sí"),
        ("nocturno_inicio", "19:00", "20:30"),
    }
    assert all(h.usuario == admin and h.fecha is not None for h in historial)
    c.refresh_from_db()
    assert (c.minimo_fotos, c.ven_valores_logistica, c.nocturno_inicio) == (6, True, time(20, 30))


def test_guardar_sin_cambios_no_deja_historial(crear_usuario):
    assert guardar_configuracion(configuracion_vigente(), usuario=crear_usuario("administrador")) == []
    assert HistorialConfiguracion.objects.count() == 0


def test_el_historial_de_configuracion_no_se_modifica_ni_se_borra(crear_usuario):
    c = configuracion_vigente()
    c.minimo_fotos = 5
    (registro,) = guardar_configuracion(c, usuario=crear_usuario("administrador"))
    registro.valor_nuevo = "9"
    with pytest.raises(HistorialInmutable):
        registro.save()
    with pytest.raises(HistorialInmutable):
        registro.delete()
    with pytest.raises(HistorialInmutable):
        HistorialConfiguracion.objects.update(valor_nuevo="9")
    with pytest.raises(HistorialInmutable):
        HistorialConfiguracion.objects.all().delete()
    registro.refresh_from_db()
    assert registro.valor_nuevo == "5"


# --- Quién ve los valores ----------------------------------------------------------------------


def test_por_defecto_ven_valores_administrador_y_facturacion_y_no_logistica(crear_usuario):
    assert puede_ver_valores(crear_usuario("administrador")) is True
    assert puede_ver_valores(crear_usuario("facturacion")) is True
    assert puede_ver_valores(crear_usuario("logistica")) is False


def test_logistica_ve_valores_si_la_configuracion_lo_permite(crear_usuario):
    c = configuracion_vigente()
    c.ven_valores_logistica = True
    c.ven_valores_facturacion = False
    c.save()
    assert puede_ver_valores(crear_usuario("logistica")) is True
    assert puede_ver_valores(crear_usuario("facturacion")) is False


def test_el_administrador_ve_valores_aunque_nadie_mas_los_vea(crear_usuario):
    c = configuracion_vigente()
    c.ven_valores_facturacion = False
    c.save()
    assert puede_ver_valores(crear_usuario("administrador")) is True


def test_el_superusuario_cuenta_como_administrador(crear_usuario):
    assert puede_ver_valores(crear_usuario(superusuario=True)) is True


def test_el_conductor_nunca_ve_valores_aunque_tenga_otro_rol(crear_usuario):
    c = configuracion_vigente()
    c.ven_valores_logistica = True
    c.save()
    assert puede_ver_valores(crear_usuario("conductor")) is False
    assert puede_ver_valores(crear_usuario("conductor", "facturacion")) is False
    assert puede_ver_valores(crear_usuario("conductor", "administrador")) is False


def test_usuario_sin_rol_anonimo_o_inactivo_no_ve_valores(crear_usuario):
    from django.contrib.auth.models import AnonymousUser

    assert puede_ver_valores(crear_usuario()) is False
    assert puede_ver_valores(AnonymousUser()) is False
    inactivo = crear_usuario("administrador")
    inactivo.is_active = False
    assert puede_ver_valores(inactivo) is False
