"""Pantallas de la sección Cobros (1a-16b). Los roles (facturación y administrador) los aplica
`requiere_rol` desde `panel/secciones.py` y `cobros/urls.py`.

- Quién ve los valores lo decide la configuración (`puede_ver_valores`). Quien no los ve tampoco
  los cambia: digitar el valor responde 403. Sí puede facturar, marcar pagada y anular, que no
  muestran ni cambian el valor.
- Las vistas solo validan lo digitado y llaman a `cobros/operaciones.py`, que aplica
  `nucleo/cobro.py` y deja el historial.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from clientes.models import tarifa_propuesta
from configuracion.operaciones import puede_ver_valores
from nucleo.cobro import CobroInvalido, EstadoCobro, formato_pesos
from nucleo.estados import Estado
from nucleo.trayecto import puntos_del_servicio
from solicitudes.models import EventoEstado, Servicio

from . import consultas, operaciones
from .formularios import FormularioAnulacion, FormularioFactura, FormularioValor
from .models import LineaCobro


def lista(request):
    """Líneas de cobro por estado (Pendientes por defecto), búsqueda y páginas. La pestaña
    Cancelados lista servicios cancelados sin línea, para decidir si se cobran."""
    texto = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro") or consultas.FILTRO_POR_DEFECTO
    if filtro not in consultas.FILTROS:
        filtro = consultas.FILTRO_POR_DEFECTO
    ve_valores = puede_ver_valores(request.user)
    cuantas = consultas.cuantas()
    contexto = {
        "pestanas": [
            (clave, nombre, cuantas[clave]) for clave, (nombre, _) in consultas.FILTROS.items()
        ],
        "filtro": filtro,
        "nombre_filtro": consultas.FILTROS[filtro][0],
        "texto": texto,
        "ve_valores": ve_valores,
    }
    if filtro == "cancelados":
        cancelados = list(consultas.cancelados_sin_cobro())
        motivos = consultas.motivos_de_cancelacion(cancelados)
        contexto["cancelados"] = [(s, motivos.get(s.pk, "")) for s in cancelados]
    else:
        pagina = Paginator(consultas.lineas(filtro, texto), consultas.POR_PAGINA).get_page(
            request.GET.get("pagina")
        )
        contexto["pagina"] = pagina
        contexto["filas"] = consultas.filas(pagina, ve_valores=ve_valores)
    return render(request, "cobros/lista.html", contexto)


def detalle(request, pk, formularios=None):
    """Una línea: el servicio que se cobra, su estado, lo que se puede hacer ahora y el historial."""
    linea = get_object_or_404(
        LineaCobro.objects.select_related(
            "pagador",
            "servicio__vehiculo",
            "servicio__conductor",
            "servicio__grua",
            "servicio__solicitud__solicitante",
        ),
        pk=pk,
    )
    servicio = linea.servicio
    solicitud = servicio.solicitud
    es_regreso = servicio.regreso_de_id is not None
    recoger, entregar = puntos_del_servicio(es_regreso, solicitud.origen, solicitud.destino)
    ve_valores = puede_ver_valores(request.user)
    estado = EstadoCobro(linea.estado)
    formularios = formularios or {}

    tarifa = None
    if ve_valores and estado == EstadoCobro.SIN_VALOR:
        tarifa = tarifa_propuesta(linea.pagador_id, solicitud.tipo)
    # Lo que ya trae el campo: la tarifa propuesta o el valor actual, sin el signo.
    propuesto = tarifa or (linea.valor if ve_valores else None)
    inicial = {"valor": formato_pesos(propuesto).removeprefix("$ ")} if propuesto else {}

    historial = list(linea.historial.select_related("usuario"))
    return render(
        request,
        "cobros/linea.html",
        {
            "linea": linea,
            "servicio": servicio,
            "solicitud": solicitud,
            "es_regreso": es_regreso,
            "recoger": recoger,
            "entregar": entregar,
            "entregado_en": _entregado_en(servicio),
            "ve_valores": ve_valores,
            "valor": formato_pesos(linea.valor) if ve_valores else None,
            "tarifa": formato_pesos(tarifa) if tarifa else None,
            "puede_fijar_valor": ve_valores
            and estado in (EstadoCobro.SIN_VALOR, EstadoCobro.POR_FACTURAR),
            "puede_facturar": estado == EstadoCobro.POR_FACTURAR,
            "puede_pagar": estado == EstadoCobro.FACTURADO,
            "formulario_valor": formularios.get("valor") or FormularioValor(initial=inicial),
            "formulario_factura": formularios.get("factura") or FormularioFactura(),
            "formulario_anulacion": formularios.get("anulacion") or FormularioAnulacion(),
            "historial": [
                (
                    registro,
                    formato_pesos(registro.valor_anterior) if ve_valores else None,
                    formato_pesos(registro.valor_nuevo) if ve_valores else None,
                )
                for registro in historial
            ],
        },
    )


@require_POST
def fijar_valor(request, pk):
    if not puede_ver_valores(request.user):
        raise PermissionDenied("Su rol no ve los valores de cobro.")
    linea = get_object_or_404(LineaCobro, pk=pk)
    formulario = FormularioValor(request.POST)
    if not formulario.is_valid():
        return detalle(request, pk, {"valor": formulario})
    return _aplicar(
        request,
        linea,
        lambda: operaciones.fijar_valor(
            linea, formulario.cleaned_data["valor"], actor=request.user
        ),
        "Valor guardado. La línea quedó por facturar.",
    )


@require_POST
def facturar(request, pk):
    linea = get_object_or_404(LineaCobro, pk=pk)
    formulario = FormularioFactura(request.POST)
    if not formulario.is_valid():
        return detalle(request, pk, {"factura": formulario})
    numero = formulario.cleaned_data["numero_factura"]
    return _aplicar(
        request,
        linea,
        lambda: operaciones.facturar(linea, numero, actor=request.user),
        f"Facturada con el número {numero.strip()}.",
    )


@require_POST
def pagar(request, pk):
    linea = get_object_or_404(LineaCobro, pk=pk)
    return _aplicar(
        request,
        linea,
        lambda: operaciones.pagar(linea, actor=request.user),
        "Marcada como pagada.",
    )


@require_POST
def anular_factura(request, pk):
    linea = get_object_or_404(LineaCobro, pk=pk)
    formulario = FormularioAnulacion(request.POST)
    if not formulario.is_valid():
        return detalle(request, pk, {"anulacion": formulario})
    return _aplicar(
        request,
        linea,
        lambda: operaciones.anular_factura(
            linea, formulario.cleaned_data["motivo"], actor=request.user
        ),
        "Factura anulada. La línea volvió a por facturar.",
    )


@require_POST
def marcar_cobrable(request, servicio_pk):
    """Un servicio cancelado que sí se cobra: nace su línea, como si se hubiera entregado."""
    servicio = get_object_or_404(Servicio, pk=servicio_pk)
    try:
        linea = operaciones.marcar_cobrable(servicio, actor=request.user)
    except operaciones.EstadoNoCobrable as error:
        messages.error(request, f"No se marcó cobrable: {error}")
        return redirect(reverse("cobros") + "?filtro=cancelados")
    messages.success(request, f"El servicio N.º {servicio.pk} quedó para cobrar.")
    return redirect("linea_cobro", pk=linea.pk)


def _aplicar(request, linea, operacion, exito):
    try:
        operacion()
    except CobroInvalido as error:
        messages.error(request, f"No se guardó: {error}.")
    else:
        messages.success(request, exito)
    return redirect("linea_cobro", pk=linea.pk)


def _entregado_en(servicio):
    """Hora del celular en que se marcó Entregado (o la del servidor si se hizo en el panel)."""
    evento = (
        EventoEstado.objects.filter(servicio=servicio, destino=Estado.ENTREGADO.value)
        .order_by("-hora_sincronizacion")
        .first()
    )
    if evento is None:
        return None
    return evento.hora_dispositivo or evento.hora_sincronizacion
