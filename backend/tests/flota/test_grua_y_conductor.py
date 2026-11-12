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


def test_la_base_rechaza_placa_sin_normalizar_aunque_no_pase_por_save():
    grua = Grua.objects.create(placa="ABC123", capacidad=1)
    with pytest.raises(IntegrityError, match="grua_placa_normalizada"), transaction.atomic():
        Grua.objects.filter(pk=grua.pk).update(placa="abc123")


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


def test_el_usuario_de_django_es_opcional_y_de_un_solo_conductor():
    assert Conductor.objects.create(nombre="Ana", celular="3001").usuario is None
    usuario = get_user_model().objects.create_user("beto")
    Conductor.objects.create(nombre="Beto", celular="3002", usuario=usuario)
    with pytest.raises(IntegrityError), transaction.atomic():
        Conductor.objects.create(nombre="Carla", celular="3003", usuario=usuario)
