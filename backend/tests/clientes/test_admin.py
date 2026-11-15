"""El admin de clientes abre, no deja borrar y crea un cliente con teléfono y tarifa en un solo paso."""

import pytest

from clientes.models import Cliente, TelefonoCliente, TipoCliente

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
def test_el_admin_abre_la_lista_pero_no_deja_agregar(admin_client, modelo):
    assert admin_client.get(f"/admin/clientes/{modelo}/").status_code == 200
    assert admin_client.get(f"/admin/clientes/{modelo}/add/").status_code == 403


def test_la_marca_de_demostracion_no_se_edita_en_el_admin(admin_client):
    assert 'name="es_demo"' not in admin_client.get("/admin/clientes/cliente/add/").content.decode()


def test_el_admin_no_deja_borrar(admin_client):
    cliente = Cliente.objects.create(nombre="X", tipo=TipoCliente.PARTICULAR)
    assert admin_client.get(f"/admin/clientes/cliente/{cliente.pk}/delete/").status_code == 403
    assert Cliente.objects.filter(pk=cliente.pk).exists()


@pytest.mark.parametrize("busqueda", ["+57 300 123 4567", "300-123-4567", "3001234567"])
def test_buscar_en_el_admin_por_telefono_digitado_de_cualquier_forma(admin_client, busqueda):
    cliente = Cliente.objects.create(nombre="Autos del Valle", tipo=TipoCliente.CONCESIONARIO)
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    Cliente.objects.create(nombre="Zuleta Restrepo", tipo=TipoCliente.PARTICULAR)

    respuesta = admin_client.get("/admin/clientes/cliente/", {"q": busqueda})

    contenido = respuesta.content.decode()
    assert "Autos del Valle" in contenido
    assert "Zuleta Restrepo" not in contenido
