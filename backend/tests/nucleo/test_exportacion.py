"""Contenido del CSV genérico de una relación de cobro, byte a byte donde importa."""
import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from nucleo.exportacion import (
    BOM,
    COLUMNAS,
    CsvGenerico,
    DatosRelacion,
    FilaRelacion,
    numero_para_excel,
    texto_para_excel,
)


def fila(**cambios) -> FilaRelacion:
    datos = {
        "servicio": 41,
        "solicitud": 12,
        "numero_caso": "SIN-2026-889",
        "fecha_servicio": date(2026, 11, 3),
        "tipo_servicio": "Traslado",
        "placa": "ABC123",
        "vin": "",
        "vehiculo": "Mazda 3",
        "origen": "Cra 43A # 1-50, Medellín",
        "destino": "Taller Envigado",
        "valor": Decimal(180000),
    }
    datos.update(cambios)
    return FilaRelacion(**datos)


def datos(*filas) -> DatosRelacion:
    return DatosRelacion(
        numero=5,
        pagador="Seguros Andinos S.A.",
        documento_pagador="900123456-7",
        desde=date(2026, 11, 1),
        hasta=date(2026, 11, 15),
        numero_factura="",
        filas=filas,
    )


def leer(contenido: bytes) -> list[list[str]]:
    texto = contenido.decode("utf-8")
    assert texto.startswith(BOM)  # Excel reconoce UTF-8 por el BOM
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


def test_el_csv_trae_encabezado_una_fila_por_linea_y_el_total():
    contenido = CsvGenerico().exportar(
        datos(fila(), fila(servicio=42, valor=Decimal("95000.50"), placa="XYZ987"))
    )
    filas = leer(contenido)
    assert filas[0] == list(COLUMNAS)
    assert filas[1] == [
        "5",
        "Seguros Andinos S.A.",
        "900123456-7",
        "",
        "41",
        "12",
        "SIN-2026-889",
        "03/11/2026",
        "Traslado",
        "ABC123",
        "",
        "Mazda 3",
        "Cra 43A # 1-50, Medellín",
        "Taller Envigado",
        "180000",
    ]
    assert filas[2][4] == "42"
    assert filas[2][-1] == "95000,50"
    assert filas[3][0] == "Subtotal"
    assert filas[3][-1] == "275000,50"
    assert filas[4][0] == "IVA 0 %"
    assert filas[4][-1] == "0"
    assert filas[5][0] == "Total"
    assert filas[5][-1] == "275000,50"
    assert len(filas) == 6


def test_el_csv_suma_el_iva_al_subtotal():
    con_iva = DatosRelacion(**{**datos(fila(), fila(servicio=42)).__dict__,
                               "porcentaje_iva": Decimal(19)})
    filas = leer(CsvGenerico().exportar(con_iva))
    assert filas[-3] == ["Subtotal", *[""] * (len(COLUMNAS) - 2), "360000"]
    assert filas[-2][0] == "IVA 19 %"
    assert filas[-2][-1] == "68400"
    assert filas[-1][0] == "Total"
    assert filas[-1][-1] == "428400"


def test_usa_punto_y_coma_y_fin_de_linea_de_windows():
    contenido = CsvGenerico().exportar(datos(fila()))
    primera = contenido.decode("utf-8").removeprefix(BOM).split("\r\n")[0]
    assert primera.startswith("Relación;Pagador;")


def test_un_texto_con_punto_y_coma_o_comillas_queda_en_su_celda():
    contenido = CsvGenerico().exportar(datos(fila(origen='Bodega "Norte"; muelle 2')))
    assert leer(contenido)[1][12] == 'Bodega "Norte"; muelle 2'


@pytest.mark.parametrize("peligroso", ["=1+1", "+57 300", "-SUMA(A1)", "@cmd", "\tx"])
def test_un_texto_que_parece_formula_no_se_ejecuta_en_excel(peligroso):
    assert texto_para_excel(peligroso) == "'" + peligroso
    assert leer(CsvGenerico().exportar(datos(fila(destino=peligroso))))[1][13] == "'" + peligroso


def test_el_texto_normal_no_se_toca():
    assert texto_para_excel("Taller Envigado") == "Taller Envigado"
    assert texto_para_excel("") == ""


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (Decimal(180000), "180000"),
        (Decimal("180000.00"), "180000"),
        (Decimal("180000.5"), "180000,50"),
        (Decimal("0.75"), "0,75"),
    ],
)
def test_los_valores_van_sin_miles_y_con_coma_decimal(valor, texto):
    assert numero_para_excel(valor) == texto


def test_una_relacion_lleva_la_factura_cuando_ya_esta_facturada():
    facturada = DatosRelacion(**{**datos(fila()).__dict__, "numero_factura": "FE-300"})
    assert leer(CsvGenerico().exportar(facturada))[1][3] == "FE-300"


def test_el_total_suma_en_decimal():
    assert datos(fila(valor=Decimal("0.10")), fila(valor=Decimal("0.20"))).total == Decimal("0.30")
