"""Solicitud: restricciones de la base, pagador por defecto y estado derivado de sus servicios.

Las pruebas de restricción guardan con objects.create() o update(), que no llaman a clean().
"""
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from clientes.models import Cliente, Contacto, TipoCliente
from nucleo.estados import Estado, EstadoSolicitud, estado_solicitud
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EstadoRegistro, MotivoNoConcretada, Solicitud

from .conftest import crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado
EVENTO = TipoServicio.EVENTO
MANANA = timezone.now() + timedelta(days=1)


def rechazada_por_la_base(restriccion, cliente, **datos):
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        crear_solicitud(cliente, **datos)


# --- Valores por defecto y pagador -------------------------------------------------------------


def test_una_solicitud_nueva_es_borrador_inmediata_y_sin_respuesta_de_regreso(cliente):
    solicitud = Solicitud.objects.create(solicitante=cliente, tipo=TipoServicio.TRASLADO)
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert solicitud.programada_para is None  # inmediato
    assert solicitud.tiene_regreso is None  # no respondido, distinto de "no"
    assert solicitud.motivo_no_concretada == ""
    assert solicitud.es_demo is False
    assert solicitud.creada_en is not None
    assert solicitud.creada_por is None


def test_el_pagador_por_defecto_es_el_solicitante(cliente):
    solicitud = Solicitud.objects.create(solicitante=cliente, tipo=TipoServicio.TRASLADO)
    solicitud.refresh_from_db()
    assert solicitud.pagador == cliente


def test_el_pagador_puede_ser_otro_cliente(cliente):
    aseguradora = Cliente.objects.create(nombre="Aseguradora Uno", tipo=TipoCliente.ASEGURADORA)
    solicitud = crear_solicitud(cliente, pagador=aseguradora)
    solicitud.refresh_from_db()
    assert (solicitud.solicitante, solicitud.pagador) == (cliente, aseguradora)


def test_el_admin_tambien_pone_el_solicitante_como_pagador(cliente):
    solicitud = Solicitud(solicitante=cliente, tipo=TipoServicio.TRASLADO)
    solicitud.full_clean()
    assert solicitud.pagador == cliente


def test_contactos_de_origen_y_destino_son_opcionales(cliente):
    portero = Contacto.objects.create(nombre="Portero", telefono="3001234567")
    solicitud = crear_solicitud(cliente, contacto_origen=portero)
    solicitud.refresh_from_db()
    assert (solicitud.contacto_origen, solicitud.contacto_destino) == (portero, None)


def test_un_cliente_con_solicitudes_no_se_puede_borrar(cliente):
    crear_solicitud(cliente)
    with pytest.raises(ProtectedError):
        cliente.delete()


# --- Restricciones de la base ------------------------------------------------------------------


def test_la_base_rechaza_tipo_de_servicio_desconocido(cliente):
    rechazada_por_la_base("solicitud_tipo_valido", cliente, tipo="grua")


def test_la_base_rechaza_estado_de_registro_desconocido(cliente):
    rechazada_por_la_base("solicitud_estado_registro_valido", cliente, estado_registro="en_curso")


def test_la_base_rechaza_motivo_de_no_concretada_desconocido(cliente):
    rechazada_por_la_base(
        "solicitud_motivo_no_concretada_valido",
        cliente,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
        motivo_no_concretada="caro",
    )


def test_no_concretada_sin_motivo_rechazada_por_la_base(cliente):
    rechazada_por_la_base(
        "solicitud_no_concretada_exige_motivo",
        cliente,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
    )


@pytest.mark.parametrize("registro", [EstadoRegistro.BORRADOR, EstadoRegistro.ABIERTA])
def test_motivo_de_no_concretada_en_otra_solicitud_rechazado_por_la_base(cliente, registro):
    rechazada_por_la_base(
        "solicitud_motivo_solo_si_no_concretada",
        cliente,
        estado_registro=registro,
        motivo_no_concretada=MotivoNoConcretada.PRECIO,
    )


@pytest.mark.parametrize("motivo", MotivoNoConcretada.values)
def test_no_concretada_con_motivo_se_acepta(cliente, motivo):
    solicitud = crear_solicitud(
        cliente,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
        motivo_no_concretada=motivo,
        detalle_no_concretada="Le pareció caro",
    )
    assert solicitud.estado == "no_concretada"


@pytest.mark.parametrize("registro", [EstadoRegistro.ABIERTA, EstadoRegistro.NO_CONCRETADA])
def test_evento_sin_responder_si_tiene_regreso_rechazado_por_la_base(cliente, registro):
    motivo = MotivoNoConcretada.PRECIO if registro == EstadoRegistro.NO_CONCRETADA else ""
    rechazada_por_la_base(
        "solicitud_evento_responde_regreso",
        cliente,
        tipo=EVENTO,
        estado_registro=registro,
        motivo_no_concretada=motivo,
    )


def test_evento_en_borrador_puede_no_responder_aun_si_tiene_regreso(cliente):
    solicitud = crear_solicitud(cliente, tipo=EVENTO, estado_registro=EstadoRegistro.BORRADOR)
    assert solicitud.tiene_regreso is None


@pytest.mark.parametrize("tipo", [TipoServicio.TRASLADO, TipoServicio.DESVARE])
def test_otros_tipos_no_exigen_la_respuesta_de_regreso(cliente, tipo):
    assert crear_solicitud(cliente, tipo=tipo).tiene_regreso is None


def test_evento_sin_regreso_se_acepta(cliente):
    solicitud = crear_solicitud(cliente, tipo=EVENTO, tiene_regreso=False)
    solicitud.refresh_from_db()
    assert solicitud.tiene_regreso is False


def test_regreso_sin_fecha_rechazado_por_la_base(cliente):
    rechazada_por_la_base("solicitud_regreso_exige_fecha", cliente, tipo=EVENTO, tiene_regreso=True)


def test_evento_con_regreso_y_fecha_se_acepta(cliente):
    solicitud = crear_solicitud(cliente, tipo=EVENTO, tiene_regreso=True, fecha_regreso=MANANA)
    solicitud.refresh_from_db()
    assert solicitud.fecha_regreso == MANANA


def test_la_base_rechaza_quitar_el_motivo_aunque_no_pase_por_save(cliente):
    solicitud = crear_solicitud(
        cliente,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
        motivo_no_concretada=MotivoNoConcretada.SIN_GRUA,
    )
    with (
        pytest.raises(IntegrityError, match="solicitud_no_concretada_exige_motivo"),
        transaction.atomic(),
    ):
        Solicitud.objects.filter(pk=solicitud.pk).update(motivo_no_concretada="")


def test_la_base_rechaza_quitar_la_respuesta_de_regreso_aunque_no_pase_por_save(cliente):
    solicitud = crear_solicitud(cliente, tipo=EVENTO, tiene_regreso=False)
    with (
        pytest.raises(IntegrityError, match="solicitud_evento_responde_regreso"),
        transaction.atomic(),
    ):
        Solicitud.objects.filter(pk=solicitud.pk).update(tiene_regreso=None)


# --- Mensajes del admin (clean) ----------------------------------------------------------------


def errores_de(solicitud):
    with pytest.raises(ValidationError) as error:
        solicitud.full_clean()
    return error.value.message_dict


def test_el_admin_avisa_que_una_no_concretada_exige_motivo(cliente):
    solicitud = Solicitud(
        solicitante=cliente,
        tipo=TipoServicio.TRASLADO,
        estado_registro=EstadoRegistro.NO_CONCRETADA,
    )
    assert errores_de(solicitud) == {
        "motivo_no_concretada": ["Una solicitud no concretada exige el motivo."]
    }


def test_el_admin_avisa_que_el_motivo_solo_aplica_a_no_concretadas(cliente):
    solicitud = Solicitud(
        solicitante=cliente,
        tipo=TipoServicio.TRASLADO,
        estado_registro=EstadoRegistro.ABIERTA,
        motivo_no_concretada=MotivoNoConcretada.DEMORA,
    )
    assert errores_de(solicitud) == {
        "motivo_no_concretada": [
            "El motivo solo aplica cuando la solicitud se cierra como no concretada."
        ]
    }


def test_el_admin_avisa_que_un_evento_debe_responder_si_tiene_regreso(cliente):
    solicitud = Solicitud(solicitante=cliente, tipo=EVENTO, estado_registro=EstadoRegistro.ABIERTA)
    assert errores_de(solicitud) == {
        "tiene_regreso": ["En un evento hay que responder si tiene regreso."]
    }


def test_el_admin_avisa_que_el_regreso_exige_fecha(cliente):
    solicitud = Solicitud(
        solicitante=cliente, tipo=EVENTO, estado_registro=EstadoRegistro.ABIERTA, tiene_regreso=True
    )
    assert errores_de(solicitud) == {
        "fecha_regreso": ["Si tiene regreso, indique la fecha de regreso."]
    }


# --- Estado derivado ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estados", "esperado"),
    [
        ([], EstadoSolicitud.ABIERTA),
        ([E.PENDIENTE_ASIGNAR, E.ASIGNADO], EstadoSolicitud.ABIERTA),
        ([E.ASIGNADO, E.EN_CAMINO], EstadoSolicitud.EN_CURSO),
        ([E.NOVEDAD, E.PENDIENTE_ASIGNAR], EstadoSolicitud.EN_CURSO),
        ([E.ENTREGADO, E.PENDIENTE_ASIGNAR], EstadoSolicitud.EN_CURSO),
        ([E.ENTREGADO, E.CANCELADO], EstadoSolicitud.COMPLETADA),
        ([E.CANCELADO, E.CANCELADO], EstadoSolicitud.CANCELADA),
    ],
)
def test_el_estado_de_una_solicitud_abierta_se_deriva_de_sus_servicios(
    solicitud, crear_servicio, estados, esperado
):
    for estado in estados:
        crear_servicio(estado)
    assert solicitud.estado == esperado
    assert solicitud.estado == estado_solicitud(estados)  # la regla es la del núcleo


def test_el_estado_derivado_no_se_guarda_y_sigue_a_los_servicios(solicitud, crear_servicio, ana,
                                                                  usuario):
    servicio = crear_servicio()
    assert solicitud.estado == EstadoSolicitud.ABIERTA
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    assert solicitud.estado == EstadoSolicitud.EN_CURSO
    operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo="El cliente desistió")
    assert solicitud.estado == EstadoSolicitud.CANCELADA
    assert solicitud.estado_etiqueta == "Cancelada"
    assert "estado" not in {campo.name for campo in Solicitud._meta.get_fields()}


@pytest.mark.parametrize(
    ("registro", "motivo", "esperado"),
    [
        (EstadoRegistro.BORRADOR, "", "borrador"),
        (EstadoRegistro.NO_CONCRETADA, MotivoNoConcretada.OTRO, "no_concretada"),
    ],
)
def test_borrador_y_no_concretada_no_se_derivan_de_los_servicios(
    cliente, crear_servicio, registro, motivo, esperado
):
    solicitud = crear_solicitud(cliente, estado_registro=registro, motivo_no_concretada=motivo)
    crear_servicio(solicitud_de=solicitud)
    assert solicitud.estado == esperado
