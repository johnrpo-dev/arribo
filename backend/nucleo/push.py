"""Avisos push al conductor (tarea 1a-14): qué lleva cada aviso, cuándo sigue valiendo y qué hacer
con la respuesta de Firebase Cloud Messaging (FCM).

Reglas:
- Al asignar un servicio, su conductor recibe un aviso. Al reasignarlo, el nuevo conductor recibe
  el de "asignado" y el anterior uno de "retirado": puede ir ya en camino a buscarlo.
- El aviso lleva lo mínimo: el número del servicio y un texto fijo. Nada de cobro (valor, tarifa,
  pagador, factura) ni datos personales (nombres, teléfonos, direcciones): el detalle lo baja la
  app con su sesión, como siempre. Un aviso queda a la vista en la pantalla bloqueada del celular.
- Un aviso que falló se reintenta un número acotado de veces, con esperas que crecen. Un aviso
  que ya no es cierto cuando toca enviarlo (el servicio cambió de conductor o terminó) no se envía.
- Un token que FCM reporta como no registrado (la app se desinstaló o borró su token) no se vuelve
  a usar.
"""
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from nucleo.estados import TERMINALES, Estado


class TipoAviso(StrEnum):
    ASIGNADO = "asignado"
    RETIRADO = "retirado"


@dataclass(frozen=True)
class Contenido:
    """Lo que ve el conductor (título y texto) y lo que lee la app (`datos`, solo textos: FCM no
    admite otros tipos en los datos)."""

    titulo: str
    cuerpo: str
    datos: dict[str, str]


def contenido(tipo: TipoAviso, servicio_id: int | str) -> Contenido:
    tipo = TipoAviso(tipo)
    datos = {"tipo": tipo.value, "servicio_id": str(servicio_id)}
    if tipo == TipoAviso.ASIGNADO:
        return Contenido(
            titulo="Nuevo servicio asignado",
            cuerpo=f"Servicio N.º {servicio_id}. Abra Arribo para ver el detalle.",
            datos=datos,
        )
    return Contenido(
        titulo="Servicio reasignado",
        cuerpo=(
            f"El servicio N.º {servicio_id} ya no está a su cargo. Abra Arribo para actualizar "
            "su lista."
        ),
        datos=datos,
    )


def sigue_vigente(
    tipo: TipoAviso,
    *,
    conductor_del_aviso: str,
    conductor_del_servicio: str | None,
    estado_del_servicio: Estado,
) -> bool:
    """¿Lo que dice el aviso sigue siendo cierto? "Asignado": el servicio sigue siendo de ese
    conductor y no ha terminado. "Retirado": el servicio ya no es suyo (si se lo devolvieron, el
    aviso diría algo falso)."""
    suyo = conductor_del_servicio is not None and conductor_del_servicio == conductor_del_aviso
    if TipoAviso(tipo) == TipoAviso.ASIGNADO:
        return suyo and Estado(estado_del_servicio) not in TERMINALES
    return not suyo


class Desenlace(StrEnum):
    """Qué hacer con un aviso después de intentar enviarlo."""

    ENVIADO = "enviado"
    # Falla pasajera (sin red, FCM caído o saturado, credencial que no se pudo renovar): se
    # reintenta más tarde, hasta el máximo de intentos.
    REINTENTAR = "reintentar"
    # FCM dice que el token ya no existe: el aviso no se envía y el token no se vuelve a usar.
    TOKEN_INVALIDO = "token_invalido"
    # FCM rechazó el mensaje (por ejemplo, datos mal formados): reintentarlo daría lo mismo.
    FALLIDO = "fallido"


# Códigos de error de la API HTTP v1 de FCM (`error.details[].errorCode`) que significan que el
# token no sirve para este proyecto y no va a servir nunca.
TOKEN_NO_SIRVE = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})
# Respuestas HTTP que son fallas pasajeras: autenticación (token de acceso vencido o revocado),
# exceso de mensajes y fallas del servidor de FCM.
HTTP_PASAJERO = frozenset({401, 403, 408, 429})


def clasificar(estado_http: int | None, codigo_error: str | None = None) -> Desenlace:
    """`estado_http` None = no hubo respuesta (sin red, tiempo agotado)."""
    if estado_http is None:
        return Desenlace.REINTENTAR
    if 200 <= estado_http < 300:
        return Desenlace.ENVIADO
    # Solo con el código de FCM: un 404 sin él puede ser, por ejemplo, un proyecto mal escrito, y
    # no es motivo para dejar de usar el token.
    if codigo_error in TOKEN_NO_SIRVE:
        return Desenlace.TOKEN_INVALIDO
    if estado_http in HTTP_PASAJERO or estado_http >= 500:
        return Desenlace.REINTENTAR
    return Desenlace.FALLIDO


# Intentos en total (el primero más cuatro reintentos) y la espera antes de cada reintento. En
# total, un aviso deja de intentarse menos de una hora después de la asignación: más tarde ya no
# avisa nada útil (el conductor ve el servicio al abrir la app).
MAXIMO_INTENTOS = 5
ESPERAS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)


def espera_tras(intentos: int) -> timedelta | None:
    """Cuánto esperar después de `intentos` intentos fallidos, o None si ya no se reintenta."""
    if intentos < 1:
        raise ValueError("Se espera solo después de un intento.")
    if intentos >= MAXIMO_INTENTOS:
        return None
    return ESPERAS[min(intentos, len(ESPERAS)) - 1]
