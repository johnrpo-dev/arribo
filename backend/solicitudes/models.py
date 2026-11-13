"""Solicitudes: quién pide, qué vehículos se mueven y cada cambio de estado que les pasa.

Un servicio es un vehículo dentro de una solicitud. Su estado, su conductor y su grúa solo cambian
con las funciones de `solicitudes/operaciones.py`, que llaman a `nucleo/` y dejan un EventoEstado
por cambio. Nada se borra: un servicio se cancela con motivo y una solicitud se cierra como no
concretada. Las reglas viven en la base de datos (restricciones con nombre); `clean()` las repite
solo para que el admin muestre el mensaje en español en vez de un error de base.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from flota.models import ES_DEMO_AYUDA
from nucleo.estados import NOVEDAD_DESDE, Estado, estado_solicitud
from nucleo.estados import Servicio as ServicioNucleo
from nucleo.identificacion import (
    PATRON_VIN,
    VinInvalido,
    normalizar_placa,
    normalizar_vin,
    validar_vin,
)
from nucleo.sincronizacion import Resultado
from nucleo.tipos import TipoServicio

PLACA_NORMALIZADA = r"^[A-Z0-9]+$"
# El VIN se guarda con 17 caracteres, pero el campo admite el texto tal como se digita
# ("1HG-CM826-33A004352") para que el admin lo normalice en vez de rechazarlo por largo.
LARGO_VIN_DIGITADO = 25

ETIQUETAS_ESTADO = {
    Estado.PENDIENTE_ASIGNAR: "Pendiente de asignar",
    Estado.ASIGNADO: "Asignado",
    Estado.EN_CAMINO: "En camino",
    Estado.RECOGIDO: "Recogido",
    Estado.ENTREGADO: "Entregado",
    Estado.NOVEDAD: "Novedad",
    Estado.CANCELADO: "Cancelado",
}
OPCIONES_ESTADO = [(estado.value, ETIQUETAS_ESTADO[estado]) for estado in Estado]
VALORES_ESTADO = [estado.value for estado in Estado]
# Estados desde los que se abre una novedad (los únicos que puede recordar como estado previo).
VALORES_ESTADO_PREVIO = sorted(estado.value for estado in NOVEDAD_DESDE)
# Estados en los que el servicio tiene conductor y grúa sí o sí.
VALORES_CON_CONDUCTOR_Y_GRUA = [
    Estado.ASIGNADO.value,
    Estado.EN_CAMINO.value,
    Estado.RECOGIDO.value,
    Estado.ENTREGADO.value,
]
OPCIONES_TIPO_SERVICIO = [(tipo.value, tipo.etiqueta) for tipo in TipoServicio]
# Estados en los que el servicio sigue en la ronda de su conductor.
VALORES_EN_RONDA = [
    Estado.ASIGNADO.value,
    Estado.EN_CAMINO.value,
    Estado.RECOGIDO.value,
    Estado.NOVEDAD.value,
]


# --- Vehículo ----------------------------------------------------------------------------------


class Vehiculo(models.Model):
    """Un vehículo que la empresa mueve. Puede existir sin placa ni VIN: se exigen al recogerlo."""

    placa = models.CharField(
        "placa",
        max_length=10,
        blank=True,
        help_text="Se guarda en mayúsculas, solo con letras y dígitos.",
    )
    vin = models.CharField(
        "VIN",
        max_length=LARGO_VIN_DIGITADO,
        blank=True,
        help_text="17 letras o dígitos, sin I, O ni Q. Se guarda en mayúsculas, sin espacios "
        "ni guiones.",
    )
    marca = models.CharField("marca", max_length=60, blank=True)
    linea = models.CharField("línea", max_length=60, blank=True)
    color = models.CharField("color", max_length=40, blank=True)
    observaciones = models.TextField("observaciones", blank=True)
    es_demo = models.BooleanField(
        "dato de demostración", default=False, editable=False, help_text=ES_DEMO_AYUDA
    )

    class Meta:
        verbose_name = "vehículo"
        verbose_name_plural = "vehículos"
        ordering = ("placa", "vin")
        constraints = (
            # Vacío = sin placa (o sin VIN): varios vehículos pueden estar así a la vez.
            models.UniqueConstraint(
                fields=("placa",),
                condition=~Q(placa=""),
                name="vehiculo_placa_unica",
                violation_error_message="Ya hay un vehículo con esa placa.",
            ),
            models.UniqueConstraint(
                fields=("vin",),
                condition=~Q(vin=""),
                name="vehiculo_vin_unico",
                violation_error_message="Ya hay un vehículo con ese VIN.",
            ),
            # Aunque se guarde sin pasar por save() (update, SQL), la placa y el VIN quedan
            # normalizados y la unicidad no se burla con minúsculas, espacios o guiones.
            models.CheckConstraint(
                condition=Q(placa="") | Q(placa__regex=PLACA_NORMALIZADA),
                name="vehiculo_placa_normalizada",
                violation_error_message="La placa va en mayúsculas, solo con letras y dígitos.",
            ),
            models.CheckConstraint(
                condition=Q(vin="") | Q(vin__regex=PATRON_VIN),
                name="vehiculo_vin_valido",
                violation_error_message="El VIN tiene 17 letras o dígitos, sin I, O ni Q.",
            ),
        )

    def __str__(self):
        identificacion = self.placa or self.vin or f"sin placa ni VIN (#{self.pk})"
        descripcion = " ".join(parte for parte in (self.marca, self.linea) if parte)
        return f"{identificacion} · {descripcion}" if descripcion else identificacion

    def clean(self):
        self.placa = normalizar_placa(self.placa)
        self.vin = normalizar_vin(self.vin)
        errores = {}
        if self.vin:
            try:
                validar_vin(self.vin)
            except VinInvalido as error:
                errores["vin"] = str(error)
        otros = Vehiculo.objects.exclude(pk=self.pk)
        if self.placa and otros.filter(placa=self.placa).exists():
            errores["placa"] = f"Ya hay un vehículo con la placa {self.placa}."
        if self.vin and "vin" not in errores and otros.filter(vin=self.vin).exists():
            errores["vin"] = f"Ya hay un vehículo con el VIN {self.vin}."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        # Solo normaliza: un VIN inválido lo rechaza la base (vehiculo_vin_valido).
        self.placa = normalizar_placa(self.placa)
        self.vin = normalizar_vin(self.vin)
        super().save(*args, **kwargs)


# --- Solicitud ---------------------------------------------------------------------------------


class EstadoRegistro(models.TextChoices):
    BORRADOR = "borrador", "Borrador"
    ABIERTA = "abierta", "Abierta"
    NO_CONCRETADA = "no_concretada", "No concretada"


class MotivoNoConcretada(models.TextChoices):
    PRECIO = "precio", "Precio"
    SIN_GRUA = "sin_grua", "Sin grúa disponible"
    DESISTIO = "desistio", "El cliente desistió"
    DEMORA = "demora", "Demora"
    OTRO = "otro", "Otro"


ETIQUETAS_ESTADO_SOLICITUD = {
    "borrador": "Borrador",
    "abierta": "Abierta",
    "en_curso": "En curso",
    "completada": "Completada",
    "cancelada": "Cancelada",
    "no_concretada": "No concretada",
}


class Solicitud(models.Model):
    """Lo que pide un cliente: uno o varios vehículos (servicios) de un mismo tipo.

    El estado operativo (abierta, en curso, completada, cancelada) no se guarda: se deriva de los
    servicios con `nucleo.estados.estado_solicitud`. Solo se guarda el estado de registro.
    """

    EstadoRegistro = EstadoRegistro
    MotivoNoConcretada = MotivoNoConcretada

    solicitante = models.ForeignKey(
        "clientes.Cliente",
        verbose_name="solicitante",
        on_delete=models.PROTECT,
        related_name="solicitudes_pedidas",
    )
    pagador = models.ForeignKey(
        "clientes.Cliente",
        verbose_name="pagador",
        on_delete=models.PROTECT,
        related_name="solicitudes_pagadas",
        blank=True,
        help_text="Si se deja vacío, paga el solicitante.",
    )
    tipo = models.CharField("tipo de servicio", max_length=20, choices=OPCIONES_TIPO_SERVICIO)
    origen = models.CharField("origen", max_length=300, blank=True)
    origen_ubicacion = models.CharField(
        "enlace o pin del origen",
        max_length=500,
        blank=True,
        help_text="Opcional: enlace de Google Maps o coordenadas. No se geocodifica.",
    )
    contacto_origen = models.ForeignKey(
        "clientes.Contacto",
        verbose_name="contacto en el origen",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes_como_origen",
    )
    destino = models.CharField("destino", max_length=300, blank=True)
    destino_ubicacion = models.CharField(
        "enlace o pin del destino",
        max_length=500,
        blank=True,
        help_text="Opcional: enlace de Google Maps o coordenadas. No se geocodifica.",
    )
    contacto_destino = models.ForeignKey(
        "clientes.Contacto",
        verbose_name="contacto en el destino",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes_como_destino",
    )
    programada_para = models.DateTimeField(
        "programada para", null=True, blank=True, help_text="Vacío = inmediato."
    )
    # Sin valor por defecto a propósito: "no respondido" (nulo) es distinto de "no tiene regreso".
    tiene_regreso = models.BooleanField("tiene regreso", null=True, blank=True)
    fecha_regreso = models.DateTimeField("fecha de regreso", null=True, blank=True)
    estado_registro = models.CharField(
        "estado de registro",
        max_length=20,
        choices=EstadoRegistro.choices,
        default=EstadoRegistro.BORRADOR,
    )
    motivo_no_concretada = models.CharField(
        "motivo de no concretada", max_length=20, choices=MotivoNoConcretada.choices, blank=True
    )
    detalle_no_concretada = models.TextField("detalle de no concretada", blank=True)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creada por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes_creadas",
    )
    es_demo = models.BooleanField(
        "dato de demostración", default=False, editable=False, help_text=ES_DEMO_AYUDA
    )

    class Meta:
        verbose_name = "solicitud"
        verbose_name_plural = "solicitudes"
        ordering = ("-creada_en",)
        constraints = (
            models.CheckConstraint(
                condition=Q(tipo__in=[tipo.value for tipo in TipoServicio]),
                name="solicitud_tipo_valido",
                violation_error_message="Tipo de servicio desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(estado_registro__in=EstadoRegistro.values),
                name="solicitud_estado_registro_valido",
                violation_error_message="Estado de registro desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(motivo_no_concretada="")
                | Q(motivo_no_concretada__in=MotivoNoConcretada.values),
                name="solicitud_motivo_no_concretada_valido",
                violation_error_message="Motivo de no concretada desconocido.",
            ),
            models.CheckConstraint(
                condition=~Q(estado_registro=EstadoRegistro.NO_CONCRETADA)
                | ~Q(motivo_no_concretada=""),
                name="solicitud_no_concretada_exige_motivo",
                violation_error_message="Una solicitud no concretada exige el motivo.",
            ),
            models.CheckConstraint(
                condition=Q(motivo_no_concretada="")
                | Q(estado_registro=EstadoRegistro.NO_CONCRETADA),
                name="solicitud_motivo_solo_si_no_concretada",
                violation_error_message="El motivo solo aplica a una solicitud no concretada.",
            ),
            # Solo una solicitud abierta: un borrador aún no responde y cerrar una llamada perdida
            # (no concretada) no obliga a preguntar por el regreso.
            models.CheckConstraint(
                condition=~Q(tipo=TipoServicio.EVENTO.value)
                | ~Q(estado_registro=EstadoRegistro.ABIERTA)
                | Q(tiene_regreso__isnull=False),
                name="solicitud_evento_responde_regreso",
                violation_error_message="En un evento hay que responder si tiene regreso.",
            ),
            models.CheckConstraint(
                condition=~Q(tiene_regreso=True) | Q(fecha_regreso__isnull=False),
                name="solicitud_regreso_exige_fecha",
                violation_error_message="Si tiene regreso, hay que indicar la fecha de regreso.",
            ),
        )

    def __str__(self):
        tipo = TipoServicio(self.tipo).etiqueta if self.tipo else ""
        return f"Solicitud {self.pk} · {tipo}"

    @property
    def estado(self) -> str:
        """Borrador o no concretada tal cual; si está abierta, se deriva de sus servicios."""
        if self.estado_registro != EstadoRegistro.ABIERTA:
            return str(self.estado_registro)
        estados = []
        if self.pk is not None:
            estados = [Estado(valor) for valor in self.servicios.values_list("estado", flat=True)]
        return str(estado_solicitud(estados))

    @property
    def estado_etiqueta(self) -> str:
        return ETIQUETAS_ESTADO_SOLICITUD[self.estado]

    def _pagador_por_defecto(self):
        if self.pagador_id is None and self.solicitante_id is not None:
            self.pagador_id = self.solicitante_id

    def clean(self):
        self._pagador_por_defecto()
        errores = {}
        no_concretada = self.estado_registro == EstadoRegistro.NO_CONCRETADA
        if no_concretada and not self.motivo_no_concretada:
            errores["motivo_no_concretada"] = "Una solicitud no concretada exige el motivo."
        if not no_concretada and self.motivo_no_concretada:
            errores["motivo_no_concretada"] = (
                "El motivo solo aplica cuando la solicitud se cierra como no concretada."
            )
        if (
            self.tipo == TipoServicio.EVENTO
            and self.estado_registro == EstadoRegistro.ABIERTA
            and self.tiene_regreso is None
        ):
            errores["tiene_regreso"] = "En un evento hay que responder si tiene regreso."
        if self.tiene_regreso and self.fecha_regreso is None:
            errores["fecha_regreso"] = "Si tiene regreso, indique la fecha de regreso."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self._pagador_por_defecto()
        super().save(*args, **kwargs)


# --- Servicio ----------------------------------------------------------------------------------


class CambioDeEstadoNoPermitido(Exception):
    """Se intentó cambiar estado, conductor o grúa de un servicio sin pasar por las operaciones."""


# Campos que solo cambian con solicitudes/operaciones.py (cada cambio deja un EventoEstado).
CAMPOS_OPERATIVOS = ("estado", "estado_previo", "conductor_id", "grua_id")
_NOMBRES_OPERATIVOS = frozenset(CAMPOS_OPERATIVOS) | {"conductor", "grua"}


class Servicio(models.Model):
    """Un vehículo dentro de una solicitud, con su propio estado operativo.

    Guarda el conductor y la grúa con que se hizo: si después el conductor cambia de grúa, el
    historial no se altera.
    """

    solicitud = models.ForeignKey(
        Solicitud, verbose_name="solicitud", on_delete=models.PROTECT, related_name="servicios"
    )
    vehiculo = models.ForeignKey(
        Vehiculo, verbose_name="vehículo", on_delete=models.PROTECT, related_name="servicios"
    )
    estado = models.CharField(
        "estado", max_length=20, choices=OPCIONES_ESTADO, default=Estado.PENDIENTE_ASIGNAR.value
    )
    estado_previo = models.CharField(
        "estado previo a la novedad",
        max_length=20,
        choices=OPCIONES_ESTADO,
        blank=True,
        help_text="Solo mientras el servicio está en novedad: a qué estado vuelve al reanudar.",
    )
    conductor = models.ForeignKey(
        "flota.Conductor",
        verbose_name="conductor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="servicios",
    )
    grua = models.ForeignKey(
        "flota.Grua",
        verbose_name="grúa",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="servicios",
    )
    orden_ronda = models.PositiveSmallIntegerField(
        "orden de ronda",
        null=True,
        blank=True,
        help_text="Orden en que el conductor lo atiende cuando lleva varios vehículos.",
    )
    referencia_externa = models.CharField(
        "referencia externa",
        max_length=60,
        blank=True,
        help_text="Número de caso de la aseguradora o del concesionario.",
    )
    regreso_de = models.OneToOneField(
        "self",
        verbose_name="regreso de",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="regreso",
        help_text="Si este servicio es un regreso, el servicio de ida.",
    )

    class Meta:
        verbose_name = "servicio"
        verbose_name_plural = "servicios"
        ordering = ("solicitud", "orden_ronda", "pk")
        constraints = (
            models.CheckConstraint(
                condition=Q(estado__in=VALORES_ESTADO),
                name="servicio_estado_valido",
                violation_error_message="Estado de servicio desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(estado_previo="") | Q(estado_previo__in=VALORES_ESTADO_PREVIO),
                name="servicio_estado_previo_valido",
                violation_error_message="Una novedad solo se abre desde asignado, en camino o "
                "recogido.",
            ),
            models.CheckConstraint(
                condition=(Q(estado=Estado.NOVEDAD.value) & ~Q(estado_previo=""))
                | (~Q(estado=Estado.NOVEDAD.value) & Q(estado_previo="")),
                name="servicio_estado_previo_solo_en_novedad",
                violation_error_message="El estado previo se guarda si y solo si el servicio "
                "está en novedad.",
            ),
            models.CheckConstraint(
                condition=~Q(estado=Estado.PENDIENTE_ASIGNAR.value)
                | Q(conductor__isnull=True, grua__isnull=True),
                name="servicio_pendiente_sin_conductor_ni_grua",
                violation_error_message="Un servicio pendiente de asignar no tiene conductor ni "
                "grúa.",
            ),
            models.CheckConstraint(
                condition=~Q(estado__in=VALORES_CON_CONDUCTOR_Y_GRUA)
                | Q(conductor__isnull=False, grua__isnull=False),
                name="servicio_en_curso_con_conductor_y_grua",
                violation_error_message="Un servicio asignado, en camino, recogido o entregado "
                "tiene conductor y grúa.",
            ),
            # Orden de ronda (nucleo/ronda.py): único por conductor entre sus servicios no
            # terminales. Vacío no choca; los terminados guardan el suyo sin estorbar.
            models.UniqueConstraint(
                fields=("conductor", "orden_ronda"),
                condition=Q(estado__in=VALORES_EN_RONDA),
                name="servicio_orden_ronda_unico_por_conductor",
                violation_error_message="Ese conductor ya tiene otro servicio en ese puesto de "
                "la ronda.",
            ),
        )

    _cambio_desde_operaciones = False

    def __str__(self):
        return f"Servicio {self.pk} · {self.vehiculo}"

    def como_nucleo(self) -> ServicioNucleo:
        """El servicio como lo entiende nucleo/estados.py."""
        return ServicioNucleo(
            estado=Estado(self.estado),
            estado_previo=Estado(self.estado_previo) if self.estado_previo else None,
        )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        toca_lo_operativo = update_fields is None or bool(_NOMBRES_OPERATIVOS & set(update_fields))
        if self._state.adding or self._cambio_desde_operaciones or not toca_lo_operativo:
            super().save(*args, **kwargs)
            return
        # Editar otros datos (referencia, orden de ronda) sí se puede, pero si el estado, el
        # conductor o la grúa difieren de lo guardado, el cambio no pasó por las operaciones y
        # no dejaría evento. El bloqueo evita además pisar lo que otra operación acaba de cambiar.
        with transaction.atomic():
            guardado = (
                Servicio.objects.select_for_update()
                .filter(pk=self.pk)
                .values(*CAMPOS_OPERATIVOS)
                .first()
            )
            if guardado is not None and any(
                guardado[campo] != getattr(self, campo) for campo in CAMPOS_OPERATIVOS
            ):
                raise CambioDeEstadoNoPermitido(
                    "El estado, el conductor y la grúa de un servicio solo cambian con las "
                    "operaciones de solicitudes/operaciones.py, que dejan el evento de estado."
                )
            super().save(*args, **kwargs)

    def _guardar_cambio_operativo(self):
        """Lo usan solo las operaciones, dentro de su transacción y con la fila bloqueada."""
        self._cambio_desde_operaciones = True
        try:
            self.save(
                update_fields=["estado", "estado_previo", "conductor", "grua", "orden_ronda"]
            )
        finally:
            self._cambio_desde_operaciones = False


# --- Evento de estado --------------------------------------------------------------------------


class EventoInmutable(Exception):
    """Un evento de estado no se modifica ni se borra."""


MENSAJE_EVENTO_INMUTABLE = (
    "Los eventos de estado son de solo agregar: no se modifican ni se borran."
)


class EventoEstadoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise EventoInmutable(MENSAJE_EVENTO_INMUTABLE)

    update.alters_data = True

    def delete(self):
        raise EventoInmutable(MENSAJE_EVENTO_INMUTABLE)

    delete.alters_data = True
    delete.queryset_only = True


class OrigenEvento(models.TextChoices):
    PANEL = "panel", "Panel"
    APP = "app", "App del conductor"


class ResultadoEvento(models.TextChoices):
    APLICADO = Resultado.APLICADO.value, "Aplicado"
    CONFLICTO = Resultado.CONFLICTO.value, "Conflicto"


class EventoEstado(models.Model):
    """Un cambio de estado de un servicio, del panel o de un toque del conductor. Solo se agrega.

    Un evento de la app que no encaja (servicio cancelado, reasignado, salto de estado) se guarda
    igual, con resultado "conflicto", y el servicio no cambia.
    """

    Origen = OrigenEvento
    Resultado = ResultadoEvento

    id = models.UUIDField(
        "id",
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Lo genera el celular; en las acciones del panel, el servidor.",
    )
    servicio = models.ForeignKey(
        Servicio, verbose_name="servicio", on_delete=models.PROTECT, related_name="eventos"
    )
    destino = models.CharField("estado destino", max_length=20, choices=OPCIONES_ESTADO)
    origen = models.CharField("origen", max_length=10, choices=OrigenEvento.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario del panel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_de_estado",
    )
    conductor = models.ForeignKey(
        "flota.Conductor",
        verbose_name="conductor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_de_estado",
        help_text="En la app, quien tocó el botón; en el panel, el conductor del servicio tras el "
        "cambio.",
    )
    # Sin restricciones de rango ni de largo: lo que manda el celular nunca se descarta por eso.
    secuencia = models.BigIntegerField(
        "secuencia del dispositivo",
        null=True,
        blank=True,
        help_text="Contador del celular: da el orden de los eventos, no la hora.",
    )
    hora_dispositivo = models.DateTimeField("hora del dispositivo", null=True, blank=True)
    hora_sincronizacion = models.DateTimeField("hora de sincronización", auto_now_add=True)
    latitud = models.FloatField("latitud", null=True, blank=True)
    longitud = models.FloatField("longitud", null=True, blank=True)
    motivo = models.TextField("motivo", blank=True)
    nombre_quien = models.TextField("nombre de quien entrega o recibe", blank=True)
    resultado = models.CharField("resultado", max_length=10, choices=ResultadoEvento.choices)
    capacidad_excedida = models.BooleanField(
        "capacidad excedida",
        default=False,
        help_text="Recogido aplicado aunque la grúa ya iba llena (celular desactualizado).",
    )

    objects = EventoEstadoQuerySet.as_manager()

    class Meta:
        verbose_name = "evento de estado"
        verbose_name_plural = "eventos de estado"
        ordering = ("hora_sincronizacion",)
        constraints = (
            models.CheckConstraint(
                condition=Q(destino__in=VALORES_ESTADO),
                name="evento_destino_valido",
                violation_error_message="Estado destino desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(origen__in=OrigenEvento.values),
                name="evento_origen_valido",
                violation_error_message="Origen de evento desconocido.",
            ),
            models.CheckConstraint(
                condition=Q(resultado__in=ResultadoEvento.values),
                name="evento_resultado_valido",
                violation_error_message="Resultado de evento desconocido.",
            ),
        )

    def __str__(self):
        return f"{ETIQUETAS_ESTADO[Estado(self.destino)]} · servicio {self.servicio_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise EventoInmutable(MENSAJE_EVENTO_INMUTABLE)
        # Siempre INSERT: un id repetido choca con la llave primaria en vez de pisar el evento.
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise EventoInmutable(MENSAJE_EVENTO_INMUTABLE)


# --- Evidencia ---------------------------------------------------------------------------------


class TipoEvidencia(models.TextChoices):
    RECOGIDA = "recogida", "Recogida"
    ENTREGA = "entrega", "Entrega"
    SOPORTE = "soporte", "Soporte"


def ruta_evidencia(instancia, nombre_original):
    """evidencias/<servicio>/<id de la evidencia>.<extensión>, dentro de MEDIA_ROOT."""
    extension = Path(nombre_original).suffix.lower()
    return f"evidencias/{instancia.servicio_id}/{instancia.pk}{extension}"


class Evidencia(models.Model):
    """Foto de recogida, entrega o soporte. Solo el modelo: la subida es de otra tarea."""

    Tipo = TipoEvidencia

    id = models.UUIDField(
        "id",
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Lo genera el celular, para que la misma foto subida dos veces no se duplique.",
    )
    servicio = models.ForeignKey(
        Servicio, verbose_name="servicio", on_delete=models.PROTECT, related_name="evidencias"
    )
    evento = models.ForeignKey(
        EventoEstado, verbose_name="evento", on_delete=models.PROTECT, related_name="evidencias"
    )
    tipo = models.CharField("tipo", max_length=10, choices=TipoEvidencia.choices)
    archivo = models.FileField("archivo", upload_to=ruta_evidencia)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ("creada_en",)
        constraints = (
            models.CheckConstraint(
                condition=Q(tipo__in=TipoEvidencia.values),
                name="evidencia_tipo_valido",
                violation_error_message="Tipo de evidencia desconocido.",
            ),
        )

    def __str__(self):
        return f"{TipoEvidencia(self.tipo).label} · servicio {self.servicio_id}"
