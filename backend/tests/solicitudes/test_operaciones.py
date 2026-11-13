"""Operaciones del panel contra PostgreSQL: rechazan exactamente lo que rechaza el núcleo, cada
cambio deja un solo evento, y Recogido exige identificación y un puesto libre en la grúa.
"""
import pytest

from flota.models import grua_vigente
from nucleo.capacidad import CapacidadExcedida
from nucleo.estados import (
    Estado,
    Resolucion,
    TransicionInvalida,
    puede_transicionar,
)
from nucleo.estados import Servicio as ServicioNucleo
from nucleo.estados import reasignar as reasignar_en_nucleo
from nucleo.estados import resolver_novedad as resolver_novedad_en_nucleo
from nucleo.identificacion import IdentificacionIncompleta
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EstadoRegistro, EventoEstado, MotivoNoConcretada, OrigenEvento
from solicitudes.operaciones import SinGruaVigente, SolicitudNoAsignable

from ..conftest import VIN, crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado
MOTIVO = "Motivo de prueba"


def foto(servicio):
    """Lo que no debe cambiar cuando una operación se rechaza."""
    servicio.refresh_from_db()
    return (servicio.estado, servicio.estado_previo, servicio.conductor_id, servicio.grua_id)


def operar(servicio, destino, conductor, actor):
    """El camino del panel hacia cada estado: asignar exige conductor; el resto, cambiar_estado."""
    if destino == E.ASIGNADO:
        return operaciones.asignar(servicio, conductor, actor=actor)
    return operaciones.cambiar_estado(servicio, destino, actor=actor, motivo=MOTIVO)


# --- Las operaciones rechazan exactamente lo que rechaza el núcleo -----------------------------


@pytest.mark.parametrize("origen", list(Estado), ids=lambda e: f"desde_{e}")
@pytest.mark.parametrize("destino", list(Estado), ids=lambda e: f"a_{e}")
def test_cambiar_de_estado_acepta_y_rechaza_lo_mismo_que_el_nucleo(
    crear_servicio, ana, usuario, origen, destino
):
    servicio = crear_servicio(origen)
    antes = foto(servicio)
    if puede_transicionar(servicio.como_nucleo(), destino):
        evento = operar(servicio, destino, ana, usuario)
        assert servicio.estado == destino
        assert list(servicio.eventos.all()) == [evento]
        assert evento.destino == destino
    else:
        with pytest.raises(TransicionInvalida):
            operar(servicio, destino, ana, usuario)
        assert foto(servicio) == antes
        assert not EventoEstado.objects.exists()


@pytest.mark.parametrize("origen", list(Estado), ids=lambda e: f"desde_{e}")
def test_reasignar_acepta_y_rechaza_lo_mismo_que_el_nucleo(
    crear_servicio, beto, usuario, origen
):
    servicio = crear_servicio(origen)
    antes = foto(servicio)
    try:
        esperado = reasignar_en_nucleo(servicio.como_nucleo())
    except TransicionInvalida:
        with pytest.raises(TransicionInvalida):
            operaciones.reasignar(servicio, beto, actor=usuario)
        assert foto(servicio) == antes
        assert not EventoEstado.objects.exists()
    else:
        operaciones.reasignar(servicio, beto, actor=usuario)
        assert servicio.estado == esperado.estado == E.ASIGNADO
        assert (servicio.conductor, servicio.grua) == (beto, grua_vigente(beto))
        assert servicio.eventos.count() == 1


ORIGENES_RESOLUCION = [
    (E.NOVEDAD, E.ASIGNADO),
    (E.NOVEDAD, E.EN_CAMINO),
    (E.NOVEDAD, E.RECOGIDO),
    (E.ASIGNADO, None),
    (E.EN_CAMINO, None),
    (E.CANCELADO, None),
]


@pytest.mark.parametrize(("origen", "previo"), ORIGENES_RESOLUCION)
@pytest.mark.parametrize("resolucion", list(Resolucion))
@pytest.mark.parametrize("motivo", [None, MOTIVO])
def test_resolver_novedad_acepta_y_rechaza_lo_mismo_que_el_nucleo(
    crear_servicio, usuario, origen, previo, resolucion, motivo
):
    servicio = crear_servicio(origen, previo=previo)
    antes = foto(servicio)
    try:
        esperado = resolver_novedad_en_nucleo(servicio.como_nucleo(), resolucion, motivo=motivo)
    except TransicionInvalida:
        with pytest.raises(TransicionInvalida):
            operaciones.resolver_novedad(servicio, resolucion, actor=usuario, motivo=motivo)
        assert foto(servicio) == antes
        assert not EventoEstado.objects.exists()
    else:
        evento = operaciones.resolver_novedad(servicio, resolucion, actor=usuario, motivo=motivo)
        assert servicio.como_nucleo() == esperado
        assert list(servicio.eventos.all()) == [evento]


# --- Cada cambio deja exactamente un evento, con actor y motivo --------------------------------


def test_cada_cambio_deja_exactamente_un_evento_con_actor_y_motivo(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    pasos = [
        lambda: operaciones.asignar(servicio, ana, actor=usuario, motivo="Primero en la ruta"),
        lambda: operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario),
        lambda: operaciones.cambiar_estado(
            servicio, E.NOVEDAD, actor=usuario, motivo="Contacto ausente"
        ),
        lambda: operaciones.resolver_novedad(
            servicio, Resolucion.REANUDAR, actor=usuario, motivo="Ya llegó"
        ),
        lambda: operaciones.cambiar_estado(
            servicio, E.RECOGIDO, actor=usuario, nombre_quien="Portero Juan"
        ),
        lambda: operaciones.cambiar_estado(
            servicio, E.ENTREGADO, actor=usuario, nombre_quien="Recepción concesionario"
        ),
    ]
    for numero, paso in enumerate(pasos, start=1):
        evento = paso()
        assert servicio.eventos.count() == numero
        assert evento.actor == usuario
        assert evento.origen == OrigenEvento.PANEL
        assert evento.resultado == EventoEstado.Resultado.APLICADO
        assert evento.conductor == ana
        assert evento.destino == servicio.estado

    eventos = list(servicio.eventos.order_by("hora_sincronizacion"))
    assert [e.destino for e in eventos] == [
        E.ASIGNADO, E.EN_CAMINO, E.NOVEDAD, E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO,
    ]
    assert [e.motivo for e in eventos] == [
        "Primero en la ruta", "", "Contacto ausente", "Ya llegó", "", "",
    ]
    assert [e.nombre_quien for e in eventos][-2:] == ["Portero Juan", "Recepción concesionario"]
    # Un evento del panel no trae datos del celular.
    assert all(e.secuencia is None and e.hora_dispositivo is None for e in eventos)


@pytest.mark.parametrize("origen", [E.PENDIENTE_ASIGNAR, E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO,
                                    E.NOVEDAD])
@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_cancelar_exige_motivo(crear_servicio, usuario, origen, motivo):
    servicio = crear_servicio(origen)
    antes = foto(servicio)
    with pytest.raises(TransicionInvalida, match="exige motivo"):
        operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo=motivo)
    assert foto(servicio) == antes
    assert not EventoEstado.objects.exists()


@pytest.mark.parametrize("origen", [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO])
@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_novedad_exige_motivo(crear_servicio, usuario, origen, motivo):
    servicio = crear_servicio(origen)
    antes = foto(servicio)
    with pytest.raises(TransicionInvalida, match="exige motivo"):
        operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo=motivo)
    assert foto(servicio) == antes
    assert not EventoEstado.objects.exists()


def test_cancelar_guarda_el_motivo_y_conserva_conductor_y_grua(crear_servicio, ana, usuario):
    servicio = crear_servicio(E.EN_CAMINO)
    grua = servicio.grua
    evento = operaciones.cambiar_estado(
        servicio, E.CANCELADO, actor=usuario, motivo="  El cliente desistió  "
    )
    assert evento.motivo == "El cliente desistió"
    assert (servicio.estado, servicio.conductor, servicio.grua) == (E.CANCELADO, ana, grua)


def test_novedad_recuerda_el_estado_previo(crear_servicio, usuario):
    servicio = crear_servicio(E.RECOGIDO)
    operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo="Destino cerrado")
    assert (servicio.estado, servicio.estado_previo) == (E.NOVEDAD, E.RECOGIDO)


def test_el_estado_destino_puede_llegar_como_texto(crear_servicio, usuario):
    servicio = crear_servicio(E.ASIGNADO)
    operaciones.cambiar_estado(servicio, "en_camino", actor=usuario)
    assert servicio.estado == E.EN_CAMINO


# --- Asignar -----------------------------------------------------------------------------------


def test_asignar_toma_la_grua_vigente_del_conductor(crear_servicio, beto, grua2, usuario):
    servicio = crear_servicio()
    evento = operaciones.asignar(servicio, beto, actor=usuario)
    assert (servicio.estado, servicio.conductor, servicio.grua) == (E.ASIGNADO, beto, grua2)
    assert evento.conductor == beto


def test_asignar_a_un_conductor_sin_grua_vigente_falla_sin_dejar_rastro(crear_servicio, usuario):
    from flota.models import Conductor

    sin_grua = Conductor.objects.create(nombre="Carla", celular="3000000003")
    servicio = crear_servicio()
    with pytest.raises(SinGruaVigente, match="Carla no tiene una grúa asignada"):
        operaciones.asignar(servicio, sin_grua, actor=usuario)
    assert foto(servicio) == (E.PENDIENTE_ASIGNAR, "", None, None)
    assert not EventoEstado.objects.exists()


def test_un_conductor_puede_recibir_mas_servicios_que_la_capacidad_de_su_grua(
    crear_servicio, ana, usuario
):
    # Ana tiene una grúa de un puesto: atiende los tres servicios en rondas.
    servicios = [crear_servicio() for _ in range(3)]
    for servicio in servicios:
        operaciones.asignar(servicio, ana, actor=usuario)
    assert all(s.estado == E.ASIGNADO and s.conductor == ana for s in servicios)


@pytest.mark.parametrize(
    ("registro", "motivo", "mensaje"),
    [
        (EstadoRegistro.BORRADOR, "", "borrador"),
        (EstadoRegistro.NO_CONCRETADA, MotivoNoConcretada.PRECIO, "no se concretó"),
    ],
)
def test_no_se_asignan_servicios_de_un_borrador_ni_de_una_no_concretada(
    cliente, crear_servicio, ana, usuario, registro, motivo, mensaje
):
    solicitud = crear_solicitud(cliente, estado_registro=registro, motivo_no_concretada=motivo)
    servicio = crear_servicio(solicitud_de=solicitud)
    with pytest.raises(SolicitudNoAsignable, match=mensaje):
        operaciones.asignar(servicio, ana, actor=usuario)
    assert foto(servicio) == (E.PENDIENTE_ASIGNAR, "", None, None)
    assert not EventoEstado.objects.exists()


def test_asignar_no_se_hace_con_cambiar_estado(crear_servicio, usuario):
    servicio = crear_servicio()
    with pytest.raises(TransicionInvalida, match="asignar"):
        operaciones.cambiar_estado(servicio, E.ASIGNADO, actor=usuario)
    assert not EventoEstado.objects.exists()


def test_quien_llama_ve_el_servicio_actualizado(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    operaciones.asignar(servicio.pk, ana.pk, actor=usuario)  # también acepta llaves primarias
    servicio.refresh_from_db()
    assert servicio.conductor == ana
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    assert servicio.estado == E.EN_CAMINO  # sin refresh_from_db


# --- Reasignar y resolver novedad --------------------------------------------------------------


def test_reasignar_pasa_el_servicio_al_otro_conductor_con_su_grua(
    crear_servicio, ana, beto, grua2, usuario
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = operaciones.reasignar(servicio, beto, actor=usuario, motivo="Ana quedó varada")
    assert (servicio.estado, servicio.conductor, servicio.grua) == (E.ASIGNADO, beto, grua2)
    assert (evento.destino, evento.conductor, evento.motivo) == (
        E.ASIGNADO, beto, "Ana quedó varada",
    )


def test_resolver_novedad_reasignando_la_devuelve_a_la_cola_sin_conductor_ni_grua(
    crear_servicio, usuario
):
    servicio = crear_servicio(E.NOVEDAD, previo=E.EN_CAMINO)
    evento = operaciones.resolver_novedad(servicio, Resolucion.REASIGNAR, actor=usuario)
    assert foto(servicio) == (E.PENDIENTE_ASIGNAR, "", None, None)
    assert (evento.destino, evento.conductor) == (E.PENDIENTE_ASIGNAR, None)


def test_resolver_novedad_reanudando_vuelve_al_estado_previo(crear_servicio, ana, usuario):
    servicio = crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    operaciones.resolver_novedad(servicio, "reanudar", actor=usuario)
    assert foto(servicio)[:3] == (E.RECOGIDO, "", ana.pk)


def test_novedad_con_vehiculo_montado_no_se_reasigna(crear_servicio, usuario):
    servicio = crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    with pytest.raises(TransicionInvalida, match="montado"):
        operaciones.resolver_novedad(servicio, Resolucion.REASIGNAR, actor=usuario)
    assert not EventoEstado.objects.exists()


# --- Identificación al recoger -----------------------------------------------------------------


def test_no_se_marca_recogido_un_vehiculo_sin_placa_ni_vin(crear_servicio, nuevo_vehiculo, usuario):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    antes = foto(servicio)
    with pytest.raises(IdentificacionIncompleta, match="placa o VIN"):
        operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert foto(servicio) == antes
    assert not EventoEstado.objects.exists()


def test_un_desvare_sin_placa_no_se_marca_recogido_aunque_tenga_vin(
    cliente, crear_servicio, nuevo_vehiculo, usuario
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(
        E.EN_CAMINO, vehiculo=nuevo_vehiculo(vin=VIN), solicitud_de=desvare
    )
    with pytest.raises(IdentificacionIncompleta, match="Un desvare exige la placa"):
        operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.EN_CAMINO
    assert not EventoEstado.objects.exists()


def test_un_desvare_con_placa_si_se_marca_recogido(cliente, crear_servicio, usuario):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(E.EN_CAMINO, solicitud_de=desvare)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_un_traslado_con_solo_vin_si_se_marca_recogido(crear_servicio, nuevo_vehiculo, usuario):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(vin=VIN))
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_la_identificacion_que_llega_despues_permite_recoger(
    crear_servicio, nuevo_vehiculo, usuario
):
    vehiculo = nuevo_vehiculo(placa="", vin="")
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    vehiculo.vin = VIN.lower()
    vehiculo.save()
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_por_defecto_la_identificacion_no_se_exige_al_asignar(
    crear_servicio, nuevo_vehiculo, ana, usuario
):
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=""))
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_el_punto_de_extension_permite_exigir_la_identificacion_al_asignar(
    monkeypatch, crear_servicio, nuevo_vehiculo, ana, usuario
):
    monkeypatch.setattr(operaciones, "identificacion_exigida_al_asignar", lambda: True)
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", vin=""))
    with pytest.raises(IdentificacionIncompleta):
        operaciones.asignar(servicio, ana, actor=usuario)
    assert foto(servicio) == (E.PENDIENTE_ASIGNAR, "", None, None)
    assert not EventoEstado.objects.exists()


# --- Capacidad al recoger desde el panel -------------------------------------------------------


def test_grua_de_un_puesto_llena_rechaza_recoger_otro_y_dice_que_falta_entregar(
    crear_servicio, grua1, usuario
):
    montado = crear_servicio(E.RECOGIDO)
    servicio = crear_servicio(E.EN_CAMINO)
    assert servicio.grua == grua1 and grua1.capacidad == 1
    with pytest.raises(CapacidadExcedida) as error:
        operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert error.value.capacidad == 1
    assert error.value.pendientes_de_entregar == [str(montado)]
    assert servicio.estado == E.EN_CAMINO
    assert not EventoEstado.objects.exists()


def test_grua_de_dos_puestos_admite_el_segundo_pero_no_el_tercero(
    crear_servicio, beto, grua2, usuario
):
    crear_servicio(E.RECOGIDO, conductor=beto)
    segundo = crear_servicio(E.EN_CAMINO, conductor=beto)
    tercero = crear_servicio(E.EN_CAMINO, conductor=beto)
    assert segundo.grua == tercero.grua == grua2 and grua2.capacidad == 2

    operaciones.cambiar_estado(segundo, E.RECOGIDO, actor=usuario)
    assert segundo.estado == E.RECOGIDO
    with pytest.raises(CapacidadExcedida) as error:
        operaciones.cambiar_estado(tercero, E.RECOGIDO, actor=usuario)
    assert len(error.value.pendientes_de_entregar) == 2
    assert tercero.estado == E.EN_CAMINO
    assert tercero.eventos.count() == 0


def test_novedad_con_vehiculo_montado_sigue_ocupando_el_puesto(crear_servicio, usuario):
    crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    servicio = crear_servicio(E.EN_CAMINO)
    with pytest.raises(CapacidadExcedida):
        operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.EN_CAMINO


def test_novedad_antes_de_recoger_no_ocupa_puesto(crear_servicio, usuario):
    crear_servicio(E.NOVEDAD, previo=E.EN_CAMINO)
    servicio = crear_servicio(E.EN_CAMINO)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


@pytest.mark.parametrize("terminado", [E.ENTREGADO, E.CANCELADO])
def test_entregado_o_cancelado_libera_el_puesto(crear_servicio, usuario, terminado):
    crear_servicio(terminado)
    servicio = crear_servicio(E.EN_CAMINO)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_entregar_libera_el_puesto_para_el_siguiente(crear_servicio, usuario):
    primero = crear_servicio(E.EN_CAMINO)
    segundo = crear_servicio(E.EN_CAMINO)
    operaciones.cambiar_estado(primero, E.RECOGIDO, actor=usuario)
    with pytest.raises(CapacidadExcedida):
        operaciones.cambiar_estado(segundo, E.RECOGIDO, actor=usuario)
    operaciones.cambiar_estado(primero, E.ENTREGADO, actor=usuario)
    operaciones.cambiar_estado(segundo, E.RECOGIDO, actor=usuario)
    assert segundo.estado == E.RECOGIDO


def test_los_vehiculos_montados_en_otra_grua_no_cuentan(crear_servicio, beto, usuario):
    crear_servicio(E.RECOGIDO, conductor=beto)
    crear_servicio(E.RECOGIDO, conductor=beto)
    servicio = crear_servicio(E.EN_CAMINO)  # Ana, grúa de un puesto vacía
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_la_capacidad_se_cuenta_con_la_grua_guardada_en_el_servicio(
    crear_servicio, ana, grua2, usuario
):
    # Ana tiene hoy la grúa de un puesto, pero este servicio se asignó con la de dos.
    crear_servicio(E.RECOGIDO, grua=grua2)
    servicio = crear_servicio(E.EN_CAMINO, grua=grua2)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    assert servicio.estado == E.RECOGIDO


def test_el_servicio_en_nucleo_refleja_lo_guardado(crear_servicio):
    servicio = crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    assert servicio.como_nucleo() == ServicioNucleo(E.NOVEDAD, E.RECOGIDO)
