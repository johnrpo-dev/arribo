"""`manage.py con_senal`: devuelve la señal después de `manage.py sin_senal` (desarrollo por USB).

Quita la marca y vuelve a crear el túnel USB al momento; `runserver` lo sigue manteniendo vivo.
"""
from django.core.management.base import BaseCommand

from panel import tunel_usb


class Command(BaseCommand):
    help = "Devuelve el túnel USB del celular después de sin_senal."

    def add_arguments(self, parser):
        parser.add_argument("--puerto", type=int, default=tunel_usb.PUERTO_POR_DEFECTO)

    def handle(self, *args, puerto, **opciones):
        tunel_usb.marca_sin_senal().unlink(missing_ok=True)
        ruta = tunel_usb.ruta_adb()
        if ruta is None:
            self.stdout.write("Señal devuelta, pero no se encontró adb para crear el túnel.")
            return
        estado = tunel_usb.revisar(tunel_usb.ejecutor_adb(ruta), puerto, sin_senal=False)
        self.stdout.write(f"Señal devuelta. {estado}")
