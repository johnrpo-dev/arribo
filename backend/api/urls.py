"""Rutas de la API del conductor, bajo `/api/v1/` (ver `config/urls.py` y `docs/api-conductor.md`)."""
from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("ingresar/", views.Ingresar.as_view(), name="ingresar"),
    path("salir/", views.Salir.as_view(), name="salir"),
    path("asignaciones/", views.Asignaciones.as_view(), name="asignaciones"),
    path("asignaciones/<int:servicio_id>/", views.Asignacion.as_view(), name="asignacion"),
    path("eventos/", views.Eventos.as_view(), name="eventos"),
    path("evidencias/<uuid:evidencia_id>/", views.Evidencia.as_view(), name="evidencia"),
]
