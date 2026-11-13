from django.contrib.auth.views import LoginView
from django.shortcuts import render

from panel.formularios import FormularioIngreso
from panel.roles import ADMINISTRADOR, ROLES_DEL_PANEL, requiere_rol
from panel.secciones import SECCIONES, secciones_para


class Ingreso(LoginView):
    template_name = "panel/ingresar.html"
    authentication_form = FormularioIngreso
    redirect_authenticated_user = True


@requiere_rol(*ROLES_DEL_PANEL)
def inicio(request):
    return render(request, "panel/inicio.html", {"secciones": secciones_para(request.user)})


def no_disponible(request, clave):
    """Lugar de una sección que todavía no tiene pantalla. Los roles los aplica `panel/urls.py`."""
    seccion = next(s for s in SECCIONES if s.clave == clave)
    return render(request, "panel/no_disponible.html", {"seccion": seccion})


@requiere_rol(ADMINISTRADOR)
def estilos(request):
    """Muestra de los componentes base con datos de ejemplo. No consulta la base."""
    return render(request, "panel/estilos.html")
