from django.contrib.auth.views import LogoutView
from django.urls import path
from django.utils.module_loading import import_string

from panel import views
from panel.roles import requiere_rol
from panel.secciones import SECCIONES


def _ruta_de_seccion(seccion):
    if seccion.disponible:
        vista, argumentos = import_string(seccion.vista), {}
    else:
        vista, argumentos = views.no_disponible, {"clave": seccion.clave}
    return path(seccion.ruta, requiere_rol(*seccion.roles)(vista), argumentos, name=seccion.clave)


urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", views.Ingreso.as_view(), name="ingresar"),
    # LogoutView de Django 5 solo acepta POST: un enlace o una precarga no cierran la sesión.
    path("salir/", LogoutView.as_view(), name="salir"),
    path("estilos/", views.estilos, name="estilos"),
    *[_ruta_de_seccion(s) for s in SECCIONES],
]
