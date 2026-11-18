"""Rutas de la sección Cobros que no son la lista (la sección `cobros` se registra en
`panel/secciones.py`). Llevan los mismos roles que esa sección: facturación y administrador."""
from django.urls import path

from panel.roles import requiere_rol
from panel.secciones import SECCIONES

from . import views

ROLES = next(s for s in SECCIONES if s.clave == "cobros").roles


def _con_rol(vista):
    return requiere_rol(*ROLES)(vista)


urlpatterns = [
    path("cobros/<int:pk>/", _con_rol(views.detalle), name="linea_cobro"),
    path("cobros/<int:pk>/valor/", _con_rol(views.fijar_valor), name="fijar_valor_cobro"),
    path("cobros/<int:pk>/facturar/", _con_rol(views.facturar), name="facturar_cobro"),
    path("cobros/<int:pk>/pagar/", _con_rol(views.pagar), name="pagar_cobro"),
    path("cobros/<int:pk>/anular/", _con_rol(views.anular_factura), name="anular_factura_cobro"),
    path(
        "cobros/servicios/<int:servicio_pk>/cobrable/",
        _con_rol(views.marcar_cobrable),
        name="marcar_cobrable",
    ),
]
