"""`manage.py runserver` de Arribo: el mismo de Django (con archivos estáticos), y en desarrollo
aplica las migraciones pendientes antes de atender.

Al traer código nuevo (una tarea fusionada) llegan migraciones nuevas. Si nadie corría
`manage.py migrate`, el panel arrancaba igual y la pantalla que usaba la tabla nueva fallaba con
un error (pasó con Cobros). Producción ya migra al arrancar (despliegue/servidor.sh); ahora
desarrollo hace lo mismo y lo dice en la consola.

Para que este comando gane sobre el de staticfiles, `panel` va antes que
`django.contrib.staticfiles` en INSTALLED_APPS (lo vigila tests/panel/test_runserver.py).
"""
from collections.abc import Callable

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as RunserverConEstaticos,
)
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor


def migraciones_pendientes() -> list[str]:
    """Las migraciones sin aplicar en la base, como "app.nombre"."""
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{m.app_label}.{m.name}" for m, _ in plan]


def aplicar_pendientes(
    escribir: Callable[[str], None],
    *,
    pendientes: Callable[[], list[str]] = migraciones_pendientes,
    migrar: Callable[[], None] = lambda: call_command("migrate", verbosity=0),
) -> None:
    """Aplica las migraciones pendientes y lo cuenta. Si algo falla, lo dice y deja arrancar el
    servidor: el error queda a la vista en la consola en vez de aparecer en una pantalla."""
    try:
        lista = pendientes()
        if not lista:
            return
        escribir(f"Aplicando {len(lista)} migración(es) pendiente(s): {', '.join(lista)}")
        migrar()
        escribir("Migraciones aplicadas: la base está al día con el código.")
    except Exception as error:  # noqa: BLE001 - el aviso no debe impedir ver el panel
        escribir(
            f"No se pudieron aplicar las migraciones pendientes: {error}\n"
            "Corra `uv run python manage.py migrate` y revise el mensaje."
        )


class Command(RunserverConEstaticos):
    def inner_run(self, *args, **options):
        # inner_run corre en el proceso que atiende (también tras cada recarga automática).
        if settings.DEBUG:
            aplicar_pendientes(lambda texto: self.stdout.write(texto))
        super().inner_run(*args, **options)
