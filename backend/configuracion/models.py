"""Configuración de la empresa: un solo registro con las opciones globales de `docs/arquitectura.md`
(sección "Opciones configurables").

Se obtiene siempre con `configuracion_vigente()`, que lo crea con los valores por defecto si aún no
existe. La base impide que haya dos: el campo `unico` vale siempre True y es único.

Lo que se configura por cliente (modalidad de cobro, firma) vive en `clientes.Cliente`; el precio,
en `clientes.Tarifa`; los tipos de documento llegan con la tarea 1a-15.
"""
from datetime import time

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

# Límite de fotos por estado. No es una regla del cliente sino un tope de sensatez: más fotos
# por servicio llenan el celular de gama media sin señal antes de que alcancen a subir.
MAXIMO_FOTOS = 20


class MomentoPlacaVin(models.TextChoices):
    AL_ASIGNAR = "asignar", "Al asignar"
    AL_RECOGER = "recoger", "Al recoger"


class RetencionFotos(models.TextChoices):
    SEIS_MESES = "6", "6 meses"
    DOCE_MESES = "12", "12 meses"
    VEINTICUATRO_MESES = "24", "24 meses"
    INDEFINIDA = "indefinida", "Indefinida"


# Costo mensual estimado del almacenamiento de fotos en el pico (50 servicios al día, unos 4 GB al
# mes), según `docs/arquitectura.md`, sección "Opciones configurables". Es el costo del proveedor de
# almacenamiento, no del cliente: por eso es una tabla aquí y no un campo de la configuración.
COSTO_MENSUAL_RETENCION = {
    RetencionFotos.SEIS_MESES: "COP 700 al mes",
    RetencionFotos.DOCE_MESES: "COP 1.900 al mes",
    RetencionFotos.VEINTICUATRO_MESES: "COP 4.200 al mes",
    RetencionFotos.INDEFINIDA: "sube unos COP 200 cada mes",
}


class FormatoExportacion(models.TextChoices):
    # Los adaptadores por software de facturación llegan después; se agregan aquí como opciones.
    CSV_GENERICO = "csv_generico", "Excel/CSV genérico"


def _umbral(etiqueta, defecto):
    return models.PositiveIntegerField(etiqueta, default=defecto, validators=[MinValueValidator(1)])


class Configuracion(models.Model):
    unico = models.BooleanField(default=True, editable=False)

    # Registro de vehículos
    momento_placa_vin = models.CharField(
        "momento en que se exige placa o VIN",
        max_length=10,
        choices=MomentoPlacaVin.choices,
        default=MomentoPlacaVin.AL_RECOGER,
    )

    # Fotos
    minimo_fotos = models.PositiveSmallIntegerField(
        "mínimo de fotos en Recogido y Entregado",
        default=4,
        validators=[MinValueValidator(0), MaxValueValidator(MAXIMO_FOTOS)],
        help_text=f"De 0 a {MAXIMO_FOTOS} fotos en cada estado.",
    )

    # Roles que ven valores. El administrador siempre los ve; el conductor nunca (no es opción).
    ven_valores_administrador = models.BooleanField(
        "administrador ve valores", default=True, editable=False
    )
    ven_valores_logistica = models.BooleanField("logística ve valores", default=False)
    ven_valores_facturacion = models.BooleanField("facturación ve valores", default=True)

    # Retención de fotos
    retencion_fotos = models.CharField(
        "retención de fotos",
        max_length=10,
        choices=RetencionFotos.choices,
        default=RetencionFotos.DOCE_MESES,
    )

    # Umbrales de alertas
    alerta_sin_asignar_minutos = _umbral("sin asignar (minutos)", 10)
    alerta_programado_sin_asignar_horas = _umbral(
        "programado sin asignar (horas antes de la hora pedida)", 2
    )
    alerta_sin_en_camino_minutos = _umbral('sin "En camino" (minutos)', 15)
    alerta_recogido_sin_entregado_horas = _umbral("Recogido sin Entregado (horas)", 4)
    alerta_sin_facturar_dias = _umbral("sin facturar (días)", 5)
    alerta_sin_pagar_dias = _umbral("sin pagar (días)", 30)

    # Horario nocturno (cruza la medianoche: de 19:00 a 06:00)
    nocturno_inicio = models.TimeField("inicio del horario nocturno", default=time(19, 0))
    nocturno_fin = models.TimeField("fin del horario nocturno", default=time(6, 0))

    # Exportación de factura
    formato_exportacion = models.CharField(
        "formato de exportación de factura",
        max_length=20,
        choices=FormatoExportacion.choices,
        default=FormatoExportacion.CSV_GENERICO,
    )

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"
        constraints = (
            models.UniqueConstraint(fields=("unico",), name="configuracion_un_solo_registro"),
            models.CheckConstraint(
                condition=Q(unico=True),
                name="configuracion_unico_siempre_verdadero",
                violation_error_message="Solo existe un registro de configuración.",
            ),
            models.CheckConstraint(
                condition=Q(momento_placa_vin__in=MomentoPlacaVin.values),
                name="configuracion_momento_placa_vin_valido",
                violation_error_message="Momento de placa o VIN desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(minimo_fotos__gte=0, minimo_fotos__lte=MAXIMO_FOTOS),
                name="configuracion_minimo_fotos_en_rango",
                violation_error_message=f"El mínimo de fotos va de 0 a {MAXIMO_FOTOS}.",
            ),
            models.CheckConstraint(
                condition=Q(ven_valores_administrador=True),
                name="configuracion_administrador_ve_valores",
                violation_error_message="El administrador siempre ve los valores.",
            ),
            models.CheckConstraint(
                condition=Q(retencion_fotos__in=RetencionFotos.values),
                name="configuracion_retencion_valida",
                violation_error_message="Retención de fotos desconocida.",
            ),
            models.CheckConstraint(
                condition=Q(
                    alerta_sin_asignar_minutos__gte=1,
                    alerta_programado_sin_asignar_horas__gte=1,
                    alerta_sin_en_camino_minutos__gte=1,
                    alerta_recogido_sin_entregado_horas__gte=1,
                    alerta_sin_facturar_dias__gte=1,
                    alerta_sin_pagar_dias__gte=1,
                ),
                name="configuracion_umbrales_positivos",
                violation_error_message="Los umbrales de alertas son mayores que cero.",
            ),
            models.CheckConstraint(
                condition=~Q(nocturno_inicio=F("nocturno_fin")),
                name="configuracion_horario_nocturno_distinto",
                violation_error_message="El inicio y el fin del horario nocturno son distintos.",
            ),
            models.CheckConstraint(
                condition=Q(formato_exportacion__in=FormatoExportacion.values),
                name="configuracion_formato_exportacion_valido",
                violation_error_message="Formato de exportación desconocido.",
            ),
        )

    def __str__(self):
        return "Configuración"

    @property
    def meses_retencion(self) -> int | None:
        """Meses que se guardan las fotos; None si es indefinida."""
        if self.retencion_fotos == RetencionFotos.INDEFINIDA:
            return None
        return int(self.retencion_fotos)


def configuracion_vigente() -> Configuracion:
    """El único registro de configuración; lo crea con los valores por defecto si no existe."""
    configuracion, _ = Configuracion.objects.get_or_create(unico=True)
    return configuracion


# --- Historial de configuración ----------------------------------------------------------------


class HistorialInmutable(Exception):
    """Un registro del historial de configuración no se modifica ni se borra."""


MENSAJE_HISTORIAL_INMUTABLE = (
    "El historial de configuración es de solo agregar: no se modifica ni se borra."
)


class HistorialConfiguracionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)

    update.alters_data = True

    def delete(self):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)

    delete.alters_data = True
    delete.queryset_only = True


class HistorialConfiguracion(models.Model):
    """Un campo cambiado en un guardado de la configuración: quién, cuándo, valor anterior y nuevo.
    Solo se agrega.
    """

    campo = models.CharField("campo", max_length=60)
    valor_anterior = models.CharField("valor anterior", max_length=60)
    valor_nuevo = models.CharField("valor nuevo", max_length=60)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        related_name="historial_de_configuracion",
    )
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    objects = HistorialConfiguracionQuerySet.as_manager()

    class Meta:
        verbose_name = "registro del historial de configuración"
        verbose_name_plural = "historial de configuración"
        ordering = ("fecha", "pk")

    def __str__(self):
        return f"{self.campo}: {self.valor_anterior} → {self.valor_nuevo}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise HistorialInmutable(MENSAJE_HISTORIAL_INMUTABLE)
