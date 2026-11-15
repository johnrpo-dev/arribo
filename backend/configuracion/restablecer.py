"""Restablecer de fábrica: borra los datos de prueba para empezar de cero.

Es la única excepción a "nada se borra" y existe para las pruebas del dueño antes de operar. Solo
funciona con `ARRIBO_PERMITIR_RESTABLECER` (activo por defecto en desarrollo, apagado en
producción) y solo lo usa el administrador desde la pantalla de configuración.

Borra: solicitudes, servicios, eventos, fotos, clientes, cobros, alertas, grúas, conductores,
documentos registrados, sesiones de la app y notificaciones; y los usuarios, salvo el que
restablece y los superusuarios. Conserva: la configuración con su historial y los tipos de
documento (son ajustes, no datos de prueba). Los números de solicitud vuelven a empezar en 1.
"""
import shutil
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import connection, transaction

from configuracion.models import HistorialConfiguracion

# Apps cuyos datos son todos de operación. De `documentos` solo se borran los documentos
# registrados: los tipos de documento son configuración.
APPS_DE_DATOS = ("solicitudes", "cobros", "alertas", "api", "clientes", "flota")
CARPETAS_DE_ARCHIVOS = ("evidencias", "documentos")


class RestablecerNoPermitido(Exception):
    pass


def permitido() -> bool:
    return bool(getattr(settings, "ARRIBO_PERMITIR_RESTABLECER", False))


def _modelos():
    modelos = []
    for etiqueta in APPS_DE_DATOS:
        modelos.extend(apps.get_app_config(etiqueta).get_models(include_auto_created=True))
    modelos.append(apps.get_model("documentos", "Documento"))
    return modelos


def _usuarios_a_borrar(conservar):
    usuarios = get_user_model().objects.exclude(is_superuser=True)
    return usuarios.exclude(pk=conservar.pk) if conservar is not None else usuarios


def resumen(conservar=None) -> list[tuple[str, int]]:
    """Lo que se borraría, para mostrarlo antes de confirmar."""
    contar = [
        ("Solicitudes", "solicitudes", "Solicitud"),
        ("Servicios", "solicitudes", "Servicio"),
        ("Clientes", "clientes", "Cliente"),
        ("Conductores", "flota", "Conductor"),
        ("Grúas", "flota", "Grua"),
        ("Documentos registrados", "documentos", "Documento"),
        ("Alertas", "alertas", "Alerta"),
    ]
    filas = [(nombre, apps.get_model(app, modelo).objects.count()) for nombre, app, modelo in contar]
    filas.append(("Usuarios", _usuarios_a_borrar(conservar).count()))
    return filas


def restablecer(conservar) -> None:
    """Borra los datos de prueba. `conservar` es el usuario que restablece: sigue con su sesión."""
    if not permitido():
        raise RestablecerNoPermitido("Restablecer está apagado en esta instalación.")
    tablas = [m._meta.db_table for m in _modelos()]
    with transaction.atomic():
        with connection.cursor() as cursor:
            # TRUNCATE no pasa por los modelos: los eventos y los historiales son de solo agregar
            # y su `delete()` lo impide a propósito.
            # Las llaves foráneas de Django son diferidas: si hay revisiones pendientes en esta
            # transacción, PostgreSQL no deja hacer TRUNCATE. Se ejecutan antes.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            nombres = ", ".join(connection.ops.quote_name(t) for t in tablas)
            cursor.execute(f"TRUNCATE {nombres} RESTART IDENTITY CASCADE")
        # Quien cambió la configuración queda en su historial (que se conserva): ese usuario no se
        # puede borrar, se desactiva.
        con_historial = HistorialConfiguracion.objects.values("usuario")
        usuarios = _usuarios_a_borrar(conservar)
        usuarios.filter(pk__in=con_historial).update(is_active=False)
        usuarios.exclude(pk__in=con_historial).delete()
        propio = str(getattr(conservar, "pk", ""))
        ajenas = [
            s.pk for s in Session.objects.all() if str(s.get_decoded().get("_auth_user_id")) != propio
        ]
        Session.objects.filter(pk__in=ajenas).delete()
        transaction.on_commit(_borrar_archivos)


def _borrar_archivos() -> None:
    raiz = Path(settings.MEDIA_ROOT)
    for carpeta in CARPETAS_DE_ARCHIVOS:
        shutil.rmtree(raiz / carpeta, ignore_errors=True)
