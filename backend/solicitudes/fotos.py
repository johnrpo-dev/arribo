"""Fotos de evidencia de una solicitud, para verlas y auditarlas en su detalle (1a-08i).

- Cada foto se muestra con el servicio, el tipo (recogida, entrega o soporte), el conductor que la
  subió y, si ya llegó su evento, la hora en que el conductor tocó el paso y quién entregó o recibió.
- Un Recogido o Entregado marcado en la app sin ninguna foto suya queda señalado
  (`nucleo.evidencia.foto_esperada`). Puede ser que la foto todavía esté subiendo desde el celular.
- Las fotos no tienen URL pública: se sirven con `views.foto_evidencia`, que exige sesión y rol.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from nucleo.estados import Estado
from nucleo.evidencia import foto_esperada

from .models import EventoEstado, Evidencia, OrigenEvento, Servicio, TipoEvidencia


@dataclass(frozen=True)
class FotoVista:
    evidencia: Evidencia
    evento: EventoEstado | None  # el toque que acompaña, si ya llegó


@dataclass(frozen=True)
class SinFoto:
    tipo: str  # "recogida" o "entrega"
    evento: EventoEstado

    @property
    def nombre_tipo(self) -> str:
        return TipoEvidencia(self.tipo).label.lower()


@dataclass
class FotosDeServicio:
    servicio: Servicio
    fotos: list[FotoVista] = field(default_factory=list)
    sin_foto: list[SinFoto] = field(default_factory=list)


_ORDEN_TIPO = {tipo: i for i, tipo in enumerate(TipoEvidencia.values)}


def fotos_de(servicios: list[Servicio]) -> list[FotosDeServicio]:
    """Por servicio, en el orden recibido: sus fotos (recogida, entrega, soporte; cada tipo por
    hora de subida) y los toques de la app que no trajeron foto. Dos consultas en total."""
    ids = [s.pk for s in servicios]
    eventos = {
        e.pk: e
        for e in EventoEstado.objects.filter(servicio_id__in=ids).select_related("conductor")
    }
    por_servicio = defaultdict(list)
    acompanados = set()
    for evidencia in Evidencia.objects.filter(servicio_id__in=ids).select_related("subida_por"):
        acompana = evidencia.evento_id or evidencia.evento_esperado
        acompanados.add(acompana)
        por_servicio[evidencia.servicio_id].append(FotoVista(evidencia, eventos.get(acompana)))

    sin_foto = defaultdict(list)
    for evento in sorted(eventos.values(), key=lambda e: (e.secuencia or 0, e.hora_sincronizacion)):
        tipo = foto_esperada(
            desde_la_app=evento.origen == OrigenEvento.APP, destino=Estado(evento.destino)
        )
        if tipo and evento.pk not in acompanados:
            sin_foto[evento.servicio_id].append(SinFoto(tipo, evento))

    resultado = []
    for servicio in servicios:
        fotos = sorted(
            por_servicio[servicio.pk],
            key=lambda f: (_ORDEN_TIPO[f.evidencia.tipo], f.evidencia.creada_en),
        )
        resultado.append(FotosDeServicio(servicio, fotos, sin_foto[servicio.pk]))
    return resultado
