from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from . import restablecer as restablecer_datos
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
    return render(
        request,
        "configuracion/configuracion.html",
        {"formulario": formulario, "puede_restablecer": restablecer_datos.permitido()},
    )


PALABRA_DE_CONFIRMACION = "BORRAR"


def restablecer(request):
    """Restablecer de fábrica. Solo administrador (`panel/urls.py`) y solo si la instalación lo
    permite; pide escribir BORRAR para que no se haga con un clic suelto."""
    if not restablecer_datos.permitido():
        raise Http404
    error = ""
    if request.method == "POST":
        if request.POST.get("confirmacion", "").strip().upper() == PALABRA_DE_CONFIRMACION:
            restablecer_datos.restablecer(conservar=request.user)
            messages.success(request, "Listo: se borraron los datos de prueba. La app quedó vacía.")
            return redirect("inicio")
        error = f"Escriba {PALABRA_DE_CONFIRMACION} para confirmar."
    return render(
        request,
        "configuracion/restablecer.html",
        {
            "resumen": restablecer_datos.resumen(conservar=request.user),
            "palabra": PALABRA_DE_CONFIRMACION,
            "error": error,
        },
    )
