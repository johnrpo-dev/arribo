"""Consultas sobre los documentos: estado de cada tipo para una grúa o un conductor, documentos
vencidos que bloquean asignaciones y documentos por vencer (para la alerta de la tarea 1a-18).

Las reglas están en `nucleo/documentos.py`; aquí solo se buscan los datos y se llaman.

- Cuenta solo el documento más reciente de cada tipo (por fecha de registro) y solo los tipos
  activos que aplican a ese lado (grúa o conductor).
- "Hoy" es el día en America/Bogota (`TIME_ZONE`): un documento que vence hoy sirve hasta la
  medianoche de Medellín, aunque en UTC ya sea mañana.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from django.utils import timezone

from flota.models import Conductor, Grua
from nucleo import documentos as regla
from nucleo.alertas import documento_alerta
from nucleo.documentos import EstadoDocumento

from .models import AplicaA, Documento, TipoDocumento

# Etiqueta de estado del panel (`estado estado--...` de arribo.css) para cada estado del documento.
CLASE_DE_ESTADO = {
    EstadoDocumento.VIGENTE: "entregado",
    EstadoDocumento.POR_VENCER: "recogido",
    EstadoDocumento.VENCIDO: "novedad",
    EstadoDocumento.AUN_NO_APLICA: "asignado",
    EstadoDocumento.FALTA: "pendiente_asignar",
}


def dia_local(en: datetime | None = None) -> date:
    """El día en Medellín del instante `en` (por defecto, ahora)."""
    return timezone.localdate(en or timezone.now())


@dataclass(frozen=True)
class EstadoDeTipo:
    """Cómo está un tipo de documento para una grúa o un conductor en un día."""

    tipo: TipoDocumento
    sujeto: Grua | Conductor
    documento: Documento | None  # el vigente (el más reciente), o None si no hay ninguno
    estado: EstadoDocumento

    @property
    def nombre_estado(self) -> str:
        return regla.NOMBRES_DE_ESTADO[self.estado]

    @property
    def clase(self) -> str:
        return CLASE_DE_ESTADO[self.estado]

    @property
    def bloquea(self) -> bool:
        return regla.bloquea(self.estado)

    @property
    def descripcion(self) -> str:
        """Nombre del documento con su dueño, para los motivos y los avisos."""
        if isinstance(self.sujeto, Grua):
            return f"{self.tipo.nombre} de la grúa {self.sujeto.placa}"
        return f"{self.tipo.nombre} de {self.sujeto.nombre}"


def _campo(aplica_a: str) -> str:
    return "grua_id" if aplica_a == AplicaA.GRUA else "conductor_id"


def tipos_activos(aplica_a: str) -> list[TipoDocumento]:
    return list(TipoDocumento.objects.filter(aplica_a=aplica_a, activo=True).order_by("nombre"))


def documentos_vigentes(aplica_a: str, ids: Iterable[int] | None = None) -> dict:
    """{(tipo_id, id de la grúa o del conductor): documento más reciente} de los tipos activos."""
    campo = _campo(aplica_a)
    documentos = Documento.objects.filter(aplica_a=aplica_a, tipo__activo=True)
    if ids is not None:
        documentos = documentos.filter(**{f"{campo}__in": list(ids)})
    # DISTINCT ON de PostgreSQL: el primero de cada (tipo, sujeto) según el orden, el más reciente.
    documentos = documentos.order_by("tipo_id", campo, "-registrado_en", "-pk").distinct(
        "tipo_id", campo
    )
    return {(d.tipo_id, getattr(d, campo)): d for d in documentos}


def estados_por_sujeto(aplica_a: str, sujetos: Iterable, hoy: date | None = None) -> dict:
    """{id del sujeto: [EstadoDeTipo por cada tipo activo]} con tres consultas en total."""
    hoy = hoy or dia_local()
    sujetos = list(sujetos)
    tipos = tipos_activos(aplica_a)
    vigentes = documentos_vigentes(aplica_a, [s.pk for s in sujetos])
    resultado = {}
    for sujeto in sujetos:
        estados = []
        for tipo in tipos:
            documento = vigentes.get((tipo.pk, sujeto.pk))
            estado = regla.estado_documento(
                documento.como_nucleo() if documento else None, hoy, tipo.dias_anticipacion
            )
            estados.append(EstadoDeTipo(tipo, sujeto, documento, estado))
        resultado[sujeto.pk] = estados
    return resultado


def estados_de(sujeto: Grua | Conductor, hoy: date | None = None) -> list[EstadoDeTipo]:
    aplica_a = AplicaA.GRUA if isinstance(sujeto, Grua) else AplicaA.CONDUCTOR
    return estados_por_sujeto(aplica_a, [sujeto], hoy)[sujeto.pk]


def estado_de_tipo(
    sujeto: Grua | Conductor, tipo: TipoDocumento, hoy: date | None = None
) -> EstadoDeTipo:
    """Estado de un tipo para un sujeto, también si el tipo está inactivo (para su historial)."""
    filtro = {"grua": sujeto} if isinstance(sujeto, Grua) else {"conductor": sujeto}
    documento = Documento.objects.filter(tipo=tipo, **filtro).order_by("-registrado_en", "-pk").first()
    estado = regla.estado_documento(
        documento.como_nucleo() if documento else None, hoy or dia_local(), tipo.dias_anticipacion
    )
    return EstadoDeTipo(tipo, sujeto, documento, estado)


def vencidos_para_asignar(
    conductor: Conductor, grua: Grua | None, hoy: date | None = None
) -> tuple[str, ...]:
    """Documentos vencidos del conductor y de su grúa vigente: impiden asignarle servicios nuevos."""
    hoy = hoy or dia_local()
    estados = estados_de(conductor, hoy)
    if grua is not None:
        estados += estados_de(grua, hoy)
    return regla.vencidos({e.descripcion: e.estado for e in estados})


class VencidosDeLaFlota:
    """Lo mismo que `vencidos_para_asignar`, para muchos conductores con pocas consultas."""

    def __init__(self, conductores: Iterable[Conductor], gruas: Iterable[Grua], hoy=None):
        hoy = hoy or dia_local()
        self._conductores = estados_por_sujeto(AplicaA.CONDUCTOR, conductores, hoy)
        self._gruas = estados_por_sujeto(AplicaA.GRUA, gruas, hoy)

    def de(self, conductor: Conductor, grua: Grua | None) -> tuple[str, ...]:
        estados = list(self._conductores.get(conductor.pk, []))
        if grua is not None:
            estados += self._gruas.get(grua.pk, [])
        return regla.vencidos({e.descripcion: e.estado for e in estados})


def documentos_por_vencer(fecha: date) -> list[EstadoDeTipo]:
    """Documentos de grúas y conductores activos que hay que avisar en el día `fecha`: por vencer
    según los días de anticipación de su tipo, o "aún no aplica" que empieza a exigirse dentro de
    esos días. No incluye los vencidos ni los que faltan. Para la alerta de la tarea 1a-18."""
    avisos = []
    for aplica_a, sujetos in (
        (AplicaA.GRUA, Grua.objects.filter(activa=True)),
        (AplicaA.CONDUCTOR, Conductor.objects.filter(activo=True)),
    ):
        for estados in estados_por_sujeto(aplica_a, sujetos, fecha).values():
            for estado in estados:
                documento = estado.documento.como_nucleo() if estado.documento else None
                if regla.requiere_aviso(documento, fecha, estado.tipo.dias_anticipacion):
                    avisos.append(estado)
    return sorted(
        avisos, key=lambda e: (e.documento.como_nucleo().ultimo_dia_valido, e.descripcion)
    )


def por_vencer_o_vencidos(fecha: date) -> list[EstadoDeTipo]:
    """Documentos de grúas y conductores activos que requieren atención en el día `fecha`: los
    por vencer (como `documentos_por_vencer`) y además los vencidos, el más urgente primero. La
    regla es `nucleo.alertas.documento_alerta`; la usan la alerta y el panel del dueño (1a-18, 1a-19)."""
    atender = []
    for aplica_a, sujetos in (
        (AplicaA.GRUA, Grua.objects.filter(activa=True)),
        (AplicaA.CONDUCTOR, Conductor.objects.filter(activo=True)),
    ):
        for estados in estados_por_sujeto(aplica_a, sujetos, fecha).values():
            for estado in estados:
                documento = estado.documento.como_nucleo() if estado.documento else None
                if documento_alerta(documento, fecha, estado.tipo.dias_anticipacion):
                    atender.append(estado)
    return sorted(
        atender, key=lambda e: (e.documento.como_nucleo().ultimo_dia_valido, e.descripcion)
    )


# --- Resumen para la lista de Flota y personal ---------------------------------------------------

# Del más grave al más leve: el resumen de una grúa o un conductor es el primero que tenga.
# Vencido bloquea asignaciones; falta y por vencer no bloquean, pero hay que atenderlos.
GRAVEDAD = (EstadoDocumento.VENCIDO, EstadoDocumento.FALTA, EstadoDocumento.POR_VENCER)
TEXTO_RESUMEN = {
    EstadoDocumento.VENCIDO: "Vencido",
    EstadoDocumento.FALTA: "Falta",
    EstadoDocumento.POR_VENCER: "Por vencer",
}


@dataclass(frozen=True)
class Resumen:
    """Cómo están, en conjunto, los documentos de una grúa o un conductor."""

    texto: str  # "Vencido", "Falta", "Por vencer" o "Al día"
    clase: str  # etiqueta de estado de arribo.css
    documentos: tuple[str, ...]  # nombres de los tipos en ese estado (vacío si al día)


def resumen(estados: Iterable[EstadoDeTipo]) -> Resumen:
    """El estado más grave entre los documentos (vigente y "aún no aplica" cuentan como al día)."""
    estados = list(estados)
    for grave in GRAVEDAD:
        nombres = tuple(e.tipo.nombre for e in estados if e.estado == grave)
        if nombres:
            return Resumen(TEXTO_RESUMEN[grave], CLASE_DE_ESTADO[grave], nombres)
    return Resumen("Al día", CLASE_DE_ESTADO[EstadoDocumento.VIGENTE], ())
