from decimal import Decimal

import pytest

from nucleo.cobro import CobroInvalido
from nucleo.facturacion import (
    FacturaNoCuadra,
    FacturaRepetida,
    etiqueta_iva,
    formato_porcentaje,
    liquidar,
    normalizar_numero,
    porcentaje_a_aplicar,
    verificar_numero_libre,
    verificar_total,
)

D = Decimal
IVA = D("19")


def test_el_iva_se_suma_al_subtotal_de_lo_que_se_factura_junto():
    liquidacion = liquidar([D("180000"), D("150000")], IVA)
    assert liquidacion.subtotal == D("330000")
    assert liquidacion.iva == D("62700")
    assert liquidacion.total == D("392700")


def test_el_iva_se_redondea_al_peso_la_mitad_hacia_arriba():
    assert liquidar([D("50")], IVA).iva == D("10")  # 9,50 → 10
    assert liquidar([D("10")], IVA).iva == D("2")  # 1,90 → 2
    assert liquidar([D("2")], IVA).iva == D("0")  # 0,38 → 0


def test_sin_iva_el_total_es_el_subtotal():
    assert liquidar([D("180000")], D("0")).total == D("180000")


def test_el_porcentaje_de_iva_va_de_cero_a_cien():
    with pytest.raises(CobroInvalido):
        liquidar([D("1")], D("-1"))
    with pytest.raises(CobroInvalido):
        liquidar([D("1")], D("101"))


def test_el_dinero_sigue_en_decimal():
    liquidacion = liquidar([D("180000.50")], IVA)
    assert all(isinstance(v, Decimal) for v in (liquidacion.subtotal, liquidacion.iva))
    assert liquidacion.total == D("180000.50") + D("34200")


def test_un_total_distinto_al_de_la_orden_no_se_registra_y_dice_la_diferencia():
    with pytest.raises(FacturaNoCuadra) as error:
        verificar_total(D("214200"), D("241200"))
    assert "$ 241.200" in str(error.value)
    assert "$ 214.200" in str(error.value)
    assert "$ 27.000 de más" in str(error.value)


def test_quien_no_ve_valores_recibe_el_aviso_sin_cifras():
    with pytest.raises(FacturaNoCuadra) as error:
        verificar_total(D("214200"), D("200000"), mostrar_valores=False)
    assert "$" not in str(error.value)


def test_el_total_exacto_pasa():
    verificar_total(D("214200"), D("214200"))


def test_un_numero_de_factura_ya_registrado_no_se_repite_y_dice_donde():
    with pytest.raises(FacturaRepetida) as error:
        verificar_numero_libre(" FE-120 ", "el servicio N.º 8")
    assert str(error.value) == "La factura FE-120 ya está registrada en el servicio N.º 8"
    verificar_numero_libre("FE-121", None)


def test_el_numero_se_compara_sin_mayusculas_ni_espacios_de_los_extremos():
    assert normalizar_numero("  fe-120 ") == normalizar_numero("FE-120")


def test_el_porcentaje_se_muestra_sin_ceros_de_sobra():
    assert formato_porcentaje(D("19.00")) == "19 %"
    assert formato_porcentaje(D("10.50")) == "10,5 %"


def test_si_lleva_iva_se_aplica_el_de_la_configuracion():
    assert porcentaje_a_aplicar(True, IVA) == IVA


def test_si_no_lleva_iva_el_total_es_el_subtotal():
    porcentaje = porcentaje_a_aplicar(False, IVA)
    liquidacion = liquidar([D("180000")], porcentaje)
    assert (liquidacion.iva, liquidacion.total) == (D("0"), D("180000"))
    assert not liquidacion.lleva_iva
    assert liquidar([D("180000")], IVA).lleva_iva


def test_la_configuracion_sigue_validandose_aunque_no_lleve_iva():
    with pytest.raises(CobroInvalido):
        porcentaje_a_aplicar(False, D("101"))


def test_el_renglon_del_iva_dice_sin_iva_cuando_no_lleva():
    assert etiqueta_iva(D("19")) == "IVA 19 %"
    assert etiqueta_iva(D("0")) == "Sin IVA"
