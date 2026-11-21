"""`manage.py sin_senal`: simula que el celular perdió la señal, en desarrollo por USB.

`runserver` mantiene vivo el túnel USB del celular (panel/tunel_usb.py), así que para probar el
modo sin señal (docs/prueba-sin-senal.md) no basta con quitarlo a mano: volvería en 3 segundos.
Este comando lo quita y deja la marca para que no se recree hasta `manage.py con_senal`.
"""
from django.core.management.base import BaseCommand

from panel import tunel_usb


class Command(BaseCommand):
    help = "Quita el túnel USB del celular y lo deja apagado hasta con_senal (prueba sin señal)."

    def add_arguments(self, parser):
        parser.add_argument("--puerto", type=int, default=tunel_usb.PUERTO_POR_DEFECTO)

    def handle(self, *args, puerto, **opciones):
        tunel_usb.marca_sin_senal().touch()
        ruta = tunel_usb.ruta_adb()
        if ruta is not None:
            tunel_usb.ejecutor_adb(ruta)(["reverse", "--remove", f"tcp:{puerto}"])
        self.stdout.write(
            "Sin señal: el celular ya no llega al panel por el cable. "
            "Para devolverla: manage.py con_senal."
        )
