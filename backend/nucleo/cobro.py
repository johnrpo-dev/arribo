"""Cobro por línea: una línea es (servicio × pagador) y tiene su propio estado."""
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

MAX_PAGADORES = 2


class EstadoCobro(StrEnum):
    NO_COBRABLE = "no_cobrable"
    SIN_VALOR = "sin_valor"
    POR_FACTURAR = "por_facturar"
    FACTURADO = "facturado"
    PAGADO = "pagado"


class CobroInvalido(Exception):
    pass


@dataclass(frozen=True)
class LineaCobro:
    estado: EstadoCobro
    valor: Decimal | None = None
    numero_factura: str | None = None


def linea_inicial(valor: Decimal | None, *, cobrable: bool = True) -> LineaCobro:
    """Estado con el que nace la línea cuando el servicio queda Entregado o se marca cobrable."""
    if not cobrable:
        return LineaCobro(EstadoCobro.NO_COBRABLE)
    sin_valor = LineaCobro(EstadoCobro.SIN_VALOR)
    return sin_valor if valor is None else fijar_valor(sin_valor, valor)


def fijar_valor(linea: LineaCobro, valor: Decimal) -> LineaCobro:
    """Quien llama guarda en el historial quién, cuándo y el valor anterior."""
    if linea.estado not in (EstadoCobro.SIN_VALOR, EstadoCobro.POR_FACTURAR):
        raise CobroInvalido(f"No se cambia el valor de una línea en {linea.estado}")
    if valor <= 0:
        raise CobroInvalido("El valor debe ser mayor que cero")
    return replace(linea, estado=EstadoCobro.POR_FACTURAR, valor=valor)


def facturar(linea: LineaCobro, numero_factura: str) -> LineaCobro:
    if linea.estado != EstadoCobro.POR_FACTURAR:
        raise CobroInvalido(f"Solo se factura una línea por facturar, no {linea.estado}")
    if not (numero_factura or "").strip():
        raise CobroInvalido("Facturar exige número de factura")
    return replace(linea, estado=EstadoCobro.FACTURADO, numero_factura=numero_factura.strip())


def pagar(linea: LineaCobro) -> LineaCobro:
    if linea.estado != EstadoCobro.FACTURADO:
        raise CobroInvalido("Solo se marca pagada una línea facturada")
    return replace(linea, estado=EstadoCobro.PAGADO)


def anular_factura(linea: LineaCobro, motivo: str) -> LineaCobro:
    if linea.estado != EstadoCobro.FACTURADO:
        raise CobroInvalido("Solo se anula una línea facturada y sin pagar")
    if not (motivo or "").strip():
        raise CobroInvalido("Anular una factura exige motivo")
    return replace(linea, estado=EstadoCobro.POR_FACTURAR, numero_factura=None)


def validar_division(total: Decimal, partes: Sequence[Decimal]) -> None:
    """Un servicio lo paga uno o lo dividen dos, y las partes suman el total."""
    if not 1 <= len(partes) <= MAX_PAGADORES:
        raise CobroInvalido(f"Un servicio tiene entre 1 y {MAX_PAGADORES} pagadores")
    if any(p <= 0 for p in partes):
        raise CobroInvalido("Cada parte debe ser mayor que cero")
    if sum(partes) != total:
        raise CobroInvalido("Las partes no suman el valor del servicio")
