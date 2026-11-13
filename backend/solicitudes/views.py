"""Pantallas de solicitudes. Los roles (logística y administrador) los aplica `requiere_rol`:
la sección `nueva_solicitud` en `panel/urls.py` y las rutas de `solicitudes/urls.py`.
"""
from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from clientes.models import buscar_cliente_por_telefono
from configuracion.models import MomentoPlacaVin, configuracion_vigente
from nucleo.estados import REASIGNABLE_DESDE, Estado, TransicionInvalida
from nucleo.identificacion import (
    IdentificacionIncompleta,
    TelefonoInvalido,
    normalizar_telefono,
)
from nucleo.registro import CierreNoPermitido, describir_faltantes
from nucleo.ronda import MovimientoInvalido

from . import operaciones
from .disponibilidad import disponibilidad_de_conductores
from .formularios import (
    FormularioAsignacion,
    FormularioNoConcretada,
    FormularioSolicitud,
    FormularioVehiculos,
    fila_vehiculo,
    inicial_de,
    inicial_vehiculos,
)
from .models import VALORES_EN_RONDA, EstadoRegistro, Servicio, Solicitud
from .operaciones import SolicitudNoAsignable
from .registro import (
    SolicitudNoEditable,
    cerrar_no_concretada,
    completar_borrador,
    duplicados_activos,
    faltantes_de,
    historial_reciente,
    puede_cerrarse_no_concretada,
    registrar_solicitud,
    servicios_de_ida,
)

BUSQUEDAS = (("solicitante", "telefono"), ("pagador", "pagador_telefono"))
CAMPO_CONFIRMACION = "duplicados_confirmados"


def nueva(request):
    """Formulario único de registro. "Guardar" la deja abierta si está completa; si no, borrador."""
    return _formulario(request, None)


def completar(request, pk):
    """El mismo formulario sobre un borrador. Una solicitud que ya no es borrador no se edita."""
    solicitud = get_object_or_404(_con_relaciones(), pk=pk)
    if solicitud.estado_registro != EstadoRegistro.BORRADOR:
        messages.info(request, f"La solicitud {pk} ya no es un borrador: no se edita aquí.")
        return redirect("detalle_solicitud", pk=pk)
    return _formulario(request, solicitud)


def _formulario(request, solicitud):
    servicios = []
    if solicitud is not None:
        servicios = list(servicios_de_ida(solicitud).select_related("vehiculo"))
    permitidos = {s.pk for s in servicios}
    if request.method == "POST":
        formulario = FormularioSolicitud(request.POST, solicitud=solicitud)
        vehiculos = FormularioVehiculos(request.POST, servicios=permitidos)
    else:
        formulario = FormularioSolicitud(
            initial=inicial_de(solicitud) if solicitud else None, solicitud=solicitud
        )
        vehiculos = FormularioVehiculos(initial=inicial_vehiculos(servicios), servicios=permitidos)

    duplicados = []
    validos = [formulario.is_valid(), vehiculos.is_valid()]  # los dos, para marcar todo error
    if request.method == "POST" and all(validos):
        datos = formulario.datos_registro(vehiculos.datos())
        duplicados = duplicados_activos(
            datos.vehiculos, excluir_solicitud=solicitud.pk if solicitud else None
        )
        if not duplicados or request.POST.get(CAMPO_CONFIRMACION) == _firma(duplicados):
            guardada = _guardar(request, formulario, solicitud, datos)
            if guardada is not None:
                return redirect("detalle_solicitud", pk=guardada.pk)

    contexto = {
        "formulario": formulario,
        "vehiculos": vehiculos,
        "solicitud": solicitud,
        "duplicados": duplicados,
        "firma_duplicados": _firma(duplicados),
        "momento_placa_vin": _momento_placa_vin(),
    }
    for para, campo in BUSQUEDAS:
        contexto[para] = _busqueda(formulario[campo].value(), para)
    return render(request, "solicitudes/nueva.html", contexto)


def _guardar(request, formulario, solicitud, datos):
    """Registra o completa; devuelve la solicitud guardada o None si no se guardó."""
    abrir = request.POST.get("accion") != "borrador"
    try:
        if solicitud is None:
            guardada, faltantes = registrar_solicitud(datos, usuario=request.user, abrir=abrir)
        else:
            guardada, faltantes = completar_borrador(
                solicitud, datos, usuario=request.user, abrir=abrir
            )
    except SolicitudNoEditable as error:
        formulario.add_error(None, f"No se guardó: {error}")
        return None
    except IntegrityError:
        # Otra persona guardó el mismo teléfono o vehículo mientras tanto; no quedó nada.
        formulario.add_error(
            None, "No se guardó: otra persona registró el mismo dato al tiempo. Intente de nuevo."
        )
        return None
    _avisar_guardado(request, guardada, faltantes)
    return guardada


def fila_nueva_vehiculo(request):
    """Fragmento HTMX: una fila de vehículo vacía, el total de filas y el botón actualizados."""
    try:
        indice = max(0, int(request.GET.get("indice", "0")))
    except ValueError:
        indice = 0
    return render(
        request,
        "solicitudes/parcial_fila_vehiculo.html",
        {"fila": fila_vehiculo(indice), "numero": indice + 1, "siguiente": indice + 1},
    )


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


def detalle(request, pk, formulario_cierre=None):
    """Datos de la solicitud, estado derivado y servicios. Un borrador se completa desde aquí; una
    solicitud que nunca se asignó se puede cerrar como no concretada; en una abierta se asigna y
    se reasigna cada servicio y se ordena la ronda de sus conductores."""
    solicitud = get_object_or_404(_con_relaciones(), pk=pk)
    servicios = list(solicitud.servicios.select_related("vehiculo", "conductor", "grua"))
    faltantes = []
    if solicitud.estado_registro == EstadoRegistro.BORRADOR:
        faltantes = faltantes_de(solicitud)
    contexto = {
        "solicitud": solicitud,
        "servicios": servicios,
        "faltantes": describir_faltantes(faltantes),
        "puede_cerrar": puede_cerrarse_no_concretada(solicitud),
        "formulario_cierre": formulario_cierre or FormularioNoConcretada(),
    }
    if solicitud.estado_registro == EstadoRegistro.ABIERTA:
        contexto.update(_contexto_asignacion(servicios))
    return render(request, "solicitudes/detalle.html", contexto)


def _contexto_asignacion(servicios):
    """Formularios de asignar (pendientes) y reasignar (antes de recoger), la lista de conductores
    con su disponibilidad y la ronda de cada conductor de esta solicitud."""
    disponibilidades = disponibilidad_de_conductores()
    asignaciones = []
    for servicio in servicios:
        estado = Estado(servicio.estado)
        if estado == Estado.PENDIENTE_ASIGNAR or estado in REASIGNABLE_DESDE:
            asignaciones.append(
                {
                    "servicio": servicio,
                    "reasignar": estado != Estado.PENDIENTE_ASIGNAR,
                    "formulario": FormularioAsignacion(
                        prefix=f"s{servicio.pk}",
                        disponibilidades=disponibilidades,
                        excluir=servicio.conductor_id,
                    ),
                }
            )
    conductores = {}
    for servicio in servicios:
        if servicio.conductor_id and servicio.estado in VALORES_EN_RONDA:
            conductores.setdefault(servicio.conductor_id, servicio.conductor)
    rondas = []
    for conductor in sorted(conductores.values(), key=lambda c: c.nombre):
        ronda = operaciones.ronda_de(conductor)
        rondas.append({"conductor": conductor, "servicios": ronda, "total": len(ronda)})
    return {
        "asignaciones": asignaciones,
        "disponibilidades": disponibilidades,
        "rondas": rondas,
    }


@require_POST
def asignar_servicio(request, pk, servicio_pk):
    """Asigna un servicio pendiente o reasigna uno ya asignado; las reglas son de las operaciones.
    Con HTMX, la respuesta (tras la redirección) reemplaza el contenido sin recargar la página."""
    servicio = get_object_or_404(
        Servicio.objects.select_related("vehiculo"), pk=servicio_pk, solicitud_id=pk
    )
    reasignando = servicio.estado != Estado.PENDIENTE_ASIGNAR
    formulario = FormularioAsignacion(
        request.POST,
        prefix=f"s{servicio.pk}",
        disponibilidades=disponibilidad_de_conductores(),
        excluir=servicio.conductor_id,
    )
    nombre = f"el servicio N.º {servicio.pk} ({servicio.vehiculo})"
    if not formulario.is_valid():
        errores = [e for lista in formulario.errors.values() for e in lista]
        messages.error(request, f"No se asignó {nombre}: {' '.join(errores)}")
        return redirect("detalle_solicitud", pk=pk)
    operacion = operaciones.reasignar if reasignando else operaciones.asignar
    try:
        operacion(
            servicio,
            formulario.cleaned_data["conductor"],
            actor=request.user,
            motivo=formulario.cleaned_data["motivo"],
        )
    except IdentificacionIncompleta as error:
        messages.error(
            request,
            f"No se asignó {nombre}: {error} La configuración exige placa o VIN al asignar.",
        )
    except (
        SolicitudNoAsignable,
        operaciones.ConductorBloqueado,
        operaciones.MismoConductor,
    ) as error:
        messages.error(request, f"No se asignó {nombre}: {error}")
    except TransicionInvalida:
        accion = "reasignar" if reasignando else "asignar"
        messages.error(
            request,
            f"No se pudo {accion} {nombre}: su estado cambió mientras tanto (otra persona lo "
            "asignó o el conductor avanzó). Revise la tabla de servicios.",
        )
    else:
        accion = "reasignado" if reasignando else "asignado"
        messages.success(
            request, f"Servicio N.º {servicio.pk} {accion} a {servicio.conductor}."
        )
    return redirect("detalle_solicitud", pk=pk)


@require_POST
def mover_en_ronda(request, pk, servicio_pk):
    """Sube o baja un servicio en la ronda de su conductor (puede ser de otra solicitud) y vuelve
    al detalle de la solicitud `pk`."""
    servicio = get_object_or_404(Servicio.objects.select_related("conductor"), pk=servicio_pk)
    try:
        operaciones.mover_en_ronda(servicio, request.POST.get("direccion", ""))
    except ValueError as error:  # MovimientoInvalido o dirección desconocida
        texto = str(error) if isinstance(error, MovimientoInvalido) else "Dirección desconocida."
        messages.error(request, f"No se movió el servicio N.º {servicio.pk}: {texto}")
    else:
        messages.success(request, f"Ronda de {servicio.conductor} actualizada.")
    return redirect("detalle_solicitud", pk=pk)


@require_POST
def no_concretada(request, pk):
    """Cierra la solicitud como no concretada, con motivo. Los errores vuelven al detalle."""
    solicitud = get_object_or_404(Solicitud, pk=pk)
    formulario = FormularioNoConcretada(request.POST)
    if not formulario.is_valid():
        return detalle(request, pk, formulario_cierre=formulario)
    try:
        cerrar_no_concretada(
            solicitud,
            motivo=formulario.cleaned_data["motivo"],
            detalle=formulario.cleaned_data["detalle"],
        )
    except CierreNoPermitido as error:
        messages.error(request, f"No se cerró: {error}")
    else:
        messages.success(request, f"Solicitud {pk} cerrada como no concretada.")
    return redirect("detalle_solicitud", pk=pk)


def _con_relaciones():
    return Solicitud.objects.select_related(
        "solicitante", "pagador", "contacto_origen", "contacto_destino", "creada_por"
    )


def _firma(duplicados) -> str:
    """Identifica las advertencias que el operador vio: si cambian, se vuelve a advertir."""
    return ",".join(sorted(d.clave for d in duplicados))


def _momento_placa_vin() -> str:
    momento = configuracion_vigente().momento_placa_vin
    return "al asignar" if momento == MomentoPlacaVin.AL_ASIGNAR else "al recoger"


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
        regresos = solicitud.servicios.filter(regreso_de__isnull=False).count()
        texto = (
            f"Solicitud {solicitud.pk} registrada. Queda abierta con sus servicios pendientes "
            "de asignar."
        )
        if regresos == 1:
            texto += " Se creó 1 servicio de regreso, enlazado al de ida."
        elif regresos:
            texto += f" Se crearon {regresos} servicios de regreso, enlazados a los de ida."
        messages.success(request, texto)
    elif faltantes:
        messages.warning(
            request,
            f"Solicitud {solicitud.pk} guardada como borrador. Para abrirla falta "
            f"{describir_faltantes(faltantes)}.",
        )
    else:
        messages.info(request, f"Solicitud {solicitud.pk} guardada como borrador.")
