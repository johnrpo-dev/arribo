"""Intentos de ingreso simultáneos de verdad: varios hilos, cada uno con su conexión a PostgreSQL.

La fila de intentos del celular se bloquea en cada intento, así que los fallos se cuentan uno tras
otro y el límite no se cuela aunque lleguen todos a la vez. Pruebas transaccionales: pytest-django
las corre después de las demás.
"""
import pytest

from api import ingreso
from api.models import IntentosIngreso, TokenDispositivo

from ..solicitudes.test_concurrencia import en_paralelo
from .conftest import CELULAR_ANA, CELULAR_DE_NADIE, OTRO_PIN, PIN

pytestmark = pytest.mark.django_db(transaction=True)


def _intento(celular, pin):
    return lambda: ingreso.ingresar(celular, pin, "celular-de-ana")


@pytest.mark.parametrize("celular", [CELULAR_ANA, CELULAR_DE_NADIE])
def test_ocho_fallos_simultaneos_revisan_el_pin_solo_cinco_veces(ana_app, celular):
    salidas = en_paralelo(*[_intento(celular, OTRO_PIN) for _ in range(8)])

    tipos = sorted(type(salida).__name__ for salida in salidas)
    assert tipos == ["CredencialesInvalidas"] * 5 + ["DemasiadosIntentos"] * 3
    assert IntentosIngreso.objects.get(celular=celular).bloqueado_hasta is not None


def test_el_pin_correcto_simultaneo_con_el_quinto_fallo_no_se_cuela_tras_el_bloqueo(ana_app):
    for _ in range(4):
        with pytest.raises(ingreso.CredencialesInvalidas):
            ingreso.ingresar(CELULAR_ANA, OTRO_PIN, "celular-de-ana")

    salidas = en_paralelo(_intento(CELULAR_ANA, OTRO_PIN), _intento(CELULAR_ANA, PIN))

    # Si el quinto fallo va primero, el PIN correcto llega bloqueado; si el correcto va primero,
    # entra y el fallo cuenta como el primero de una cuenta nueva. Nunca las dos cosas.
    if isinstance(salidas[1], ingreso.DemasiadosIntentos):
        assert isinstance(salidas[0], ingreso.CredencialesInvalidas)
        assert not TokenDispositivo.objects.exists()
    else:
        token, _ = salidas[1]
        assert token.vigente
        assert isinstance(salidas[0], ingreso.CredencialesInvalidas)
        assert IntentosIngreso.objects.get(celular=CELULAR_ANA).fallos == 1
