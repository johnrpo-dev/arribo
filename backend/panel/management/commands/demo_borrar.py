"""`manage.py demo_borrar`: quita los datos de demostración y nada más (1a-20).

Borra lo que tiene la marca de demo y lo que cuelga de ello, en una transacción. Si algún dato
real usa un dato de la demo, no borra nada y dice qué lo impide. Ver `panel/demo.py`.
"""
from django.core.management.base import BaseCommand, CommandError

from panel import demo


class Command(BaseCommand):
    help = "Borra los datos ficticios de demostración, sin tocar los datos reales."

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput", "--no-input", action="store_false", dest="interactive",
            help="No pide confirmación.",
        )

    def handle(self, *args, interactive=True, **opciones):
        if not demo.hay_demo():
            self.stdout.write("No hay datos de demo: no se borró nada.")
            return
        self.stdout.write(f"Se borrará la demo: {demo.contar()}.")
        if interactive and input("Escriba «si» para borrarla: ").strip().lower() not in ("si", "sí"):
            self.stdout.write("Cancelado: no se borró nada.")
            return
        try:
            demo.borrar()
        except demo.DemoEnConflicto as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS("Demo borrada. Los datos reales quedaron intactos."))
