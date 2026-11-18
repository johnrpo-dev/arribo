from decimal import Decimal

import pytest

from nucleo.cobro import EstadoCobro
from nucleo.resumen import LineaPendiente, contar, por_cobrar, total_por_cobrar

C = EstadoCobro


def test_contar_trae_todas_las_categorias_en_orden_y_con_ceros():
    assert contar(["b", "a", "b"], ["a", "b", "c"]) == [("a", 1), ("b", 2), ("c", 0)]
    assert contar([], ["a"]) == [("a", 0)]


def test_contar_no_acepta_una_categoria_desconocida():
    with pytest.raises(ValueError, match="x"):
        contar(["x"], ["a"])


def linea(pagador, estado, valor=None, nombre=None):
    return LineaPendiente(pagador, nombre or f"Cliente {pagador}", estado, valor)


def test_por_cobrar_suma_por_facturar_y_facturado_de_cada_pagador():
    filas = por_cobrar(
        [
            linea(1, C.POR_FACTURAR, Decimal(180000)),
            linea(1, C.FACTURADO, Decimal(95000)),
            linea(1, C.FACTURADO, Decimal("5000.50")),
            linea(1, C.SIN_VALOR),
            linea(1, C.PAGADO, Decimal(999999)),  # ya pagada: no cuenta
            linea(1, C.NO_COBRABLE),
            linea(2, C.POR_FACTURAR, Decimal(300000)),
        ]
    )
    uno = next(f for f in filas if f.pagador == 1)
    assert (uno.sin_valor, uno.por_facturar, uno.facturadas) == (1, 1, 2)
    assert uno.valor_por_facturar == Decimal(180000)
    assert uno.valor_facturado == Decimal("100000.50")
    assert uno.total == Decimal("280000.50")


def test_los_pagadores_van_del_que_mas_debe_al_que_menos():
    filas = por_cobrar(
        [
            linea(1, C.POR_FACTURAR, Decimal(100), "Zeta"),
            linea(2, C.FACTURADO, Decimal(500), "Beta"),
            linea(3, C.POR_FACTURAR, Decimal(100), "Alfa"),
        ]
    )
    assert [f.nombre for f in filas] == ["Beta", "Alfa", "Zeta"]


def test_un_pagador_solo_con_pagadas_no_aparece():
    assert por_cobrar([linea(1, C.PAGADO, Decimal(10))]) == []


def test_un_pagador_solo_sin_valor_aparece_con_total_cero():
    [fila] = por_cobrar([linea(1, C.SIN_VALOR), linea(1, C.SIN_VALOR)])
    assert (fila.sin_valor, fila.total) == (2, Decimal(0))


def test_dos_clientes_con_el_mismo_nombre_no_se_mezclan():
    filas = por_cobrar(
        [linea(1, C.POR_FACTURAR, Decimal(1), "Igual"), linea(2, C.POR_FACTURAR, Decimal(2), "Igual")]
    )
    assert len(filas) == 2


def test_el_total_suma_todas_las_filas_en_decimal():
    filas = por_cobrar(
        [
            linea(1, C.POR_FACTURAR, Decimal("0.10")),
            linea(2, C.FACTURADO, Decimal("0.20")),
            linea(2, C.SIN_VALOR),
        ]
    )
    total = total_por_cobrar(filas)
    assert total.total == Decimal("0.30")
    assert (total.sin_valor, total.por_facturar, total.facturadas) == (1, 1, 1)
