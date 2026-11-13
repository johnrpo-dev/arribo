"""Rutas de solicitudes que no son secciones de la navegación (la sección `nueva_solicitud` se
registra en `panel/secciones.py`). Llevan los mismos roles que esa sección.
"""
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "nueva_solicitud").roles


urlpatterns = [
    path(
        "solicitudes/nueva/cliente/",
        requiere_rol(*ROLES)(views.buscar_cliente),
        name="buscar_cliente",
    ),
    path("solicitudes/<int:pk>/", requiere_rol(*ROLES)(views.detalle), name="detalle_solicitud"),
]
