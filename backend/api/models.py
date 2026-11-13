"""Sesiones de la app del conductor: un token por celular y los intentos fallidos de ingreso.

Del token solo se guarda su hash (SHA-256): quien lea la base no puede usarlo. Un token se revoca
(no se borra) desde el admin o al cerrar sesión en la app. Los intentos fallidos se guardan aquí, en
la base, y no en una caché en memoria: el límite se cumple aunque se reinicie el servidor o haya más
de un proceso atendiendo.
"""
import hashlib
import secrets

from django.db import models
from django.db.models import Q

from nucleo.ingreso import Intentos

# 32 bytes aleatorios (256 bits): imposible de adivinar, por eso basta un hash rápido para buscarlo.
BYTES_DEL_TOKEN = 32


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

    class Meta:
        verbose_name = "token de celular"
        verbose_name_plural = "tokens de celular"
        ordering = ("-creado_en",)
        constraints = (
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
