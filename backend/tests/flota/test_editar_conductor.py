"""Corregir nombre y celular de un conductor desde su página (1a-08c), contra PostgreSQL: el celular
se normaliza, es único y, si choca, se dice claro y no cambia nada."""
import pytest
from django.db import IntegrityError

from documentos import consultas as documentos
from documentos.models import TipoDocumento
from flota import operaciones as op
from flota.models import Conductor
from nucleo.documentos import EstadoDocumento

from ..api.conftest import PIN, ingresar

pytestmark = pytest.mark.django_db


def url(conductor, accion=""):
    return f"/flota/conductores/{conductor.pk}/{accion}"


def datos(nombre="Ana María", celular="+57 311 222 3344"):
    return {"datos-nombre": nombre, "datos-celular": celular}


def test_la_pagina_del_conductor_trae_el_formulario_con_sus_datos(client, administrador, ana):
    html = client.get(url(ana)).content.decode()
    assert f'action="/flota/conductores/{ana.pk}/datos/"' in html
    assert 'value="Ana"' in html
    assert 'value="3000000001"' in html


def test_corregir_nombre_y_celular_los_guarda_normalizados(client, administrador, ana_app):
    respuesta = client.post(url(ana_app, "datos/"), datos(nombre="  Ana María "), follow=True)

    ana_app.refresh_from_db()
    assert (ana_app.nombre, ana_app.celular) == ("Ana María", "3112223344")
    assert ana_app.usuario.first_name == "Ana María"
    assert respuesta.redirect_chain == [(url(ana_app), 302)]
    assert "Datos del conductor guardados." in respuesta.content.decode()


def test_con_el_celular_nuevo_entra_a_la_app_con_el_mismo_pin(client, administrador, ana_app, api):
    client.post(url(ana_app, "datos/"), datos())
    assert ingresar(api, celular="3112223344", pin=PIN).status_code == 200
    assert ingresar(api, celular="3000000001", pin=PIN).status_code != 200


def test_un_celular_de_otro_conductor_se_rechaza_con_mensaje_claro(
    client, administrador, ana, beto
):
    respuesta = client.post(url(ana, "datos/"), datos(celular="300 000 0002"))

    assert respuesta.status_code == 200
    assert "Ya hay un conductor con el celular 3000000002: Beto." in respuesta.content.decode()
    ana.refresh_from_db()
    assert (ana.nombre, ana.celular) == ("Ana", "3000000001")


def test_su_propio_celular_no_choca_consigo_mismo(client, administrador, ana):
    client.post(url(ana, "datos/"), datos(nombre="Ana Gómez", celular="3000000001"))
    ana.refresh_from_db()
    assert ana.nombre == "Ana Gómez"


@pytest.mark.parametrize(
    ("campos", "mensaje"),
    [
        (datos(celular="12"), "El teléfono debe tener entre"),
        (datos(nombre="   "), "Este campo es requerido."),
    ],
)
def test_datos_invalidos_no_se_guardan(client, administrador, ana, campos, mensaje):
    respuesta = client.post(url(ana, "datos/"), campos)
    assert mensaje in respuesta.content.decode()
    ana.refresh_from_db()
    assert (ana.nombre, ana.celular) == ("Ana", "3000000001")


def test_la_operacion_rechaza_el_celular_repetido_aunque_no_pase_por_el_formulario(ana, beto):
    with pytest.raises(op.OperacionInvalida):
        op.editar_datos_conductor(ana, nombre="Ana", celular=beto.celular)
    ana.refresh_from_db()
    assert ana.celular == "3000000001"


def test_la_base_tambien_impide_dos_conductores_con_el_mismo_celular(ana):
    with pytest.raises(IntegrityError):
        Conductor.objects.create(nombre="Copia", celular="3000000001")


@pytest.mark.parametrize("rol", ["logistica", "facturacion"])
def test_solo_el_administrador_corrige_los_datos(client, crear_usuario, ana, rol):
    client.force_login(crear_usuario(rol))
    assert client.post(url(ana, "datos/"), datos()).status_code == 403
    ana.refresh_from_db()
    assert ana.celular == "3000000001"


def test_corregir_por_get_no_esta_permitido(client, administrador, ana):
    assert client.get(url(ana, "datos/")).status_code == 405


# --- Resumen de documentos de la lista -----------------------------------------------------------


def estado(tipo, valor):
    return documentos.EstadoDeTipo(tipo, None, None, valor)


@pytest.mark.parametrize(
    ("estados", "texto", "nombres"),
    [
        ([], "Al día", ()),
        ([EstadoDocumento.VIGENTE, EstadoDocumento.AUN_NO_APLICA], "Al día", ()),
        ([EstadoDocumento.VIGENTE, EstadoDocumento.POR_VENCER], "Por vencer", ("B",)),
        ([EstadoDocumento.POR_VENCER, EstadoDocumento.FALTA], "Falta", ("B",)),
        ([EstadoDocumento.FALTA, EstadoDocumento.VENCIDO], "Vencido", ("B",)),
        ([EstadoDocumento.VENCIDO, EstadoDocumento.VENCIDO], "Vencido", ("A", "B")),
    ],
)
def test_el_resumen_es_el_estado_mas_grave(estados, texto, nombres):
    tipos = [TipoDocumento(nombre=n) for n in ("A", "B")]
    resumen = documentos.resumen(estado(t, e) for t, e in zip(tipos, estados, strict=False))
    assert (resumen.texto, resumen.documentos) == (texto, nombres)
