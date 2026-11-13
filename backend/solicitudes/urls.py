"""Rutas de solicitudes que no son secciones de la navegación (la sección `nueva_solicitud` se
registra en `panel/secciones.py`). Llevan los mismos roles que esa sección.
"""
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "nueva_solicitud").roles


def _con_rol(vista):
    return requiere_rol(*ROLES)(vista)


urlpatterns = [
    path("solicitudes/nueva/cliente/", _con_rol(views.buscar_cliente), name="buscar_cliente"),
    path(
        "solicitudes/nueva/vehiculo/",
        _con_rol(views.fila_nueva_vehiculo),
        name="fila_nueva_vehiculo",
    ),
    path("solicitudes/<int:pk>/", _con_rol(views.detalle), name="detalle_solicitud"),
    path(
        "solicitudes/<int:pk>/completar/",
        _con_rol(views.completar),
        name="completar_solicitud",
    ),
    path(
        "solicitudes/<int:pk>/no-concretada/",
        _con_rol(views.no_concretada),
        name="no_concretada_solicitud",
    ),
    path(
        "solicitudes/<int:pk>/servicios/<int:servicio_pk>/asignar/",
        _con_rol(views.asignar_servicio),
        name="asignar_servicio",
    ),
    path(
        "solicitudes/<int:pk>/servicios/<int:servicio_pk>/ronda/",
        _con_rol(views.mover_en_ronda),
        name="mover_en_ronda",
    ),
]
