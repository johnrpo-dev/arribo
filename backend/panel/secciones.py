"""Secciones de la navegación del panel: el único lugar donde se registran.

Para conectar una pantalla nueva, la tarea que la construye cambia `vista=None` por la ruta de
importación de su vista (por ejemplo `"solicitudes.views.lista"`). Mientras `vista` sea `None`,
la sección muestra "Aún no disponible". Los roles de cada sección los aplica `requiere_rol` en
`panel/urls.py`; la vista no necesita repetirlos.
"""
from dataclasses import dataclass

from panel.roles import ADMINISTRADOR, FACTURACION, LOGISTICA, tiene_rol


@dataclass(frozen=True)
class Seccion:
    clave: str  # nombre de la URL
    nombre: str  # texto en la navegación
    ruta: str  # ruta relativa a la raíz, terminada en "/"
    roles: tuple[str, ...]
    vista: str | None = None  # ruta de importación de la vista; None = aún no disponible

    @property
    def disponible(self) -> bool:
        return self.vista is not None


SECCIONES = (
    Seccion("tablero", "Tablero", "tablero/", (LOGISTICA, ADMINISTRADOR)),
    Seccion(
        "nueva_solicitud",
        "Nueva solicitud",
        "solicitudes/nueva/",
        (LOGISTICA, ADMINISTRADOR),
        vista="solicitudes.views.nueva",
    ),
    Seccion("solicitudes", "Solicitudes", "solicitudes/", (LOGISTICA, ADMINISTRADOR)),
    Seccion("cobros", "Cobros", "cobros/", (FACTURACION, ADMINISTRADOR)),
    Seccion("flota", "Flota y documentos", "flota/", (ADMINISTRADOR,)),
    Seccion("panel_dueno", "Panel del dueño", "dueno/", (ADMINISTRADOR,)),
    Seccion(
        "configuracion",
        "Configuración",
        "configuracion/",
        (ADMINISTRADOR,),
        vista="configuracion.views.configuracion",
    ),
)


def secciones_para(usuario) -> list[Seccion]:
    """Secciones que el usuario puede ver, en el orden de la navegación."""
    return [s for s in SECCIONES if tiene_rol(usuario, s.roles)]
