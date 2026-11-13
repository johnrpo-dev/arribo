"""Procesador de contexto: la navegación y el rol del usuario para `base.html`."""
from panel.roles import nombre_de_rol
from panel.secciones import secciones_para


def navegacion(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    coincidencia = getattr(request, "resolver_match", None)
    return {
        "secciones_visibles": secciones_para(usuario),
        "seccion_actual": coincidencia.url_name if coincidencia else "",
        "rol_usuario": nombre_de_rol(usuario),
    }
