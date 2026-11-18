"""Totales del panel del dueño (1a-19): cuántos servicios hay en cada estado, cuántas solicitudes no
se concretaron por cada motivo y cuánto falta por cobrar a cada pagador.

Reglas:
- Los conteos traen todas las categorías, también las que están en cero, en un orden fijo: el
  dueño ve siempre las mismas filas.
- Por cobrar de un pagador = sus líneas por facturar + sus líneas facturadas sin pagar. Las sin
  valor se cuentan aparte (todavía no hay cuánto cobrar); las pagadas y las no cobrables no cuentan.
- Los pagadores van del que más debe al que menos; a igual total, por nombre.
- Dinero en `Decimal`.
"""
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from nucleo.cobro import EstadoCobro


def contar(valores: Iterable[str], categorias: Sequence[str]) -> list[tuple[str, int]]:
    """[(categoría, cuántas)] en el orden de `categorias`, con ceros. Un valor que no está entre
    las categorías es un error: el total no cuadraría."""
    cuenta = Counter(valores)
    desconocidas = set(cuenta) - set(categorias)
    if desconocidas:
        raise ValueError(f"Categorías desconocidas: {sorted(desconocidas)}")
    return [(categoria, cuenta.get(categoria, 0)) for categoria in categorias]


@dataclass(frozen=True)
class LineaPendiente:
    pagador: int  # id del cliente: dos clientes con el mismo nombre no se mezclan
    nombre: str
    estado: EstadoCobro
    valor: Decimal | None


@dataclass
class PorCobrar:
    pagador: int | None
    nombre: str
    sin_valor: int = 0
    por_facturar: int = 0
    valor_por_facturar: Decimal = Decimal(0)
    facturadas: int = 0
    valor_facturado: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.valor_por_facturar + self.valor_facturado


def por_cobrar(lineas: Iterable[LineaPendiente]) -> list[PorCobrar]:
    """Lo pendiente de cada pagador. Las pagadas y no cobrables se ignoran."""
    pagadores: dict[int, PorCobrar] = {}
    for linea in lineas:
        estado = EstadoCobro(linea.estado)
        if estado in (EstadoCobro.PAGADO, EstadoCobro.NO_COBRABLE):
            continue
        fila = pagadores.setdefault(linea.pagador, PorCobrar(linea.pagador, linea.nombre))
        if estado == EstadoCobro.SIN_VALOR:
            fila.sin_valor += 1
        elif estado == EstadoCobro.POR_FACTURAR:
            fila.por_facturar += 1
            fila.valor_por_facturar += linea.valor
        else:
            fila.facturadas += 1
            fila.valor_facturado += linea.valor
    return sorted(pagadores.values(), key=lambda f: (-f.total, f.nombre, f.pagador))


def total_por_cobrar(filas: Iterable[PorCobrar]) -> PorCobrar:
    """Una fila con la suma de todas, para el pie de la tabla."""
    suma = PorCobrar(None, "Total")
    for fila in filas:
        suma.sin_valor += fila.sin_valor
        suma.por_facturar += fila.por_facturar
        suma.valor_por_facturar += fila.valor_por_facturar
        suma.facturadas += fila.facturadas
        suma.valor_facturado += fila.valor_facturado
    return suma
