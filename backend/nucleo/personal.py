"""Reglas del personal (1a-08b): el usuario interno de cada conductor y quién administra el panel.

Python puro. La pantalla "Personal y grúas" (`flota/operaciones.py`) carga los datos de la base,
llama a estas funciones y guarda lo que deciden.

- El conductor entra a la app solo con celular y PIN. Por detrás necesita un usuario de Django (del
  grupo conductor) que nadie ve ni escribe: su nombre se deriva del celular y debe ser único.
- El panel nunca se queda sin administrador: ningún cambio de rol ni desactivación puede dejar cero
  administradores activos, y nadie se desactiva a sí mismo.
"""

PREFIJO_USUARIO_CONDUCTOR = "conductor-"


class UltimoAdministrador(ValueError):
    """El cambio dejaría el panel sin ningún administrador activo."""


class DesactivarseASiMismo(ValueError):
    """Un usuario no se desactiva a sí mismo."""


def nombre_de_usuario_de_conductor(celular: str, ocupados) -> str:
    """"conductor-<celular>"; si ya existe (sin distinguir mayúsculas), "-2", "-3", etc.

    `celular` ya va normalizado (solo dígitos). `ocupados`: nombres de usuario que ya existen.
    """
    ocupados = {nombre.lower() for nombre in ocupados}
    base = f"{PREFIJO_USUARIO_CONDUCTOR}{celular}"
    candidato, numero = base, 1
    while candidato.lower() in ocupados:
        numero += 1
        candidato = f"{base}-{numero}"
    return candidato


def validar_quedan_administradores(administradores_activos_despues: int) -> None:
    """Después del cambio debe quedar al menos un administrador activo."""
    if administradores_activos_despues < 1:
        raise UltimoAdministrador(
            "Es el único administrador activo: el panel se quedaría sin quien lo administre. "
            "Primero dele el rol de administrador a otra persona."
        )


def validar_no_se_desactiva_a_si_mismo(es_uno_mismo: bool) -> None:
    if es_uno_mismo:
        raise DesactivarseASiMismo(
            "No puede desactivar su propio usuario. Pídaselo a otro administrador."
        )
