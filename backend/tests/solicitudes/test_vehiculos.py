"""Vehículo: placa y VIN únicos cuando existen, normalizados y garantizados por la base.

Las pruebas de restricción guardan con objects.create() o update(), que no llaman a clean(): lo que
rechaza es PostgreSQL.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from solicitudes.models import Servicio, Vehiculo

from .conftest import VIN, crear_solicitud

pytestmark = pytest.mark.django_db

PLACA_UNICA = "vehiculo_placa_unica"
VIN_UNICO = "vehiculo_vin_unico"
PLACA_NORMALIZADA = "vehiculo_placa_normalizada"
VIN_VALIDO = "vehiculo_vin_valido"


def rechazado_por_la_base(restriccion, **datos):
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        Vehiculo.objects.create(**datos)


# --- Normalización -----------------------------------------------------------------------------


def test_la_placa_y_el_vin_se_guardan_normalizados():
    vehiculo = Vehiculo.objects.create(placa=" abc-123 ", vin="1hg-cm826 33a004352")
    vehiculo.refresh_from_db()
    assert (vehiculo.placa, vehiculo.vin) == ("ABC123", VIN)


def test_un_vehiculo_puede_existir_sin_placa_ni_vin():
    # Un concesionario puede pedir el servicio sin tener aún el VIN: se exige al recoger.
    vehiculo = Vehiculo.objects.create(marca="Mazda", linea="3")
    vehiculo.refresh_from_db()
    assert (vehiculo.placa, vehiculo.vin) == ("", "")


# --- Unicidad de placa -------------------------------------------------------------------------


@pytest.mark.parametrize("variante", ["ABC123", "abc123", "ABC-123", "abc 123", " a-b-c 1.2.3 "])
def test_placa_duplicada_rechazada_por_la_base_aunque_se_escriba_distinto(variante):
    Vehiculo.objects.create(placa="ABC123")
    rechazado_por_la_base(PLACA_UNICA, placa=variante)


def test_varios_vehiculos_sin_placa_se_permiten():
    Vehiculo.objects.create(placa="")
    Vehiculo.objects.create(placa="", vin=VIN)
    Vehiculo.objects.create(placa=" - ")  # queda vacía al normalizar
    assert Vehiculo.objects.filter(placa="").count() == 3


@pytest.mark.parametrize("sin_normalizar", ["abc123", "ABC-123", "ABC 123", "ÑAB123"])
def test_la_base_rechaza_placa_sin_normalizar_aunque_no_pase_por_save(sin_normalizar):
    vehiculo = Vehiculo.objects.create(placa="ABC123")
    with pytest.raises(IntegrityError, match=PLACA_NORMALIZADA), transaction.atomic():
        Vehiculo.objects.filter(pk=vehiculo.pk).update(placa=sin_normalizar)


def test_la_base_rechaza_placa_duplicada_aunque_no_pase_por_save():
    Vehiculo.objects.create(placa="ABC123")
    otro = Vehiculo.objects.create(placa="XYZ987")
    with pytest.raises(IntegrityError, match=PLACA_UNICA), transaction.atomic():
        Vehiculo.objects.filter(pk=otro.pk).update(placa="ABC123")


# --- Unicidad y formato del VIN ----------------------------------------------------------------


@pytest.mark.parametrize(
    "variante", [VIN, VIN.lower(), "1HG-CM826-33A004352", " 1hg cm826 33a004352 "]
)
def test_vin_duplicado_rechazado_por_la_base_aunque_se_escriba_distinto(variante):
    Vehiculo.objects.create(vin=VIN)
    rechazado_por_la_base(VIN_UNICO, vin=variante)


def test_varios_vehiculos_sin_vin_se_permiten():
    Vehiculo.objects.create(placa="ABC123")
    Vehiculo.objects.create(placa="XYZ987", vin="")
    Vehiculo.objects.create()
    assert Vehiculo.objects.filter(vin="").count() == 3


def test_la_misma_placa_no_choca_con_un_vin_ni_al_reves():
    Vehiculo.objects.create(placa="ABC123")
    Vehiculo.objects.create(vin=VIN)
    Vehiculo.objects.create(placa="XYZ987", vin="WVWZZZ1JZXW000001")
    assert Vehiculo.objects.count() == 3


@pytest.mark.parametrize("letra", ["I", "O", "Q", "i", "o", "q"])
def test_la_base_rechaza_vin_con_i_o_q(letra):
    rechazado_por_la_base(VIN_VALIDO, vin=VIN[:-1] + letra)


@pytest.mark.parametrize("vin", [VIN[:16], VIN + "1", VIN[:5], "1" * 25])
def test_la_base_rechaza_vin_de_largo_distinto_de_17(vin):
    rechazado_por_la_base(VIN_VALIDO, vin=vin)


@pytest.mark.parametrize("vin", ["1HGCM.82633A00435", "1HGCM82633A00435*", "1HGCM82633A00435Ñ"])
def test_la_base_rechaza_vin_con_simbolos(vin):
    rechazado_por_la_base(VIN_VALIDO, vin=vin)


@pytest.mark.parametrize("sin_normalizar", [VIN.lower(), "1HG-CM82633A00435", "1HG CM82633A00435"])
def test_la_base_rechaza_vin_sin_normalizar_aunque_no_pase_por_save(sin_normalizar):
    vehiculo = Vehiculo.objects.create(vin=VIN)
    with pytest.raises(IntegrityError, match=VIN_VALIDO), transaction.atomic():
        Vehiculo.objects.filter(pk=vehiculo.pk).update(vin=sin_normalizar)


def test_la_base_rechaza_vin_duplicado_aunque_no_pase_por_save():
    Vehiculo.objects.create(vin=VIN)
    otro = Vehiculo.objects.create(vin="WVWZZZ1JZXW000001")
    with pytest.raises(IntegrityError, match=VIN_UNICO), transaction.atomic():
        Vehiculo.objects.filter(pk=otro.pk).update(vin=VIN)


# --- Mensajes del admin (clean) ----------------------------------------------------------------


def test_el_admin_avisa_en_espanol_que_la_placa_ya_existe():
    Vehiculo.objects.create(placa="ABC123")
    with pytest.raises(ValidationError) as error:
        Vehiculo(placa="abc-123").full_clean()
    assert error.value.message_dict == {"placa": ["Ya hay un vehículo con la placa ABC123."]}


def test_el_admin_avisa_en_espanol_que_el_vin_ya_existe():
    Vehiculo.objects.create(vin=VIN)
    with pytest.raises(ValidationError) as error:
        Vehiculo(vin=VIN.lower()).full_clean()
    assert error.value.message_dict == {"vin": [f"Ya hay un vehículo con el VIN {VIN}."]}


@pytest.mark.parametrize("vin", [VIN[:-1] + "O", VIN[:16], "1HGCM.82633A00435"])
def test_el_admin_avisa_en_espanol_que_el_vin_no_es_valido(vin):
    with pytest.raises(ValidationError) as error:
        Vehiculo(vin=vin).full_clean()
    mensajes = error.value.message_dict
    assert list(mensajes) == ["vin"]
    assert len(mensajes["vin"]) == 1
    assert "sin I, O ni Q" in mensajes["vin"][0]


def test_el_admin_acepta_vehiculo_sin_placa_ni_vin_y_editar_el_mismo():
    Vehiculo(marca="Renault").full_clean()
    vehiculo = Vehiculo.objects.create(placa="ABC123", vin=VIN)
    vehiculo.color = "Rojo"
    vehiculo.full_clean()  # no choca consigo mismo


# --- Relación con servicios --------------------------------------------------------------------


def test_el_mismo_vehiculo_puede_tener_muchos_servicios(solicitud, cliente):
    vehiculo = Vehiculo.objects.create(placa="ABC123")
    Servicio.objects.create(solicitud=solicitud, vehiculo=vehiculo)
    Servicio.objects.create(solicitud=crear_solicitud(cliente), vehiculo=vehiculo)
    assert vehiculo.servicios.count() == 2


def test_un_vehiculo_con_servicios_no_se_puede_borrar(solicitud):
    vehiculo = Vehiculo.objects.create(placa="ABC123")
    Servicio.objects.create(solicitud=solicitud, vehiculo=vehiculo)
    with pytest.raises(ProtectedError):
        vehiculo.delete()


def test_un_vehiculo_nuevo_no_es_de_demostracion():
    assert Vehiculo.objects.create(placa="ABC123").es_demo is False
