"""Cobros: la línea de cobro (servicio × pagador) con su propio estado, y su historial.

El estado de cobro vive en la línea, no en el servicio. Una línea nace cuando el servicio queda
Entregado (o cuando un servicio cancelado se marca cobrable) y solo cambia con las funciones de
`cobros/operaciones.py`, que llaman a `nucleo/cobro.py` y dejan un registro de historial por cambio.

La coherencia entre estado, valor y número de factura la garantiza PostgreSQL (restricciones con
nombre): ninguna escritura, ni siquiera un `update()` directo, deja una línea en un estado inválido.
`clean()` repite las reglas solo para que un formulario muestre el mensaje en español.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from nucleo.cobro import MAX_PAGADORES, EstadoCobro
from nucleo.cobro import LineaCobro as LineaNucleo
from nucleo.relacion import EstadoRelacion
from nucleo.relacion import Relacion as RelacionNucleo

# Un número de factura hecho solo de espacios (o vacío) no cuenta como número.
EN_BLANCO = r"^\s*$"

ETIQUETAS_ESTADO_COBRO = {
    EstadoCobro.NO_COBRABLE: "No cobrable",
    EstadoCobro.SIN_VALOR: "Sin valor",
    EstadoCobro.POR_FACTURAR: "Por facturar",
    EstadoCobro.FACTURADO: "Facturado",
    EstadoCobro.PAGADO: "Pagado",
}
OPCIONES_ESTADO_COBRO = [(estado.value, ETIQUETAS_ESTADO_COBRO[estado]) for estado in EstadoCobro]
VALORES_ESTADO_COBRO = [estado.value for estado in EstadoCobro]
POSICIONES = list(range(1, MAX_PAGADORES + 1))
CON_VALOR = (EstadoCobro.POR_FACTURAR, EstadoCobro.FACTURADO, EstadoCobro.PAGADO)
CON_FACTURA = (EstadoCobro.FACTURADO, EstadoCobro.PAGADO)

VALOR_POSITIVO = Q(valor__isnull=False) & Q(valor__gt=0)  # NULL > 0 no es falso en SQL: se excluye
SIN_FACTURA = Q(numero_factura="")
CON_NUMERO_DE_FACTURA = ~Q(numero_factura__regex=EN_BLANCO)


# --- Línea de cobro ----------------------------------------------------------------------------


class CambioDeCobroNoPermitido(Exception):
    """Se intentó cambiar estado, valor o factura de una línea sin pasar por las operaciones."""


# Campos que solo cambian con cobros/operaciones.py (cada cambio deja un registro de historial).
CAMPOS_DE_COBRO = ("estado", "valor", "numero_factura")


class LineaCobro(models.Model):
    """Lo que se le cobra a un pagador por un servicio. Un servicio tiene como máximo dos líneas
    (posición 1 y 2) y no repite pagador.
    """

    servicio = models.ForeignKey(
        "solicitudes.Servicio",
        verbose_name="servicio",
        on_delete=models.PROTECT,
        related_name="lineas_cobro",
    )
    pagador = models.ForeignKey(
        "clientes.Cliente",
        verbose_name="pagador",
        on_delete=models.PROTECT,
        related_name="lineas_cobro",
    )
    posicion = models.PositiveSmallIntegerField(
        "posición",
        choices=[(posicion, str(posicion)) for posicion in POSICIONES],
        default=1,
        help_text="1 para el pagador principal; 2 si el servicio se divide entre dos pagadores.",
    )
    estado = models.CharField(
        "estado de cobro",
        max_length=20,
        choices=OPCIONES_ESTADO_COBRO,
        default=EstadoCobro.SIN_VALOR.value,
    )
    valor = models.DecimalField(
        "valor", max_digits=12, decimal_places=2, null=True, blank=True
    )
    numero_factura = models.CharField("número de factura", max_length=60, blank=True)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "línea de cobro"
        verbose_name_plural = "líneas de cobro"
        ordering = ("-creada_en", "servicio", "posicion")
        constraints = (
            models.CheckConstraint(
                condition=Q(estado__in=VALORES_ESTADO_COBRO),
                name="linea_cobro_estado_valido",
                violation_error_message="Estado de cobro desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(posicion__in=POSICIONES),
                name="linea_cobro_posicion_valida",
                violation_error_message="Un servicio tiene como máximo dos pagadores "
                "(posición 1 o 2).",
            ),
            # Con la posición limitada a 1 o 2, esto deja como máximo dos líneas por servicio.
            models.UniqueConstraint(
                fields=("servicio", "posicion"),
                name="linea_cobro_unica_por_servicio_y_posicion",
                violation_error_message="El servicio ya tiene una línea de cobro en esa posición.",
            ),
            models.UniqueConstraint(
                fields=("servicio", "pagador"),
                name="linea_cobro_unica_por_servicio_y_pagador",
                violation_error_message="El servicio ya tiene una línea de cobro para ese pagador.",
            ),
            # Coherencia entre estado, valor y factura, un estado por restricción.
            models.CheckConstraint(
                condition=~Q(estado=EstadoCobro.SIN_VALOR.value)
                | (Q(valor__isnull=True) & SIN_FACTURA),
                name="linea_cobro_sin_valor_coherente",
                violation_error_message="Una línea sin valor no lleva valor ni número de factura.",
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoCobro.POR_FACTURAR.value)
                | (VALOR_POSITIVO & SIN_FACTURA),
                name="linea_cobro_por_facturar_coherente",
                violation_error_message="Una línea por facturar lleva un valor mayor que cero y "
                "aún no tiene número de factura.",
            ),
            models.CheckConstraint(
                condition=~Q(estado__in=[estado.value for estado in CON_FACTURA])
                | (VALOR_POSITIVO & CON_NUMERO_DE_FACTURA),
                name="linea_cobro_facturada_coherente",
                violation_error_message="Una línea facturada o pagada lleva un valor mayor que "
                "cero y el número de factura.",
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoCobro.NO_COBRABLE.value) | SIN_FACTURA,
                name="linea_cobro_no_cobrable_sin_factura",
                violation_error_message="Una línea no cobrable no lleva número de factura.",
            ),
        )

    _cambio_desde_operaciones = False

    def __str__(self):
        return f"Cobro del servicio {self.servicio_id} · {self.pagador}"

    @property
    def estado_etiqueta(self) -> str:
        return ETIQUETAS_ESTADO_COBRO[EstadoCobro(self.estado)]

    def como_nucleo(self) -> LineaNucleo:
        """La línea como la entiende nucleo/cobro.py (sin factura = None)."""
        return LineaNucleo(
            estado=EstadoCobro(self.estado),
            valor=self.valor,
            numero_factura=self.numero_factura or None,
        )

    def tomar_del_nucleo(self, linea: LineaNucleo):
        """Copia lo que decidió el núcleo. Solo la usan las operaciones antes de guardar."""
        self.estado = linea.estado.value
        self.valor = linea.valor
        self.numero_factura = linea.numero_factura or ""

    def clean(self):
        errores = {}
        estado = EstadoCobro(self.estado) if self.estado in VALORES_ESTADO_COBRO else None
        hay_factura = bool((self.numero_factura or "").strip())
        if estado == EstadoCobro.SIN_VALOR and self.valor is not None:
            errores["valor"] = "Una línea sin valor no lleva valor."
        if estado in CON_VALOR and (self.valor is None or self.valor <= 0):
            errores["valor"] = "El valor debe ser mayor que cero."
        if estado in CON_FACTURA and not hay_factura:
            errores["numero_factura"] = "Una línea facturada o pagada exige el número de factura."
        if estado not in CON_FACTURA and self.numero_factura:
            errores["numero_factura"] = (
                "El número de factura solo va en una línea facturada o pagada."
            )
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        toca_el_cobro = update_fields is None or bool(set(CAMPOS_DE_COBRO) & set(update_fields))
        if self._state.adding or self._cambio_desde_operaciones or not toca_el_cobro:
            super().save(*args, **kwargs)
            return
        # Si estado, valor o factura difieren de lo guardado, el cambio no pasó por las
        # operaciones y no dejaría historial. El bloqueo evita pisar lo que otra operación cambió.
        with transaction.atomic():
            guardado = (
                LineaCobro.objects.select_for_update()
                .filter(pk=self.pk)
                .values(*CAMPOS_DE_COBRO)
                .first()
            )
            if guardado is not None and any(
                guardado[campo] != getattr(self, campo) for campo in CAMPOS_DE_COBRO
            ):
                raise CambioDeCobroNoPermitido(
                    "El estado, el valor y el número de factura de una línea de cobro solo "
                    "cambian con las operaciones de cobros/operaciones.py, que dejan el historial."
                )
            super().save(*args, **kwargs)

    def _guardar_cambio_de_cobro(self):
        """Lo usan solo las operaciones, dentro de su transacción y con la fila bloqueada."""
        self._cambio_desde_operaciones = True
        try:
            self.save(update_fields=list(CAMPOS_DE_COBRO))
        finally:
            self._cambio_desde_operaciones = False


# --- Historial de cobro ------------------------------------------------------------------------


class HistorialInmutable(Exception):
    """Un registro del historial de cobro no se modifica ni se borra."""


MENSAJE_HISTORIAL_INMUTABLE = (
    "El historial de cobro es de solo agregar: no se modifica ni se borra."
)


class HistorialCobroQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)

    update.alters_data = True

    def delete(self):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)

    delete.alters_data = True
    delete.queryset_only = True


class AccionCobro(models.TextChoices):
    CREADA = "creada", "Creada al entregar"
    VALOR = "valor", "Cambio de valor"
    FACTURADA = "facturada", "Facturada"
    PAGADA = "pagada", "Pagada"
    FACTURA_ANULADA = "factura_anulada", "Factura anulada"
    MARCADA_COBRABLE = "marcada_cobrable", "Marcada cobrable"


class HistorialCobro(models.Model):
    """Un cambio de una línea de cobro: quién, cuándo, qué acción y el valor anterior. Solo se
    agrega.
    """

    Accion = AccionCobro

    linea = models.ForeignKey(
        LineaCobro, verbose_name="línea", on_delete=models.PROTECT, related_name="historial"
    )
    accion = models.CharField("acción", max_length=20, choices=AccionCobro.choices)
    valor_anterior = models.DecimalField(
        "valor anterior", max_digits=12, decimal_places=2, null=True, blank=True
    )
    valor_nuevo = models.DecimalField(
        "valor nuevo", max_digits=12, decimal_places=2, null=True, blank=True
    )
    numero_factura = models.CharField("número de factura", max_length=60, blank=True)
    motivo = models.TextField("motivo", blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="historial_de_cobro",
        help_text="Vacío si el cambio lo hizo el sistema (por ejemplo, un Entregado desde la app).",
    )
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    objects = HistorialCobroQuerySet.as_manager()

    class Meta:
        verbose_name = "registro del historial de cobro"
        verbose_name_plural = "historial de cobro"
        ordering = ("fecha", "pk")
        constraints = (
            models.CheckConstraint(
                condition=Q(accion__in=AccionCobro.values),
                name="historial_cobro_accion_valida",
                violation_error_message="Acción de cobro desconocida.",
            ),
            models.CheckConstraint(
                condition=~Q(accion=AccionCobro.FACTURA_ANULADA) | ~Q(motivo__regex=EN_BLANCO),
                name="historial_cobro_anulacion_con_motivo",
                violation_error_message="Anular una factura exige el motivo.",
            ),
            models.CheckConstraint(
                condition=~Q(accion=AccionCobro.VALOR) | Q(valor_nuevo__isnull=False),
                name="historial_cobro_cambio_de_valor_con_valor",
                violation_error_message="Un cambio de valor guarda el valor nuevo.",
            ),
        )

    def __str__(self):
        return f"{AccionCobro(self.accion).label} · línea {self.linea_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)


# --- Relación de cobro (1a-17) -----------------------------------------------------------------

ETIQUETAS_ESTADO_RELACION = {
    EstadoRelacion.ARMADA: "Armada",
    EstadoRelacion.FACTURADA: "Facturada",
    EstadoRelacion.PAGADA: "Pagada",
    EstadoRelacion.DESCARTADA: "Descartada",
}
VALORES_ESTADO_RELACION = [estado.value for estado in EstadoRelacion]
RELACION_CON_FACTURA = [EstadoRelacion.FACTURADA.value, EstadoRelacion.PAGADA.value]


class RelacionCobro(models.Model):
    """Las líneas por facturar de un pagador en un rango de fechas, que se le mandan juntas y se
    facturan con un solo número. Reglas en `nucleo/relacion.py`; solo cambia con
    `cobros/relaciones.py`. Nada se borra: una relación que sobra se descarta con motivo.
    """

    pagador = models.ForeignKey(
        "clientes.Cliente",
        verbose_name="pagador",
        on_delete=models.PROTECT,
        related_name="relaciones_cobro",
    )
    desde = models.DateField("desde")
    hasta = models.DateField("hasta")
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=[(e.value, ETIQUETAS_ESTADO_RELACION[e]) for e in EstadoRelacion],
        default=EstadoRelacion.ARMADA.value,
    )
    numero_factura = models.CharField("número de factura", max_length=60, blank=True)
    motivo_descarte = models.TextField("motivo del descarte", blank=True)
    creada_en = models.DateTimeField("armada en", auto_now_add=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="armada por",
        on_delete=models.PROTECT,
        related_name="relaciones_armadas",
    )
    cerrada_en = models.DateTimeField("facturada, pagada o descartada en", null=True, blank=True)
    cerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="facturada, pagada o descartada por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="relaciones_cerradas",
    )
    lineas = models.ManyToManyField(
        LineaCobro, through="LineaEnRelacion", related_name="relaciones", verbose_name="líneas"
    )

    class Meta:
        verbose_name = "relación de cobro"
        verbose_name_plural = "relaciones de cobro"
        ordering = ("-creada_en", "-pk")
        constraints = (
            models.CheckConstraint(
                condition=Q(estado__in=VALORES_ESTADO_RELACION),
                name="relacion_cobro_estado_valido",
                violation_error_message="Estado de relación desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(desde__lte=models.F("hasta")),
                name="relacion_cobro_rango_valido",
                violation_error_message="La fecha inicial va antes de la final.",
            ),
            models.CheckConstraint(
                condition=~Q(estado__in=RELACION_CON_FACTURA) | CON_NUMERO_DE_FACTURA,
                name="relacion_cobro_facturada_con_numero",
                violation_error_message="Una relación facturada o pagada lleva número de factura.",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=RELACION_CON_FACTURA) | SIN_FACTURA,
                name="relacion_cobro_sin_factura_si_no_esta_facturada",
                violation_error_message="Solo una relación facturada o pagada lleva factura.",
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoRelacion.DESCARTADA.value)
                | ~Q(motivo_descarte__regex=EN_BLANCO),
                name="relacion_cobro_descarte_con_motivo",
                violation_error_message="Descartar una relación exige motivo.",
            ),
        )

    def __str__(self):
        return f"Relación {self.pk} · {self.pagador}"

    @property
    def estado_etiqueta(self) -> str:
        return ETIQUETAS_ESTADO_RELACION[EstadoRelacion(self.estado)]

    def como_nucleo(self) -> RelacionNucleo:
        return RelacionNucleo(
            estado=EstadoRelacion(self.estado),
            numero_factura=self.numero_factura or None,
            motivo_descarte=self.motivo_descarte or None,
        )


class LineaEnRelacion(models.Model):
    """Una línea dentro de una relación. `reservada` mientras la relación está armada: PostgreSQL no
    deja que la misma línea esté reservada en dos relaciones. Al facturar o descartar la relación
    deja de estar reservada (y la fila queda, como registro de en qué relación estuvo)."""

    relacion = models.ForeignKey(
        RelacionCobro, verbose_name="relación", on_delete=models.PROTECT, related_name="incluidas"
    )
    linea = models.ForeignKey(
        LineaCobro, verbose_name="línea", on_delete=models.PROTECT, related_name="inclusiones"
    )
    reservada = models.BooleanField("reservada", default=True)

    class Meta:
        verbose_name = "línea en relación"
        verbose_name_plural = "líneas en relación"
        constraints = (
            models.UniqueConstraint(
                fields=("relacion", "linea"),
                name="linea_en_relacion_una_vez",
                violation_error_message="La línea ya está en esa relación.",
            ),
            models.UniqueConstraint(
                fields=("linea",),
                condition=Q(reservada=True),
                name="linea_reservada_en_una_sola_relacion",
                violation_error_message="La línea ya está en otra relación armada.",
            ),
        )
