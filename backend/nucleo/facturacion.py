"""Orden de facturación (1a-19b): el total con IVA que Arribo calcula y la verificación de la
factura que hizo el facturador en su programa de facturación.

Reglas:
- El valor de cada línea es sin IVA. Al facturar se suma el IVA (porcentaje de la configuración,
  19 % por defecto) sobre el subtotal de lo que se factura junto.
- Si lleva IVA o no se pregunta en Cobros cada vez: al armar la relación y al facturar una línea
  suelta. Si no lleva, el IVA es cero y el total es el subtotal.
- El IVA se redondea al peso, la mitad hacia arriba.
- Al registrar la factura se digita su número y su total. Si el total no es exactamente el de la
  orden, no se registra: casi siempre es un error de digitación.
- Un número de factura no se registra dos veces (sin importar mayúsculas ni espacios en los
  extremos). Las líneas de una misma relación comparten el número: eso no cuenta como repetido.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from nucleo.cobro import CobroInvalido, formato_pesos

UN_PESO = Decimal(1)


class FacturaNoCuadra(CobroInvalido):
    """El total digitado no es el total de la orden."""


class FacturaRepetida(CobroInvalido):
    """Ese número de factura ya está registrado."""


@dataclass(frozen=True)
class Liquidacion:
    subtotal: Decimal
    porcentaje_iva: Decimal
    iva: Decimal
    total: Decimal

    @property
    def lleva_iva(self) -> bool:
        return self.porcentaje_iva > 0


def validar_porcentaje_iva(porcentaje: Decimal) -> None:
    if not Decimal(0) <= porcentaje <= Decimal(100):
        raise CobroInvalido("El IVA va de 0 % a 100 %")


def liquidar(valores: Iterable[Decimal], porcentaje_iva: Decimal) -> Liquidacion:
    """Subtotal, IVA y total de lo que se factura junto."""
    validar_porcentaje_iva(porcentaje_iva)
    subtotal = sum(valores, Decimal(0))
    iva = (subtotal * porcentaje_iva / 100).quantize(UN_PESO, rounding=ROUND_HALF_UP)
    return Liquidacion(subtotal, porcentaje_iva, iva, subtotal + iva)


def porcentaje_a_aplicar(lleva_iva: bool, porcentaje_configurado: Decimal) -> Decimal:
    """El IVA de lo que se factura: el de la configuración si lleva IVA; cero si no lleva."""
    validar_porcentaje_iva(porcentaje_configurado)
    return porcentaje_configurado if lleva_iva else Decimal(0)


def etiqueta_iva(porcentaje: Decimal) -> str:
    """Cómo se nombra el renglón del IVA: "IVA 19 %" o "Sin IVA"."""
    return f"IVA {formato_porcentaje(porcentaje)}" if porcentaje > 0 else "Sin IVA"


def formato_porcentaje(porcentaje: Decimal) -> str:
    """19.00 → "19 %"; 10.50 → "10,5 %"."""
    texto = format(porcentaje.normalize(), "f")
    return f"{texto.replace('.', ',')} %"


def normalizar_numero(numero: str) -> str:
    """Como se compara un número de factura para saber si está repetido."""
    return (numero or "").strip().upper()


def verificar_total(esperado: Decimal, digitado: Decimal, *, mostrar_valores: bool = True) -> None:
    """El total de la factura es el de la orden. Quien no ve valores recibe el aviso sin cifras."""
    if digitado == esperado:
        return
    if not mostrar_valores:
        raise FacturaNoCuadra("El total de la factura no coincide con el de la orden")
    diferencia = abs(digitado - esperado)
    sentido = "más" if digitado > esperado else "menos"
    raise FacturaNoCuadra(
        f"El total de la factura ({formato_pesos(digitado)}) no coincide con el de la orden "
        f"({formato_pesos(esperado)}): tiene {formato_pesos(diferencia)} de {sentido}"
    )


def verificar_numero_libre(numero: str, usado_en: str | None) -> None:
    """`usado_en` dice dónde está ya registrado ese número (o None si está libre)."""
    if usado_en:
        raise FacturaRepetida(f"La factura {numero.strip()} ya está registrada en {usado_en}")
