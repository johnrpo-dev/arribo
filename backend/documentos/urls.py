"""Rutas de documentos de Flota y personal (la sección `flota` se registra en
`panel/secciones.py`; su lista está en `flota/views.py`). Llevan los mismos roles que esa sección:
solo administrador."""
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "flota").roles


def _con_rol(vista):
    return requiere_rol(*ROLES)(vista)


urlpatterns = [
    path(
        "flota/gruas/<int:pk>/documentos/<int:tipo_pk>/",
        _con_rol(views.documento_de_grua),
        name="documento_de_grua",
    ),
    path(
        "flota/conductores/<int:pk>/documentos/<int:tipo_pk>/",
        _con_rol(views.documento_de_conductor),
        name="documento_de_conductor",
    ),
    path("flota/documentos/<int:pk>/archivo/", _con_rol(views.archivo), name="archivo_documento"),
    path("flota/tipos/", _con_rol(views.tipos), name="tipos_documento"),
    path("flota/tipos/<int:pk>/", _con_rol(views.editar_tipo), name="editar_tipo_documento"),
]
