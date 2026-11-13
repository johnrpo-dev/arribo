"""Vistas de la API del conductor (`/api/v1/`). Delgadas: validan la entrada, llaman a
`api/ingreso.py` o a `api/asignaciones.py` y responden con la forma de `docs/api-conductor.md`.
"""
import hashlib

from django.utils.http import parse_etags
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from configuracion.models import configuracion_vigente

from . import errores, ingreso
from .asignaciones import asignaciones_de
from .contrato import VERSION
from .serializadores import (
    IngresoSerializer,
    ServicioDelConductorSerializer,
    conductor_para_la_app,
    configuracion_para_la_app,
)


class Ingresar(APIView):
    """POST: celular, PIN e identificador del celular → token. No pide token (no autentica)."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        entrada = IngresoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            token, clave = ingreso.ingresar(**entrada.validated_data)
        except ingreso.CredencialesInvalidas as error:
            raise errores.CredencialesInvalidas() from error
        except ingreso.DemasiadosIntentos as error:
            raise errores.DemasiadosIntentos(error.segundos) from error
        except ingreso.ConductorNoHabilitado as error:
            raise errores.ConductorNoHabilitado() from error
        return Response(
            {"version": VERSION, "token": clave, "conductor": conductor_para_la_app(token.conductor)}
        )


class Salir(APIView):
    """POST: cierra la sesión de este celular (revoca su token)."""

    def post(self, request):
        ingreso.cerrar_sesion(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)


class Asignaciones(APIView):
    """GET: los servicios no terminales del conductor, en orden de ronda, con ETag."""

    def get(self, request):
        servicios = asignaciones_de(request.auth.conductor)
        return _responder_con_etag(request, {
            "version": VERSION,
            "configuracion": configuracion_para_la_app(configuracion_vigente()),
            "servicios": ServicioDelConductorSerializer(servicios, many=True).data,
        })


class Asignacion(APIView):
    """GET: uno de sus servicios no terminales; 404 si no existe, es de otro o ya terminó."""

    def get(self, request, servicio_id):
        servicio = asignaciones_de(request.auth.conductor).filter(pk=servicio_id).first()
        if servicio is None:
            raise errores.ServicioNoEncontrado()
        return _responder_con_etag(request, {
            "version": VERSION,
            "configuracion": configuracion_para_la_app(configuracion_vigente()),
            "servicio": ServicioDelConductorSerializer(servicio).data,
        })


def _responder_con_etag(request, datos) -> Response:
    """El ETag es el hash del cuerpo: si la app manda el mismo en If-None-Match, nada cambió y se
    responde 304 sin cuerpo (ahorra datos móviles; el servidor igual arma la respuesta)."""
    etag = '"' + hashlib.sha256(JSONRenderer().render(datos)).hexdigest()[:32] + '"'
    cabeceras = {"ETag": etag, "Cache-Control": "private, no-cache"}
    enviados = {e.removeprefix("W/") for e in parse_etags(request.headers.get("If-None-Match", ""))}
    if etag in enviados:
        return Response(status=status.HTTP_304_NOT_MODIFIED, headers=cabeceras)
    return Response(datos, headers=cabeceras)
