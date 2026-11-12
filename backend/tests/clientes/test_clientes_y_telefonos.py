"""Clientes, teléfonos y contactos: lo que la base garantiza aunque se guarde sin pasar por el admin."""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from clientes.models import (
    Cliente,
    Contacto,
    ModalidadCobro,
    TelefonoCliente,
    TipoCliente,
    buscar_cliente_por_telefono,
)
from nucleo.identificacion import TelefonoInvalido

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente():
    return Cliente.objects.create(nombre="Autos del Valle", tipo=TipoCliente.CONCESIONARIO)


@pytest.fixture
def otro_cliente():
    return Cliente.objects.create(nombre="Ana Pérez", tipo=TipoCliente.PARTICULAR)


def test_valores_por_defecto_de_un_cliente_nuevo(cliente):
    cliente.refresh_from_db()
    assert cliente.modalidad_cobro == ModalidadCobro.POR_SERVICIO
    assert cliente.firma_obligatoria is False
    assert cliente.activo is True
    assert cliente.es_demo is False
    assert cliente.documento == ""
    assert cliente.notas == ""


def test_tipos_de_cliente():
    assert TipoCliente.values == ["particular", "concesionario", "aseguradora"]
    assert TipoCliente.ASEGURADORA.label == "Aseguradora o empresa de asistencia"


def test_la_base_rechaza_tipo_de_cliente_desconocido():
    with pytest.raises(IntegrityError, match="cliente_tipo_valido"), transaction.atomic():
        Cliente.objects.create(nombre="X", tipo="otro")


def test_la_base_rechaza_modalidad_de_cobro_desconocida():
    with pytest.raises(IntegrityError, match="cliente_modalidad_cobro_valida"), transaction.atomic():
        Cliente.objects.create(nombre="X", tipo=TipoCliente.PARTICULAR, modalidad_cobro="mensual")


def test_el_telefono_se_guarda_solo_con_digitos_y_sin_57(cliente):
    telefono = TelefonoCliente.objects.create(cliente=cliente, numero="+57 300 123 4567")
    telefono.refresh_from_db()
    assert telefono.numero == "3001234567"


@pytest.mark.parametrize("variante", ["3001234567", "300 123 4567", "+57 300-123-4567"])
def test_telefono_duplicado_rechazado_por_la_base_aunque_se_escriba_distinto(
    cliente, otro_cliente, variante
):
    TelefonoCliente.objects.create(cliente=cliente, numero="300-123-4567")
    with pytest.raises(IntegrityError, match="clientes_telefonocliente_numero"), transaction.atomic():
        TelefonoCliente.objects.create(cliente=otro_cliente, numero=variante)


@pytest.mark.parametrize("sin_normalizar", ["300 123 4567", "+573001234567", ""])
def test_la_base_rechaza_telefono_sin_normalizar_aunque_no_pase_por_save(cliente, sin_normalizar):
    telefono = TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    with pytest.raises(IntegrityError, match="telefono_cliente_solo_digitos"), transaction.atomic():
        TelefonoCliente.objects.filter(pk=telefono.pk).update(numero=sin_normalizar)


def test_guardar_un_telefono_invalido_falla(cliente):
    with pytest.raises(TelefonoInvalido):
        TelefonoCliente.objects.create(cliente=cliente, numero="12345")


def test_el_admin_avisa_en_espanol_a_que_cliente_pertenece_el_telefono(cliente, otro_cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    with pytest.raises(ValidationError) as error:
        TelefonoCliente(cliente=otro_cliente, numero="+57 300 123 4567").full_clean()
    assert error.value.message_dict["numero"] == [
        "El teléfono 3001234567 ya pertenece al cliente Autos del Valle."
    ]


def test_el_admin_avisa_en_espanol_que_el_telefono_no_es_valido(cliente):
    with pytest.raises(ValidationError) as error:
        TelefonoCliente(cliente=cliente, numero="300 12").full_clean()
    assert "entre 7 y 15 dígitos" in error.value.message_dict["numero"][0]


def test_un_cliente_puede_tener_varios_telefonos(cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567", etiqueta="gerente")
    TelefonoCliente.objects.create(cliente=cliente, numero="6044445566", etiqueta="oficina")
    assert cliente.telefonos.count() == 2


def test_un_cliente_con_telefonos_no_se_puede_borrar(cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    with pytest.raises(ProtectedError):
        cliente.delete()


@pytest.mark.parametrize("digitado", ["+57 300 123 4567", "300-123-4567", "3001234567"])
def test_buscar_cliente_por_telefono_digitado_de_cualquier_forma(cliente, digitado):
    TelefonoCliente.objects.create(cliente=cliente, numero="300 123 4567")
    assert buscar_cliente_por_telefono(digitado) == cliente


def test_buscar_cliente_por_telefono_inexistente_da_none(cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    assert buscar_cliente_por_telefono("3109876543") is None


@pytest.mark.parametrize("texto", ["", None, "hola", "300 12", "1" * 16])
def test_buscar_cliente_con_texto_que_no_es_telefono_da_none_sin_fallar(cliente, texto):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    assert buscar_cliente_por_telefono(texto) is None


def test_el_telefono_de_contacto_se_normaliza_y_puede_repetirse(cliente):
    primero = Contacto.objects.create(nombre="Portero", telefono="+57 300 123 4567")
    segundo = Contacto.objects.create(nombre="Portero", telefono="300-123-4567", cliente=cliente)
    primero.refresh_from_db()
    segundo.refresh_from_db()
    assert primero.telefono == segundo.telefono == "3001234567"
    assert primero.cliente is None


def test_la_base_rechaza_telefono_de_contacto_sin_normalizar():
    contacto = Contacto.objects.create(nombre="Portero", telefono="3001234567")
    with pytest.raises(IntegrityError, match="contacto_telefono_solo_digitos"), transaction.atomic():
        Contacto.objects.filter(pk=contacto.pk).update(telefono="300 123 4567")


def test_el_admin_avisa_en_espanol_que_el_telefono_de_contacto_no_es_valido():
    with pytest.raises(ValidationError) as error:
        Contacto(nombre="Portero", telefono="12").full_clean()
    assert "entre 7 y 15 dígitos" in error.value.message_dict["telefono"][0]
