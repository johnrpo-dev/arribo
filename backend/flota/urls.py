"""Rutas de "Personal y grúas" que no son la sección de la navegación (la sección `personal` se
registra en `panel/secciones.py`). Llevan los mismos roles que esa sección: solo administrador."""
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "personal").roles


def _con_rol(vista):
    return requiere_rol(*ROLES)(vista)


urlpatterns = [
    path("personal/conductores/nuevo/", _con_rol(views.nuevo_conductor), name="nuevo_conductor"),
    path("personal/conductores/<int:pk>/", _con_rol(views.conductor), name="conductor_personal"),
    path(
        "personal/conductores/<int:pk>/habilitar/",
        _con_rol(views.habilitar_conductor),
        name="habilitar_conductor",
    ),
    path("personal/conductores/<int:pk>/pin/", _con_rol(views.cambiar_pin), name="cambiar_pin"),
    path("personal/conductores/<int:pk>/grua/", _con_rol(views.cambiar_grua), name="cambiar_grua"),
    path(
        "personal/conductores/<int:pk>/desactivar/",
        _con_rol(views.desactivar_conductor),
        name="desactivar_conductor",
    ),
    path(
        "personal/conductores/<int:pk>/reactivar/",
        _con_rol(views.reactivar_conductor),
        name="reactivar_conductor",
    ),
    path("personal/usuarios/nuevo/", _con_rol(views.nuevo_usuario), name="nuevo_usuario"),
    path("personal/usuarios/<int:pk>/", _con_rol(views.usuario), name="usuario_personal"),
    path("personal/usuarios/<int:pk>/rol/", _con_rol(views.cambiar_rol), name="cambiar_rol"),
    path(
        "personal/usuarios/<int:pk>/contrasena/",
        _con_rol(views.restablecer_contrasena),
        name="restablecer_contrasena",
    ),
    path(
        "personal/usuarios/<int:pk>/desactivar/",
        _con_rol(views.desactivar_usuario),
        name="desactivar_usuario",
    ),
    path(
        "personal/usuarios/<int:pk>/reactivar/",
        _con_rol(views.reactivar_usuario),
        name="reactivar_usuario",
    ),
    path("personal/gruas/nueva/", _con_rol(views.nueva_grua), name="nueva_grua"),
    path("personal/gruas/<int:pk>/", _con_rol(views.editar_grua), name="editar_grua"),
]
