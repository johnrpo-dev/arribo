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


# --- Pesos escritos a mano ---------------------------------------------------------------------

_DIGITOS_DE_MILES = 3
_MAX_DECIMALES = 2


def leer_pesos(texto: str) -> Decimal:
    """Lo que digitan en el panel, a Decimal: "180000", "180.000", "$ 180.000", "180.000,50".

    El punto o la coma con tres dígitos después separan miles; con uno o dos, son los centavos.
    Lo que no tenga esa forma (letras, grupos mal hechos, más de dos decimales) es CobroInvalido.
    """
    limpio = "".join((texto or "").replace("$", "").split())
    if not limpio or not all(c.isdigit() or c in ".," for c in limpio):
        raise CobroInvalido("Escriba el valor en números, por ejemplo 180.000")
    entero, centavos = limpio, ""
    ultimo = max(limpio.rfind("."), limpio.rfind(","))
    if ultimo >= 0 and 0 < len(limpio) - ultimo - 1 <= _MAX_DECIMALES:
        entero, centavos = limpio[:ultimo], limpio[ultimo + 1 :]
    grupos = entero.replace(",", ".").split(".")
    bien_agrupado = (
        len(grupos) == 1
        or (1 <= len(grupos[0]) <= _DIGITOS_DE_MILES
            and all(len(g) == _DIGITOS_DE_MILES for g in grupos[1:]))
    )
    if not entero or not all(g.isdigit() for g in grupos) or not bien_agrupado:
        raise CobroInvalido("Escriba el valor en números, por ejemplo 180.000")
    return Decimal("".join(grupos) + (f".{centavos}" if centavos else ""))


def formato_pesos(valor: Decimal | None) -> str:
    """Como se lee en Colombia: "$ 180.000" o, con centavos, "$ 180.000,50". Sin valor: "—"."""
    if valor is None:
        return "—"
    entero, _, centavos = f"{valor:,.2f}".partition(".")
    texto = "$ " + entero.replace(",", ".")
    return texto if centavos == "00" else f"{texto},{centavos}"
