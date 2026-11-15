"""El admin de Django queda solo de consulta y solo para superusuarios.

Todo el trabajo del día a día (conductores, grúas, usuarios, solicitudes, configuración) se hace en
el panel de Arribo, que aplica las reglas. El admin es para soporte técnico: mirar la base por dentro
sin poder cambiar nada. Usuarios y grupos no aparecen: los roles los maneja "Flota y personal".

Se aplica en `PanelConfig.ready`, cuando el admin ya registró los modelos de todas las apps.
"""
from django.contrib import admin
from django.contrib.auth.models import Group, User


def _solo_superusuario(request, obj=None) -> bool:
    return bool(request.user.is_active and request.user.is_superuser)


def _nunca(request, obj=None) -> bool:
    return False


def _sin_acciones(request):
    return {}


def dejar_admin_de_solo_consulta(sitio=admin.site) -> None:
    for modelo in (User, Group):
        if sitio.is_registered(modelo):
            sitio.unregister(modelo)
    sitio.has_permission = _solo_superusuario
    sitio.site_header = "Arribo: consulta técnica (solo lectura)"
    sitio.site_title = "Arribo: consulta"
    sitio.index_title = "Solo lectura. El trabajo diario se hace en el panel de Arribo."
    for modelo_admin in sitio._registry.values():
        modelo_admin.has_view_permission = _solo_superusuario
        modelo_admin.has_add_permission = _nunca
        modelo_admin.has_change_permission = _nunca
        modelo_admin.has_delete_permission = _nunca
        modelo_admin.get_actions = _sin_acciones
        modelo_admin.get_inlines = lambda request, obj, _m=modelo_admin: [
            _en_linea_de_consulta(i) for i in _m.inlines
        ]


def _en_linea_de_consulta(clase):
    return type(
        clase.__name__,
        (clase,),
        {
            "has_add_permission": lambda self, request, obj=None: False,
            "has_change_permission": lambda self, request, obj=None: False,
            "has_delete_permission": lambda self, request, obj=None: False,
        },
    )
