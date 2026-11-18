"""Relación de cobro: las líneas por facturar de un pagador en un rango de fechas, que se le mandan
juntas y se facturan con un solo número (1a-17).

Reglas:
- Entra una línea por facturar (ya tiene valor) del mismo pagador, cuya fecha de servicio está
  dentro del rango, con los dos extremos incluidos. Las que están sin valor quedan por fuera: hay que
  digitarles el valor primero.
- Una línea está como máximo en una relación armada. Al facturar o descartar la relación, la línea
  queda libre: si después le anulan la factura, puede entrar en otra.
- Una relación sin líneas no se arma.
- Estados: Armada → Facturada (número obligatorio) → Pagada. Una armada se puede descartar con
  motivo; no se borra. Facturada, Pagada y Descartada no vuelven atrás.
"""
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from nucleo.cobro import CobroInvalido, EstadoCobro


class EstadoRelacion(StrEnum):
    ARMADA = "armada"
    FACTURADA = "facturada"
    PAGADA = "pagada"
    DESCARTADA = "descartada"


@dataclass(frozen=True)
class Relacion:
    estado: EstadoRelacion
    numero_factura: str | None = None
    motivo_descarte: str | None = None


def validar_rango(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise CobroInvalido("La fecha inicial va antes de la final")


def entra_en_relacion(
    *,
    estado_linea: EstadoCobro,
    pagador_linea: int,
    pagador: int,
    fecha_servicio: date,
    desde: date,
    hasta: date,
) -> bool:
    return (
        estado_linea == EstadoCobro.POR_FACTURAR
        and pagador_linea == pagador
        and desde <= fecha_servicio <= hasta
    )


def armar(cuantas_lineas: int) -> Relacion:
    if cuantas_lineas < 1:
        raise CobroInvalido("No hay líneas por facturar de ese pagador en esas fechas")
    return Relacion(EstadoRelacion.ARMADA)


def facturar(relacion: Relacion, numero_factura: str) -> Relacion:
    if relacion.estado != EstadoRelacion.ARMADA:
        raise CobroInvalido("Solo se factura una relación armada")
    if not (numero_factura or "").strip():
        raise CobroInvalido("Facturar exige número de factura")
    return replace(
        relacion, estado=EstadoRelacion.FACTURADA, numero_factura=numero_factura.strip()
    )


def pagar(relacion: Relacion) -> Relacion:
    if relacion.estado != EstadoRelacion.FACTURADA:
        raise CobroInvalido("Solo se marca pagada una relación facturada")
    return replace(relacion, estado=EstadoRelacion.PAGADA)


def descartar(relacion: Relacion, motivo: str) -> Relacion:
    if relacion.estado != EstadoRelacion.ARMADA:
        raise CobroInvalido("Solo se descarta una relación armada (aún sin factura)")
    if not (motivo or "").strip():
        raise CobroInvalido("Descartar una relación exige motivo")
    return replace(relacion, estado=EstadoRelacion.DESCARTADA, motivo_descarte=motivo.strip())
