"""Autenticación y permiso de la API: `Authorization: Bearer <token>` con el token de un celular.

Es la única autenticación de la API (sin sesión del panel ni usuario y contraseña): un usuario del
panel con sesión abierta en el navegador recibe 401 igual que cualquiera sin token.
"""
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission

from .errores import REINO, ConductorNoHabilitado, SesionInvalida
from .ingreso import en_grupo_conductor, habilitado
from .models import TokenDispositivo, hash_del_token


class TokenDeCelular(BaseAuthentication):
    """Busca el token por su hash. Revocado o desconocido: 401 `sesion_invalida`; conductor
    inactivo, o usuario inactivo o fuera del grupo conductor: 401 `conductor_no_habilitado`."""

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes or partes[0].lower() != b"bearer":
            return None  # sin token: el permiso responde 401 `no_autenticado`
        if len(partes) != 2:
            raise SesionInvalida()
        try:
            clave = partes[1].decode("ascii")
        except UnicodeDecodeError as error:
            raise SesionInvalida() from error

        token = (
            TokenDispositivo.objects.select_related("conductor__usuario")
            .annotate(en_grupo=en_grupo_conductor("conductor__usuario_id"))
            .filter(clave_hash=hash_del_token(clave))
            .first()
        )
        if token is None or not token.vigente:
            raise SesionInvalida()
        if not habilitado(token.conductor, token.en_grupo):
            raise ConductorNoHabilitado()

        token.ultimo_uso = timezone.now()
        TokenDispositivo.objects.filter(pk=token.pk).update(ultimo_uso=token.ultimo_uso)
        return token.conductor.usuario, token

    def authenticate_header(self, request):
        return REINO


class EsConductor(BasePermission):
    """Solo pasa una petición autenticada con el token de un conductor habilitado."""

    def has_permission(self, request, view):
        return isinstance(request.auth, TokenDispositivo)
