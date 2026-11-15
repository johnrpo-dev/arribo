"""Operaciones de la pantalla "Personal y grúas" (1a-08b): conductores, usuarios de oficina y grúas.

Cada operación corre en una transacción: si algo falla, no queda nada a medias (ni un usuario sin
ficha de conductor, ni una asignación cerrada sin la nueva). Nada se borra: se desactiva.

Las reglas están donde ya estaban: formato del PIN en `nucleo/ingreso.py` (vía `Conductor.fijar_pin`),
celular en `nucleo/identificacion.py` (vía `Conductor.save`), traslapes de asignaciones en la base
(`AsignacionConductorGrua`), revocación de sesiones en `api/ingreso.py` y el usuario del conductor y
el último administrador en `nucleo/personal.py`.

Un conductor puede usar la app si está activo y su usuario está activo y en el grupo conductor
(`api.ingreso.habilitado`). Ese usuario lo crea esta pantalla, con contraseña inutilizable: el
conductor entra solo con celular y PIN, nunca al panel.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from api.ingreso import revocar_tokens
from api.models import TokenDispositivo
from nucleo.estados import TERMINALES
from nucleo.personal import (
    nombre_de_usuario_de_conductor,
    validar_no_se_desactiva_a_si_mismo,
    validar_quedan_administradores,
)
from panel.roles import ADMINISTRADOR, CONDUCTOR, ROLES_DEL_PANEL

from .models import AsignacionConductorGrua, Conductor, Grua

Usuario = get_user_model()


class OperacionInvalida(Exception):
    """La operación no se hizo; el mensaje es para mostrarlo tal cual en la pantalla."""


def _grupo(nombre: str) -> Group:
    # get_or_create: los grupos los crea la migración de flota, pero las pruebas transaccionales
    # vacían las tablas.
    return Group.objects.get_or_create(name=nombre)[0]


def _en_grupo(nombre: str, ruta_usuario: str = "pk") -> Exists:
    return Exists(
        Usuario.groups.through.objects.filter(user_id=OuterRef(ruta_usuario), group__name=nombre)
    )


def _mensajes(error: ValidationError) -> str:
    return " ".join(error.messages)


# --- Conductores ---------------------------------------------------------------------------------


def es_usuario_de_conductor(usuario) -> bool:
    """¿Es un usuario del grupo conductor? (Uno de oficina enlazado por error no lo es.)"""
    # groups.all(): aprovecha el prefetch de la lista y no hace una consulta por conductor.
    return usuario is not None and any(g.name == CONDUCTOR for g in usuario.groups.all())


def puede_usar_la_app(conductor) -> bool:
    usuario = conductor.usuario
    return bool(
        conductor.activo
        and conductor.tiene_pin
        and usuario is not None
        and usuario.is_active
        and es_usuario_de_conductor(usuario)
    )


def necesita_habilitar(conductor) -> bool:
    """Sin usuario, o enlazado a uno que no es de conductor (por ejemplo, uno de oficina)."""
    return not es_usuario_de_conductor(conductor.usuario)


def asignaciones_vigentes(en=None) -> dict:
    """{id del conductor: grúa vigente} de todos los conductores, en una consulta."""
    en = en or timezone.now()
    vigentes = (
        AsignacionConductorGrua.objects.filter(inicio__lte=en)
        .filter(Q(fin__isnull=True) | Q(fin__gt=en))
        .select_related("grua")
    )
    return {a.conductor_id: a.grua for a in vigentes}


def servicios_activos(conductor) -> int:
    """Servicios del conductor que no están entregados ni cancelados."""
    from solicitudes.models import Servicio

    return (
        Servicio.objects.filter(conductor=conductor)
        .exclude(estado__in=[estado.value for estado in TERMINALES])
        .count()
    )


def _crear_usuario_de_conductor(conductor) -> "Usuario":
    base = nombre_de_usuario_de_conductor(conductor.celular, [])
    ocupados = Usuario.objects.filter(username__istartswith=base).values_list(
        "username", flat=True
    )
    usuario = Usuario(
        username=nombre_de_usuario_de_conductor(conductor.celular, ocupados),
        first_name=conductor.nombre[: Usuario._meta.get_field("first_name").max_length],
        is_active=conductor.activo,
    )
    usuario.set_unusable_password()
    usuario.save()
    usuario.groups.add(_grupo(CONDUCTOR))
    return usuario


def _bloquear(conductor) -> Conductor:
    """La fila del conductor, bloqueada hasta el fin de la transacción, con su usuario cargado."""
    return (
        Conductor.objects.select_for_update(of=("self",))
        .select_related("usuario")
        .get(pk=conductor.pk)
    )


def _vigente_de(conductor, ahora):
    return (
        AsignacionConductorGrua.objects.select_for_update()
        .filter(conductor=conductor, inicio__lte=ahora)
        .filter(Q(fin__isnull=True) | Q(fin__gt=ahora))
        .select_related("grua")
        .first()
    )


def _abrir_asignacion(conductor, grua, ahora) -> AsignacionConductorGrua:
    # Bloquea la grúa: dos personas que le dan la misma grúa a dos conductores quedan en fila, y
    # la segunda ve el mensaje en vez del error de la base.
    Grua.objects.select_for_update().get(pk=grua.pk)
    otra = (
        AsignacionConductorGrua.objects.filter(grua=grua)
        .filter(Q(fin__isnull=True) | Q(fin__gt=ahora))
        .exclude(conductor=conductor)
        .select_related("conductor")
        .first()
    )
    if otra is not None:
        raise OperacionInvalida(
            f"La grúa {grua.placa} ya la tiene {otra.conductor}. "
            f"Primero cámbiele la grúa a {otra.conductor} o déjelo sin grúa."
        )
    asignacion = AsignacionConductorGrua(conductor=conductor, grua=grua, inicio=ahora)
    try:
        asignacion.full_clean()
    except ValidationError as error:
        raise OperacionInvalida(_mensajes(error)) from error
    asignacion.save()
    return asignacion


@transaction.atomic
def crear_conductor(*, nombre: str, celular: str, pin: str, grua=None) -> Conductor:
    """Ficha del conductor, su usuario para la app (grupo conductor, sin contraseña) y, si se eligió
    grúa, la asignación desde ahora. Todo o nada. `pin` ya validado; si no, PinInvalido."""
    conductor = Conductor(nombre=nombre.strip(), celular=celular)
    conductor.fijar_pin(pin)
    try:
        conductor.full_clean(exclude=["usuario"])
    except ValidationError as error:
        raise OperacionInvalida(_mensajes(error)) from error
    conductor.usuario = _crear_usuario_de_conductor(conductor)
    conductor.save()
    if grua is not None:
        _abrir_asignacion(conductor, grua, timezone.now())
    return conductor


@transaction.atomic
def habilitar_para_la_app(conductor) -> Conductor:
    """A un conductor sin usuario (o enlazado a uno que no es de conductor) le crea y enlaza su
    usuario de la app. El usuario anterior, si había, no se toca: sigue como estaba."""
    conductor = _bloquear(conductor)
    if not necesita_habilitar(conductor):
        raise OperacionInvalida(f"{conductor} ya está habilitado para la app.")
    conductor.usuario = _crear_usuario_de_conductor(conductor)
    conductor.save(update_fields=["usuario"])
    return conductor


@transaction.atomic
def cambiar_pin(conductor, pin: str) -> None:
    """Guarda solo el hash del PIN nuevo (6 dígitos; si no, PinInvalido). No cierra sesiones."""
    conductor = Conductor.objects.select_for_update().get(pk=conductor.pk)
    conductor.fijar_pin(pin)
    conductor.save(update_fields=["pin_hash"])


@transaction.atomic
def cambiar_grua(conductor, grua=None) -> None:
    """Cierra la asignación vigente ahora mismo y abre otra con `grua` desde el mismo instante (el
    periodo es [inicio, fin), así que no se cruzan). `grua=None` lo deja sin grúa."""
    conductor = Conductor.objects.select_for_update().get(pk=conductor.pk)
    ahora = timezone.now()
    vigente = _vigente_de(conductor, ahora)
    if (vigente.grua_id if vigente else None) == (grua.pk if grua else None):
        raise OperacionInvalida(
            f"{conductor} ya tiene la grúa {grua.placa}." if grua else f"{conductor} ya está sin grúa."
        )
    if vigente is not None:
        vigente.fin = ahora
        vigente.save(update_fields=["fin"])
    if grua is not None:
        _abrir_asignacion(conductor, grua, ahora)


@transaction.atomic
def desactivar_conductor(conductor) -> int:
    """Deja de recibir servicios y de entrar a la app: ficha y usuario inactivos y sus sesiones de la
    app revocadas (con ellas se borra su token de push). Devuelve cuántas sesiones se revocaron.

    Sus servicios en curso no se tocan (pregunta abierta en QUESTIONS.md). Un usuario de oficina
    enlazado por error no se desactiva: no es del conductor."""
    conductor = _bloquear(conductor)
    conductor.activo = False
    conductor.save(update_fields=["activo"])
    if es_usuario_de_conductor(conductor.usuario):
        conductor.usuario.is_active = False
        conductor.usuario.save(update_fields=["is_active"])
    return revocar_tokens(TokenDispositivo.objects.filter(conductor=conductor))


@transaction.atomic
def reactivar_conductor(conductor) -> None:
    """Vuelve a recibir servicios y a poder entrar a la app (ingresa de nuevo con su PIN)."""
    conductor = _bloquear(conductor)
    conductor.activo = True
    conductor.save(update_fields=["activo"])
    if es_usuario_de_conductor(conductor.usuario):
        conductor.usuario.is_active = True
        conductor.usuario.save(update_fields=["is_active"])


# --- Usuarios de oficina -------------------------------------------------------------------------


def usuarios_de_oficina():
    """Todos los usuarios menos los de la app del conductor."""
    return (
        Usuario.objects.annotate(de_conductor=_en_grupo(CONDUCTOR))
        .filter(de_conductor=False)
        .prefetch_related("groups")
        .order_by("-is_active", "first_name", "username")
    )


def rol_de(usuario) -> str:
    """El rol del panel del usuario ('' si no tiene, o si tiene varios)."""
    roles = [g.name for g in usuario.groups.all() if g.name in ROLES_DEL_PANEL]
    return roles[0] if len(roles) == 1 else ""


def _administradores_activos():
    """Quienes pueden administrar el panel: superusuarios activos y usuarios activos con el rol
    administrador que no son de la app del conductor (`panel.roles.tiene_rol`)."""
    return Usuario.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | (_en_grupo(ADMINISTRADOR) & ~_en_grupo(CONDUCTOR))
    )


def _verificar_que_queda_un_administrador(sin: "Usuario") -> None:
    """Bloquea a los administradores (dos cambios simultáneos quedan en fila) y revisa que, sin
    `sin`, quede al menos uno activo."""
    list(_administradores_activos().select_for_update().order_by("pk").values_list("pk"))
    validar_quedan_administradores(_administradores_activos().exclude(pk=sin.pk).count())


def _es_administrador_activo(usuario) -> bool:
    return _administradores_activos().filter(pk=usuario.pk).exists()


def _no_es_superusuario(usuario, *, por=None) -> None:
    """La cuenta con acceso total (la del dueño) no se cambia desde esta pantalla: así nadie con el
    rol administrador toma su lugar restableciéndole la contraseña. Su dueño sí cambia la propia."""
    if usuario.is_superuser and (por is None or por.pk != usuario.pk):
        raise OperacionInvalida(
            "Este usuario tiene acceso total: no se cambia desde esta pantalla."
        )


@transaction.atomic
def crear_usuario_de_oficina(*, nombre: str, usuario: str, contrasena: str, rol: str):
    """`contrasena` ya pasó los validadores de Django en el formulario."""
    if rol not in ROLES_DEL_PANEL:
        raise OperacionInvalida("Elija un rol: Logística, Facturación o Administrador.")
    nuevo = Usuario(username=usuario, first_name=nombre.strip())
    nuevo.set_password(contrasena)
    nuevo.save()
    nuevo.groups.add(_grupo(rol))
    return nuevo


@transaction.atomic
def cambiar_rol(usuario, rol: str) -> None:
    """Deja al usuario con un solo rol del panel. Nadie le quita el rol al último administrador."""
    if rol not in ROLES_DEL_PANEL:
        raise OperacionInvalida("Elija un rol: Logística, Facturación o Administrador.")
    _no_es_superusuario(usuario)
    if usuario.groups.filter(name=CONDUCTOR).exists():
        raise OperacionInvalida("Ese usuario es de la app del conductor.")
    if rol != ADMINISTRADOR and _es_administrador_activo(usuario):
        _verificar_que_queda_un_administrador(sin=usuario)
    usuario.groups.remove(*Group.objects.filter(name__in=ROLES_DEL_PANEL))
    usuario.groups.add(_grupo(rol))


@transaction.atomic
def restablecer_contrasena(usuario, contrasena: str, *, por) -> None:
    """`contrasena` ya pasó los validadores de Django en el formulario."""
    _no_es_superusuario(usuario, por=por)
    usuario.set_password(contrasena)
    usuario.save(update_fields=["password"])


@transaction.atomic
def desactivar_usuario(usuario, *, por) -> None:
    """No vuelve a entrar al panel. Ni a sí mismo ni al último administrador."""
    validar_no_se_desactiva_a_si_mismo(usuario.pk == por.pk)
    _no_es_superusuario(usuario)
    if _es_administrador_activo(usuario):
        _verificar_que_queda_un_administrador(sin=usuario)
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])


@transaction.atomic
def reactivar_usuario(usuario) -> None:
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
