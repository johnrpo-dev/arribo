"""Asignación conductor–grúa: sin traslapes por conductor ni por grúa, garantizado por la base.

Las pruebas de restricción guardan con objects.create(), que no llama a clean(): lo que rechaza
es PostgreSQL. Los periodos son [inicio, fin): el fin de uno puede ser el inicio del siguiente.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from flota.models import AsignacionConductorGrua, Conductor, Grua, grua_vigente

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")


def h(dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    """Una hora de noviembre de 2026 en Medellín."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=BOGOTA)


@pytest.fixture
def ana():
    return Conductor.objects.create(nombre="Ana", celular="3000000001")


@pytest.fixture
def beto():
    return Conductor.objects.create(nombre="Beto", celular="3000000002")


@pytest.fixture
def grua1():
    return Grua.objects.create(placa="GRU001", capacidad=2)


@pytest.fixture
def grua2():
    return Grua.objects.create(placa="GRU002", capacidad=1)


def asignar(conductor, grua, inicio, fin=None, **otros):
    return AsignacionConductorGrua.objects.create(
        conductor=conductor, grua=grua, inicio=inicio, fin=fin, **otros
    )


POR_CONDUCTOR = "asignacion_sin_traslape_por_conductor"
POR_GRUA = "asignacion_sin_traslape_por_grua"
FIN_POSTERIOR = "asignacion_fin_posterior_a_inicio"


def rechazada_por_la_base(restriccion, conductor, grua, inicio, fin=None):
    """Guarda sin clean() y exige que PostgreSQL lo rechace con esa restricción."""
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        asignar(conductor, grua, inicio, fin)


# --- Restricciones en la base de datos ---------------------------------------------------------


def test_traslape_por_conductor_rechazado(ana, grua1, grua2):
    asignar(ana, grua1, h(1, 8), h(1, 18))
    rechazada_por_la_base(POR_CONDUCTOR, ana, grua2, h(1, 12), h(1, 20))


def test_traslape_por_grua_rechazado(ana, beto, grua1):
    asignar(ana, grua1, h(1, 8), h(1, 18))
    rechazada_por_la_base(POR_GRUA, beto, grua1, h(1, 6), h(1, 9))


def test_periodo_contenido_en_otro_tambien_es_traslape(ana, grua1, grua2):
    asignar(ana, grua1, h(1, 8), h(1, 18))
    rechazada_por_la_base(POR_CONDUCTOR, ana, grua2, h(1, 10), h(1, 11))


def test_asignacion_vigente_bloquea_otra_posterior_del_mismo_conductor(ana, grua1, grua2):
    asignar(ana, grua1, h(1, 8))
    rechazada_por_la_base(POR_CONDUCTOR, ana, grua2, h(20, 8))
    rechazada_por_la_base(POR_CONDUCTOR, ana, grua2, h(20, 8), h(20, 18))


def test_asignacion_vigente_bloquea_otra_posterior_de_la_misma_grua(ana, beto, grua1):
    asignar(ana, grua1, h(1, 8))
    rechazada_por_la_base(POR_GRUA, beto, grua1, h(20, 8))
    rechazada_por_la_base(POR_GRUA, beto, grua1, h(20, 8), h(20, 18))


def test_periodos_contiguos_permitidos(ana, beto, grua1, grua2):
    asignar(ana, grua1, h(1, 8), h(1, 14))
    asignar(ana, grua2, h(1, 14), h(1, 18))  # mismo conductor, empieza cuando termina el otro
    asignar(beto, grua1, h(1, 14))  # misma grúa, empieza cuando termina la otra
    assert AsignacionConductorGrua.objects.count() == 3


def test_otro_conductor_y_otra_grua_en_el_mismo_periodo_no_chocan(ana, beto, grua1, grua2):
    asignar(ana, grua1, h(1, 8))
    asignar(beto, grua2, h(1, 8))
    assert AsignacionConductorGrua.objects.count() == 2


@pytest.mark.parametrize("fin", [h(1, 7), h(1, 8)], ids=["fin_anterior", "fin_igual"])
def test_fin_anterior_o_igual_a_inicio_rechazado(ana, grua1, fin):
    rechazada_por_la_base(FIN_POSTERIOR, ana, grua1, h(1, 8), fin)


def test_la_grua_y_el_conductor_no_se_pueden_borrar_con_asignaciones(ana, grua1):
    asignar(ana, grua1, h(1, 8))
    with pytest.raises(ProtectedError):
        grua1.delete()
    with pytest.raises(ProtectedError):
        ana.delete()


# --- Cambio temporal de grúa y grua_vigente ----------------------------------------------------


def test_cambio_temporal_de_grua_y_grua_vigente_antes_durante_y_despues(ana, grua1, grua2):
    habitual = asignar(ana, grua1, h(1, 8))
    assert grua_vigente(ana, en=h(5, 10)) == grua1

    # La grúa habitual entra al taller el día 5 a las 12: se cierra la vigente y se abre la temporal.
    habitual.fin = h(5, 12)
    habitual.save()
    asignar(ana, grua2, h(5, 12), h(7, 12), temporal=True, motivo="GRU001 en el taller")
    # Vuelve a la habitual cuando sale del taller.
    asignar(ana, grua1, h(7, 12))

    assert grua_vigente(ana, en=h(5, 11, 59)) == grua1  # antes
    assert grua_vigente(ana, en=h(5, 12)) == grua2  # en el instante del cambio ya rige la nueva
    assert grua_vigente(ana, en=h(6, 9)) == grua2  # durante
    assert grua_vigente(ana, en=h(7, 12)) == grua1  # después
    assert grua_vigente(ana, en=h(30, 23)) == grua1


def test_grua_vigente_es_none_sin_asignacion_o_fuera_del_periodo(ana, grua1):
    assert grua_vigente(ana) is None
    asignar(ana, grua1, h(2, 8), h(3, 8))
    assert grua_vigente(ana, en=h(1, 8)) is None
    assert grua_vigente(ana, en=h(3, 8)) is None


def test_grua_vigente_por_defecto_es_ahora(ana, grua1):
    asignar(ana, grua1, h(1, 8))  # sin fin: vigente hoy
    assert grua_vigente(ana) == grua1


# --- Validación de clean(): mensajes para el admin ---------------------------------------------


def test_clean_explica_en_espanol_el_traslape_por_conductor(ana, grua1, grua2):
    asignar(ana, grua1, h(1, 8))
    nueva = AsignacionConductorGrua(conductor=ana, grua=grua2, inicio=h(3, 8))
    with pytest.raises(ValidationError) as error:
        nueva.full_clean()
    mensajes = error.value.message_dict
    assert list(mensajes) == ["conductor"]
    assert "Ana ya tiene asignada la grúa GRU001" in mensajes["conductor"][0]
    assert "se cruza con este periodo" in mensajes["conductor"][0]


def test_clean_explica_en_espanol_el_traslape_por_grua(ana, beto, grua1):
    asignar(ana, grua1, h(1, 8), h(1, 18))
    nueva = AsignacionConductorGrua(conductor=beto, grua=grua1, inicio=h(1, 12))
    with pytest.raises(ValidationError) as error:
        nueva.full_clean()
    mensajes = error.value.message_dict
    assert list(mensajes) == ["grua"]
    assert "La grúa GRU001 ya está asignada a Ana" in mensajes["grua"][0]


def test_clean_explica_en_espanol_que_el_fin_va_despues_del_inicio(ana, grua1):
    nueva = AsignacionConductorGrua(conductor=ana, grua=grua1, inicio=h(1, 8), fin=h(1, 8))
    with pytest.raises(ValidationError) as error:
        nueva.full_clean()
    assert error.value.message_dict == {"fin": ["El fin debe ser posterior al inicio."]}


def test_clean_acepta_periodos_contiguos_y_editar_la_misma_asignacion(ana, grua1):
    vigente = asignar(ana, grua1, h(1, 8), h(1, 14))
    AsignacionConductorGrua(conductor=ana, grua=grua1, inicio=h(1, 14)).full_clean()
    vigente.motivo = "Turno de la mañana"
    vigente.full_clean()  # no choca consigo misma
