"""Servicio: restricciones de la base, cambios solo por operaciones y conductor y grúa históricos.

Las pruebas de restricción guardan con objects.create() o update(), sin pasar por las operaciones:
lo que rechaza es PostgreSQL.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from flota.models import AsignacionConductorGrua, grua_vigente
from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import CambioDeEstadoNoPermitido, EventoEstado, Servicio

pytestmark = pytest.mark.django_db

E = Estado
EN_CURSO = [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO]


def rechazado_por_la_base(restriccion, crear):
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        crear()


# --- Restricciones de la base ------------------------------------------------------------------


def test_un_servicio_nuevo_queda_pendiente_de_asignar_sin_conductor_ni_grua(
    solicitud, nuevo_vehiculo
):
    servicio = Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo())
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR
    assert (servicio.estado_previo, servicio.conductor, servicio.grua) == ("", None, None)


def test_la_base_rechaza_estado_desconocido(solicitud, nuevo_vehiculo):
    rechazado_por_la_base(
        "servicio_estado_valido",
        lambda: Servicio.objects.create(
            solicitud=solicitud, vehiculo=nuevo_vehiculo(), estado="volando"
        ),
    )


def test_la_base_rechaza_estado_desconocido_aunque_no_pase_por_save(crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    with pytest.raises(IntegrityError, match="servicio_estado_valido"), transaction.atomic():
        Servicio.objects.filter(pk=servicio.pk).update(estado="volando")


def test_novedad_sin_estado_previo_rechazada_por_la_base(crear_servicio):
    servicio = crear_servicio(E.NOVEDAD)
    with (
        pytest.raises(IntegrityError, match="servicio_estado_previo_solo_en_novedad"),
        transaction.atomic(),
    ):
        Servicio.objects.filter(pk=servicio.pk).update(estado_previo="")


@pytest.mark.parametrize("estado", [e for e in Estado if e != E.NOVEDAD])
def test_estado_previo_fuera_de_novedad_rechazado_por_la_base(crear_servicio, estado):
    servicio = crear_servicio(estado)
    with (
        pytest.raises(IntegrityError, match="servicio_estado_previo_solo_en_novedad"),
        transaction.atomic(),
    ):
        Servicio.objects.filter(pk=servicio.pk).update(estado_previo=E.EN_CAMINO)


@pytest.mark.parametrize(
    "previo", [E.PENDIENTE_ASIGNAR, E.ENTREGADO, E.CANCELADO, E.NOVEDAD, "x"]
)
def test_estado_previo_desde_el_que_no_se_abre_novedad_rechazado_por_la_base(
    crear_servicio, previo
):
    servicio = crear_servicio(E.NOVEDAD)
    with pytest.raises(IntegrityError, match="servicio_estado_previo_valido"), transaction.atomic():
        Servicio.objects.filter(pk=servicio.pk).update(estado_previo=previo)


@pytest.mark.parametrize("previo", [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO])
def test_novedad_con_estado_previo_valido_se_acepta(crear_servicio, previo):
    servicio = crear_servicio(E.NOVEDAD, previo=previo)
    servicio.refresh_from_db()
    assert servicio.estado_previo == previo


@pytest.mark.parametrize("falta", ["conductor", "grua"])
def test_pendiente_de_asignar_con_conductor_o_grua_rechazado_por_la_base(
    solicitud, nuevo_vehiculo, ana, grua1, falta
):
    datos = {"conductor": ana} if falta == "conductor" else {"grua": grua1}
    rechazado_por_la_base(
        "servicio_pendiente_sin_conductor_ni_grua",
        lambda: Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo(), **datos),
    )


@pytest.mark.parametrize("estado", EN_CURSO)
@pytest.mark.parametrize("sin", ["conductor", "grua", "ambos"])
def test_asignado_en_camino_recogido_o_entregado_sin_conductor_o_grua_rechazado_por_la_base(
    solicitud, nuevo_vehiculo, ana, grua1, estado, sin
):
    datos = {
        "conductor": None if sin in ("conductor", "ambos") else ana,
        "grua": None if sin in ("grua", "ambos") else grua1,
    }
    rechazado_por_la_base(
        "servicio_en_curso_con_conductor_y_grua",
        lambda: Servicio.objects.create(
            solicitud=solicitud, vehiculo=nuevo_vehiculo(), estado=estado, **datos
        ),
    )


def test_la_base_rechaza_quitar_el_conductor_aunque_no_pase_por_save(crear_servicio):
    servicio = crear_servicio(E.EN_CAMINO)
    with (
        pytest.raises(IntegrityError, match="servicio_en_curso_con_conductor_y_grua"),
        transaction.atomic(),
    ):
        Servicio.objects.filter(pk=servicio.pk).update(conductor=None)


@pytest.mark.parametrize("estado", [E.NOVEDAD, E.CANCELADO])
def test_novedad_y_cancelado_conservan_el_conductor(crear_servicio, ana, estado):
    servicio = crear_servicio(estado)
    servicio.refresh_from_db()
    assert servicio.conductor == ana


def test_un_servicio_cancelado_antes_de_asignar_no_tiene_conductor(solicitud, nuevo_vehiculo):
    servicio = Servicio.objects.create(
        solicitud=solicitud, vehiculo=nuevo_vehiculo(), estado=E.CANCELADO
    )
    assert servicio.conductor is None


# --- Regreso -----------------------------------------------------------------------------------


def test_el_regreso_es_un_servicio_nuevo_enlazado_a_la_ida(crear_servicio):
    ida = crear_servicio()
    regreso = crear_servicio()
    regreso.regreso_de = ida
    regreso.save()
    ida.refresh_from_db()
    assert ida.regreso == regreso


def test_una_ida_tiene_un_solo_regreso(solicitud, nuevo_vehiculo, crear_servicio):
    ida = crear_servicio()
    Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo(), regreso_de=ida)
    with pytest.raises(IntegrityError), transaction.atomic():
        Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo(), regreso_de=ida)


# --- El estado solo cambia por las operaciones -------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("estado", E.EN_CAMINO), ("estado_previo", E.ASIGNADO), ("conductor", None), ("grua", None)],
)
def test_cambiar_estado_conductor_o_grua_guardando_el_modelo_falla_y_no_deja_evento(
    crear_servicio, campo, valor
):
    servicio = crear_servicio(E.ASIGNADO)
    setattr(servicio, campo, valor)
    with pytest.raises(CambioDeEstadoNoPermitido, match="solo cambian con las operaciones"):
        servicio.save()
    servicio.refresh_from_db()
    assert servicio.estado == E.ASIGNADO
    assert servicio.conductor is not None
    assert not EventoEstado.objects.exists()


def test_cambiar_a_otro_conductor_guardando_el_modelo_falla(crear_servicio, beto):
    servicio = crear_servicio(E.ASIGNADO)
    servicio.conductor = beto
    servicio.grua = grua_vigente(beto)
    with pytest.raises(CambioDeEstadoNoPermitido):
        servicio.save()


def test_editar_otros_datos_del_servicio_si_se_puede(crear_servicio):
    servicio = crear_servicio(E.EN_CAMINO)
    servicio.referencia_externa = "CASO-2026-001"
    servicio.orden_ronda = 2
    servicio.save()
    servicio.refresh_from_db()
    assert (servicio.referencia_externa, servicio.orden_ronda) == ("CASO-2026-001", 2)
    assert servicio.estado == E.EN_CAMINO


def test_guardar_una_copia_vieja_no_pisa_un_cambio_hecho_por_las_operaciones(
    crear_servicio, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    copia_vieja = Servicio.objects.get(pk=servicio.pk)
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    copia_vieja.referencia_externa = "CASO-1"
    with pytest.raises(CambioDeEstadoNoPermitido):
        copia_vieja.save()
    servicio.refresh_from_db()
    assert servicio.estado == E.EN_CAMINO


def test_un_servicio_con_eventos_no_se_puede_borrar(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    with pytest.raises(ProtectedError):
        servicio.delete()


# --- Conductor y grúa históricos ---------------------------------------------------------------


def cambiar_de_grua(conductor, grua_nueva):
    """El conductor deja su grúa actual y pasa a otra desde ahora."""
    cambio = timezone.now() - timedelta(seconds=1)
    vigente = AsignacionConductorGrua.objects.get(conductor=conductor, fin__isnull=True)
    vigente.fin = cambio
    vigente.save()
    AsignacionConductorGrua.objects.create(conductor=conductor, grua=grua_nueva, inicio=cambio)


def test_el_servicio_conserva_conductor_y_grua_aunque_el_conductor_cambie_de_grua(
    crear_servicio, ana, grua1, grua2, usuario
):
    en_curso = crear_servicio()
    terminado = crear_servicio()
    operaciones.asignar(en_curso, ana, actor=usuario)
    operaciones.asignar(terminado, ana, actor=usuario)
    for destino in (E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO):
        operaciones.cambiar_estado(terminado, destino, actor=usuario)
    assert en_curso.grua == terminado.grua == grua1

    cambiar_de_grua(ana, grua2)
    assert grua_vigente(ana) == grua2

    for servicio in (en_curso, terminado):
        servicio.refresh_from_db()
        assert (servicio.conductor, servicio.grua) == (ana, grua1)
    # Seguir trabajando el servicio no le cambia la grúa con que se asignó.
    operaciones.cambiar_estado(en_curso, E.EN_CAMINO, actor=usuario)
    assert en_curso.grua == grua1
    # Un servicio asignado después del cambio sí sale con la grúa nueva.
    nuevo = crear_servicio()
    operaciones.asignar(nuevo, ana, actor=usuario)
    assert nuevo.grua == grua2
