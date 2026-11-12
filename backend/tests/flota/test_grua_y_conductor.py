"""Grúa y conductor: lo que la base de datos garantiza aunque se guarde sin pasar por el admin."""
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from flota.models import Conductor, Grua

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("capacidad", [0, 3])
def test_la_base_rechaza_capacidad_distinta_de_1_o_2(capacidad):
    with pytest.raises(IntegrityError, match="grua_capacidad_1_o_2"), transaction.atomic():
        Grua.objects.create(placa="ABC123", capacidad=capacidad)


@pytest.mark.parametrize("capacidad", [1, 2])
def test_capacidad_1_o_2_se_acepta(capacidad):
    assert Grua.objects.create(placa="ABC123", capacidad=capacidad).capacidad == capacidad


def test_la_placa_se_guarda_en_mayusculas_y_sin_espacios():
    grua = Grua.objects.create(placa=" abc 123 ", capacidad=1)
    grua.refresh_from_db()
    assert grua.placa == "ABC123"


def test_placa_duplicada_rechazada():
    Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(IntegrityError, match="flota_grua_placa"), transaction.atomic():
        Grua.objects.create(placa="ABC123", capacidad=2)


@pytest.mark.parametrize("variante", ["abc123", "abc 123", "ABC 123"])
def test_placa_duplicada_en_minusculas_o_con_espacios_rechazada(variante):
    Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(IntegrityError, match="flota_grua_placa"), transaction.atomic():
        Grua.objects.create(placa=variante, capacidad=2)


@pytest.mark.parametrize("variante", ["ABC-123", "abc-123", "A.B.C 1-2-3"])
def test_la_placa_se_guarda_sin_guiones_ni_simbolos(variante):
    grua = Grua.objects.create(placa=variante, capacidad=1)
    grua.refresh_from_db()
    assert grua.placa == "ABC123"


def test_placa_duplicada_con_guion_rechazada():
    Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(IntegrityError, match="flota_grua_placa"), transaction.atomic():
        Grua.objects.create(placa="ABC-123", capacidad=2)


@pytest.mark.parametrize("sin_normalizar", ["abc123", "ABC-123", "ABC 123", ""])
def test_la_base_rechaza_placa_sin_normalizar_aunque_no_pase_por_save(sin_normalizar):
    grua = Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(IntegrityError, match="grua_placa_normalizada"), transaction.atomic():
        Grua.objects.filter(pk=grua.pk).update(placa=sin_normalizar)


def test_el_admin_avisa_en_espanol_que_la_placa_ya_existe():
    Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(ValidationError) as error:
        Grua(placa="abc 123", capacidad=2).full_clean()
    assert error.value.message_dict["placa"][0].startswith("Ya existe")


def test_una_grua_nueva_es_operativa_y_activa():
    grua = Grua.objects.create(placa="ABC123", capacidad=2)
    assert grua.estado_operativo == Grua.EstadoOperativo.OPERATIVA
    assert grua.activa is True


def test_celular_de_conductor_duplicado_rechazado():
    Conductor.objects.create(nombre="Ana", celular="3001234567")
    with pytest.raises(IntegrityError), transaction.atomic():
        Conductor.objects.create(nombre="Beto", celular="3001234567")


@pytest.mark.parametrize("celular", ["300 123 4567", "300-123-4567", "+57 300 123 4567"])
def test_el_celular_se_guarda_solo_con_digitos_y_sin_57(celular):
    conductor = Conductor.objects.create(nombre="Ana", celular=celular)
    conductor.refresh_from_db()
    assert conductor.celular == "3001234567"


@pytest.mark.parametrize("variante", ["300 123 4567", "+57 300 123 4567", "57-300-123-4567"])
def test_celular_duplicado_con_espacios_o_57_rechazado(variante):
    Conductor.objects.create(nombre="Ana", celular="3001234567")
    with pytest.raises(IntegrityError, match="flota_conductor_celular"), transaction.atomic():
        Conductor.objects.create(nombre="Beto", celular=variante)


@pytest.mark.parametrize("sin_normalizar", ["300 123 4567", "+573001234567", ""])
def test_la_base_rechaza_celular_sin_normalizar_aunque_no_pase_por_save(sin_normalizar):
    conductor = Conductor.objects.create(nombre="Ana", celular="3001234567")
    with pytest.raises(IntegrityError, match="conductor_celular_solo_digitos"), transaction.atomic():
        Conductor.objects.filter(pk=conductor.pk).update(celular=sin_normalizar)


def test_el_admin_avisa_en_espanol_que_el_celular_ya_existe():
    Conductor.objects.create(nombre="Ana", celular="3001234567")
    with pytest.raises(ValidationError) as error:
        Conductor(nombre="Beto", celular="+57 300 123 4567").full_clean()
    assert error.value.message_dict["celular"][0].startswith("Ya existe")


def test_el_admin_avisa_en_espanol_que_el_celular_no_es_valido():
    with pytest.raises(ValidationError) as error:
        Conductor(nombre="Ana", celular="300 12").full_clean()
    assert "entre 7 y 15 dígitos" in error.value.message_dict["celular"][0]


def test_grua_y_conductor_nuevos_no_son_de_demostracion():
    assert Grua.objects.create(placa="ABC123", capacidad=1).es_demo is False
    assert Conductor.objects.create(nombre="Ana", celular="3001234567").es_demo is False


def test_el_usuario_de_django_es_opcional_y_de_un_solo_conductor():
    assert Conductor.objects.create(nombre="Ana", celular="3000000001").usuario is None
    usuario = get_user_model().objects.create_user("beto")
    Conductor.objects.create(nombre="Beto", celular="3000000002", usuario=usuario)
    with pytest.raises(IntegrityError), transaction.atomic():
        Conductor.objects.create(nombre="Carla", celular="3000000003", usuario=usuario)
