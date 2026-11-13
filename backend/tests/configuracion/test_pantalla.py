"""Pantalla de configuración: acceso solo del administrador, validaciones junto al campo y guardado
con historial.
"""
import re

import pytest

from configuracion.formularios import FormularioConfiguracion
from configuracion.models import Configuracion, HistorialConfiguracion, configuracion_vigente

pytestmark = pytest.mark.django_db

RUTA = "/configuracion/"


def datos_validos(**cambios):
    """Lo que manda el formulario con los valores por defecto, más los cambios pedidos."""
    datos = {
        "momento_placa_vin": "recoger",
        "minimo_fotos": "4",
        "ven_valores_facturacion": "on",
        "retencion_fotos": "12",
        "alerta_sin_asignar_minutos": "10",
        "alerta_programado_sin_asignar_horas": "2",
        "alerta_sin_en_camino_minutos": "15",
        "alerta_recogido_sin_entregado_horas": "4",
        "alerta_sin_facturar_dias": "5",
        "alerta_sin_pagar_dias": "30",
        "nocturno_inicio": "19:00",
        "nocturno_fin": "06:00",
        "formato_exportacion": "csv_generico",
    }
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


@pytest.fixture
def admin(client, crear_usuario):
    usuario = crear_usuario("administrador")
    client.force_login(usuario)
    return usuario


# --- Acceso ------------------------------------------------------------------------------------


def test_el_administrador_entra_a_la_configuracion(client, admin):
    respuesta = client.get(RUTA)
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert '<h1 class="titulo-pagina">Configuración</h1>' in html
    assert "Aún no disponible" not in html


@pytest.mark.parametrize("rol", ["logistica", "facturacion", "conductor"])
def test_otros_roles_reciben_403(client, crear_usuario, rol):
    client.force_login(crear_usuario(rol))
    assert client.get(RUTA).status_code == 403
    assert client.post(RUTA, datos_validos(minimo_fotos="6")).status_code == 403
    assert configuracion_vigente().minimo_fotos == 4


def test_sin_sesion_lleva_al_ingreso(client):
    respuesta = client.get(RUTA)
    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/ingresar/?next=/configuracion/")


# --- Contenido ---------------------------------------------------------------------------------


def test_la_pantalla_muestra_las_secciones_y_el_costo_de_cada_retencion(client, admin):
    html = client.get(RUTA).content.decode()
    for titulo in ("Registro de vehículos", "Fotos", "Valores", "Retención de fotos", "Alertas",
                   "Horario nocturno", "Exportación"):
        assert f">{titulo}</h2>" in html
    for costo in ("COP 700 al mes", "COP 1.900 al mes", "COP 4.200 al mes",
                  "sube unos COP 200 cada mes"):
        assert costo in html
    assert "todavía no cambia a quién llegan las alertas" in html
    assert "Excel/CSV genérico" in html


def test_el_administrador_aparece_marcado_y_deshabilitado_en_ven_valores(client, admin):
    html = client.get(RUTA).content.decode()
    (casilla,) = re.findall(r'<input[^>]*name="ven_valores_administrador"[^>]*>', html)
    assert "disabled" in casilla
    assert "checked" in casilla


# --- Guardar -----------------------------------------------------------------------------------


def test_cambiar_el_minimo_de_fotos_lo_guarda_y_deja_historial(client, admin):
    respuesta = client.post(RUTA, datos_validos(minimo_fotos="6"), follow=True)
    assert respuesta.redirect_chain == [(RUTA, 302)]
    assert "Configuración guardada." in respuesta.content.decode()
    assert configuracion_vigente().minimo_fotos == 6
    (registro,) = HistorialConfiguracion.objects.all()
    assert (registro.campo, registro.valor_anterior, registro.valor_nuevo) == (
        "minimo_fotos", "4", "6",
    )
    assert registro.usuario == admin


@pytest.mark.parametrize("valor", ["-1", "21"])
def test_minimo_de_fotos_fuera_de_rango_se_rechaza_junto_al_campo(client, admin, valor):
    respuesta = client.post(RUTA, datos_validos(minimo_fotos=valor))
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "El mínimo de fotos va de 0 a 20." in html
    assert "campo campo--error" in html
    assert configuracion_vigente().minimo_fotos == 4
    assert HistorialConfiguracion.objects.count() == 0


def test_quitar_al_administrador_de_ven_valores_no_tiene_efecto(client, admin):
    client.post(RUTA, datos_validos(ven_valores_administrador=None, minimo_fotos="5"))
    c = configuracion_vigente()
    assert c.ven_valores_administrador is True
    assert c.minimo_fotos == 5
    assert not HistorialConfiguracion.objects.filter(campo="ven_valores_administrador").exists()


def test_formulario_ignora_un_intento_de_desmarcar_al_administrador():
    formulario = FormularioConfiguracion(
        datos_validos(ven_valores_administrador=""), instance=configuracion_vigente()
    )
    assert formulario.is_valid(), formulario.errors
    assert formulario.cleaned_data["ven_valores_administrador"] is True


def test_horario_nocturno_con_inicio_igual_al_fin_se_rechaza(client, admin):
    respuesta = client.post(RUTA, datos_validos(nocturno_inicio="19:00", nocturno_fin="19:00"))
    assert respuesta.status_code == 200
    assert "El fin debe ser distinto del inicio." in respuesta.content.decode()
    assert configuracion_vigente().nocturno_fin.hour == 6


def test_umbral_de_alerta_en_cero_se_rechaza(client, admin):
    respuesta = client.post(RUTA, datos_validos(alerta_sin_pagar_dias="0"))
    assert "Escriba un número mayor que cero." in respuesta.content.decode()
    assert configuracion_vigente().alerta_sin_pagar_dias == 30


def test_la_pantalla_no_crea_un_segundo_registro(client, admin):
    client.get(RUTA)
    client.post(RUTA, datos_validos(minimo_fotos="3"))
    assert Configuracion.objects.count() == 1
