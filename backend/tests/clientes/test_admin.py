"""El admin de clientes abre, no deja borrar y crea un cliente con teléfono y tarifa en un solo paso."""
from decimal import Decimal

import pytest

from clientes.models import Cliente, Tarifa, TelefonoCliente, TipoCliente

pytestmark = pytest.mark.django_db

MODELOS = ["cliente", "telefonocliente", "contacto", "tarifa"]


def _formulario_cliente(**extra):
    datos = {
        "nombre": "Autos del Valle",
        "tipo": "concesionario",
        "documento": "900123456",
        "modalidad_cobro": "por_corte",
        "notas": "",
        "activo": "on",
        "telefonos-TOTAL_FORMS": "1",
        "telefonos-INITIAL_FORMS": "0",
        "telefonos-0-numero": "+57 300 123 4567",
        "telefonos-0-etiqueta": "gerente",
        "tarifas-TOTAL_FORMS": "1",
        "tarifas-INITIAL_FORMS": "0",
        "tarifas-0-tipo_servicio": "traslado",
        "tarifas-0-valor": "180000",
        "tarifas-0-descripcion": "Convenio 2026",
        "tarifas-0-vigente": "on",
    }
    datos.update(extra)
    return datos


@pytest.mark.parametrize("modelo", MODELOS)
def test_el_admin_abre_la_lista_y_el_formulario(admin_client, modelo):
    assert admin_client.get(f"/admin/clientes/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/clientes/{modelo}/add/").status_code == 200


def test_la_marca_de_demostracion_no_se_edita_en_el_admin(admin_client):
    assert 'name="es_demo"' not in admin_client.get("/admin/clientes/cliente/add/").content.decode()


def test_el_admin_no_deja_borrar(admin_client):
    cliente = Cliente.objects.create(nombre="X", tipo=TipoCliente.PARTICULAR)
    assert admin_client.get(f"/admin/clientes/cliente/{cliente.pk}/delete/").status_code == 403
    assert Cliente.objects.filter(pk=cliente.pk).exists()


def test_crear_cliente_con_telefono_y_tarifa_en_el_admin(admin_client):
    respuesta = admin_client.post("/admin/clientes/cliente/add/", _formulario_cliente())

    assert respuesta.status_code == 302, respuesta.content.decode()
    cliente = Cliente.objects.get()
    assert cliente.modalidad_cobro == "por_corte"
    assert list(cliente.telefonos.values_list("numero", flat=True)) == ["3001234567"]
    assert Tarifa.objects.get(cliente=cliente).valor == Decimal("180000.00")


def test_el_admin_avisa_si_el_telefono_ya_es_de_otro_cliente(admin_client):
    otro = Cliente.objects.create(nombre="Ana Pérez", tipo=TipoCliente.PARTICULAR)
    TelefonoCliente.objects.create(cliente=otro, numero="3001234567")

    respuesta = admin_client.post("/admin/clientes/cliente/add/", _formulario_cliente())

    assert respuesta.status_code == 200
    assert "ya pertenece al cliente Ana Pérez" in respuesta.content.decode()
    assert Cliente.objects.count() == 1


def test_el_admin_avisa_si_el_mismo_telefono_va_dos_veces_escrito_distinto(admin_client):
    datos = _formulario_cliente(
        **{"telefonos-TOTAL_FORMS": "2", "telefonos-1-numero": "300-123-4567"}
    )
    respuesta = admin_client.post("/admin/clientes/cliente/add/", datos)

    assert respuesta.status_code == 200
    assert "El teléfono 3001234567 está repetido." in respuesta.content.decode()
    assert not Cliente.objects.exists()


def test_el_admin_avisa_si_van_dos_tarifas_vigentes_del_mismo_tipo(admin_client):
    datos = _formulario_cliente(
        **{
            "tarifas-TOTAL_FORMS": "2",
            "tarifas-1-tipo_servicio": "traslado",
            "tarifas-1-valor": "200000",
            "tarifas-1-vigente": "on",
        }
    )
    respuesta = admin_client.post("/admin/clientes/cliente/add/", datos)

    assert respuesta.status_code == 200
    assert "Hay dos tarifas vigentes para el mismo tipo de servicio." in respuesta.content.decode()
    assert not Cliente.objects.exists()


@pytest.mark.parametrize("busqueda", ["+57 300 123 4567", "300-123-4567", "3001234567"])
def test_buscar_en_el_admin_por_telefono_digitado_de_cualquier_forma(admin_client, busqueda):
    cliente = Cliente.objects.create(nombre="Autos del Valle", tipo=TipoCliente.CONCESIONARIO)
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    Cliente.objects.create(nombre="Zuleta Restrepo", tipo=TipoCliente.PARTICULAR)

    respuesta = admin_client.get("/admin/clientes/cliente/", {"q": busqueda})

    contenido = respuesta.content.decode()
    assert "Autos del Valle" in contenido
    assert "Zuleta Restrepo" not in contenido
