"""Pantallas de la sección Cobros (1a-16b). Los roles (facturación y administrador) los aplica
`requiere_rol` desde `panel/secciones.py` y `cobros/urls.py`.

- Quién ve los valores lo decide la configuración (`puede_ver_valores`). Quien no los ve tampoco
  los cambia: digitar el valor responde 403. Sí puede facturar, marcar pagada y anular, que no
  muestran ni cambian el valor.
- Las vistas solo validan lo digitado y llaman a `cobros/operaciones.py`, que aplica
  `nucleo/cobro.py` y deja el historial.
"""
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from clientes.models import Cliente, tarifa_propuesta
from configuracion.models import configuracion_vigente
from configuracion.operaciones import puede_ver_valores
from nucleo.cobro import CobroInvalido, EstadoCobro, formato_pesos
from nucleo.estados import Estado
from nucleo.facturacion import formato_porcentaje
from nucleo.relacion import EstadoRelacion
from nucleo.trayecto import puntos_del_servicio
from solicitudes.models import EventoEstado, Servicio

from . import consultas, facturacion, operaciones
from . import relaciones as relaciones_op
from .exportacion import exportador_configurado
from .formularios import (
    FormularioAnulacion,
    FormularioDatosFacturacion,
    FormularioDescarte,
    FormularioFactura,
    FormularioRelacion,
    FormularioValor,
)
from .models import LineaCobro, RelacionCobro


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
    reserva = linea.inclusiones.filter(reservada=True).first()
    cuenta = None
    if ve_valores and estado == EstadoCobro.POR_FACTURAR:
        cuenta = _cuenta_para_mostrar(facturacion.liquidar_lineas([linea]))
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
            "cuenta": cuenta,
            "puede_fijar_valor": ve_valores
            and estado in (EstadoCobro.SIN_VALOR, EstadoCobro.POR_FACTURAR),
            "puede_facturar": estado == EstadoCobro.POR_FACTURAR and reserva is None,
            "puede_pagar": estado == EstadoCobro.FACTURADO,
            "en_relacion": reserva.relacion_id if reserva else None,
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
        lambda: facturacion.facturar_linea(
            linea,
            numero,
            formulario.cleaned_data["total_factura"],
            actor=request.user,
            mostrar_valores=puede_ver_valores(request.user),
        ),
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


def _cuenta_para_mostrar(cuenta):
    return {
        "subtotal": formato_pesos(cuenta.subtotal),
        "porcentaje": formato_porcentaje(cuenta.porcentaje_iva),
        "iva": formato_pesos(cuenta.iva),
        "total": formato_pesos(cuenta.total),
    }


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


# --- Relaciones de cobro (1a-17) ---------------------------------------------------------------


def _exigir_valores(request):
    """Una relación es una cuenta de valores: quien no los ve no la arma ni la descarga."""
    if not puede_ver_valores(request.user):
        raise PermissionDenied("Su rol no ve los valores de cobro.")


def _pagadores_con_pendientes():
    """Clientes con alguna línea por facturar que no esté ya en una relación armada."""
    libres = LineaCobro.objects.filter(estado=EstadoCobro.POR_FACTURAR.value).exclude(
        inclusiones__reservada=True
    )
    return Cliente.objects.filter(pk__in=libres.values("pagador")).order_by("nombre")


def relaciones(request, formulario=None):
    """Relaciones armadas y facturadas, y el formulario para armar una nueva. Con pagador y fechas
    elegidos (GET), muestra qué líneas entrarían antes de armarla."""
    _exigir_valores(request)
    hoy = timezone.localdate()
    pagadores = _pagadores_con_pendientes()
    if formulario is None:
        datos = request.GET if "pagador" in request.GET else None
        formulario = FormularioRelacion(
            datos,
            pagadores=pagadores,
            initial={"desde": hoy.replace(day=1), "hasta": hoy},
        )
    vista_previa = None
    if formulario.is_bound and formulario.is_valid():
        d = formulario.cleaned_data
        lineas = list(relaciones_op.candidatas(d["pagador"], d["desde"], d["hasta"]))
        vista_previa = {
            "lineas": [(linea, formato_pesos(linea.valor)) for linea in lineas],
            "total": formato_pesos(sum((linea.valor for linea in lineas), Decimal(0))),
            "sin_valor": list(relaciones_op.sin_valor(d["pagador"], d["desde"], d["hasta"])),
            "datos": d,
        }
    lista = RelacionCobro.objects.select_related("pagador").annotate(
        cuantas=Count("incluidas"), total=Sum("incluidas__linea__valor")
    )[:50]
    return render(
        request,
        "cobros/relaciones.html",
        {
            "formulario": formulario,
            "hay_pagadores": pagadores.exists(),
            "vista_previa": vista_previa,
            "relaciones": [(r, formato_pesos(r.total)) for r in lista],
        },
    )


@require_POST
def armar_relacion(request):
    _exigir_valores(request)
    formulario = FormularioRelacion(request.POST, pagadores=_pagadores_con_pendientes())
    if not formulario.is_valid():
        return relaciones(request, formulario)
    d = formulario.cleaned_data
    try:
        relacion = relaciones_op.armar(d["pagador"], d["desde"], d["hasta"], actor=request.user)
    except CobroInvalido as error:
        messages.error(request, f"No se armó: {error}.")
        return redirect("relaciones_cobro")
    messages.success(request, f"Relación N.º {relacion.pk} armada. Descárguela y envíela al pagador.")
    return redirect("relacion_cobro", pk=relacion.pk)


def ver_relacion(request, pk, formularios=None):
    _exigir_valores(request)
    relacion = get_object_or_404(
        RelacionCobro.objects.select_related("pagador", "creada_por", "cerrada_por"), pk=pk
    )
    lineas = list(relaciones_op.lineas_de(relacion))
    formularios = formularios or {}
    estado = EstadoRelacion(relacion.estado)
    return render(
        request,
        "cobros/relacion.html",
        {
            "relacion": relacion,
            "lineas": [(linea, formato_pesos(linea.valor)) for linea in lineas],
            "cuenta": _cuenta_para_mostrar(facturacion.liquidar_relacion(relacion, lineas)),
            "faltan": relacion.pagador.datos_de_facturacion_que_faltan(),
            "formulario_pagador": formularios.get("pagador")
            or FormularioDatosFacturacion(instance=relacion.pagador),
            "exportador": exportador_configurado(),
            "puede_facturar": estado == EstadoRelacion.ARMADA,
            "puede_pagar": estado == EstadoRelacion.FACTURADA,
            "formulario_factura": formularios.get("factura") or FormularioFactura(),
            "formulario_descarte": formularios.get("descarte") or FormularioDescarte(),
        },
    )


def descargar_relacion(request, pk):
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro.objects.select_related("pagador"), pk=pk)
    exportador = exportador_configurado()
    contenido = exportador.exportar(relaciones_op.datos_para_exportar(relacion))
    nombre = f"relacion-{relacion.pk}-{slugify(relacion.pagador.nombre)}.{exportador.extension}"
    respuesta = HttpResponse(contenido, content_type=exportador.tipo_contenido)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@require_POST
def facturar_relacion(request, pk):
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro, pk=pk)
    formulario = FormularioFactura(request.POST)
    if not formulario.is_valid():
        return ver_relacion(request, pk, {"factura": formulario})
    numero = formulario.cleaned_data["numero_factura"].strip()
    try:
        facturacion.facturar_relacion(
            relacion, numero, formulario.cleaned_data["total_factura"], actor=request.user
        )
    except CobroInvalido as error:
        messages.error(request, f"No se facturó: {error}.")
    else:
        messages.success(request, f"Relación facturada con el número {numero}: cada línea quedó facturada.")
    return redirect("relacion_cobro", pk=pk)


def orden_de_facturacion(request, pk):
    """La orden de facturación de una relación: lo que el facturador pasa a su programa, con el
    subtotal, el IVA y el total calculados por Arribo. Se imprime desde el navegador."""
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro.objects.select_related("pagador"), pk=pk)
    lineas = list(relaciones_op.lineas_de(relacion))
    datos = relaciones_op.datos_para_exportar(relacion)
    return render(
        request,
        "cobros/orden.html",
        {
            "relacion": relacion,
            "pagador": relacion.pagador,
            "faltan": relacion.pagador.datos_de_facturacion_que_faltan(),
            "empresa": configuracion_vigente(),
            "filas": [(fila, formato_pesos(fila.valor)) for fila in datos.filas],
            "cuenta": _cuenta_para_mostrar(facturacion.liquidar_relacion(relacion, lineas)),
            "hoy": timezone.localdate(),
        },
    )


@require_POST
def datos_facturacion_pagador(request, pk):
    """Guarda en el cliente los datos de facturación que pide la orden."""
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro.objects.select_related("pagador"), pk=pk)
    formulario = FormularioDatosFacturacion(request.POST, instance=relacion.pagador)
    if not formulario.is_valid():
        return ver_relacion(request, pk, {"pagador": formulario})
    formulario.save()
    messages.success(request, f"Datos de facturación de {relacion.pagador.nombre} guardados.")
    return redirect("relacion_cobro", pk=pk)


@require_POST
def pagar_relacion(request, pk):
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro, pk=pk)
    try:
        pago = relaciones_op.pagar(relacion, actor=request.user)
    except CobroInvalido as error:
        messages.error(request, f"No se marcó pagada: {error}.")
    else:
        messages.success(request, "Relación pagada: sus líneas quedaron pagadas.")
        if pago.sin_marcar:
            servicios = ", ".join(f"N.º {n}" for n in pago.sin_marcar)
            messages.warning(
                request, f"No se marcaron porque ya no tienen esta factura: servicio {servicios}."
            )
    return redirect("relacion_cobro", pk=pk)


@require_POST
def descartar_relacion(request, pk):
    _exigir_valores(request)
    relacion = get_object_or_404(RelacionCobro, pk=pk)
    formulario = FormularioDescarte(request.POST)
    if not formulario.is_valid():
        return ver_relacion(request, pk, {"descarte": formulario})
    try:
        relaciones_op.descartar(relacion, formulario.cleaned_data["motivo"], actor=request.user)
    except CobroInvalido as error:
        messages.error(request, f"No se descartó: {error}.")
    else:
        messages.success(request, "Relación descartada: sus líneas quedaron libres.")
    return redirect("relacion_cobro", pk=pk)
