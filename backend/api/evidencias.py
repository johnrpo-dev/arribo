"""Subida de una foto de evidencia (`PUT /api/v1/evidencias/<uuid>/`, ver `docs/api-conductor.md`).

La foto nunca se carga completa en memoria: llega como `multipart/form-data` y se escribe por
partes (de 64 KB) en un archivo temporal del disco, sea grande o pequeña; al guardarla, ese archivo
se mueve a `MEDIA_ROOT`. Por eso esta vista no usa los manejadores de subida por defecto de Django,
que dejan en memoria los archivos de menos de 2,5 MB. Mientras se escribe se calculan su tamaño, su
huella (SHA-256) y sus primeros bytes, que dicen si es un JPEG.
"""
import hashlib

from django.conf import settings
from django.core.files.uploadhandler import StopUpload, TemporaryFileUploadHandler
from django.http.multipartparser import MultiPartParser as AnalizadorDeDjango
from django.http.multipartparser import MultiPartParserError
from rest_framework import serializers
from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser, DataAndFiles

from nucleo.evidencia import MARCA_JPEG, TAMANO_MAXIMO_FOTO, TIPOS_DESDE_LA_APP, es_jpeg

from .errores import FotoDemasiadoGrande

# Lo que puede ocupar el resto del cuerpo (los otros campos y los separadores del multipart).
MARGEN_DEL_CUERPO = 64 * 1024
# De un cuerpo que ya se sabe demasiado grande se descarta como mucho esto antes de responder.
DESCARTE_MAXIMO = 4 * TAMANO_MAXIMO_FOTO
TROZO = 64 * 1024


def _descartar(stream, tope: int) -> None:
    """Lee por partes y bota lo leído, sin pasar de `tope` bytes."""
    restante = tope
    while restante > 0:
        parte = stream.read(min(TROZO, restante))
        if not parte:
            return
        restante -= len(parte)


class FotoADisco(TemporaryFileUploadHandler):
    """Escribe el archivo en un temporal, por partes, y corta si pasa del tamaño máximo."""

    def __init__(self, request=None):
        super().__init__(request)
        self.excedido = False

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self._huella = hashlib.sha256()
        self._cabecera = b""

    def receive_data_chunk(self, raw_data, start):
        if start + len(raw_data) > TAMANO_MAXIMO_FOTO:
            self.excedido = True
            # No se guarda nada más; lo que falta del cuerpo se lee y se descarta.
            raise StopUpload(connection_reset=False)
        if len(self._cabecera) < len(MARCA_JPEG):
            self._cabecera += raw_data[: len(MARCA_JPEG) - len(self._cabecera)]
        self._huella.update(raw_data)
        return super().receive_data_chunk(raw_data, start)

    def file_complete(self, file_size):
        archivo = super().file_complete(file_size)
        archivo.sha256 = self._huella.hexdigest()
        archivo.cabecera = self._cabecera
        return archivo


class FotoEnMultipart(BaseParser):
    """`multipart/form-data` cuyo archivo va directo a disco (ver `FotoADisco`)."""

    media_type = "multipart/form-data"

    def parse(self, stream, media_type=None, parser_context=None):
        request = parser_context["request"]
        meta = request.META.copy()
        meta["CONTENT_TYPE"] = media_type
        try:
            largo = int(meta.get("CONTENT_LENGTH") or 0)
        except ValueError:
            largo = 0
        if largo > TAMANO_MAXIMO_FOTO + MARGEN_DEL_CUERPO:
            # No se guarda ni se analiza: se lee y se descarta (hasta un tope) solo para que el
            # celular alcance a recibir el 413 en vez de una conexión cortada, que reintentaría.
            _descartar(stream, DESCARTE_MAXIMO)
            raise FotoDemasiadoGrande()
        a_disco = FotoADisco(request)
        try:
            datos, archivos = AnalizadorDeDjango(
                meta, stream, [a_disco], parser_context.get("encoding", settings.DEFAULT_CHARSET)
            ).parse()
        except MultiPartParserError as error:
            raise ParseError(f"El cuerpo multipart no se pudo leer: {error}") from error
        if a_disco.excedido:
            raise FotoDemasiadoGrande()
        return DataAndFiles(datos, archivos)


class FotoSerializer(serializers.Serializer):
    servicio_id = serializers.IntegerField(min_value=1)
    evento_id = serializers.UUIDField()
    tipo = serializers.ChoiceField(choices=sorted(TIPOS_DESDE_LA_APP))
    archivo = serializers.FileField(allow_empty_file=False, use_url=False)

    def validate_archivo(self, archivo):
        # Se mira el contenido: el nombre y el tipo que declara el celular no se usan para nada.
        if not es_jpeg(getattr(archivo, "cabecera", b"")):
            raise serializers.ValidationError("La foto debe ser un JPEG.")
        return archivo
