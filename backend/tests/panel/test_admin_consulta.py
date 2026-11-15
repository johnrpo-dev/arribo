"""El admin de Django es solo de consulta y solo para superusuarios; usuarios y grupos no aparecen."""
import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.test import RequestFactory

from clientes.models import Cliente, TipoCliente

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente():
    return Cliente.objects.create(nombre="Autos del Valle", tipo=TipoCliente.CONCESIONARIO)


def test_la_comprobacion_de_django_pasa_sin_usuarios_en_el_admin():
    """Un admin que referencia a User (autocompletar) impide que arranque el servidor."""
    from django.core.management import call_command

    call_command("check", fail_level="ERROR")


def test_usuarios_y_grupos_no_aparecen_en_el_admin(admin_client):
    assert not admin.site.is_registered(User)
    assert not admin.site.is_registered(Group)
    assert admin_client.get("/admin/auth/user/").status_code == 404


def test_ningun_modelo_se_agrega_edita_ni_borra(admin_user):
    peticion = RequestFactory().get("/admin/")
    peticion.user = admin_user
    for modelo, modelo_admin in admin.site._registry.items():
        nombre = modelo.__name__
        assert modelo_admin.has_view_permission(peticion), nombre
        assert not modelo_admin.has_add_permission(peticion), nombre
        assert not modelo_admin.has_change_permission(peticion), nombre
        assert not modelo_admin.has_delete_permission(peticion), nombre
        assert modelo_admin.get_actions(peticion) == {}, nombre


def test_el_superusuario_consulta_la_lista_y_la_ficha(admin_client, cliente):
    assert admin_client.get("/admin/clientes/cliente/").status_code == 200
    ficha = admin_client.get(f"/admin/clientes/cliente/{cliente.pk}/change/")
    assert ficha.status_code == 200
    assert 'name="_save"' not in ficha.content.decode()


def test_un_post_al_admin_no_cambia_nada(admin_client, cliente):
    respuesta = admin_client.post(
        f"/admin/clientes/cliente/{cliente.pk}/change/", {"nombre": "Otro", "tipo": cliente.tipo}
    )
    assert respuesta.status_code == 403
    cliente.refresh_from_db()
    assert cliente.nombre == "Autos del Valle"


def test_un_usuario_de_oficina_no_entra_al_admin_aunque_sea_staff(client, django_user_model):
    usuario = django_user_model.objects.create_user("lina", password="x", is_staff=True)
    client.force_login(usuario)
    assert client.get("/admin/").status_code == 302  # al ingreso del admin
    assert client.get("/admin/clientes/cliente/").status_code == 302


def test_el_admin_dice_que_es_solo_lectura(admin_client):
    assert "solo lectura" in admin_client.get("/admin/").content.decode()
