"""Ingreso del conductor a la app, cierre de sesión y revocación de tokens.

`ingresar` recibe celular y PIN y devuelve un token para ese celular. Cada intento corre en una
transacción con la fila de intentos del celular bloqueada (`select_for_update`), así que dos intentos
simultáneos se cuentan uno tras otro y el límite no se cuela. Las reglas del PIN y del límite están en
`nucleo/ingreso.py`; aquí solo se cargan los datos, se llama al núcleo y se guarda lo que decide.

Un celular que no es de ningún conductor se trata igual que un PIN equivocado: mismo error, misma
cuenta de fallos y el mismo trabajo de hash, para que la respuesta no revele si el celular existe.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from flota.models import Conductor
from nucleo.identificacion import normalizar_telefono
from nucleo.ingreso import bloqueado, registrar_acierto, registrar_fallo, segundos_de_bloqueo
from panel.roles import CONDUCTOR

from .models import IntentosIngreso, TokenDispositivo


class CredencialesInvalidas(Exception):
    """Celular o PIN incorrectos (también si el celular no es de ningún conductor)."""


class DemasiadosIntentos(Exception):
    """El celular está bloqueado por fallos recientes; no se revisó el PIN."""

    def __init__(self, segundos: int):
        self.segundos = segundos
        super().__init__(f"Celular bloqueado {segundos} segundos más")


class ConductorNoHabilitado(Exception):
    """El PIN es correcto, pero el conductor no puede usar la app (inactivo o sin usuario)."""


def en_grupo_conductor(ruta_usuario: str) -> Exists:
    """Anotación para la consulta: el usuario de `ruta_usuario` está en el grupo conductor."""
    pertenencias = get_user_model().groups.through.objects.filter(
        user_id=OuterRef(ruta_usuario), group__name=CONDUCTOR
    )
    return Exists(pertenencias)


def habilitado(conductor, en_grupo: bool) -> bool:
    """Usa la app solo un conductor activo cuyo usuario esté activo y en el grupo conductor."""
    usuario = conductor.usuario
    return bool(conductor.activo and usuario is not None and usuario.is_active and en_grupo)


def ingresar(celular: str, pin: str, dispositivo_id: str, dispositivo_nombre: str = ""):
    """Devuelve (token, clave en claro) o lanza CredencialesInvalidas, DemasiadosIntentos o
    ConductorNoHabilitado. Un ingreso nuevo en el mismo celular revoca el token anterior de ese
    conductor en ese celular. `celular` puede venir con cualquier formato (se normaliza)."""
    celular = normalizar_telefono(celular)
    with transaction.atomic():
        fila, _ = IntentosIngreso.objects.select_for_update().get_or_create(celular=celular)
        ahora = timezone.now()
        intentos = fila.como_nucleo()
        if bloqueado(intentos, ahora):
            error = DemasiadosIntentos(segundos_de_bloqueo(intentos, ahora))
        else:
            conductor = (
                Conductor.objects.select_related("usuario")
                .annotate(en_grupo=en_grupo_conductor("usuario_id"))
                .filter(celular=celular)
                .first()
            )
            if conductor is None or not conductor.tiene_pin:
                make_password(pin)  # el mismo tiempo de respuesta que si existiera
                acierto = False
            else:
                acierto = conductor.verificar_pin(pin)

            if not acierto:
                fila.guardar(registrar_fallo(intentos, ahora))
                error = CredencialesInvalidas()
            else:
                fila.guardar(registrar_acierto())
                if not habilitado(conductor, conductor.en_grupo):
                    error = ConductorNoHabilitado()
                else:
                    revocar_tokens(
                        TokenDispositivo.objects.filter(
                            conductor=conductor, dispositivo_id=dispositivo_id
                        )
                    )
                    return TokenDispositivo.emitir(conductor, dispositivo_id, dispositivo_nombre)
    # Fuera de la transacción: el fallo ya quedó guardado aunque se responda con error.
    raise error


def revocar_tokens(tokens) -> int:
    """Revoca los tokens vigentes de la consulta (los ya revocados no cambian); devuelve cuántos."""
    return tokens.filter(revocado_en__isnull=True).update(revocado_en=timezone.now())


def cerrar_sesion(token: TokenDispositivo) -> None:
    """La app cierra su sesión: su token deja de servir."""
    revocar_tokens(TokenDispositivo.objects.filter(pk=token.pk))
