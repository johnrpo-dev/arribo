"""Errores de la API con la forma del contrato (`docs/api-conductor.md`):

    {"version": 1, "error": "<código>", "detalle": "<texto para el conductor>"}

más `campos` (errores por campo) en los datos inválidos y `reintentar_en` (segundos) en el bloqueo
por intentos. La app decide por `error`, que no cambia; `detalle` es el texto en español que muestra.
"""
import math

from django.core.exceptions import PermissionDenied as PermisoDenegadoDeDjango
from django.http import Http404
from rest_framework import exceptions, status

from .contrato import VERSION

# Cabecera WWW-Authenticate de toda respuesta 401 (la exige HTTP).
REINO = 'Bearer realm="arribo"'


class NoAutorizado(exceptions.APIException):
    """401 con la cabecera WWW-Authenticate. Toda respuesta 401 lleva a la pantalla de ingreso."""

    status_code = status.HTTP_401_UNAUTHORIZED
    auth_header = REINO


class CredencialesInvalidas(NoAutorizado):
    default_code = "credenciales_invalidas"
    default_detail = "Celular o PIN incorrectos."


class ConductorNoHabilitado(NoAutorizado):
    default_code = "conductor_no_habilitado"
    default_detail = "Este conductor no tiene acceso a la app. Hable con logística."


class SesionInvalida(NoAutorizado):
    default_code = "sesion_invalida"
    default_detail = "La sesión se cerró o no es válida. Ingrese de nuevo con su celular y PIN."


class DemasiadosIntentos(exceptions.APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "demasiados_intentos"

    def __init__(self, segundos: int):
        self.wait = segundos  # DRF la devuelve también en la cabecera Retry-After
        minutos = math.ceil(segundos / 60)
        unidad = "minuto" if minutos == 1 else "minutos"
        super().__init__(
            f"Demasiados intentos fallidos. Intente de nuevo en {minutos} {unidad}."
        )


class ServicioNoEncontrado(exceptions.NotFound):
    default_detail = "El servicio no existe o ya no está asignado a usted."


# Errores propios de DRF: código del contrato y texto en español.
_DE_DRF = {
    "not_authenticated": (
        "no_autenticado",
        "Falta el token de sesión. Ingrese con su celular y PIN.",
    ),
    "authentication_failed": ("sesion_invalida", SesionInvalida.default_detail),
    "not_found": ("no_encontrado", None),
    "method_not_allowed": ("metodo_no_permitido", None),
    "parse_error": ("json_invalido", "El cuerpo de la petición no es un JSON válido."),
    "unsupported_media_type": ("tipo_no_soportado", "Envíe el cuerpo como application/json."),
    "not_acceptable": ("formato_no_aceptado", None),
    "permission_denied": ("sin_permiso", None),
    "throttled": ("demasiados_intentos", None),
}


def manejar_excepcion(exc, context):
    """EXCEPTION_HANDLER de DRF: la respuesta de DRF con el cuerpo del contrato."""
    # Aquí y no arriba: rest_framework.views carga la autenticación, que importa este módulo.
    from rest_framework.views import exception_handler

    respuesta = exception_handler(exc, context)
    if respuesta is None:
        return None  # error del servidor: 500 de Django, que queda en el registro
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermisoDenegadoDeDjango):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, exceptions.ValidationError):
        campos = respuesta.data if isinstance(respuesta.data, dict) else {
            "non_field_errors": respuesta.data
        }
        cuerpo = {"error": "datos_invalidos", "detalle": "Revise los datos enviados.",
                  "campos": campos}
    else:
        codigo = getattr(exc.detail, "code", None) or exc.default_code
        codigo, detalle = _DE_DRF.get(codigo, (codigo, None))
        cuerpo = {"error": codigo, "detalle": detalle or str(exc.detail)}
        if getattr(exc, "wait", None):
            cuerpo["reintentar_en"] = math.ceil(exc.wait)
    respuesta.data = {"version": VERSION, **cuerpo}
    return respuesta
