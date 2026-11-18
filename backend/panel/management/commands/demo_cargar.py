"""`manage.py demo_cargar`: carga datos ficticios para mostrar y probar el sistema (1a-20).

Tres grúas, tres conductores, tres clientes (el concesionario con tarifa), servicios en todos los
estados, líneas de cobro en cada estado, alertas activas y documentos por vencer y vencidos. Todo
lleva la marca de demo y `demo_borrar` lo quita sin tocar los datos reales. Ver `panel/demo.py`.
"""
from django.core.management.base import BaseCommand, CommandError

from panel import demo


class Command(BaseCommand):
    help = "Carga datos ficticios de demostración (se quitan con demo_borrar)."

    def handle(self, *args, **opciones):
        try:
            resumen = demo.cargar()
        except (demo.DemoYaCargada, demo.DemoEnConflicto) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Demo cargada: {resumen}."))
        self.stdout.write(
            "Los nombres de clientes y conductores de la demo terminan en «(demo)». "
            "Para quitarla: manage.py demo_borrar."
        )
