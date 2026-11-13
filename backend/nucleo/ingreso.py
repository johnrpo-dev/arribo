"""Ingreso del conductor a la app: formato del PIN y límite de intentos fallidos por celular.

Python puro. El PIN se guarda solo con hash (lo hace `flota.Conductor` con las funciones de Django);
aquí está su formato. Los intentos se guardan en la base (`api.IntentosIngreso`) y estas funciones
deciden qué pasa con cada uno.

PIN de 6 dígitos: el conductor lo digita una vez por celular (después usa su token), así que dos
dígitos más casi no le cuestan. Con el límite de intentos, adivinar el PIN de un conductor toma en
promedio unos tres años, y unos siete meses si se prueban los 10 celulares a la vez. Con 4 dígitos
(10.000 combinaciones) serían 10 días para uno y unos 2 días para alguno de los 10.

El límite no es configuración del cliente: depende de cuánto resiste un PIN de 6 dígitos, no de la
empresa. Como mucho 5 fallos cada 15 minutos (unos 480 al día) frente a un millón de PIN posibles.
"""
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

LARGO_PIN = 6
_PIN_VALIDO = re.compile(rf"[0-9]{{{LARGO_PIN}}}")

MAXIMO_FALLOS = 5
VENTANA_FALLOS = timedelta(minutes=15)
DURACION_BLOQUEO = timedelta(minutes=15)


class PinInvalido(ValueError):
    """El PIN no tiene el formato pedido."""


def validar_pin(pin) -> None:
    """Exactamente 6 dígitos del 0 al 9 (sin espacios, letras ni dígitos de otros alfabetos)."""
    if not isinstance(pin, str) or not _PIN_VALIDO.fullmatch(pin):
        raise PinInvalido(f"El PIN tiene exactamente {LARGO_PIN} dígitos, del 0 al 9.")


@dataclass(frozen=True)
class Intentos:
    """Fallos recientes de un celular. `primer_fallo` abre la ventana de 15 minutos."""

    fallos: int = 0
    primer_fallo: datetime | None = None
    bloqueado_hasta: datetime | None = None


def bloqueado(intentos: Intentos, ahora: datetime) -> bool:
    """Mientras dura el bloqueo no se revisa el PIN: ni uno correcto entra."""
    return intentos.bloqueado_hasta is not None and ahora < intentos.bloqueado_hasta


def segundos_de_bloqueo(intentos: Intentos, ahora: datetime) -> int:
    """Segundos que faltan para poder intentar de nuevo (redondeado hacia arriba); 0 si no hay."""
    if not bloqueado(intentos, ahora):
        return 0
    return math.ceil((intentos.bloqueado_hasta - ahora).total_seconds())


def registrar_fallo(intentos: Intentos, ahora: datetime) -> Intentos:
    """Un PIN equivocado (o un celular que no es de nadie: se cuentan igual).

    Los fallos se cuentan desde el primero; pasados 15 minutos, la cuenta empieza de nuevo. El
    quinto fallo dentro de la ventana bloquea el celular 15 minutos y deja la cuenta en cero.
    """
    if bloqueado(intentos, ahora):
        # No debería pasar (con bloqueo no se revisa el PIN); en todo caso, no alarga el bloqueo.
        return intentos
    en_ventana = (
        intentos.primer_fallo is not None and ahora - intentos.primer_fallo < VENTANA_FALLOS
    )
    fallos = intentos.fallos + 1 if en_ventana else 1
    if fallos >= MAXIMO_FALLOS:
        return Intentos(bloqueado_hasta=ahora + DURACION_BLOQUEO)
    return Intentos(fallos=fallos, primer_fallo=intentos.primer_fallo if en_ventana else ahora)


def registrar_acierto() -> Intentos:
    """PIN correcto (fuera de un bloqueo): la cuenta de fallos vuelve a cero."""
    return Intentos()
