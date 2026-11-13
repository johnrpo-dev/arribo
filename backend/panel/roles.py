"""Acceso al panel por rol. Los roles son los grupos de Django creados en `flota/migrations/0002_roles.py`.

El superusuario pasa siempre. Un usuario del grupo `conductor` no entra al panel aunque tenga otro
rol: su lugar es la app.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

ADMINISTRADOR = "administrador"
LOGISTICA = "logistica"
FACTURACION = "facturacion"
CONDUCTOR = "conductor"

ROLES_DEL_PANEL = (ADMINISTRADOR, LOGISTICA, FACTURACION)

NOMBRES_DE_ROL = {
    ADMINISTRADOR: "Administrador",
    LOGISTICA: "Logística",
    FACTURACION: "Facturación",
    CONDUCTOR: "Conductor",
}


def roles_de(usuario) -> frozenset[str]:
    """Nombres de los grupos del usuario. Se guardan en el objeto para consultar una vez por petición."""
    if not usuario.is_authenticated:
        return frozenset()
    roles = getattr(usuario, "_roles_arribo", None)
    if roles is None:
        roles = frozenset(usuario.groups.values_list("name", flat=True))
        usuario._roles_arribo = roles
    return roles


def tiene_rol(usuario, roles) -> bool:
    """True si el usuario puede entrar a algo del panel abierto a cualquiera de `roles`."""
    if not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True
    propios = roles_de(usuario)
    if CONDUCTOR in propios:
        return False
    return bool(propios & set(roles))


def nombre_de_rol(usuario) -> str:
    """Texto que se muestra bajo el nombre del usuario en la barra lateral."""
    if usuario.is_superuser:
        return "Superusuario"
    propios = [NOMBRES_DE_ROL[r] for r in ROLES_DEL_PANEL if r in roles_de(usuario)]
    return ", ".join(propios) or "Sin rol"


def requiere_rol(*roles):
    """Decorador de vistas: sin sesión lleva al ingreso; con sesión y sin el rol, 403.

    Uso: `@requiere_rol(LOGISTICA, ADMINISTRADOR)`. Solo acepta roles del panel.
    """
    if not roles:
        raise ValueError("requiere_rol necesita al menos un rol")
    desconocidos = set(roles) - set(ROLES_DEL_PANEL)
    if desconocidos:
        raise ValueError(f"Roles que no son del panel: {sorted(desconocidos)}")

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not tiene_rol(request.user, roles):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        envoltura.roles_permitidos = tuple(roles)
        return envoltura

    return decorador
