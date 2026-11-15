"""Sesiones de la app del conductor: un token por celular, los intentos fallidos de ingreso y la
tabla de salida de los avisos push.

Del token solo se guarda su hash (SHA-256): quien lea la base no puede usarlo. Un token se revoca
(no se borra) desde el admin o al cerrar sesión en la app. Los intentos fallidos se guardan aquí, en
la base, y no en una caché en memoria: el límite se cumple aunque se reinicie el servidor o haya más
de un proceso atendiendo.
"""
import hashlib
import secrets

from django.db import models
from django.db.models import Q
from django.utils import timezone

from nucleo.ingreso import Intentos
from nucleo.push import TipoAviso

# 32 bytes aleatorios (256 bits): imposible de adivinar, por eso basta un hash rápido para buscarlo.
BYTES_DEL_TOKEN = 32
# Un token de FCM mide unos 160 caracteres; el tope deja margen sin pasarse del índice único.
LARGO_MAXIMO_TOKEN_PUSH = 1000


def hash_del_token(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()


class TokenDispositivo(models.Model):
    """La sesión de un conductor en un celular. Hay como máximo un token vigente por celular."""

    conductor = models.ForeignKey(
        "flota.Conductor",
        verbose_name="conductor",
        on_delete=models.PROTECT,
        related_name="tokens",
    )
    clave_hash = models.CharField("hash del token", max_length=64, unique=True, editable=False)
    dispositivo_id = models.CharField(
        "identificador del celular",
        max_length=100,
        help_text="Lo genera la app al instalarse; identifica el celular, no al conductor.",
    )
    dispositivo_nombre = models.CharField("nombre del celular", max_length=100, blank=True)
    creado_en = models.DateTimeField("creado", auto_now_add=True)
    ultimo_uso = models.DateTimeField("último uso", null=True, blank=True)
    revocado_en = models.DateTimeField(
        "revocado", null=True, blank=True, help_text="Vacío = vigente."
    )
    # Push (1a-14): el token que Firebase le dio a la app en este celular. Lo registra la app con
    # PUT /api/v1/push/; se borra al revocar la sesión o cuando FCM dice que ya no existe.
    push_token = models.CharField(
        "token de push",
        max_length=LARGO_MAXIMO_TOKEN_PUSH,
        blank=True,
        editable=False,
        help_text="Vacío = este celular no recibe avisos push.",
    )
    push_registrado_en = models.DateTimeField("push registrado", null=True, blank=True)
    push_desactivado_en = models.DateTimeField(
        "push desactivado",
        null=True,
        blank=True,
        help_text="Cuándo Firebase dijo que el token de push ya no existe (por ejemplo, la app se "
        "desinstaló). Se vacía cuando la app registra uno nuevo.",
    )

    class Meta:
        verbose_name = "token de celular"
        verbose_name_plural = "tokens de celular"
        ordering = ("-creado_en",)
        constraints = (
            # Un token de push llega a un solo celular: si estuviera en dos sesiones, un aviso de
            # un conductor le sonaría a otro (el mismo celular usado antes por otro conductor).
            models.UniqueConstraint(
                fields=("push_token",),
                condition=~Q(push_token=""),
                name="token_push_unico",
                violation_error_message="Ese token de push ya está registrado en otra sesión.",
            ),
            models.CheckConstraint(
                condition=Q(revocado_en__isnull=True) | Q(push_token=""),
                name="token_revocado_sin_push",
                violation_error_message="Una sesión revocada no recibe avisos push.",
            ),
            models.UniqueConstraint(
                fields=("conductor", "dispositivo_id"),
                condition=Q(revocado_en__isnull=True),
                name="token_uno_vigente_por_dispositivo",
                violation_error_message="El conductor ya tiene una sesión abierta en ese celular.",
            ),
            # El token en claro (43 caracteres en base64) nunca tiene esta forma.
            models.CheckConstraint(
                condition=Q(clave_hash__regex=r"^[0-9a-f]{64}$"),
                name="token_solo_hash",
                violation_error_message="Del token se guarda solo su hash SHA-256.",
            ),
            models.CheckConstraint(
                condition=~Q(dispositivo_id=""),
                name="token_con_dispositivo",
                violation_error_message="Falta el identificador del celular.",
            ),
        )

    def __str__(self):
        celular = self.dispositivo_nombre or self.dispositivo_id
        return f"{self.conductor} en {celular}"

    @property
    def vigente(self) -> bool:
        return self.revocado_en is None

    @classmethod
    def emitir(cls, conductor, dispositivo_id: str, dispositivo_nombre: str = ""):
        """Crea el token y devuelve (token, clave). La clave en claro solo existe en esta respuesta."""
        clave = secrets.token_urlsafe(BYTES_DEL_TOKEN)
        token = cls.objects.create(
            conductor=conductor,
            clave_hash=hash_del_token(clave),
            dispositivo_id=dispositivo_id,
            dispositivo_nombre=dispositivo_nombre,
        )
        return token, clave


class IntentosIngreso(models.Model):
    """Fallos recientes de ingreso de un celular, sea o no de un conductor (así la respuesta no
    revela si existe). Las reglas están en `nucleo/ingreso.py`."""

    celular = models.CharField("celular", max_length=20, unique=True)
    fallos = models.PositiveSmallIntegerField("fallos en la ventana", default=0)
    primer_fallo = models.DateTimeField("primer fallo de la ventana", null=True, blank=True)
    bloqueado_hasta = models.DateTimeField("bloqueado hasta", null=True, blank=True)

    class Meta:
        verbose_name = "intentos de ingreso"
        verbose_name_plural = "intentos de ingreso"
        ordering = ("celular",)
        constraints = (
            models.CheckConstraint(
                condition=Q(celular__regex=r"^[0-9]+$"),
                name="intentos_celular_solo_digitos",
                violation_error_message="El celular va solo con dígitos.",
            ),
        )

    def __str__(self):
        return self.celular

    def como_nucleo(self) -> Intentos:
        return Intentos(
            fallos=self.fallos,
            primer_fallo=self.primer_fallo,
            bloqueado_hasta=self.bloqueado_hasta,
        )

    def guardar(self, intentos: Intentos) -> None:
        self.fallos = intentos.fallos
        self.primer_fallo = intentos.primer_fallo
        self.bloqueado_hasta = intentos.bloqueado_hasta
        self.save(update_fields=["fallos", "primer_fallo", "bloqueado_hasta"])


OPCIONES_TIPO_AVISO = [
    (TipoAviso.ASIGNADO.value, "Servicio asignado"),
    (TipoAviso.RETIRADO.value, "Servicio retirado (reasignado a otro conductor)"),
]


class EstadoNotificacion(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    ENVIADA = "enviada", "Enviada"
    FALLIDA = "fallida", "Fallida"


class NotificacionPush(models.Model):
    """Tabla de salida de los avisos push (1a-14): un aviso para un celular.

    Se crea en la misma transacción que la asignación (si la asignación se deshace, el aviso
    también) y se envía después de confirmada, con reintentos acotados (`nucleo/push.py`). Las
    que quedan pendientes las reenvía `manage.py enviar_notificaciones_pendientes`. No se borra.
    """

    dispositivo = models.ForeignKey(
        TokenDispositivo,
        verbose_name="celular",
        on_delete=models.PROTECT,
        related_name="notificaciones",
    )
    servicio = models.ForeignKey(
        "solicitudes.Servicio",
        verbose_name="servicio",
        on_delete=models.PROTECT,
        related_name="notificaciones_push",
    )
    tipo = models.CharField("tipo", max_length=10, choices=OPCIONES_TIPO_AVISO)
    titulo = models.CharField("título", max_length=100)
    cuerpo = models.CharField("texto", max_length=300)
    estado = models.CharField(
        "estado",
        max_length=10,
        choices=EstadoNotificacion.choices,
        default=EstadoNotificacion.PENDIENTE,
    )
    intentos = models.PositiveSmallIntegerField("intentos", default=0)
    proximo_intento = models.DateTimeField(
        "próximo intento", default=timezone.now, help_text="Solo cuenta mientras está pendiente."
    )
    creada_en = models.DateTimeField("creada", auto_now_add=True)
    enviada_en = models.DateTimeField("enviada", null=True, blank=True)
    error = models.TextField(
        "último error", blank=True, help_text="Por qué falló el último intento, si falló."
    )

    class Meta:
        verbose_name = "notificación push"
        verbose_name_plural = "notificaciones push"
        ordering = ("-creada_en", "-pk")
        indexes = (models.Index(fields=("estado", "proximo_intento"), name="push_pendientes"),)
        constraints = (
            models.CheckConstraint(
                condition=Q(estado__in=EstadoNotificacion.values),
                name="push_estado_valido",
                violation_error_message="Estado de notificación desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(tipo__in=[t.value for t in TipoAviso]),
                name="push_tipo_valido",
                violation_error_message="Tipo de aviso desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(estado=EstadoNotificacion.ENVIADA, enviada_en__isnull=False)
                | (~Q(estado=EstadoNotificacion.ENVIADA) & Q(enviada_en__isnull=True)),
                name="push_enviada_con_hora",
                violation_error_message="Una notificación enviada guarda cuándo se envió (y solo "
                "ella).",
            ),
        )

    def __str__(self):
        return f"{self.titulo} · servicio {self.servicio_id} · {self.dispositivo}"
