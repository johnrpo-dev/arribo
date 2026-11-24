"""Número de bodega como tercera forma de identificar un vehículo, contra PostgreSQL.

El vehículo necesita placa, VIN o número de bodega (al menos uno); el desvare sigue exigiendo la
placa. El número de bodega lo escribe la oficina, no es único y se guarda en mayúsculas sin
espacios. Sirve para asignar (con "al asignar" configurado) y para que el Recogido de la app no
quede en conflicto aunque el conductor no digite placa ni VIN.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from clientes.models import TelefonoCliente
from configuracion.models import MomentoPlacaVin, configuracion_vigente
from nucleo.estados import Estado
from nucleo.identificacion import IdentificacionIncompleta
from nucleo.sincronizacion import Motivo, Resultado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EventoEstado, Servicio, Vehiculo
from solicitudes.operaciones import aplicar_evento_del_conductor

from ..conftest import crear_solicitud
from .test_registro import datos

pytestmark = pytest.mark.django_db

E = Estado
RUTA_NUEVA = "/solicitudes/nueva/"


@pytest.fixture
def al_asignar():
    configuracion = configuracion_vigente()
    configuracion.momento_placa_vin = MomentoPlacaVin.AL_ASIGNAR
    configuracion.save()


@pytest.fixture
def de_bodega(nuevo_vehiculo):
    return nuevo_vehiculo(placa="", vin="", numero_bodega="B-1024", marca="Renault", linea="Logan")


# --- Modelo -------------------------------------------------------------------------------------


def test_el_numero_de_bodega_se_guarda_en_mayusculas_y_sin_espacios(nuevo_vehiculo):
    vehiculo = nuevo_vehiculo(placa="", vin="", numero_bodega=" b 1024 ")
    vehiculo.refresh_from_db()
    assert vehiculo.numero_bodega == "B1024"


def test_el_numero_de_bodega_no_es_unico(nuevo_vehiculo):
    nuevo_vehiculo(placa="", vin="", numero_bodega="77")
    nuevo_vehiculo(placa="", vin="", numero_bodega="77")
    assert Vehiculo.objects.filter(numero_bodega="77").count() == 2


def test_la_base_no_acepta_un_numero_de_bodega_sin_normalizar(nuevo_vehiculo):
    vehiculo = nuevo_vehiculo(placa="", vin="")
    with pytest.raises(IntegrityError), transaction.atomic():
        Vehiculo.objects.filter(pk=vehiculo.pk).update(numero_bodega="b 12")


def test_un_numero_de_bodega_con_simbolos_no_pasa_la_validacion():
    vehiculo = Vehiculo(numero_bodega="12/4")
    with pytest.raises(ValidationError) as error:
        vehiculo.full_clean()
    assert "numero_bodega" in error.value.message_dict


def test_sin_placa_ni_vin_el_vehiculo_se_reconoce_por_la_bodega(de_bodega):
    assert de_bodega.identificacion == "bodega B-1024"
    assert str(de_bodega) == "bodega B-1024 · Renault Logan"


# --- Asignar y recoger --------------------------------------------------------------------------


def test_al_asignar_basta_el_numero_de_bodega(al_asignar, crear_servicio, de_bodega, ana, usuario):
    servicio = crear_servicio(vehiculo=de_bodega)
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_un_desvare_con_solo_numero_de_bodega_no_se_asigna(
    al_asignar, solicitud, crear_servicio, de_bodega, ana, usuario
):
    desvare = crear_solicitud(solicitud.solicitante, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(vehiculo=de_bodega, solicitud_de=desvare)
    with pytest.raises(IdentificacionIncompleta, match="placa"):
        operaciones.asignar(servicio, ana, actor=usuario)


def test_recogido_de_la_app_sin_digitar_nada_se_aplica_si_hay_numero_de_bodega(
    crear_servicio, de_bodega, evento_app
):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=de_bodega)
    datos_evento = evento_app(servicio, E.RECOGIDO)

    assert aplicar_evento_del_conductor(**datos_evento) == Resultado.APLICADO

    servicio.refresh_from_db()
    assert servicio.estado == E.RECOGIDO


def test_recogido_de_la_app_sin_ninguna_identificacion_sigue_en_conflicto(
    crear_servicio, nuevo_vehiculo, evento_app
):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    datos_evento = evento_app(servicio, E.RECOGIDO)

    assert aplicar_evento_del_conductor(**datos_evento) == Resultado.CONFLICTO

    evento = EventoEstado.objects.get(pk=datos_evento["id"])
    assert evento.motivo_conflicto == Motivo.IDENTIFICACION_INCOMPLETA


# --- Formulario de la solicitud, lista y búsqueda -----------------------------------------------


@pytest.fixture
def logistica(client, crear_usuario, cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


def test_el_formulario_registra_un_vehiculo_solo_con_numero_de_bodega(client, logistica):
    client.post(RUTA_NUEVA, datos(placa="", numero_bodega="b-2048"))
    vehiculo = Servicio.objects.get().vehiculo
    assert (vehiculo.placa, vehiculo.vin, vehiculo.numero_bodega) == ("", "", "B-2048")


def test_el_formulario_rechaza_un_numero_de_bodega_con_simbolos(client, logistica):
    respuesta = client.post(RUTA_NUEVA, datos(placa="", numero_bodega="12/4"))
    assert respuesta.status_code == 200
    assert "número de bodega" in respuesta.content.decode()
    assert not Servicio.objects.exists()


def test_el_numero_de_bodega_completa_al_vehiculo_ya_guardado(client, logistica, nuevo_vehiculo):
    guardado = nuevo_vehiculo(placa="ABC123")
    client.post(RUTA_NUEVA, datos(numero_bodega="77"))
    guardado.refresh_from_db()
    assert guardado.numero_bodega == "77"
    assert Servicio.objects.get().vehiculo == guardado


def test_la_lista_y_la_busqueda_muestran_el_numero_de_bodega(client, logistica):
    client.post(RUTA_NUEVA, datos(placa="", numero_bodega="B-4096"))
    html = client.get("/solicitudes/", {"q": "b-4096"}).content.decode()
    assert "bodega B-4096" in html
    assert client.get("/solicitudes/", {"q": "b-4095"}).content.decode().count("bodega B-4096") == 0
