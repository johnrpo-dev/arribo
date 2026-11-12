"""Flota: grúas, conductores y qué conductor maneja qué grúa en cada momento.

Nada se borra: las grúas y los conductores se desactivan, y las asignaciones se cierran con fecha
de fin. Las reglas de traslape viven en la base de datos (restricciones de exclusión); `clean()`
las repite solo para que el admin muestre un mensaje entendible en vez de un error de base.
"""
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone
from django.utils.formats import date_format

from nucleo.identificacion import TelefonoInvalido, normalizar_placa, normalizar_telefono

ES_DEMO_AYUDA = "Dato ficticio de demostración; el comando de borrado de la demo lo quita."


class Grua(models.Model):
    class EstadoOperativo(models.TextChoices):
        OPERATIVA = "operativa", "Operativa"
        FUERA_DE_SERVICIO = "fuera_de_servicio", "Fuera de servicio"

    placa = models.CharField("placa", max_length=10, unique=True)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    capacidad = models.PositiveSmallIntegerField(
        "capacidad", choices=[(1, "1 vehículo"), (2, "2 vehículos")]
    )
    estado_operativo = models.CharField(
        "estado operativo",
        max_length=20,
        choices=EstadoOperativo.choices,
        default=EstadoOperativo.OPERATIVA,
    )
    activa = models.BooleanField("activa", default=True)
    es_demo = models.BooleanField("dato de demostración", default=False, editable=False,
                                  help_text=ES_DEMO_AYUDA)

    class Meta:
        verbose_name = "grúa"
        verbose_name_plural = "grúas"
        ordering = ("placa",)
        constraints = (
            models.CheckConstraint(
                condition=Q(capacidad__in=[1, 2]),
                name="grua_capacidad_1_o_2",
                violation_error_message="La capacidad de una grúa es 1 o 2 vehículos.",
            ),
            # Aunque alguien guarde sin pasar por save() (update, SQL), la placa queda normalizada
            # y la unicidad no se puede burlar con minúsculas, espacios o guiones.
            models.CheckConstraint(
                condition=Q(placa__regex=r"^[A-Z0-9]+$"),
                name="grua_placa_normalizada",
                violation_error_message="La placa va en mayúsculas, solo con letras y dígitos.",
            ),
        )

    def __str__(self):
        return self.placa

    def clean(self):
        self.placa = normalizar_placa(self.placa)

    def save(self, *args, **kwargs):
        self.placa = normalizar_placa(self.placa)
        super().save(*args, **kwargs)


class Conductor(models.Model):
    nombre = models.CharField("nombre", max_length=120)
    celular = models.CharField("celular", max_length=20, unique=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conductor",
        help_text="Opcional. Lo usará el ingreso del conductor a la app.",
    )
    activo = models.BooleanField("activo", default=True)
    es_demo = models.BooleanField("dato de demostración", default=False, editable=False,
                                  help_text=ES_DEMO_AYUDA)

    class Meta:
        verbose_name = "conductor"
        verbose_name_plural = "conductores"
        ordering = ("nombre",)
        constraints = (
            # El celular se guarda normalizado (ver nucleo/identificacion.py) para que la unicidad
            # no se burle con espacios, guiones o el +57.
            models.CheckConstraint(
                condition=Q(celular__regex=r"^[0-9]+$"),
                name="conductor_celular_solo_digitos",
                violation_error_message="El celular va solo con dígitos.",
            ),
        )

    def __str__(self):
        return self.nombre

    def clean(self):
        try:
            self.celular = normalizar_telefono(self.celular)
        except TelefonoInvalido as error:
            raise ValidationError({"celular": str(error)}) from error

    def save(self, *args, **kwargs):
        self.celular = normalizar_telefono(self.celular)
        super().save(*args, **kwargs)


class TsTzRange(Func):
    """tstzrange(inicio, fin, '[)'): fin nulo es un periodo sin límite superior."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


def _periodo():
    # '[)': el fin de un periodo puede ser el inicio del siguiente sin que cuente como traslape.
    return TsTzRange("inicio", "fin", RangeBoundary(inclusive_lower=True, inclusive_upper=False))


class AsignacionConductorGrua(models.Model):
    conductor = models.ForeignKey(
        Conductor,
        verbose_name="conductor",
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    grua = models.ForeignKey(
        Grua, verbose_name="grúa", on_delete=models.PROTECT, related_name="asignaciones"
    )
    inicio = models.DateTimeField("inicio")
    fin = models.DateTimeField("fin", null=True, blank=True, help_text="Vacío = vigente.")
    temporal = models.BooleanField("temporal", default=False)
    motivo = models.CharField("motivo", max_length=200, blank=True)

    class Meta:
        verbose_name = "asignación conductor–grúa"
        verbose_name_plural = "asignaciones conductor–grúa"
        ordering = ("-inicio",)
        constraints = (
            models.CheckConstraint(
                condition=Q(fin__isnull=True) | Q(fin__gt=F("inicio")),
                name="asignacion_fin_posterior_a_inicio",
                violation_error_message="El fin debe ser posterior al inicio.",
            ),
            ExclusionConstraint(
                name="asignacion_sin_traslape_por_conductor",
                expressions=[
                    ("conductor", RangeOperators.EQUAL),
                    (_periodo(), RangeOperators.OVERLAPS),
                ],
                violation_error_message="El conductor ya tiene otra asignación en ese periodo.",
            ),
            ExclusionConstraint(
                name="asignacion_sin_traslape_por_grua",
                expressions=[
                    ("grua", RangeOperators.EQUAL),
                    (_periodo(), RangeOperators.OVERLAPS),
                ],
                violation_error_message="La grúa ya tiene otra asignación en ese periodo.",
            ),
        )

    def __str__(self):
        return f"{self.conductor} en {self.grua} ({self._describir_periodo()})"

    @property
    def vigente(self) -> bool:
        ahora = timezone.now()
        return self.inicio <= ahora and (self.fin is None or self.fin > ahora)

    def _describir_periodo(self) -> str:
        desde = date_format(timezone.localtime(self.inicio), "DATETIME_FORMAT")
        if self.fin is None:
            return f"desde {desde}, sin fin"
        hasta = date_format(timezone.localtime(self.fin), "DATETIME_FORMAT")
        return f"del {desde} al {hasta}"

    def _que_se_cruzan(self):
        """Otras asignaciones cuyo periodo [inicio, fin) se cruza con el de esta."""
        cruces = AsignacionConductorGrua.objects.exclude(pk=self.pk).filter(
            Q(fin__isnull=True) | Q(fin__gt=self.inicio)
        )
        if self.fin is not None:
            cruces = cruces.filter(inicio__lt=self.fin)
        return cruces.select_related("conductor", "grua").order_by("inicio")

    def clean(self):
        # Los errores van atados al campo: así Django no vuelve a validar la restricción de la
        # base sobre ese campo y el admin muestra un solo mensaje, en español.
        if self.inicio is None:
            return
        if self.fin is not None and self.fin <= self.inicio:
            raise ValidationError({"fin": "El fin debe ser posterior al inicio."})

        errores = {}
        cruces = self._que_se_cruzan()
        if self.conductor_id is not None:
            otra = cruces.filter(conductor_id=self.conductor_id).first()
            if otra is not None:
                errores["conductor"] = (
                    f"{otra.conductor} ya tiene asignada la grúa {otra.grua} "
                    f"({otra._describir_periodo()}), que se cruza con este periodo. "
                    "Cierre esa asignación con fecha de fin antes de abrir otra."
                )
        if self.grua_id is not None:
            otra = cruces.filter(grua_id=self.grua_id).first()
            if otra is not None:
                errores["grua"] = (
                    f"La grúa {otra.grua} ya está asignada a {otra.conductor} "
                    f"({otra._describir_periodo()}), que se cruza con este periodo. "
                    "Cierre esa asignación con fecha de fin antes de abrir otra."
                )
        if errores:
            raise ValidationError(errores)


def grua_vigente(conductor, en=None):
    """Grúa asignada al conductor en el instante `en` (por defecto, ahora), o None.

    Periodo [inicio, fin): en el instante exacto del fin ya rige la asignación siguiente.
    """
    en = en or timezone.now()
    asignacion = (
        AsignacionConductorGrua.objects.filter(conductor=conductor, inicio__lte=en)
        .filter(Q(fin__isnull=True) | Q(fin__gt=en))
        .select_related("grua")
        .first()
    )
    return asignacion.grua if asignacion else None
