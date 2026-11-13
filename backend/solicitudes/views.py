"""Pantallas de solicitudes. Los roles (logística y administrador) los aplica `requiere_rol`:
la sección `nueva_solicitud` en `panel/urls.py` y las rutas de `solicitudes/urls.py`.
"""
from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import buscar_cliente_por_telefono
from nucleo.identificacion import TelefonoInvalido, normalizar_telefono
from nucleo.registro import describir_faltantes

from .formularios import FormularioSolicitud
from .models import EstadoRegistro, Solicitud
from .registro import faltantes_de, historial_reciente, registrar_solicitud

BUSQUEDAS = (("solicitante", "telefono"), ("pagador", "pagador_telefono"))


def nueva(request):
    """Formulario único de registro. "Guardar" la deja abierta si está completa; si no, borrador."""
    formulario = FormularioSolicitud(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        abrir = request.POST.get("accion") != "borrador"
        try:
            solicitud, faltantes = registrar_solicitud(
                formulario.datos_registro(), usuario=request.user, abrir=abrir
            )
        except IntegrityError:
            # Otra persona guardó el mismo teléfono o vehículo mientras tanto; no quedó nada.
            formulario.add_error(
                None, "No se guardó: otra persona registró el mismo dato al tiempo. Intente de nuevo."
            )
        else:
            _avisar_guardado(request, solicitud, faltantes)
            return redirect("detalle_solicitud", pk=solicitud.pk)
    contexto = {"formulario": formulario}
    for para, campo in BUSQUEDAS:
        contexto[para] = _busqueda(formulario[campo].value(), para)
    return render(request, "solicitudes/nueva.html", contexto)


def buscar_cliente(request):
    """Fragmento HTMX: el cliente del teléfono digitado, con su historial reciente o, si no
    existe y es quien llama, los campos para crearlo ahí mismo."""
    para = "pagador" if request.GET.get("para") == "pagador" else "solicitante"
    campo = dict(BUSQUEDAS)[para]
    return render(
        request,
        "solicitudes/parcial_cliente.html",
        {
            "formulario": FormularioSolicitud(),
            "busqueda": _busqueda(request.GET.get(campo, ""), para),
        },
    )


def detalle(request, pk):
    """Solo lectura: datos de la solicitud, estado derivado y servicios."""
    solicitud = get_object_or_404(
        Solicitud.objects.select_related(
            "solicitante", "pagador", "contacto_origen", "contacto_destino", "creada_por"
        ),
        pk=pk,
    )
    servicios = solicitud.servicios.select_related("vehiculo", "conductor", "grua")
    faltantes = []
    if solicitud.estado_registro == EstadoRegistro.BORRADOR:
        faltantes = faltantes_de(solicitud)
    return render(
        request,
        "solicitudes/detalle.html",
        {
            "solicitud": solicitud,
            "servicios": servicios,
            "faltantes": describir_faltantes(faltantes),
        },
    )


def _busqueda(texto, para) -> dict:
    """Resultado de buscar un cliente por teléfono, para el fragmento."""
    resultado = {"para": para, "telefono_completo": False, "cliente": None, "historial": []}
    try:
        normalizar_telefono(texto)
    except TelefonoInvalido:
        return resultado
    resultado["telefono_completo"] = True
    cliente = buscar_cliente_por_telefono(texto)
    resultado["cliente"] = cliente
    if cliente is not None and para == "solicitante":
        resultado["historial"] = historial_reciente(cliente)
    return resultado


def _avisar_guardado(request, solicitud, faltantes):
    if solicitud.estado_registro == EstadoRegistro.ABIERTA:
        messages.success(
            request,
            f"Solicitud {solicitud.pk} registrada. Queda abierta y su servicio, pendiente de "
            "asignar.",
        )
    elif faltantes:
        messages.warning(
            request,
            f"Solicitud {solicitud.pk} guardada como borrador. Para abrirla falta "
            f"{describir_faltantes(faltantes)}.",
        )
    else:
        messages.info(request, f"Solicitud {solicitud.pk} guardada como borrador.")
