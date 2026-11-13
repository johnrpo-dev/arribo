"""Operaciones sobre la configuración: guardarla dejando historial y saber quién ve los valores.

`guardar_configuracion` es la forma de cambiarla: bloquea el registro, compara campo por campo con
lo guardado y deja un registro de historial por cada campo que cambió (quién, cuándo, valor anterior
y nuevo), todo en la misma transacción.
"""
from datetime import time

from django.db import transaction

from panel.roles import ADMINISTRADOR, CONDUCTOR, FACTURACION, LOGISTICA, roles_de

from .models import Configuracion, HistorialConfiguracion, configuracion_vigente


def _campos_editables():
    return [
        campo
        for campo in Configuracion._meta.concrete_fields
        if campo.editable and not campo.primary_key
    ]


def _texto(valor) -> str:
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    return str(valor)


def guardar_configuracion(configuracion: Configuracion, *, usuario) -> list[HistorialConfiguracion]:
    """Guarda los cambios de `configuracion` y devuelve el historial que dejaron (vacío si nada
    cambió).
    """
    with transaction.atomic():
        guardada = Configuracion.objects.select_for_update().get(pk=configuracion.pk)
        cambios = []
        for campo in _campos_editables():
            anterior = getattr(guardada, campo.attname)
            nuevo = getattr(configuracion, campo.attname)
            if anterior != nuevo:
                cambios.append((campo.name, _texto(anterior), _texto(nuevo)))
        if not cambios:
            return []
        configuracion.full_clean()
        configuracion.save(update_fields=[nombre for nombre, _, _ in cambios])
        return [
            HistorialConfiguracion.objects.create(
                campo=nombre, valor_anterior=anterior, valor_nuevo=nuevo, usuario=usuario
            )
            for nombre, anterior, nuevo in cambios
        ]


def puede_ver_valores(usuario) -> bool:
    """True si el usuario ve los valores de cobro en el panel.

    El superusuario cuenta como administrador y el administrador siempre los ve. Logística y
    facturación, según la configuración. El conductor nunca, aunque tenga otro rol.
    """
    if not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True
    roles = roles_de(usuario)
    if CONDUCTOR in roles:
        return False
    if ADMINISTRADOR in roles:
        return True
    configuracion = configuracion_vigente()
    return (LOGISTICA in roles and configuracion.ven_valores_logistica) or (
        FACTURACION in roles and configuracion.ven_valores_facturacion
    )
