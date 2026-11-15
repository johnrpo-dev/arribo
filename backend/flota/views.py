"""Pantallas de "Flota y personal" (solo administrador: lo aplican `panel/urls.py` para la sección y
`flota/urls.py` para el resto, con `requiere_rol`). Las vistas validan con los formularios, llaman a
`flota/operaciones.py` y responden; la regla no vive aquí. Los documentos de cada grúa y conductor
se ven en su página y se registran con las pantallas de `documentos`."""
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from documentos import consultas as documentos
from documentos.models import AplicaA
from nucleo.documentos import EstadoDocumento
from nucleo.personal import DesactivarseASiMismo, UltimoAdministrador
from panel.roles import ADMINISTRADOR, CONDUCTOR, NOMBRES_DE_ROL, nombre_de_rol

from . import operaciones as op
from .formularios import (
    FormularioContrasena,
    FormularioDatosConductor,
    FormularioEditarGrua,
    FormularioGrua,
    FormularioNuevoConductor,
    FormularioNuevoUsuario,
    FormularioPin,
    FormularioRol,
)
from .models import Conductor, Grua

Usuario = get_user_model()
ERRORES = (op.OperacionInvalida, UltimoAdministrador, DesactivarseASiMismo)


def _acceso_a_la_app(conductor) -> str:
    """Texto corto para la persona de oficina: qué le falta al conductor para usar la app."""
    if not conductor.activo:
        return "Inactivo"
    if op.necesita_habilitar(conductor):
        return "Falta habilitar"
    if not conductor.tiene_pin:
        return "Falta el PIN"
    if not conductor.usuario.is_active:
        return "Sin acceso"
    return "Puede entrar"


def _rol(usuario) -> str:
    """El rol para mostrar en la pantalla; la cuenta con acceso total (la del dueño) lo dice así."""
    return "Acceso total" if usuario.is_superuser else nombre_de_rol(usuario)


def flota(request):
    """Conductores y grúas con el estado de sus documentos, y los usuarios de oficina, con el botón
    para crear cada uno."""
    hoy = documentos.dia_local()
    vigentes = op.asignaciones_vigentes()
    conductores = list(
        Conductor.objects.select_related("usuario")
        .prefetch_related("usuario__groups")
        .order_by("-activo", "nombre", "pk")
    )
    gruas = list(Grua.objects.order_by("-activa", "placa"))
    de_conductores = documentos.estados_por_sujeto(AplicaA.CONDUCTOR, conductores, hoy)
    de_gruas = documentos.estados_por_sujeto(AplicaA.GRUA, gruas, hoy)
    todos = [e for estados in (*de_conductores.values(), *de_gruas.values()) for e in estados]
    return render(
        request,
        "flota/flota.html",
        {
            "hoy": hoy,
            "conductores": [
                (
                    c,
                    vigentes.get(c.pk),
                    _acceso_a_la_app(c),
                    documentos.resumen(de_conductores[c.pk]),
                )
                for c in conductores
            ],
            "gruas": [(g, documentos.resumen(de_gruas[g.pk])) for g in gruas],
            "usuarios": [(u, _rol(u)) for u in op.usuarios_de_oficina()],
            "vencidos": sum(e.estado == EstadoDocumento.VENCIDO for e in todos),
            "por_vencer": sum(e.estado == EstadoDocumento.POR_VENCER for e in todos),
        },
    )


# --- Conductores ---------------------------------------------------------------------------------


def nuevo_conductor(request):
    formulario = FormularioNuevoConductor(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            conductor = op.crear_conductor(
                nombre=datos["nombre"], celular=datos["celular"], pin=datos["pin"], grua=datos["grua"]
            )
        except ERRORES as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(
                request,
                f"Conductor {conductor} creado. Ya puede entrar a la app con el celular "
                f"{conductor.celular} y su PIN.",
            )
            return redirect("conductor_personal", conductor.pk)
    return render(request, "flota/conductor_nuevo.html", {"formulario": formulario})


def _conductor(pk):
    return get_object_or_404(Conductor.objects.select_related("usuario"), pk=pk)


def conductor(request, pk, formulario_pin=None, formulario_datos=None):
    """Datos del conductor, sus documentos y sus acciones: corregir nombre y celular, habilitar,
    PIN, grúa, desactivar o reactivar."""
    c = _conductor(pk)
    vigente = op.asignaciones_vigentes().get(c.pk)
    usuario_ajeno = c.usuario is not None and op.necesita_habilitar(c)
    return render(
        request,
        "flota/conductor.html",
        {
            "conductor": c,
            "grua": vigente,
            "acceso": _acceso_a_la_app(c),
            "necesita_habilitar": op.necesita_habilitar(c),
            "usuario_ajeno": usuario_ajeno,
            "servicios_activos": op.servicios_activos(c),
            "documentos": documentos.estados_de(c),
            "vencidos": documentos.vencidos_para_asignar(c, vigente),
            "formulario_datos": formulario_datos
            or FormularioDatosConductor(
                prefix="datos",
                conductor=c,
                initial={"nombre": c.nombre, "celular": c.celular, "grua": vigente},
            ),
            "formulario_pin": formulario_pin or FormularioPin(prefix="pin"),
        },
    )


@require_POST
def editar_conductor(request, pk):
    """Corrige nombre, celular y grúa con un solo Guardar. Si el celular ya es de otro conductor o
    la grúa no se puede asignar, lo dice y no cambia nada."""
    c = _conductor(pk)
    formulario = FormularioDatosConductor(request.POST, prefix="datos", conductor=c)
    if formulario.is_valid():
        datos = dict(formulario.cleaned_data)
        grua = datos.pop("grua")
        try:
            with transaction.atomic():
                op.editar_datos_conductor(c, **datos)
                vigente = op.asignaciones_vigentes().get(c.pk)
                if (vigente.pk if vigente else None) != (grua.pk if grua else None):
                    op.cambiar_grua(c, grua)
        except ERRORES as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, "Datos del conductor guardados.")
            return redirect("conductor_personal", pk)
    return conductor(request, pk, formulario_datos=formulario)


@require_POST
def habilitar_conductor(request, pk):
    c = _conductor(pk)
    try:
        op.habilitar_para_la_app(c)
    except ERRORES as error:
        messages.error(request, str(error))
    else:
        c.refresh_from_db()
        if c.tiene_pin:
            messages.success(request, f"{c} quedó habilitado para la app.")
        else:
            messages.warning(request, f"{c} quedó habilitado. Falta ponerle el PIN para que entre.")
    return redirect("conductor_personal", pk)


@require_POST
def cambiar_pin(request, pk):
    c = _conductor(pk)
    formulario = FormularioPin(request.POST, prefix="pin")
    if not formulario.is_valid():
        return conductor(request, pk, formulario_pin=formulario)
    op.cambiar_pin(c, formulario.cleaned_data["pin"])
    messages.success(request, f"PIN de {c} cambiado.")
    return redirect("conductor_personal", pk)


def desactivar_conductor(request, pk):
    """GET: confirmación con cuántos servicios activos tiene. POST: desactiva."""
    c = _conductor(pk)
    if request.method == "POST":
        if not c.activo:
            messages.error(request, f"{c} ya estaba inactivo.")
        else:
            op.desactivar_conductor(c)
            messages.success(
                request, f"{c} quedó inactivo: no recibe servicios nuevos ni entra a la app."
            )
        return redirect("conductor_personal", pk)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    return render(
        request,
        "flota/conductor_desactivar.html",
        {"conductor": c, "servicios_activos": op.servicios_activos(c)},
    )


@require_POST
def reactivar_conductor(request, pk):
    c = _conductor(pk)
    op.reactivar_conductor(c)
    messages.success(request, f"{c} quedó activo otra vez.")
    return redirect("conductor_personal", pk)


# --- Usuarios de oficina -------------------------------------------------------------------------


def nuevo_usuario(request):
    formulario = FormularioNuevoUsuario(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            usuario = op.crear_usuario_de_oficina(
                nombre=datos["nombre"],
                usuario=datos["usuario"],
                contrasena=datos["contrasena"],
                rol=datos["rol"],
            )
        except ERRORES as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(
                request,
                f"Usuario {usuario.username} creado con el rol {NOMBRES_DE_ROL[datos['rol']]}.",
            )
            return redirect("flota")
    return render(request, "flota/usuario_nuevo.html", {"formulario": formulario})


def _usuario(pk):
    return get_object_or_404(Usuario.objects.exclude(groups__name=CONDUCTOR), pk=pk)


def usuario(request, pk, formulario_rol=None, formulario_contrasena=None):
    u = _usuario(pk)
    return render(
        request,
        "flota/usuario.html",
        {
            "usuario": u,
            "rol": _rol(u),
            "es_uno_mismo": u.pk == request.user.pk,
            "formulario_rol": formulario_rol
            or FormularioRol(prefix="rol", initial={"rol": op.rol_de(u)}),
            "formulario_contrasena": formulario_contrasena
            or FormularioContrasena(prefix="clave", usuario=u),
        },
    )


@require_POST
def cambiar_rol(request, pk):
    u = _usuario(pk)
    formulario = FormularioRol(request.POST, prefix="rol")
    if formulario.is_valid():
        rol = formulario.cleaned_data["rol"]
        try:
            op.cambiar_rol(u, rol)
        except ERRORES as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, f"{u.get_username()} tiene ahora el rol {NOMBRES_DE_ROL[rol]}.")
            if u.pk == request.user.pk and rol != ADMINISTRADOR:
                return redirect("inicio")  # ya no entra a esta pantalla
            return redirect("usuario_personal", pk)
    return usuario(request, pk, formulario_rol=formulario)


@require_POST
def restablecer_contrasena(request, pk):
    u = _usuario(pk)
    formulario = FormularioContrasena(request.POST, prefix="clave", usuario=u)
    if formulario.is_valid():
        try:
            op.restablecer_contrasena(u, formulario.cleaned_data["contrasena"], por=request.user)
        except ERRORES as error:
            # La pantalla no muestra este formulario cuando no se puede usar: va como mensaje.
            messages.error(request, str(error))
            return redirect("usuario_personal", pk)
        else:
            if u.pk == request.user.pk:
                update_session_auth_hash(request, u)  # que no se le cierre la sesión
            messages.success(request, f"Contraseña de {u.get_username()} cambiada.")
            return redirect("usuario_personal", pk)
    return usuario(request, pk, formulario_contrasena=formulario)


@require_POST
def desactivar_usuario(request, pk):
    u = _usuario(pk)
    try:
        op.desactivar_usuario(u, por=request.user)
    except ERRORES as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{u.get_username()} quedó inactivo: ya no entra al panel.")
    return redirect("usuario_personal", pk)


@require_POST
def reactivar_usuario(request, pk):
    u = _usuario(pk)
    op.reactivar_usuario(u)
    messages.success(request, f"{u.get_username()} quedó activo otra vez.")
    return redirect("usuario_personal", pk)


# --- Grúas ---------------------------------------------------------------------------------------


def nueva_grua(request):
    formulario = FormularioGrua(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        grua = formulario.save()
        messages.success(request, f"Grúa {grua.placa} creada. Registre aquí sus documentos.")
        return redirect("editar_grua", grua.pk)
    return render(request, "flota/grua.html", {"formulario": formulario, "grua": None})


def editar_grua(request, pk):
    grua = get_object_or_404(Grua, pk=pk)
    formulario = FormularioEditarGrua(request.POST or None, instance=grua)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, f"Grúa {formulario.instance.placa} guardada.")
        return redirect("flota")
    estados = documentos.estados_de(grua)
    return render(
        request,
        "flota/grua.html",
        {
            "formulario": formulario,
            "grua": grua,
            "documentos": estados,
            "vencidos": [e.descripcion for e in estados if e.bloquea],
        },
    )
