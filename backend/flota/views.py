"""Pantallas de "Personal y grúas" (solo administrador: lo aplican `panel/urls.py` para la sección y
`flota/urls.py` para el resto, con `requiere_rol`). Las vistas validan con los formularios, llaman a
`flota/operaciones.py` y responden; la regla no vive aquí."""
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from nucleo.personal import DesactivarseASiMismo, UltimoAdministrador
from panel.roles import ADMINISTRADOR, CONDUCTOR, NOMBRES_DE_ROL, nombre_de_rol

from . import operaciones as op
from .formularios import (
    FormularioCambiarGrua,
    FormularioContrasena,
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


def personal(request):
    """Conductores, usuarios de oficina y grúas, con el botón para crear cada uno."""
    vigentes = op.asignaciones_vigentes()
    conductores = [
        (c, vigentes.get(c.pk), _acceso_a_la_app(c))
        for c in Conductor.objects.select_related("usuario")
        .prefetch_related("usuario__groups")
        .order_by("-activo", "nombre", "pk")
    ]
    usuarios = [(u, _rol(u)) for u in op.usuarios_de_oficina()]
    return render(
        request,
        "flota/personal.html",
        {
            "conductores": conductores,
            "usuarios": usuarios,
            "gruas": Grua.objects.order_by("-activa", "placa"),
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


def conductor(request, pk, formulario_pin=None, formulario_grua=None):
    """Datos del conductor y sus acciones: habilitar, PIN, grúa, desactivar o reactivar."""
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
            "formulario_pin": formulario_pin or FormularioPin(prefix="pin"),
            "formulario_grua": formulario_grua
            or FormularioCambiarGrua(prefix="grua", initial={"grua": vigente}),
        },
    )


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


@require_POST
def cambiar_grua(request, pk):
    c = _conductor(pk)
    formulario = FormularioCambiarGrua(request.POST, prefix="grua")
    if formulario.is_valid():
        grua = formulario.cleaned_data["grua"]
        try:
            op.cambiar_grua(c, grua)
        except ERRORES as error:
            formulario.add_error(None, str(error))
        else:
            if grua:
                messages.success(request, f"{c} tiene ahora la grúa {grua.placa}.")
            else:
                messages.success(request, f"{c} quedó sin grúa.")
            return redirect("conductor_personal", pk)
    return conductor(request, pk, formulario_grua=formulario)


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
            return redirect("personal")
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
        messages.success(request, f"Grúa {grua.placa} creada.")
        return redirect("personal")
    return render(request, "flota/grua.html", {"formulario": formulario, "grua": None})


def editar_grua(request, pk):
    grua = get_object_or_404(Grua, pk=pk)
    formulario = FormularioEditarGrua(request.POST or None, instance=grua)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, f"Grúa {formulario.instance.placa} guardada.")
        return redirect("personal")
    return render(request, "flota/grua.html", {"formulario": formulario, "grua": grua})
