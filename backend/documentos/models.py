"""Documentos de grúas y conductores (SOAT, tecnomecánica, licencia de conducción...).

- Los tipos son configuración: la lista se edita en el panel (Flota y personal). La migración de
  datos siembra SOAT y tecnomecánica (grúa) y licencia de conducción (conductor), con aviso desde
  30 días antes. Un tipo no se borra: se desactiva.
- Un documento es de una grúa o de un conductor, exactamente uno, y del lado que dice su tipo. Lo
  garantiza la base: el documento copia `aplica_a` de su tipo y una llave foránea compuesta
  (tipo, aplica_a) → (id, aplica_a) del tipo impide que no coincidan; por eso un tipo con
  documentos ya no puede cambiar de lado.
- Nada se borra ni se edita: un documento nuevo del mismo tipo reemplaza al anterior para esa grúa
  o conductor (el que cuenta es el más reciente) y los anteriores quedan como historial.
- Las reglas (estado a una fecha, qué bloquea) están en `nucleo/documentos.py`.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from flota.models import ES_DEMO_AYUDA, Conductor, Grua
from nucleo.documentos import DIAS_ANTICIPACION_POR_DEFECTO, TIPOS_DE_ARCHIVO
from nucleo.documentos import Documento as DocumentoNucleo


class AplicaA(models.TextChoices):
    GRUA = "grua", "Grúa"
    CONDUCTOR = "conductor", "Conductor"


class TipoArchivo(models.TextChoices):
    JPEG = "jpeg", "Imagen JPEG"
    PNG = "png", "Imagen PNG"
    PDF = "pdf", "PDF"


class TipoDocumento(models.Model):
    nombre = models.CharField("nombre", max_length=80)
    aplica_a = models.CharField("aplica a", max_length=10, choices=AplicaA.choices)
    dias_anticipacion = models.PositiveSmallIntegerField(
        "días de anticipación del aviso",
        default=DIAS_ANTICIPACION_POR_DEFECTO,
        help_text="Desde cuántos días antes del vencimiento se avisa que está por vencer.",
    )
    activo = models.BooleanField(
        "activo", default=True, help_text="Un tipo inactivo no se exige ni bloquea a nadie."
    )

    class Meta:
        verbose_name = "tipo de documento"
        verbose_name_plural = "tipos de documento"
        ordering = ("aplica_a", "nombre")
        constraints = (
            models.UniqueConstraint(
                Lower("nombre"),
                name="tipodocumento_nombre_unico",
                violation_error_message="Ya hay un tipo de documento con ese nombre.",
            ),
            models.CheckConstraint(
                condition=~Q(nombre__regex=r"^\s*$"),
                name="tipodocumento_con_nombre",
                violation_error_message="El tipo de documento lleva nombre.",
            ),
            models.CheckConstraint(
                condition=Q(aplica_a__in=AplicaA.values),
                name="tipodocumento_aplica_a_valido",
                violation_error_message="Un tipo de documento aplica a grúa o a conductor.",
            ),
            # Destino de la llave foránea compuesta del documento (ver la migración 0001).
            models.UniqueConstraint(fields=("id", "aplica_a"), name="tipodocumento_id_aplica_a"),
        )

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre = " ".join(self.nombre.split())
        super().save(*args, **kwargs)


def ruta_documento(instancia, nombre_original):
    """documentos/<grua|conductor>/<id>/<nombre aleatorio>.<ext>, dentro de MEDIA_ROOT.

    El nombre lo pone el servidor; del que trae el archivo no se usa nada. La extensión sale del
    contenido (`tipo_archivo`), no del nombre.
    """
    _, extension = TIPOS_DE_ARCHIVO[instancia.tipo_archivo]
    sujeto = instancia.grua_id if instancia.aplica_a == AplicaA.GRUA else instancia.conductor_id
    return f"documentos/{instancia.aplica_a}/{sujeto}/{uuid.uuid4().hex}.{extension}"


class DocumentoInmutable(Exception):
    """Un documento guardado no se edita: se registra uno nuevo."""


class Documento(models.Model):
    tipo = models.ForeignKey(
        TipoDocumento, verbose_name="tipo", on_delete=models.PROTECT, related_name="documentos"
    )
    # Copia del lado del tipo: la base exige que coincida con el del tipo y con el sujeto.
    aplica_a = models.CharField("aplica a", max_length=10, choices=AplicaA.choices, editable=False)
    grua = models.ForeignKey(
        Grua,
        verbose_name="grúa",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documentos",
    )
    conductor = models.ForeignKey(
        Conductor,
        verbose_name="conductor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documentos",
    )
    numero = models.CharField("número", max_length=60, blank=True)
    vence = models.DateField("vence", null=True, blank=True, help_text="Sirve hasta este día inclusive.")
    aplica_desde = models.DateField(
        "aún no aplica; aplica desde",
        null=True,
        blank=True,
        help_text="Solo si el documento aún no se exige: el día desde el que se exige.",
    )
    archivo = models.FileField("archivo", upload_to=ruta_documento, blank=True, max_length=200)
    tipo_archivo = models.CharField(
        "tipo de archivo", max_length=5, choices=TipoArchivo.choices, blank=True, editable=False
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.PROTECT,
        related_name="documentos_registrados",
    )
    registrado_en = models.DateTimeField("registrado", auto_now_add=True)
    es_demo = models.BooleanField(
        "dato de demostración", default=False, editable=False, help_text=ES_DEMO_AYUDA
    )

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ("-registrado_en", "-pk")
        indexes = (
            models.Index(fields=("tipo", "grua", "conductor", "-registrado_en"),
                         name="documento_vigente_idx"),
        )
        constraints = (
            models.CheckConstraint(
                condition=Q(aplica_a__in=AplicaA.values),
                name="documento_aplica_a_valido",
                violation_error_message="Un documento es de una grúa o de un conductor.",
            ),
            models.CheckConstraint(
                condition=(
                    Q(aplica_a=AplicaA.GRUA, grua__isnull=False, conductor__isnull=True)
                    | Q(aplica_a=AplicaA.CONDUCTOR, conductor__isnull=False, grua__isnull=True)
                ),
                name="documento_de_una_grua_o_un_conductor",
                violation_error_message=(
                    "El documento es de una grúa o de un conductor (uno solo), según su tipo."
                ),
            ),
            models.CheckConstraint(
                condition=(
                    Q(vence__isnull=False, aplica_desde__isnull=True)
                    | Q(vence__isnull=True, aplica_desde__isnull=False)
                ),
                name="documento_vence_o_aun_no_aplica",
                violation_error_message=(
                    "El documento lleva fecha de vencimiento o, si aún no aplica, la fecha desde "
                    "la que aplica (una de las dos)."
                ),
            ),
            models.CheckConstraint(
                condition=(
                    Q(archivo="", tipo_archivo="")
                    | (~Q(archivo="") & Q(tipo_archivo__in=TipoArchivo.values))
                ),
                name="documento_archivo_con_tipo",
                violation_error_message="Un archivo adjunto lleva su tipo, y solo si hay archivo.",
            ),
        )

    def __str__(self):
        return f"{self.tipo} de {self.sujeto}"

    @property
    def sujeto(self):
        return self.grua if self.aplica_a == AplicaA.GRUA else self.conductor

    @property
    def aun_no_aplica(self) -> bool:
        return self.aplica_desde is not None

    def como_nucleo(self) -> DocumentoNucleo:
        return DocumentoNucleo(vence=self.vence, aplica_desde=self.aplica_desde)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise DocumentoInmutable(
                "Un documento guardado no se edita: registre uno nuevo, que lo reemplaza."
            )
        if self.tipo_id is not None and not self.aplica_a:
            self.aplica_a = self.tipo.aplica_a
        super().save(*args, **kwargs)
