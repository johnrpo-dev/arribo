"""Alertas para logística: algo que una persona debe revisar.

Lo mínimo para la sincronización (tarea 1a-10): el modelo y `alertas/operaciones.py`. El comando
que evalúa las alertas por umbral y el tablero son de la tarea 1a-18.

Una alerta apunta a un registro cualquiera (un evento de estado, un conductor, más adelante un
servicio o un documento) y está abierta hasta que alguien la resuelve. No se borra. Mientras siga
abierta no se abre otra del mismo tipo para el mismo registro: lo garantiza la base.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q


class TipoAlerta(models.TextChoices):
    CONFLICTO_SINCRONIZACION = "conflicto_sincronizacion", "Conflicto de sincronización"
    CAPACIDAD_EXCEDIDA = "capacidad_excedida", "Capacidad de la grúa excedida"
    EVENTO_RECHAZADO = "evento_rechazado", "Evento de la app que no se pudo guardar"


class Alerta(models.Model):
    Tipo = TipoAlerta

    tipo = models.CharField("tipo", max_length=40, choices=TipoAlerta.choices)
    tipo_registro = models.ForeignKey(
        ContentType, verbose_name="tipo de registro", on_delete=models.PROTECT, related_name="+"
    )
    # Texto: la llave del registro puede ser un número (servicio, conductor) o un UUID (evento).
    registro_id = models.CharField("id del registro", max_length=64)
    registro = GenericForeignKey("tipo_registro", "registro_id")
    mensaje = models.TextField("mensaje")
    creada_en = models.DateTimeField("creada", auto_now_add=True)
    resuelta_en = models.DateTimeField(
        "resuelta", null=True, blank=True, help_text="Vacío = abierta."
    )
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="resuelta por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alertas_resueltas",
    )

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ("-creada_en", "-pk")
        constraints = (
            models.CheckConstraint(
                condition=Q(tipo__in=TipoAlerta.values),
                name="alerta_tipo_valido",
                violation_error_message="Tipo de alerta desconocido.",
            ),
            models.UniqueConstraint(
                fields=("tipo", "tipo_registro", "registro_id"),
                condition=Q(resuelta_en__isnull=True),
                name="alerta_una_abierta_por_registro",
                violation_error_message="Ya hay una alerta abierta de ese tipo para ese registro.",
            ),
            models.CheckConstraint(
                condition=~Q(mensaje__regex=r"^\s*$") & ~Q(registro_id=""),
                name="alerta_con_mensaje_y_registro",
                violation_error_message="La alerta lleva mensaje y el registro al que apunta.",
            ),
            models.CheckConstraint(
                condition=Q(resuelta_por__isnull=True) | Q(resuelta_en__isnull=False),
                name="alerta_resuelta_por_solo_si_resuelta",
                violation_error_message="Solo una alerta resuelta guarda quién la resolvió.",
            ),
        )

    def __str__(self):
        return f"{TipoAlerta(self.tipo).label} · {self.registro_id}"

    @property
    def abierta(self) -> bool:
        return self.resuelta_en is None
