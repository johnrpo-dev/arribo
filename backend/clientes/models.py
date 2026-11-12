"""Clientes: quién pide y quién paga, sus teléfonos, las personas en origen o destino y sus tarifas.

Nada se borra: un cliente se desactiva y una tarifa deja de estar vigente. Las reglas viven en la
base de datos (restricciones); `clean()` las repite solo para que el admin muestre un mensaje en
español en vez de un error de base. Los teléfonos se guardan normalizados con
`nucleo/identificacion.py`, así que se encuentran aunque se digiten con espacios, guiones o +57.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from nucleo.identificacion import TelefonoInvalido, normalizar_telefono
from nucleo.tipos import TipoServicio

SOLO_DIGITOS = r"^[0-9]+$"
# Se guardan como mucho 15 dígitos, pero el campo admite el texto tal como se digita
# ("+57 300 123 4567") para que el admin lo normalice en vez de rechazarlo por largo.
LARGO_TELEFONO_DIGITADO = 30


def _normalizar_campo_telefono(instancia, campo):
    """Para clean(): normaliza el campo o deja el error atado a él, en español."""
    try:
        setattr(instancia, campo, normalizar_telefono(getattr(instancia, campo)))
    except TelefonoInvalido as error:
        raise ValidationError({campo: str(error)}) from error


class TipoCliente(models.TextChoices):
    PARTICULAR = "particular", "Particular"
    CONCESIONARIO = "concesionario", "Concesionario"
    ASEGURADORA = "aseguradora", "Aseguradora o empresa de asistencia"


class ModalidadCobro(models.TextChoices):
    POR_SERVICIO = "por_servicio", "Por servicio"
    POR_CORTE = "por_corte", "Por corte"


class Cliente(models.Model):
    """Un mismo cliente puede ser quien pide el servicio y quien lo paga."""

    Tipo = TipoCliente
    ModalidadCobro = ModalidadCobro

    nombre = models.CharField("nombre", max_length=200)
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices)
    documento = models.CharField("documento o NIT", max_length=30, blank=True)
    modalidad_cobro = models.CharField(
        "modalidad de cobro",
        max_length=20,
        choices=ModalidadCobro.choices,
        default=ModalidadCobro.POR_SERVICIO,
    )
    firma_obligatoria = models.BooleanField("firma obligatoria", default=False)
    notas = models.TextField("notas", blank=True)
    activo = models.BooleanField("activo", default=True)
    es_demo = models.BooleanField(
        "dato de demostración",
        default=False,
        editable=False,
        help_text="Dato ficticio de demostración; el comando de borrado de la demo lo quita.",
    )

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ("nombre",)
        constraints = (
            models.CheckConstraint(
                condition=Q(tipo__in=TipoCliente.values),
                name="cliente_tipo_valido",
                violation_error_message="Tipo de cliente desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(modalidad_cobro__in=ModalidadCobro.values),
                name="cliente_modalidad_cobro_valida",
                violation_error_message="Modalidad de cobro desconocida.",
            ),
        )

    def __str__(self):
        return self.nombre


class TelefonoCliente(models.Model):
    """Un teléfono pertenece a un solo cliente: es la llave del registro rápido de llamadas."""

    cliente = models.ForeignKey(
        Cliente, verbose_name="cliente", on_delete=models.PROTECT, related_name="telefonos"
    )
    numero = models.CharField(
        "número",
        max_length=LARGO_TELEFONO_DIGITADO,
        unique=True,
        help_text="Se guarda solo con dígitos, sin +57.",
    )
    etiqueta = models.CharField(
        "etiqueta", max_length=40, blank=True, help_text="Opcional, por ejemplo: oficina, gerente."
    )

    class Meta:
        verbose_name = "teléfono de cliente"
        verbose_name_plural = "teléfonos de cliente"
        ordering = ("numero",)
        constraints = (
            models.CheckConstraint(
                condition=Q(numero__regex=SOLO_DIGITOS),
                name="telefono_cliente_solo_digitos",
                violation_error_message="El teléfono va solo con dígitos.",
            ),
        )

    def __str__(self):
        return self.numero

    def clean(self):
        _normalizar_campo_telefono(self, "numero")
        otro = (
            TelefonoCliente.objects.exclude(pk=self.pk)
            .filter(numero=self.numero)
            .select_related("cliente")
            .first()
        )
        if otro is not None:
            raise ValidationError(
                {"numero": f"El teléfono {self.numero} ya pertenece al cliente {otro.cliente}."}
            )

    def save(self, *args, **kwargs):
        self.numero = normalizar_telefono(self.numero)
        super().save(*args, **kwargs)


class Contacto(models.Model):
    """Persona en el origen o destino de un servicio. Puede repetirse: el teléfono no es único."""

    nombre = models.CharField("nombre", max_length=120)
    telefono = models.CharField(
        "teléfono",
        max_length=LARGO_TELEFONO_DIGITADO,
        help_text="Se guarda solo con dígitos, sin +57.",
    )
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contactos",
    )

    class Meta:
        verbose_name = "contacto"
        verbose_name_plural = "contactos"
        ordering = ("nombre",)
        constraints = (
            models.CheckConstraint(
                condition=Q(telefono__regex=SOLO_DIGITOS),
                name="contacto_telefono_solo_digitos",
                violation_error_message="El teléfono va solo con dígitos.",
            ),
        )

    def __str__(self):
        return f"{self.nombre} ({self.telefono})"

    def clean(self):
        _normalizar_campo_telefono(self, "telefono")

    def save(self, *args, **kwargs):
        self.telefono = normalizar_telefono(self.telefono)
        super().save(*args, **kwargs)


class Tarifa(models.Model):
    """Valor que se propone para un tipo de servicio de un cliente; siempre se puede ajustar."""

    cliente = models.ForeignKey(
        Cliente, verbose_name="cliente", on_delete=models.PROTECT, related_name="tarifas"
    )
    tipo_servicio = models.CharField(
        "tipo de servicio",
        max_length=20,
        choices=[(tipo.value, tipo.etiqueta) for tipo in TipoServicio],
    )
    valor = models.DecimalField("valor", max_digits=12, decimal_places=2)
    descripcion = models.CharField("descripción o convenio", max_length=200, blank=True)
    vigente = models.BooleanField("vigente", default=True)

    class Meta:
        verbose_name = "tarifa"
        verbose_name_plural = "tarifas"
        ordering = ("cliente__nombre", "tipo_servicio", "-vigente")
        constraints = (
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="tarifa_valor_mayor_que_cero",
                violation_error_message="El valor de la tarifa debe ser mayor que cero.",
            ),
            models.CheckConstraint(
                condition=Q(tipo_servicio__in=[tipo.value for tipo in TipoServicio]),
                name="tarifa_tipo_servicio_valido",
                violation_error_message="Tipo de servicio desconocido.",
            ),
            # Las tarifas viejas se conservan como no vigentes; solo una propone el valor.
            models.UniqueConstraint(
                fields=("cliente", "tipo_servicio"),
                condition=Q(vigente=True),
                name="tarifa_vigente_unica_por_cliente_y_tipo",
                violation_error_message=(
                    "El cliente ya tiene una tarifa vigente para ese tipo de servicio."
                ),
            ),
        )

    def __str__(self):
        etiqueta = TipoServicio(self.tipo_servicio).etiqueta if self.tipo_servicio else ""
        return f"{self.cliente} · {etiqueta}: {self.valor}"

    def clean(self):
        errores = {}
        if self.valor is not None and self.valor <= Decimal(0):
            errores["valor"] = "El valor de la tarifa debe ser mayor que cero."
        if self.vigente and self.cliente_id is not None and self.tipo_servicio:
            otra = (
                Tarifa.objects.exclude(pk=self.pk)
                .filter(cliente_id=self.cliente_id, tipo_servicio=self.tipo_servicio, vigente=True)
                .first()
            )
            if otra is not None:
                errores["tipo_servicio"] = (
                    f"El cliente ya tiene una tarifa vigente de {otra.valor} para "
                    f"{TipoServicio(self.tipo_servicio).etiqueta.lower()}. "
                    "Márquela como no vigente antes de agregar otra."
                )
        if errores:
            raise ValidationError(errores)


def buscar_cliente_por_telefono(texto) -> Cliente | None:
    """Cliente dueño del teléfono, digitado como sea ("+57 300…", "300-…"), o None.

    Un texto que no es un teléfono válido no es un error aquí: simplemente no hay cliente.
    """
    try:
        numero = normalizar_telefono(texto)
    except TelefonoInvalido:
        return None
    telefono = TelefonoCliente.objects.select_related("cliente").filter(numero=numero).first()
    return telefono.cliente if telefono else None


def tarifa_propuesta(cliente, tipo_servicio) -> Decimal | None:
    """Valor de la tarifa vigente del cliente para ese tipo de servicio, o None si no hay.

    Solo es una propuesta: quien registra el cobro puede ajustarla.
    """
    return (
        Tarifa.objects.filter(
            cliente=cliente, tipo_servicio=TipoServicio(tipo_servicio), vigente=True
        )
        .values_list("valor", flat=True)
        .first()
    )
