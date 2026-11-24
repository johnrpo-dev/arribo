"""Normalización de placas, VIN y teléfonos, y la regla de identificación del vehículo.

La misma placa o el mismo número se escriben de muchas formas. Se normaliza antes de guardar y
antes de buscar, para que "abc-123" encuentre "ABC123" y "+57 300 123 4567" encuentre "3001234567".
Python puro: lo usan los modelos y la app del conductor (su copia en Dart cumple los casos de
docs/casos-reglas.json).

Número de bodega (pedido del dueño, 24/11/2026): un vehículo también se identifica por el número
que tiene en la bodega (de un concesionario, por ejemplo). Cuenta igual que la placa o el VIN para
tenerlo identificado; un desvare sigue exigiendo la placa. No es único: cada bodega numera a su
manera. Lo escribe la oficina; en la app el conductor lo ve, pero al recoger solo digita placa o VIN.

Placa o VIN digitados al recoger (1a-13b): si el vehículo llega sin identificación, el conductor
la digita en la app y viaja en el evento de Recogido. `validar_identificacion_al_recoger` cuenta
lo digitado; `completar_identificacion` dice qué se guarda en el vehículo y qué revisa logística.
"""
import re
from dataclasses import dataclass
from enum import StrEnum

from nucleo.tipos import TipoServicio

INDICATIVO_COLOMBIA = "57"
MIN_DIGITOS_TELEFONO = 7
MAX_DIGITOS_TELEFONO = 15

# Lo que cabe en la placa del vehículo (`solicitudes.Vehiculo.placa`), ya normalizada.
LARGO_MAXIMO_PLACA = 10

LARGO_VIN = 17
# Letras y dígitos sin I, O ni Q (se confunden con 1 y 0). No se valida el dígito verificador.
CARACTERES_VIN = "A-HJ-NPR-Z0-9"
# Para la restricción de la base (PostgreSQL); en Python se usa fullmatch con el mismo conjunto.
PATRON_VIN = rf"^[{CARACTERES_VIN}]{{{LARGO_VIN}}}$"

_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]")
_NO_DIGITO = re.compile(r"[^0-9]")
_SEPARADORES_VIN = re.compile(r"[\s-]")
_VIN_VALIDO = re.compile(rf"[{CARACTERES_VIN}]{{{LARGO_VIN}}}")
_PLACA_VALIDA = re.compile(rf"[A-Z0-9]{{1,{LARGO_MAXIMO_PLACA}}}")

LARGO_MAXIMO_NUMERO_BODEGA = 20
# Para la restricción de la base: mayúsculas, dígitos y guiones, sin espacios.
PATRON_NUMERO_BODEGA = rf"^[A-Z0-9-]{{1,{LARGO_MAXIMO_NUMERO_BODEGA}}}$"
_NUMERO_BODEGA_VALIDO = re.compile(rf"[A-Z0-9-]{{1,{LARGO_MAXIMO_NUMERO_BODEGA}}}")
_ESPACIOS = re.compile(r"\s")


class TelefonoInvalido(ValueError):
    """El texto no se puede leer como un teléfono."""


class PlacaInvalida(ValueError):
    """La placa no tiene de 1 a 10 letras o dígitos."""


class VinInvalido(ValueError):
    """El VIN no tiene 17 caracteres válidos."""


class NumeroBodegaInvalido(ValueError):
    """El número de bodega no tiene de 1 a 20 letras, dígitos o guiones."""


class IdentificacionIncompleta(ValueError):
    """Al vehículo le falta la placa, el VIN o el número de bodega que el servicio exige."""


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


def validar_placa(placa: str) -> None:
    """Una placa ya normalizada: de 1 a 10 letras o dígitos (lo que cabe en el vehículo)."""
    if not _PLACA_VALIDA.fullmatch(placa or ""):
        raise PlacaInvalida(
            f"La placa debe tener de 1 a {LARGO_MAXIMO_PLACA} letras o dígitos; "
            f"se leyó {placa!r} ({len(placa or '')} caracteres)."
        )


def normalizar_numero_bodega(texto: str | None) -> str:
    """Mayúsculas y sin espacios: " b-12 " da "B-12". Otros símbolos se dejan: los rechaza
    validar_numero_bodega."""
    return _ESPACIOS.sub("", (texto or "").upper())


def validar_numero_bodega(numero: str) -> None:
    """Un número de bodega ya normalizado: de 1 a 20 letras, dígitos o guiones."""
    if not _NUMERO_BODEGA_VALIDO.fullmatch(numero or ""):
        raise NumeroBodegaInvalido(
            f"El número de bodega debe tener de 1 a {LARGO_MAXIMO_NUMERO_BODEGA} letras, dígitos "
            f"o guiones; se leyó {numero!r}."
        )


def validar_identificacion(
    placa: str | None,
    vin: str | None,
    tipo_servicio: TipoServicio | str,
    numero_bodega: str | None = None,
) -> None:
    """El vehículo tiene placa, VIN o número de bodega (al menos uno); un desvare exige la placa.

    Solo revisa que estén; el formato lo revisan validar_vin y validar_numero_bodega.
    """
    tiene_placa = bool(normalizar_placa(placa))
    if TipoServicio(tipo_servicio) == TipoServicio.DESVARE and not tiene_placa:
        raise IdentificacionIncompleta("Un desvare exige la placa del vehículo.")
    if not tiene_placa and not normalizar_vin(vin) and not normalizar_numero_bodega(numero_bodega):
        raise IdentificacionIncompleta(
            "El vehículo necesita placa, VIN o número de bodega (al menos uno)."
        )


# --- Placa o VIN digitados al recoger ------------------------------------------------------------


def validar_identificacion_al_recoger(
    placa_guardada: str | None,
    vin_guardado: str | None,
    placa_digitada: str | None,
    vin_digitado: str | None,
    tipo_servicio: TipoServicio | str,
    numero_bodega: str | None = None,
) -> None:
    """Un Recogido que llega de la app: `validar_identificacion` con lo que el vehículo tiene
    (placa, VIN y número de bodega) y, donde le falte, la placa o el VIN que el conductor digitó.

    Lo digitado cuenta aunque no se pueda guardar en el vehículo (mal formado, o de otro vehículo):
    el conductor lo leyó del vehículo que montó, queda en el evento y logística lo revisa. Solo
    revisa que esté, como `validar_identificacion`. Lanza IdentificacionIncompleta.
    """
    validar_identificacion(
        normalizar_placa(placa_guardada) or normalizar_placa(placa_digitada),
        normalizar_vin(vin_guardado) or normalizar_vin(vin_digitado),
        tipo_servicio,
        numero_bodega,
    )


class CampoIdentificacion(StrEnum):
    PLACA = "placa"
    VIN = "vin"


class Revision(StrEnum):
    """Por qué un dato digitado al recoger no quedó en el vehículo. Logística lo revisa."""

    # El vehículo ya tenía otro: no se sobreescribe.
    DISTINTO = "distinto"
    # No cumple el formato (`validar_placa`, `validar_vin`).
    INVALIDO = "invalido"
    # Otro vehículo ya lo tiene (placa y VIN son únicos). Lo detecta la base, no esta función.
    DE_OTRO_VEHICULO = "de_otro_vehiculo"


@dataclass(frozen=True)
class DatoPorRevisar:
    campo: CampoIdentificacion
    digitado: str  # normalizado
    revision: Revision
    # Lo que impidió guardarlo: el dato que ya tenía el vehículo (DISTINTO) o el vehículo que ya
    # tiene ese dato (DE_OTRO_VEHICULO). Vacío en INVALIDO.
    existente: str = ""


@dataclass(frozen=True)
class Complemento:
    """Lo que la placa y el VIN digitados al recoger hacen con la identificación del vehículo."""

    placa: str  # la placa que queda en el vehículo (normalizada; vacía si no tiene)
    vin: str
    nuevos: tuple[CampoIdentificacion, ...]  # los datos que se completan con lo digitado
    por_revisar: tuple[DatoPorRevisar, ...]


def _es_valido(validar, dato: str) -> bool:
    try:
        validar(dato)
    except ValueError:
        return False
    return True


def completar_identificacion(
    placa_guardada: str | None,
    vin_guardado: str | None,
    placa_digitada: str | None,
    vin_digitado: str | None,
) -> Complemento:
    """La placa y el VIN que el conductor digitó al recoger, comparados con los del vehículo.

    Por cada dato digitado (normalizado; vacío = no digitado):
    - Si el vehículo no lo tiene y es válido, se completa con él (`nuevos`).
    - Si es igual al que tiene, no pasa nada.
    - Si el vehículo ya tiene otro, no se sobreescribe: queda por revisar (DISTINTO).
    - Si no es válido, no se guarda: queda por revisar (INVALIDO).
    Que otro vehículo ya tenga ese dato lo sabe la base: quien guarda agrega DE_OTRO_VEHICULO.
    """
    placa, vin = normalizar_placa(placa_guardada), normalizar_vin(vin_guardado)
    quedan = {CampoIdentificacion.PLACA: placa, CampoIdentificacion.VIN: vin}
    nuevos, por_revisar = [], []
    for campo, guardado, digitado, validar in (
        (CampoIdentificacion.PLACA, placa, normalizar_placa(placa_digitada), validar_placa),
        (CampoIdentificacion.VIN, vin, normalizar_vin(vin_digitado), validar_vin),
    ):
        if not digitado or digitado == guardado:
            continue
        if not _es_valido(validar, digitado):
            por_revisar.append(DatoPorRevisar(campo, digitado, Revision.INVALIDO))
        elif guardado:
            por_revisar.append(DatoPorRevisar(campo, digitado, Revision.DISTINTO, guardado))
        else:
            quedan[campo] = digitado
            nuevos.append(campo)
    return Complemento(
        placa=quedan[CampoIdentificacion.PLACA],
        vin=quedan[CampoIdentificacion.VIN],
        nuevos=tuple(nuevos),
        por_revisar=tuple(por_revisar),
    )


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
