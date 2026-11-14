"""Archivo (foto o escaneo) de un documento que sube el administrador desde el panel.

Nunca se carga entero en memoria: se escribe por partes en un temporal del disco, sea grande o
pequeño (los manejadores por defecto de Django dejan en memoria lo que pesa menos de 2,5 MB), y al
guardar el documento se mueve a `MEDIA_ROOT` con el nombre que pone el servidor. Si pasa del tamaño
máximo se deja de escribir y el resto del cuerpo se descarta. Mientras se escribe se guardan sus
primeros bytes, que dicen de qué tipo es (`nucleo/documentos.py`).

La vista debe cambiar los manejadores antes de que algo lea `request.POST`; por eso la protección
CSRF se aplica dentro de la vista (`con_archivo_a_disco`) y no en el middleware.
"""
from functools import wraps

from django.core.files.uploadhandler import StopUpload, TemporaryFileUploadHandler
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from nucleo import documentos as regla


class ArchivoADisco(TemporaryFileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.excedido = False

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self._cabecera = b""

    def receive_data_chunk(self, raw_data, start):
        if regla.excede_el_tamano(start + len(raw_data)):
            self.excedido = True
            raise StopUpload(connection_reset=False)
        if len(self._cabecera) < regla.LARGO_DE_MARCA:
            self._cabecera += raw_data[: regla.LARGO_DE_MARCA - len(self._cabecera)]
        return super().receive_data_chunk(raw_data, start)

    def file_complete(self, file_size):
        archivo = super().file_complete(file_size)
        archivo.cabecera = self._cabecera
        return archivo


def con_archivo_a_disco(vista):
    """Decorador: la vista recibe los archivos ya en disco y `request.archivo_excedido` dice si
    alguno pasó del tamaño máximo (y se descartó). Mantiene la protección CSRF."""
    protegida = csrf_protect(vista)

    @csrf_exempt
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        manejador = ArchivoADisco(request)
        request.upload_handlers = [manejador]
        request.archivo_excedido = lambda: manejador.excedido
        return protegida(request, *args, **kwargs)

    return envoltura
