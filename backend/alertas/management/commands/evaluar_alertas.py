"""`manage.py evaluar_alertas`: abre y cierra las alertas por umbral (sin asignar, Recogido sin
Entregado, documento por vencer o vencido) con los umbrales de la configuración.

En producción se corre cada minuto (cron o temporizador del servidor, tarea 1a-21). El tablero
también la corre al cargarse, así que en desarrollo basta con abrirlo.
"""
from django.core.management.base import BaseCommand

from alertas.evaluacion import evaluar
from alertas.models import TipoAlerta


class Command(BaseCommand):
    help = "Abre las alertas por umbral que tocan y cierra las que ya no aplican."

    def handle(self, *args, **opciones):
        resumen = evaluar()
        for tipo, nuevas in resumen.abiertas.items():
            cerradas = resumen.cerradas.get(tipo, 0)
            self.stdout.write(f"{TipoAlerta(tipo).label}: {nuevas} nuevas, {cerradas} cerradas.")
