"""Rutas de "Flota y personal" que no son la sección de la navegación (la sección `flota` se registra
en `panel/secciones.py`). Llevan los mismos roles que esa sección: solo administrador.

Hasta la 1a-08c esto era "Personal y grúas", bajo `/personal/`: esas direcciones redirigen aquí.
"""
from django.shortcuts import redirect
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "flota").roles


def _con_rol(vista):
    return requiere_rol(*ROLES)(vista)


def _de_personal(request, resto=""):
    """/personal/... (antes de la 1a-08c) lleva a la misma pantalla en /flota/..."""
    return redirect(f"/flota/{resto}")


urlpatterns = [
    path("flota/conductores/nuevo/", _con_rol(views.nuevo_conductor), name="nuevo_conductor"),
    path("flota/conductores/<int:pk>/", _con_rol(views.conductor), name="conductor_personal"),
    path(
        "flota/conductores/<int:pk>/datos/",
        _con_rol(views.editar_conductor),
        name="editar_conductor",
    ),
    path(
        "flota/conductores/<int:pk>/habilitar/",
        _con_rol(views.habilitar_conductor),
        name="habilitar_conductor",
    ),
    path("flota/conductores/<int:pk>/pin/", _con_rol(views.cambiar_pin), name="cambiar_pin"),
    path(
        "flota/conductores/<int:pk>/desactivar/",
        _con_rol(views.desactivar_conductor),
        name="desactivar_conductor",
    ),
    path(
        "flota/conductores/<int:pk>/reactivar/",
        _con_rol(views.reactivar_conductor),
        name="reactivar_conductor",
    ),
    path("flota/usuarios/nuevo/", _con_rol(views.nuevo_usuario), name="nuevo_usuario"),
    path("flota/usuarios/<int:pk>/", _con_rol(views.usuario), name="usuario_personal"),
    path("flota/usuarios/<int:pk>/rol/", _con_rol(views.cambiar_rol), name="cambiar_rol"),
    path(
        "flota/usuarios/<int:pk>/contrasena/",
        _con_rol(views.restablecer_contrasena),
        name="restablecer_contrasena",
    ),
    path(
        "flota/usuarios/<int:pk>/desactivar/",
        _con_rol(views.desactivar_usuario),
        name="desactivar_usuario",
    ),
    path(
        "flota/usuarios/<int:pk>/reactivar/",
        _con_rol(views.reactivar_usuario),
        name="reactivar_usuario",
    ),
    path("flota/gruas/nueva/", _con_rol(views.nueva_grua), name="nueva_grua"),
    path("flota/gruas/<int:pk>/", _con_rol(views.editar_grua), name="editar_grua"),
    path("personal/", _de_personal, name="personal_antes"),
    path("personal/<path:resto>", _de_personal),
]
