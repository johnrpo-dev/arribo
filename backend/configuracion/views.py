from django.contrib import messages
from django.shortcuts import redirect, render

from .formularios import FormularioConfiguracion
from .models import configuracion_vigente
from .operaciones import guardar_configuracion


def configuracion(request):
    """Pantalla de configuración. Solo administrador: lo aplica `panel/urls.py` con `requiere_rol`."""
    formulario = FormularioConfiguracion(request.POST or None, instance=configuracion_vigente())
    if request.method == "POST" and formulario.is_valid():
        guardar_configuracion(formulario.instance, usuario=request.user)
        messages.success(request, "Configuración guardada.")
        return redirect("configuracion")
    return render(request, "configuracion/configuracion.html", {"formulario": formulario})
