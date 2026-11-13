"""Normalización de placas, VIN y teléfonos, y la regla de identificación del vehículo.

La misma placa o el mismo número se escriben de muchas formas. Se normaliza antes de guardar y
antes de buscar, para que "abc-123" encuentre "ABC123" y "+57 300 123 4567" encuentre "3001234567".
Python puro: lo usan los modelos y, más adelante, la app.
"""
import re
from enum import StrEnum

from nucleo.tipos import TipoServicio

INDICATIVO_COLOMBIA = "57"
MIN_DIGITOS_TELEFONO = 7
MAX_DIGITOS_TELEFONO = 15

LARGO_VIN = 17
# Letras y dígitos sin I, O ni Q (se confunden con 1 y 0). No se valida el dígito verificador.
CARACTERES_VIN = "A-HJ-NPR-Z0-9"
# Para la restricción de la base (PostgreSQL); en Python se usa fullmatch con el mismo conjunto.
PATRON_VIN = rf"^[{CARACTERES_VIN}]{{{LARGO_VIN}}}$"

_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]")
_NO_DIGITO = re.compile(r"[^0-9]")
_SEPARADORES_VIN = re.compile(r"[\s-]")
_VIN_VALIDO = re.compile(rf"[{CARACTERES_VIN}]{{{LARGO_VIN}}}")


class TelefonoInvalido(ValueError):
    """El texto no se puede leer como un teléfono."""


class VinInvalido(ValueError):
    """El VIN no tiene 17 caracteres válidos."""


class IdentificacionIncompleta(ValueError):
    """Al vehículo le falta la placa o el VIN que el servicio exige."""


def normalizar_placa(texto: str | None) -> str:
    """Mayúsculas y solo letras y dígitos: "abc-123", "ABC 123" y "abc123" dan "ABC123"."""
    return _NO_ALFANUMERICO.sub("", (texto or "").upper())


def normalizar_telefono(texto: str | None) -> str:
    """Solo dígitos y sin el indicativo 57: "+57 300 123 4567" y "300-123-4567" dan "3001234567".

    El 57 se quita solo cuando quedan 12 dígitos (57 + un número de 10), para no recortar un
    número que simplemente empieza por 57.
    """
    digitos = _NO_DIGITO.sub("", texto or "")
    if len(digitos) == 12 and digitos.startswith(INDICATIVO_COLOMBIA):
        digitos = digitos[len(INDICATIVO_COLOMBIA):]
    if not MIN_DIGITOS_TELEFONO <= len(digitos) <= MAX_DIGITOS_TELEFONO:
        raise TelefonoInvalido(
            f"El teléfono debe tener entre {MIN_DIGITOS_TELEFONO} y {MAX_DIGITOS_TELEFONO} "
            f"dígitos; se leyeron {len(digitos)} en {texto!r}."
        )
    return digitos


def normalizar_vin(texto: str | None) -> str:
    """Mayúsculas, sin espacios ni guiones: "1hg-cm826 33a004352" da "1HGCM82633A004352".

    Otros símbolos se dejan: validar_vin los rechaza en vez de esconder un error al digitar.
    """
    return _SEPARADORES_VIN.sub("", (texto or "").upper())


def validar_vin(vin: str) -> None:
    """Un VIN ya normalizado: exactamente 17 letras o dígitos, sin I, O ni Q.

    No se valida el dígito verificador (muchos VIN reales no lo cumplen).
    """
    if not _VIN_VALIDO.fullmatch(vin or ""):
        raise VinInvalido(
            f"El VIN debe tener exactamente {LARGO_VIN} letras o dígitos, sin I, O ni Q; "
            f"se leyó {vin!r} ({len(vin or '')} caracteres)."
        )


def validar_identificacion(
    placa: str | None, vin: str | None, tipo_servicio: TipoServicio | str
) -> None:
    """El vehículo tiene placa o VIN (al menos uno); un desvare exige la placa.

    Solo revisa que estén; el formato del VIN lo revisa validar_vin.
    """
    tiene_placa = bool(normalizar_placa(placa))
    if TipoServicio(tipo_servicio) == TipoServicio.DESVARE and not tiene_placa:
        raise IdentificacionIncompleta("Un desvare exige la placa del vehículo.")
    if not tiene_placa and not normalizar_vin(vin):
        raise IdentificacionIncompleta("El vehículo necesita placa o VIN (al menos uno).")


class MomentoIdentificacion(StrEnum):
    """Momentos en que se puede exigir la placa o el VIN, en el orden en que ocurren.

    Los valores son los que guarda la configuración (`configuracion.MomentoPlacaVin`).
    """

    AL_ASIGNAR = "asignar"
    AL_RECOGER = "recoger"


_ORDEN_MOMENTOS = (MomentoIdentificacion.AL_ASIGNAR, MomentoIdentificacion.AL_RECOGER)


def identificacion_exigida(
    momento_configurado: MomentoIdentificacion | str, momento_actual: MomentoIdentificacion | str
) -> bool:
    """¿Se exige la placa o el VIN en `momento_actual`?

    Desde el momento configurado en adelante: configurado "al asignar", se exige al asignar y al
    recoger; configurado "al recoger", solo al recoger. Al recoger se exige siempre.
    """
    configurado = _ORDEN_MOMENTOS.index(MomentoIdentificacion(momento_configurado))
    return _ORDEN_MOMENTOS.index(MomentoIdentificacion(momento_actual)) >= configurado
