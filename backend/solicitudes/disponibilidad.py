"""Disponibilidad de los conductores para asignar: grúa vigente, carga y bloqueos.

`motivos_de_bloqueo(conductor)` es el único lugar donde se decide si un conductor puede recibir
asignaciones nuevas (la regla es `nucleo.disponibilidad.motivos_de_bloqueo`). Lo usan la lista de
conductores del panel y las operaciones `asignar` y `reasignar`. Los documentos vencidos (tarea
1a-15) se agregan en `_datos_del_conductor`, sin tocar a quien la llama.
"""
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from flota.models import AsignacionConductorGrua, Conductor, Grua, grua_vigente
from nucleo import disponibilidad as regla
from nucleo.estados import TERMINALES

from .models import Servicio


def _datos_del_conductor(conductor: Conductor, grua: Grua | None) -> regla.DatosConductor:
    return regla.DatosConductor(
        activo=conductor.activo,
        grua_placa=grua.placa if grua else None,
        grua_operativa=grua is None or grua.estado_operativo == Grua.EstadoOperativo.OPERATIVA,
        grua_activa=grua is None or grua.activa,
        # 1a-15: documentos_vencidos=tuple(nombres de los documentos vencidos del conductor y de
        # su grúa).
    )


def motivos_de_bloqueo(conductor: Conductor, grua: Grua | None = None) -> list[str]:
    """Por qué el conductor no puede recibir asignaciones nuevas; vacía = disponible.

    `grua` es su grúa vigente si quien llama ya la tiene; si no, se busca.
    """
    if grua is None:
        grua = grua_vigente(conductor)
    return regla.motivos_de_bloqueo(_datos_del_conductor(conductor, grua))


@dataclass(frozen=True)
class Disponibilidad:
    conductor: Conductor
    grua: Grua | None
    no_terminales: int
    montados: int
    motivos: tuple[str, ...]

    @property
    def bloqueado(self) -> bool:
        return bool(self.motivos)


def disponibilidad_de_conductores() -> list[Disponibilidad]:
    """Todos los conductores: primero los disponibles, luego los bloqueados; por nombre."""
    ahora = timezone.now()
    gruas = {
        a.conductor_id: a.grua
        for a in AsignacionConductorGrua.objects.filter(inicio__lte=ahora)
        .filter(Q(fin__isnull=True) | Q(fin__gt=ahora))
        .select_related("grua")
    }
    servicios: dict[int, list] = {}
    activos = Servicio.objects.filter(conductor__isnull=False).exclude(
        estado__in=[e.value for e in TERMINALES]
    )
    for servicio in activos.only("conductor_id", "estado", "estado_previo"):
        servicios.setdefault(servicio.conductor_id, []).append(servicio.como_nucleo())

    lista = []
    for conductor in Conductor.objects.order_by("nombre", "pk"):
        grua = gruas.get(conductor.pk)
        carga = regla.carga(servicios.get(conductor.pk, []))
        lista.append(
            Disponibilidad(
                conductor=conductor,
                grua=grua,
                no_terminales=carga.no_terminales,
                montados=carga.montados,
                motivos=tuple(regla.motivos_de_bloqueo(_datos_del_conductor(conductor, grua))),
            )
        )
    return sorted(lista, key=lambda d: d.bloqueado)  # sorted es estable: conserva el nombre
