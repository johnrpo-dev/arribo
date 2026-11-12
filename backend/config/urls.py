from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def salud(request):
    """Comprobación de vida para el despliegue y para la app del conductor."""
    return JsonResponse({"estado": "ok", "servicio": "arribo"})


urlpatterns = [
    path("salud/", salud, name="salud"),
    path("admin/", admin.site.urls),
]
