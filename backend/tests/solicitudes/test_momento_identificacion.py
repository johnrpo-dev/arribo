"""Momento en que se exige la placa o el VIN, leído de la configuración guardada en PostgreSQL.

"Al asignar": `asignar` rechaza el servicio cuyo vehículo no cumple `validar_identificacion`
(desvare exige placa; el resto, placa o VIN). "Al recoger" (por defecto): asignar no lo exige.
"""
import pytest

from configuracion.models import MomentoPlacaVin, configuracion_vigente
from nucleo.estados import Estado
from nucleo.identificacion import IdentificacionIncompleta, MomentoIdentificacion
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EventoEstado

from ..conftest import VIN, crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado


def configurar(momento):
    configuracion = configuracion_vigente()
    configuracion.momento_placa_vin = momento
    configuracion.save()


@pytest.fixture
def al_asignar():
    configurar(MomentoPlacaVin.AL_ASIGNAR)


@pytest.fixture
def al_recoger():
    configurar(MomentoPlacaVin.AL_RECOGER)


def test_las_opciones_de_la_configuracion_son_los_momentos_del_nucleo():
    assert set(MomentoPlacaVin.values) == {m.value for m in MomentoIdentificacion}


def test_al_asignar_sin_placa_ni_vin_no_se_asigna(al_asignar, crear_servicio, nuevo_vehiculo, ana, usuario):
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=""))
    with pytest.raises(IdentificacionIncompleta, match="placa o VIN"):
        operaciones.asignar(servicio, ana, actor=usuario)
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor_id) == (E.PENDIENTE_ASIGNAR, None)
    assert not EventoEstado.objects.exists()


@pytest.mark.parametrize("identificacion", [{"placa": "ABC123"}, {"placa": "", "vin": VIN}])
def test_al_asignar_un_traslado_con_placa_o_vin_se_asigna(
    al_asignar, crear_servicio, nuevo_vehiculo, ana, usuario, identificacion
):
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(**identificacion))
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_al_asignar_un_desvare_con_solo_vin_no_se_asigna(
    al_asignar, cliente, crear_servicio, nuevo_vehiculo, ana, usuario
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=VIN), solicitud_de=desvare)
    with pytest.raises(IdentificacionIncompleta, match="desvare exige la placa"):
        operaciones.asignar(servicio, ana, actor=usuario)
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR


def test_al_asignar_un_desvare_con_placa_se_asigna(
    al_asignar, cliente, crear_servicio, nuevo_vehiculo, ana, usuario
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="ABC123"), solicitud_de=desvare)
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_al_recoger_se_asigna_sin_placa_ni_vin(al_recoger, crear_servicio, nuevo_vehiculo, ana, usuario):
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=""))
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_al_recoger_la_identificacion_se_sigue_exigiendo_al_recoger(
    al_recoger, crear_servicio, nuevo_vehiculo, usuario
):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    with pytest.raises(IdentificacionIncompleta):
        operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)


def test_el_cambio_de_configuracion_aplica_a_la_siguiente_asignacion(
    crear_servicio, nuevo_vehiculo, ana, usuario
):
    configurar(MomentoPlacaVin.AL_ASIGNAR)
    primero = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=""))
    with pytest.raises(IdentificacionIncompleta):
        operaciones.asignar(primero, ana, actor=usuario)
    configurar(MomentoPlacaVin.AL_RECOGER)
    operaciones.asignar(primero, ana, actor=usuario)
    assert primero.estado == E.ASIGNADO
