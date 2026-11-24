"""Exportar una relación de cobro a un archivo (1a-17).

Una sola interfaz (`Exportador`) y, por ahora, una implementación: `CsvGenerico`, que se abre
directo en Excel en español. Otros formatos (el de un software de facturación, por ejemplo) se
agregan después como otra implementación, sin tocar quien la usa. Cuál se usa lo dice la
configuración (`formato_exportacion`).

El CSV genérico:
- UTF-8 con BOM, para que Excel muestre bien tildes y eñes.
- Separado por punto y coma y con coma decimal, como lo espera Excel configurado en español.
- Valores sin signo ni separador de miles, para que Excel los tome como números y pueda sumarlos.
- Una fila por línea de cobro y al final tres filas: subtotal (los valores son sin IVA), IVA con su
  porcentaje y total a facturar (1a-19b).
- Un texto que empiece con =, +, -, @ (o tabulador/retorno) va precedido de un apóstrofo: así Excel
  no lo ejecuta como fórmula (una dirección o un nombre digitado no debe poder correr nada).
"""
import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from nucleo.facturacion import Liquidacion, formato_porcentaje, liquidar

BOM = "﻿"


@dataclass(frozen=True)
class FilaRelacion:
    servicio: int
    solicitud: int
    numero_caso: str  # referencia externa de la aseguradora o del concesionario
    fecha_servicio: date
    tipo_servicio: str
    placa: str
    vin: str
    vehiculo: str  # marca y línea
    origen: str
    destino: str
    valor: Decimal
    numero_bodega: str = ""  # si el vehículo se identifica así (sin placa ni VIN, o además)


@dataclass(frozen=True)
class DatosRelacion:
    numero: int
    pagador: str
    documento_pagador: str
    desde: date
    hasta: date
    numero_factura: str
    filas: tuple[FilaRelacion, ...]
    porcentaje_iva: Decimal = Decimal(0)

    @property
    def liquidacion(self) -> Liquidacion:
        return liquidar((fila.valor for fila in self.filas), self.porcentaje_iva)

    @property
    def total(self) -> Decimal:
        return self.liquidacion.total


class Exportador(Protocol):
    nombre: str
    extension: str
    tipo_contenido: str

    def exportar(self, datos: DatosRelacion) -> bytes: ...


def numero_para_excel(valor: Decimal) -> str:
    """180000 → "180000"; 180000.5 → "180000,50". Sin miles: Excel lo lee como número."""
    if valor == valor.to_integral_value():
        return str(int(valor))
    return f"{valor:.2f}".replace(".", ",")


_INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def texto_para_excel(texto: str) -> str:
    texto = texto or ""
    return f"'{texto}" if texto.startswith(_INICIOS_DE_FORMULA) else texto


def fecha_para_excel(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


COLUMNAS = (
    "Relación",
    "Pagador",
    "Documento o NIT",
    "Factura",
    "Servicio",
    "Solicitud",
    "Número de caso",
    "Fecha del servicio",
    "Tipo de servicio",
    "Placa",
    "VIN",
    "Número de bodega",
    "Vehículo",
    "Origen",
    "Destino",
    "Valor",
)


class CsvGenerico:
    nombre = "Excel/CSV genérico"
    extension = "csv"
    tipo_contenido = "text/csv; charset=utf-8"

    def exportar(self, datos: DatosRelacion) -> bytes:
        salida = io.StringIO()
        escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
        escritor.writerow(COLUMNAS)
        for fila in datos.filas:
            escritor.writerow(
                (
                    datos.numero,
                    texto_para_excel(datos.pagador),
                    texto_para_excel(datos.documento_pagador),
                    texto_para_excel(datos.numero_factura),
                    fila.servicio,
                    fila.solicitud,
                    texto_para_excel(fila.numero_caso),
                    fecha_para_excel(fila.fecha_servicio),
                    texto_para_excel(fila.tipo_servicio),
                    texto_para_excel(fila.placa),
                    texto_para_excel(fila.vin),
                    texto_para_excel(fila.numero_bodega),
                    texto_para_excel(fila.vehiculo),
                    texto_para_excel(fila.origen),
                    texto_para_excel(fila.destino),
                    numero_para_excel(fila.valor),
                )
            )
        vacias = [""] * (len(COLUMNAS) - 2)
        cuenta = datos.liquidacion
        escritor.writerow(["Subtotal", *vacias, numero_para_excel(cuenta.subtotal)])
        iva = f"IVA {formato_porcentaje(cuenta.porcentaje_iva)}"
        escritor.writerow([iva, *vacias, numero_para_excel(cuenta.iva)])
        escritor.writerow(["Total", *vacias, numero_para_excel(cuenta.total)])
        return (BOM + salida.getvalue()).encode("utf-8")
