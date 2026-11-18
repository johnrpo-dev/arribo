from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from alertas.evaluacion import evaluar
from alertas.models import Alerta
from alertas.operaciones import resolver_alerta
from panel.formularios import FormularioIngreso
from panel.roles import ADMINISTRADOR, LOGISTICA, ROLES_DEL_PANEL, requiere_rol, tiene_rol
from panel.secciones import SECCIONES, secciones_para
from panel.tablero import datos_del_tablero


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
    """Lo que requiere acción ahora, de forma visual: cifras del día, servicios por asignar (con su
    espera y para asignarlos ahí mismo), alertas para resolver, borradores y una tarjeta por
    conductor. Es también el inicio de logística y del administrador. Se recarga solo cada minuto
    (HTMX). Vive en el panel porque junta solicitudes, flota y alertas.

    Antes de mostrarse evalúa las alertas por umbral, para que estén al día aunque el comando
    programado no haya corrido."""
    evaluar()
    datos = datos_del_tablero()
    datos["es_administrador"] = tiene_rol(request.user, (ADMINISTRADOR,))
    return render(request, "solicitudes/tablero.html", datos)


@require_POST
@requiere_rol(LOGISTICA, ADMINISTRADOR)
def resolver_alerta_desde_tablero(request, pk):
    alerta = get_object_or_404(Alerta, pk=pk)
    if alerta.se_cierra_sola:
        messages.error(
            request, "Esta alerta se cierra sola cuando se atiende lo que la abrió."
        )
        return redirect("inicio")
    resolver_alerta(alerta, por=request.user)
    messages.success(request, "Alerta marcada como resuelta.")
    return redirect("inicio")


def no_disponible(request, clave):
    """Lugar de una sección que todavía no tiene pantalla. Los roles los aplica `panel/urls.py`."""
    seccion = next(s for s in SECCIONES if s.clave == clave)
    return render(request, "panel/no_disponible.html", {"seccion": seccion})


@requiere_rol(ADMINISTRADOR)
def estilos(request):
    """Muestra de los componentes base con datos de ejemplo. No consulta la base."""
    return render(request, "panel/estilos.html")
