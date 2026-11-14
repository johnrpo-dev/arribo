"""Documentos de grúas y conductores (SOAT, tecnomecánica, licencia...): estado a una fecha.

Reglas:
- Cada tipo de documento aplica a grúas o a conductores y tiene sus días de anticipación para
  avisar (por defecto 30). Los tipos son configuración: la lista es editable.
- De cada tipo, para cada grúa o conductor, cuenta solo el documento más reciente; los anteriores
  son historial.
- Las fechas son días en America/Bogota (quien llama pasa `hoy` ya en esa zona). Un documento que
  vence hoy sirve todo el día de hoy: vencido es desde el día siguiente.
- "Aún no aplica" (por ejemplo, la tecnomecánica de una grúa nueva) lleva la fecha desde la que se
  exige: ese día ya hace falta el documento, así que desde esa fecha cuenta como vencido.
- Solo el documento vencido bloquea asignaciones nuevas. Un documento que falta no bloquea (la
  regla escrita solo habla de vencido; ver QUESTIONS.md). Lo que ya está en curso no se interrumpe.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

DIAS_ANTICIPACION_POR_DEFECTO = 30

# Archivo (foto o escaneo) del documento. Límite técnico del servidor, no opción del cliente.
TAMANO_MAXIMO_ARCHIVO = 10 * 1024 * 1024  # bytes
# Tipo de archivo → (marca con la que empieza el contenido, extensión con que se guarda).
TIPOS_DE_ARCHIVO = {
    "jpeg": (b"\xff\xd8\xff", "jpg"),
    "png": (b"\x89PNG\r\n\x1a\n", "png"),
    "pdf": (b"%PDF-", "pdf"),
}
LARGO_DE_MARCA = max(len(marca) for marca, _ in TIPOS_DE_ARCHIVO.values())


class EstadoDocumento(StrEnum):
    VIGENTE = "vigente"
    POR_VENCER = "por_vencer"
    VENCIDO = "vencido"
    AUN_NO_APLICA = "aun_no_aplica"
    FALTA = "falta"


NOMBRES_DE_ESTADO = {
    EstadoDocumento.VIGENTE: "Vigente",
    EstadoDocumento.POR_VENCER: "Por vencer",
    EstadoDocumento.VENCIDO: "Vencido",
    EstadoDocumento.AUN_NO_APLICA: "Aún no aplica",
    EstadoDocumento.FALTA: "Falta",
}


@dataclass(frozen=True)
class Documento:
    """El documento vigente de un tipo: o vence, o aún no aplica (y dice desde cuándo)."""

    vence: date | None = None
    aplica_desde: date | None = None

    def __post_init__(self):
        if (self.vence is None) == (self.aplica_desde is None):
            raise ValueError("Un documento lleva fecha de vencimiento o, si aún no aplica, "
                             "la fecha desde la que aplica (una de las dos).")

    @property
    def ultimo_dia_valido(self) -> date:
        """Último día en que el documento sirve (o en que aún no se exige)."""
        if self.vence is not None:
            return self.vence
        return self.aplica_desde - timedelta(days=1)


def dias_restantes(documento: Documento, hoy: date) -> int:
    """Días que le quedan hasta su último día válido (0 = hoy es el último; negativo = vencido)."""
    return (documento.ultimo_dia_valido - hoy).days


def estado_documento(
    documento: Documento | None, hoy: date, dias_anticipacion: int
) -> EstadoDocumento:
    """Estado del documento vigente de un tipo en el día `hoy`; None = no hay ninguno."""
    if dias_anticipacion < 0:
        raise ValueError("Los días de anticipación no pueden ser negativos.")
    if documento is None:
        return EstadoDocumento.FALTA
    restantes = dias_restantes(documento, hoy)
    if restantes < 0:
        return EstadoDocumento.VENCIDO
    if documento.aplica_desde is not None:
        return EstadoDocumento.AUN_NO_APLICA
    if restantes <= dias_anticipacion:
        return EstadoDocumento.POR_VENCER
    return EstadoDocumento.VIGENTE


def requiere_aviso(documento: Documento | None, hoy: date, dias_anticipacion: int) -> bool:
    """¿Hay que avisar que se acerca la fecha? Por vencer, o "aún no aplica" que empieza a
    exigirse dentro de los días de anticipación. Lo vencido y lo que falta no son "por vencer"."""
    estado = estado_documento(documento, hoy, dias_anticipacion)
    if estado == EstadoDocumento.POR_VENCER:
        return True
    return (
        estado == EstadoDocumento.AUN_NO_APLICA
        and dias_restantes(documento, hoy) <= dias_anticipacion
    )


def bloquea(estado: EstadoDocumento) -> bool:
    """¿Este estado impide recibir asignaciones nuevas? Solo vencido."""
    return estado == EstadoDocumento.VENCIDO


def vencidos(estados: dict[str, EstadoDocumento]) -> tuple[str, ...]:
    """Nombres de los documentos que bloquean, en el orden en que llegan."""
    return tuple(nombre for nombre, estado in estados.items() if bloquea(estado))


def tipo_de_archivo(primeros_bytes: bytes) -> str | None:
    """Tipo del archivo según su contenido (no según el nombre); None si no es uno aceptado."""
    for tipo, (marca, _) in TIPOS_DE_ARCHIVO.items():
        if primeros_bytes[: len(marca)] == marca:
            return tipo
    return None


def excede_el_tamano(tamano: int) -> bool:
    return tamano > TAMANO_MAXIMO_ARCHIVO
