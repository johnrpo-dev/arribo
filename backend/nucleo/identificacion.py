"""Normalización de placas y teléfonos: la misma placa o el mismo número se escriben de muchas formas.

Se normaliza antes de guardar y antes de buscar, para que "abc-123" encuentre "ABC123" y
"+57 300 123 4567" encuentre "3001234567". Python puro: lo usan los modelos y, más adelante, la app.
"""
import re

INDICATIVO_COLOMBIA = "57"
MIN_DIGITOS_TELEFONO = 7
MAX_DIGITOS_TELEFONO = 15

_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]")
_NO_DIGITO = re.compile(r"[^0-9]")


class TelefonoInvalido(ValueError):
    """El texto no se puede leer como un teléfono."""


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
