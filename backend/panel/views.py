from django.contrib.auth.views import LoginView
from django.shortcuts import render

from alertas.operaciones import alertas_para_tablero
from panel.formularios import FormularioIngreso
from panel.roles import ADMINISTRADOR, LOGISTICA, ROLES_DEL_PANEL, requiere_rol, tiene_rol
from panel.secciones import SECCIONES, secciones_para
from solicitudes import consultas


class Ingreso(LoginView):
    template_name = "panel/ingresar.html"
    authentication_form = FormularioIngreso
    redirect_authenticated_user = True


@requiere_rol(*ROLES_DEL_PANEL)
def inicio(request):
    """Logística y administrador ven el tablero (lo que requiere acción ahora); los demás roles,
    sus secciones."""
    if tiene_rol(request.user, (LOGISTICA, ADMINISTRADOR)):
        return tablero(request)
    return render(request, "panel/inicio.html", {"secciones": secciones_para(request.user)})


def tablero(request):
    """Lo que requiere acción ahora: por asignar, borradores, alertas abiertas y lo que está en
    curso por conductor. Es también el inicio de logística y del administrador. Vive en el panel
    porque junta solicitudes y alertas (`solicitudes` no importa `alertas`)."""
    return render(
        request,
        "solicitudes/tablero.html",
        {
            "por_asignar": consultas.por_asignar(),
            "borradores": consultas.borradores(),
            "alertas": alertas_para_tablero(),
            "en_curso": consultas.en_curso(),
        },
    )


def no_disponible(request, clave):
    """Lugar de una sección que todavía no tiene pantalla. Los roles los aplica `panel/urls.py`."""
    seccion = next(s for s in SECCIONES if s.clave == clave)
    return render(request, "panel/no_disponible.html", {"seccion": seccion})


@requiere_rol(ADMINISTRADOR)
def estilos(request):
    """Muestra de los componentes base con datos de ejemplo. No consulta la base."""
    return render(request, "panel/estilos.html")
