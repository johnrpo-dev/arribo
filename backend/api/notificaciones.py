"""Avisos push al conductor (1a-14): el token de push de cada celular, la tabla de salida
(`NotificacionPush`) y su envío.

Cómo viaja un aviso:
1. Al asignar o reasignar, `solicitudes` envía la señal `servicio_asignado` dentro de su
   transacción y `api/receptores.py` llama a `encolar_avisos_de_asignacion`: una fila por cada
   celular con sesión y token de push del conductor (y del anterior, al reasignar). Si la
   asignación se deshace, las filas también.
2. Confirmada la transacción (`transaction.on_commit`), se intenta enviar cada una. Un fallo aquí
   nunca deshace la asignación: ya está guardada, y lo que falle queda en la fila.
3. Lo que falla por algo pasajero queda pendiente con la hora del próximo intento (esperas de
   `nucleo.push`), hasta `MAXIMO_INTENTOS`. `manage.py enviar_notificaciones_pendientes` envía las
   que ya tocan (en producción, cada minuto; ver PROGRESS.md).

Cada envío bloquea su fila (`skip_locked`): el envío tras confirmar y el comando nunca mandan el
mismo aviso dos veces.
"""
import logging
from collections import Counter
from functools import partial

from django.db import transaction
from django.utils import timezone

from nucleo.estados import Estado
from nucleo.push import MAXIMO_INTENTOS, Desenlace, TipoAviso, contenido, espera_tras, sigue_vigente

from . import push
from .models import EstadoNotificacion, NotificacionPush, TokenDispositivo

registro = logging.getLogger(__name__)


# --- Token de push de cada celular -----------------------------------------------------------------


def registrar_token_push(dispositivo: TokenDispositivo, token_push: str) -> None:
    """La app registra (o cambia) el token de push de su sesión. Si ese token estaba en otra
    sesión (el mismo celular, usado antes por otro conductor que no cerró sesión con señal), se
    quita de allá: cada aviso le llega solo al conductor que lo tiene ahora."""
    with transaction.atomic():
        TokenDispositivo.objects.filter(push_token=token_push).exclude(pk=dispositivo.pk).update(
            push_token=""
        )
        TokenDispositivo.objects.filter(pk=dispositivo.pk, revocado_en__isnull=True).update(
            push_token=token_push,
            push_registrado_en=timezone.now(),
            push_desactivado_en=None,
        )


def celulares_con_push(conductor_id):
    """Las sesiones vigentes del conductor que tienen token de push."""
    return TokenDispositivo.objects.filter(
        conductor_id=conductor_id, revocado_en__isnull=True
    ).exclude(push_token="")


# --- Tabla de salida -------------------------------------------------------------------------------


def encolar_avisos_de_asignacion(servicio, conductor_anterior=None) -> list[NotificacionPush]:
    """En la transacción de la asignación: el aviso "asignado" para cada celular del conductor del
    servicio y, al reasignar, el de "retirado" para cada celular del anterior. Al confirmarse la
    transacción se intenta enviarlos. Un conductor sin celular con push no recibe nada (verá el
    servicio al abrir la app)."""
    destinos = [(TipoAviso.ASIGNADO, servicio.conductor_id)]
    if conductor_anterior is not None:
        destinos.append((TipoAviso.RETIRADO, getattr(conductor_anterior, "pk", conductor_anterior)))
    creadas = []
    ahora = timezone.now()
    for tipo, conductor_id in destinos:
        texto = contenido(tipo, servicio.pk)
        for dispositivo in celulares_con_push(conductor_id):
            creadas.append(
                NotificacionPush.objects.create(
                    dispositivo=dispositivo,
                    servicio=servicio,
                    tipo=tipo.value,
                    titulo=texto.titulo,
                    cuerpo=texto.cuerpo,
                    proximo_intento=ahora,
                )
            )
    if creadas:
        # robust: si el envío falla de una forma inesperada, se registra y no sube a la vista.
        transaction.on_commit(
            partial(enviar_tras_confirmar, [n.pk for n in creadas]), robust=True
        )
    return creadas


def enviar_tras_confirmar(ids: list[int]) -> None:
    """Primer intento de cada aviso, ya confirmada la asignación. Nada de lo que pase aquí la
    toca; lo que no se pueda enviar queda pendiente para el comando."""
    for pk in ids:
        try:
            enviar(pk)
        except Exception:  # noqa: BLE001
            registro.exception("No se pudo enviar el aviso push %s; queda pendiente.", pk)


def enviar(notificacion_id: int) -> str | None:
    """Intenta enviar una notificación pendiente y devuelve su estado al terminar (pendiente si
    queda por reintentar), o None si no estaba pendiente o la está enviando otro proceso."""
    with transaction.atomic():
        notificacion = (
            NotificacionPush.objects.select_for_update(of=("self",), skip_locked=True)
            .select_related("dispositivo", "servicio")
            .filter(pk=notificacion_id, estado=EstadoNotificacion.PENDIENTE)
            .first()
        )
        if notificacion is None:
            return None
        _intentar(notificacion, timezone.now())
        notificacion.save()
    return notificacion.estado


def enviar_pendientes(*, limite: int = 200) -> Counter:
    """Las pendientes cuyo próximo intento ya llegó, de la más atrasada a la más nueva. Devuelve
    cuántas quedaron en cada estado ("ocupada": la estaba enviando otro proceso)."""
    ids = list(
        NotificacionPush.objects.filter(
            estado=EstadoNotificacion.PENDIENTE, proximo_intento__lte=timezone.now()
        )
        .order_by("proximo_intento", "pk")
        .values_list("pk", flat=True)[:limite]
    )
    resumen = Counter()
    for pk in ids:
        resumen[enviar(pk) or "ocupada"] += 1
    return resumen


def _intentar(notificacion: NotificacionPush, ahora) -> None:
    dispositivo = notificacion.dispositivo
    servicio = notificacion.servicio
    if not dispositivo.vigente or not dispositivo.push_token:
        _fallar(notificacion, "El celular ya no tiene sesión abierta o no tiene push registrado.")
        return
    del_servicio = servicio.conductor_id
    if not sigue_vigente(
        TipoAviso(notificacion.tipo),
        conductor_del_aviso=str(dispositivo.conductor_id),
        conductor_del_servicio=None if del_servicio is None else str(del_servicio),
        estado_del_servicio=Estado(servicio.estado),
    ):
        _fallar(notificacion, "Ya no aplica: el servicio cambió de conductor o terminó antes.")
        return
    enviador = push.enviador_configurado()
    if enviador is None:
        registro.warning(
            "Aviso push %s sin enviar: falta ARRIBO_FIREBASE_CREDENCIALES en el .env del servidor "
            "(o el archivo no se pudo leer).",
            notificacion.pk,
        )
        _fallar(notificacion, "El push no está configurado en el servidor.")
        return
    try:
        envio = enviador.enviar(dispositivo.push_token, contenido(notificacion.tipo, servicio.pk))
    # Un error que el enviador no esperaba cuenta como intento: así los reintentos siguen acotados.
    except Exception as error:  # noqa: BLE001
        registro.exception("Error inesperado al enviar el aviso push %s", notificacion.pk)
        envio = push.Envio(
            Desenlace.REINTENTAR, f"Error inesperado al enviar ({type(error).__name__})."
        )
    notificacion.intentos += 1

    if envio.desenlace == Desenlace.ENVIADO:
        notificacion.estado = EstadoNotificacion.ENVIADA
        notificacion.enviada_en = ahora
        notificacion.error = ""
    elif envio.desenlace == Desenlace.TOKEN_INVALIDO:
        # Solo si el celular no registró otro token mientras tanto.
        TokenDispositivo.objects.filter(
            pk=dispositivo.pk, push_token=dispositivo.push_token
        ).update(push_token="", push_desactivado_en=ahora)
        registro.warning(
            "FCM dice que el token de push de %s ya no existe: se desactivó.", dispositivo
        )
        _fallar(notificacion, f"{envio.detalle}. El token de push del celular se desactivó.")
    elif envio.desenlace == Desenlace.FALLIDO:
        registro.error("FCM rechazó el aviso push %s: %s", notificacion.pk, envio.detalle)
        _fallar(notificacion, envio.detalle)
    else:
        espera = espera_tras(notificacion.intentos)
        if espera is None:
            registro.error(
                "El aviso push %s no se pudo enviar en %s intentos: %s",
                notificacion.pk,
                MAXIMO_INTENTOS,
                envio.detalle,
            )
            _fallar(
                notificacion,
                f"Se agotaron los {MAXIMO_INTENTOS} intentos. Último error: {envio.detalle}",
            )
        else:
            registro.warning(
                "El aviso push %s no se pudo enviar (%s); se reintenta en %s.",
                notificacion.pk,
                envio.detalle,
                espera,
            )
            notificacion.proximo_intento = ahora + espera
            notificacion.error = envio.detalle


def _fallar(notificacion: NotificacionPush, motivo: str) -> None:
    notificacion.estado = EstadoNotificacion.FALLIDA
    notificacion.error = motivo
