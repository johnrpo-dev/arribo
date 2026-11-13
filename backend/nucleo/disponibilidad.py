"""Disponibilidad de un conductor para recibir asignaciones nuevas.

Un conductor bloqueado no recibe asignaciones nuevas (ni por asignar ni por reasignar); lo que ya
tiene en curso no se interrumpe. La carga no bloquea: a un conductor sí se le pueden asignar más
vehículos que la capacidad de su grúa, porque los atiende en rondas.
"""
from collections.abc import Iterable
from dataclasses import dataclass

from nucleo.estados import TERMINALES, Servicio, a_bordo


@dataclass(frozen=True)
class DatosConductor:
    """Lo que la regla necesita saber del conductor y de su grúa vigente (si tiene)."""

    activo: bool
    grua_placa: str | None
    grua_operativa: bool = True
    grua_activa: bool = True
    # Llegan con los documentos (tarea 1a-15): nombre de cada documento vencido.
    documentos_vencidos: tuple[str, ...] = ()


def motivos_de_bloqueo(datos: DatosConductor) -> list[str]:
    """Por qué el conductor no puede recibir asignaciones nuevas; lista vacía = disponible."""
    motivos = []
    if not datos.activo:
        motivos.append("El conductor está inactivo.")
    if datos.grua_placa is None:
        motivos.append("No tiene una grúa asignada en este momento.")
    else:
        if not datos.grua_activa:
            motivos.append(f"La grúa {datos.grua_placa} está inactiva.")
        if not datos.grua_operativa:
            motivos.append(f"La grúa {datos.grua_placa} está fuera de servicio.")
    for documento in datos.documentos_vencidos:
        motivos.append(f"Documento vencido: {documento}.")
    return motivos


@dataclass(frozen=True)
class Carga:
    no_terminales: int  # servicios que aún tiene por atender o en curso
    montados: int  # vehículos que lleva a bordo (cuentan para la capacidad)


def carga(servicios: Iterable[Servicio]) -> Carga:
    """Carga del conductor a partir de sus servicios (en cualquier estado)."""
    activos = [s for s in servicios if s.estado not in TERMINALES]
    return Carga(no_terminales=len(activos), montados=sum(1 for s in activos if a_bordo(s)))
