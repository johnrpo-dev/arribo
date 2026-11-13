"""Registro de una solicitud desde el formulario del panel.

- `registrar_solicitud` crea en una sola transacción el cliente nuevo (si lo hay), los contactos,
  los vehículos, la solicitud y un servicio por vehículo.
- `completar_borrador` guarda lo digitado sobre un borrador (solo borradores) con el mismo
  formulario: actualiza datos y vehículos, agrega los nuevos y cancela, con motivo, los que se
  quitan (nada se borra).
- Al quedar abierta, un evento con regreso recibe por cada vehículo su servicio de regreso,
  enlazado al de ida (`Servicio.regreso_de`); el regreso va del destino al origen.
- `cerrar_no_concretada` cierra con motivo una solicitud que nunca se asignó.
- `duplicados_activos` encuentra servicios activos de los mismos vehículos en otras solicitudes
  (es una advertencia: no bloquea).

Toda escritura corre en una transacción: si algo falla a mitad, no queda nada guardado. Las reglas
son de `nucleo/registro.py`; aquí solo se cargan los datos, se pregunta al núcleo y se guarda.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Q

from clientes.models import Cliente, Contacto, TelefonoCliente, TipoCliente
from nucleo.estados import TERMINALES, Estado
from nucleo.registro import (
    CierreNoPermitido,
    Faltante,
    crea_regreso,
    faltantes_para_abrir,
    verificar_cierre_no_concretada,
)
from nucleo.tipos import TipoServicio

from . import operaciones
from .models import EstadoRegistro, EventoEstado, Servicio, Solicitud, Vehiculo

# Filas del historial reciente que se muestran al encontrar al cliente por su teléfono.
FILAS_HISTORIAL = 5
MOTIVO_QUITADO = "Se quitó el vehículo al completar el borrador."


@dataclass(frozen=True)
class ClienteNuevo:
    nombre: str
    tipo: str
    telefono: str  # ya normalizado


@dataclass(frozen=True)
class DatosContacto:
    nombre: str
    telefono: str  # ya normalizado


@dataclass(frozen=True)
class DatosVehiculo:
    placa: str  # ya normalizada
    vin: str  # ya normalizado y válido
    marca: str = ""
    linea: str = ""
    color: str = ""
    referencia_externa: str = ""
    servicio_id: int | None = None  # el servicio del borrador que esta fila edita
    quitar: bool = False  # solo con servicio_id: cancelar ese servicio

    @property
    def tiene_datos(self) -> bool:
        return any(
            (getattr(self, campo) or "").strip()
            for campo in ("placa", "vin", "marca", "linea", "color")
        )


@dataclass(frozen=True)
class DatosRegistro:
    """Lo que trae el formulario ya validado. `solicitante` o `cliente_nuevo`, uno de los dos."""

    tipo: str
    solicitante: Cliente | None = None
    cliente_nuevo: ClienteNuevo | None = None
    pagador: Cliente | None = None  # None = paga el solicitante
    origen: str = ""
    destino: str = ""
    contacto_origen: DatosContacto | None = None
    contacto_destino: DatosContacto | None = None
    vehiculos: tuple[DatosVehiculo, ...] = ()
    programada_para: datetime | None = None
    tiene_regreso: bool | None = None  # solo se guarda en un evento
    fecha_regreso: datetime | None = None


class VehiculoEnConflicto(ValueError):
    """La placa y el VIN digitados no pueden ser del mismo vehículo guardado."""

    def __init__(self, campo, mensaje):
        super().__init__(mensaje)
        self.campo = campo


class SolicitudNoEditable(ValueError):
    """Solo un borrador se completa con el formulario de registro."""


def vehiculo_existente(placa: str, vin: str) -> Vehiculo | None:
    """El vehículo ya guardado con esa placa o ese VIN, o None si es nuevo.

    La placa y el VIN son únicos: si apuntan a vehículos distintos, o el vehículo guardado tiene
    otra placa u otro VIN, se lanza VehiculoEnConflicto con el campo al que corresponde el error.
    """
    por_placa = Vehiculo.objects.filter(placa=placa).first() if placa else None
    por_vin = Vehiculo.objects.filter(vin=vin).first() if vin else None
    if por_placa and por_vin and por_placa.pk != por_vin.pk:
        raise VehiculoEnConflicto("vin", f"Ese VIN ya es del vehículo {por_vin}.")
    if por_placa and vin and por_placa.vin and por_placa.vin != vin:
        raise VehiculoEnConflicto(
            "vin", f"El vehículo con placa {placa} ya tiene otro VIN: {por_placa.vin}."
        )
    if por_vin and placa and por_vin.placa and por_vin.placa != placa:
        raise VehiculoEnConflicto(
            "placa", f"El vehículo con ese VIN ya tiene otra placa: {por_vin.placa}."
        )
    return por_placa or por_vin


def historial_reciente(cliente) -> list[Solicitud]:
    """Últimas solicitudes que pidió el cliente, la más reciente primero."""
    return list(
        Solicitud.objects.filter(solicitante=cliente).order_by("-creada_en")[:FILAS_HISTORIAL]
    )


def servicios_de_ida(solicitud: Solicitud):
    """Un servicio por vehículo: sin los de regreso ni los cancelados (vehículos quitados)."""
    return solicitud.servicios.filter(regreso_de__isnull=True).exclude(
        estado=Estado.CANCELADO.value
    )


def faltantes_de(solicitud: Solicitud) -> list[Faltante]:
    """Lo que le falta a una solicitud guardada para quedar abierta."""
    idas = servicios_de_ida(solicitud)
    return faltantes_para_abrir(
        tiene_solicitante=solicitud.solicitante_id is not None,
        tipo=solicitud.tipo,
        origen=solicitud.origen,
        destino=solicitud.destino,
        vehiculos=idas.count(),
        tiene_regreso=solicitud.tiene_regreso,
        paga_aseguradora=Cliente.objects.filter(
            pk=solicitud.pagador_id, tipo=TipoCliente.ASEGURADORA
        ).exists(),
        vehiculos_sin_referencia=idas.filter(referencia_externa="").count(),
    )


# --- Duplicados --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Duplicado:
    """Un vehículo digitado que ya tiene un servicio activo en otra solicitud."""

    identificacion: str  # placa o VIN
    solicitud_id: int
    estado: str  # etiqueta del estado del servicio

    @property
    def clave(self) -> str:
        return f"{self.identificacion}@{self.solicitud_id}"


def duplicados_activos(
    vehiculos: Iterable[DatosVehiculo], *, excluir_solicitud: int | None = None
) -> list[Duplicado]:
    """Servicios activos (no terminales) de los mismos vehículos, por placa o VIN, en otras
    solicitudes que no estén cerradas como no concretadas. Solo advierte: no bloquea."""
    vehiculos = [v for v in vehiculos if not v.quitar]
    placas = {v.placa for v in vehiculos if v.placa}
    vins = {v.vin for v in vehiculos if v.vin}
    if not placas and not vins:
        return []
    servicios = (
        Servicio.objects.filter(Q(vehiculo__placa__in=placas) | Q(vehiculo__vin__in=vins))
        .exclude(estado__in=[estado.value for estado in TERMINALES])
        .exclude(solicitud__estado_registro=EstadoRegistro.NO_CONCRETADA)
        .select_related("vehiculo")
        .order_by("solicitud_id", "pk")
    )
    if excluir_solicitud is not None:
        servicios = servicios.exclude(solicitud_id=excluir_solicitud)
    duplicados = {}
    for servicio in servicios:
        placa, vin = servicio.vehiculo.placa, servicio.vehiculo.vin
        identificacion = placa if placa in placas else vin
        duplicado = Duplicado(identificacion, servicio.solicitud_id, servicio.get_estado_display())
        duplicados.setdefault(duplicado.clave, duplicado)
    return list(duplicados.values())


# --- Registrar y completar ---------------------------------------------------------------------


def registrar_solicitud(
    datos: DatosRegistro, *, usuario, abrir: bool = True
) -> tuple[Solicitud, list[Faltante]]:
    """Guarda la solicitud. Queda abierta si `abrir` y no le falta nada; si no, borrador.

    Devuelve la solicitud y lo que le falta para quedar abierta (vacío si nada). Cada vehículo
    tiene su servicio pendiente de asignar también en un borrador, para no perder lo digitado: un
    servicio de un borrador no se puede asignar (`operaciones.asignar` lo impide).
    """
    with transaction.atomic():
        solicitante = datos.solicitante or _crear_cliente(datos.cliente_nuevo)
        solicitud = Solicitud(creada_por=usuario, estado_registro=EstadoRegistro.BORRADOR)
        _cargar(solicitud, datos, solicitante)
        solicitud.save()
        _guardar_vehiculos(solicitud, datos.vehiculos, usuario=usuario)
        faltantes = _abrir_si_completa(solicitud, abrir)
    return solicitud, faltantes


def completar_borrador(
    solicitud: Solicitud, datos: DatosRegistro, *, usuario, abrir: bool = True
) -> tuple[Solicitud, list[Faltante]]:
    """Guarda lo digitado sobre un borrador; queda abierta si `abrir` y ya no le falta nada.

    Solo borradores (SolicitudNoEditable si no): una solicitud abierta no se edita aquí. La fila
    de la solicitud queda bloqueada hasta el final, para que dos personas no la completen a la vez.
    """
    with transaction.atomic():
        bloqueada = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
        if bloqueada.estado_registro != EstadoRegistro.BORRADOR:
            raise SolicitudNoEditable("Solo un borrador se completa; esta solicitud ya no lo es.")
        solicitante = datos.solicitante or _crear_cliente(datos.cliente_nuevo)
        _cargar(bloqueada, datos, solicitante)
        bloqueada.save()
        _guardar_vehiculos(bloqueada, datos.vehiculos, usuario=usuario)
        faltantes = _abrir_si_completa(bloqueada, abrir)
    return bloqueada, faltantes


def _cargar(solicitud: Solicitud, datos: DatosRegistro, solicitante: Cliente) -> None:
    """Pasa lo digitado a la solicitud (sin guardar). El regreso solo se guarda en un evento."""
    es_evento = datos.tipo == TipoServicio.EVENTO
    solicitud.solicitante = solicitante
    solicitud.pagador = datos.pagador or solicitante
    solicitud.tipo = datos.tipo
    solicitud.origen = datos.origen.strip()
    solicitud.destino = datos.destino.strip()
    solicitud.contacto_origen = _contacto(datos.contacto_origen)
    solicitud.contacto_destino = _contacto(datos.contacto_destino)
    solicitud.programada_para = datos.programada_para
    solicitud.tiene_regreso = datos.tiene_regreso if es_evento else None
    solicitud.fecha_regreso = datos.fecha_regreso if es_evento and datos.tiene_regreso else None


def _guardar_vehiculos(solicitud: Solicitud, vehiculos: Iterable[DatosVehiculo], *, usuario):
    """Un servicio por vehículo: edita los del borrador, crea los nuevos y cancela los quitados."""
    del_borrador = {s.pk: s for s in servicios_de_ida(solicitud).select_for_update()}
    for datos in vehiculos:
        if datos.servicio_id is not None:
            servicio = del_borrador.get(datos.servicio_id)
            if servicio is None:
                raise ValueError(f"El servicio {datos.servicio_id} no es de esta solicitud.")
            if datos.quitar:
                operaciones.cambiar_estado(
                    servicio, Estado.CANCELADO, actor=usuario, motivo=MOTIVO_QUITADO
                )
                continue
            servicio.vehiculo = _vehiculo_del_servicio(servicio, datos)
            servicio.referencia_externa = datos.referencia_externa.strip()
            servicio.save(update_fields=["vehiculo", "referencia_externa"])
        elif datos.tiene_datos and not datos.quitar:
            _crear_servicio(solicitud, _vehiculo(datos), datos.referencia_externa.strip())


def _abrir_si_completa(solicitud: Solicitud, abrir: bool) -> list[Faltante]:
    """Si `abrir` y no falta nada, la deja abierta y, en un evento con regreso, crea por cada
    vehículo su servicio de regreso enlazado al de ida."""
    faltantes = faltantes_de(solicitud)
    if abrir and not faltantes:
        solicitud.estado_registro = EstadoRegistro.ABIERTA
        solicitud.save(update_fields=["estado_registro"])
        if crea_regreso(solicitud.tipo, solicitud.tiene_regreso):
            for ida in servicios_de_ida(solicitud):
                Servicio.objects.create(
                    solicitud=solicitud,
                    vehiculo_id=ida.vehiculo_id,
                    referencia_externa=ida.referencia_externa,
                    regreso_de=ida,
                )
    return faltantes


# --- No concretada -----------------------------------------------------------------------------


def puede_cerrarse_no_concretada(solicitud: Solicitud) -> bool:
    """Para mostrar u ocultar la opción en el detalle (la regla es del núcleo)."""
    try:
        _verificar_cierre(solicitud, motivo="consulta")
    except CierreNoPermitido:
        return False
    return True


def cerrar_no_concretada(solicitud: Solicitud, *, motivo: str, detalle: str = "") -> Solicitud:
    """Cierra como no concretada una solicitud (borrador o abierta) que nunca se asignó.

    Bloquea la solicitud y las filas de sus servicios: una asignación simultánea espera y, al
    seguir, ve la solicitud cerrada (`operaciones.asignar` vuelve a leerla); o, si asignó primero,
    el cierre ve el servicio asignado y se rechaza. Lanza `nucleo.registro.CierreNoPermitido`.
    Los servicios no se cancelan: "no concretada" es de la solicitud y es distinto de "Cancelado".
    """
    with transaction.atomic():
        bloqueada = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
        list(Servicio.objects.select_for_update().filter(solicitud=bloqueada))
        _verificar_cierre(bloqueada, motivo=motivo)
        bloqueada.estado_registro = EstadoRegistro.NO_CONCRETADA
        bloqueada.motivo_no_concretada = motivo
        bloqueada.detalle_no_concretada = detalle.strip()
        bloqueada.save(
            update_fields=["estado_registro", "motivo_no_concretada", "detalle_no_concretada"]
        )
    solicitud.refresh_from_db()
    return solicitud


def _verificar_cierre(solicitud: Solicitud, *, motivo: str) -> None:
    servicios = Servicio.objects.filter(solicitud=solicitud)
    verificar_cierre_no_concretada(
        ya_no_concretada=solicitud.estado_registro == EstadoRegistro.NO_CONCRETADA,
        estados=[Estado(e) for e in servicios.values_list("estado", flat=True)],
        alguno_fue_asignado=EventoEstado.objects.filter(
            servicio__solicitud=solicitud, destino=Estado.ASIGNADO.value
        ).exists(),
        motivo=motivo,
    )


# --- Apoyo -------------------------------------------------------------------------------------


def _crear_cliente(nuevo: ClienteNuevo) -> Cliente:
    cliente = Cliente.objects.create(nombre=nuevo.nombre.strip(), tipo=nuevo.tipo)
    TelefonoCliente.objects.create(cliente=cliente, numero=nuevo.telefono)
    return cliente


def _contacto(datos: DatosContacto | None) -> Contacto | None:
    """El contacto ya guardado con ese nombre y teléfono, o uno nuevo."""
    if datos is None:
        return None
    nombre = datos.nombre.strip()
    existente = Contacto.objects.filter(telefono=datos.telefono, nombre__iexact=nombre).first()
    return existente or Contacto.objects.create(nombre=nombre, telefono=datos.telefono)


def _vehiculo(datos: DatosVehiculo) -> Vehiculo:
    """El vehículo guardado (completando lo que le faltaba) o uno nuevo."""
    vehiculo = vehiculo_existente(datos.placa, datos.vin)
    if vehiculo is None:
        return Vehiculo.objects.create(
            placa=datos.placa,
            vin=datos.vin,
            marca=datos.marca.strip(),
            linea=datos.linea.strip(),
            color=datos.color.strip(),
        )
    cambios = []
    for campo in ("placa", "vin", "marca", "linea", "color"):
        nuevo = getattr(datos, campo).strip()
        if nuevo and not getattr(vehiculo, campo):
            setattr(vehiculo, campo, nuevo)
            cambios.append(campo)
    if cambios:
        vehiculo.save(update_fields=cambios)
    return vehiculo


def _vehiculo_del_servicio(servicio: Servicio, datos: DatosVehiculo) -> Vehiculo:
    """El vehículo de una fila que edita un servicio del borrador.

    Con placa o VIN, el vehículo de esa placa o VIN (guardado o nuevo). Sin ninguno de los dos,
    si el vehículo actual tampoco los tiene, se corrigen ahí marca, línea y color: un vehículo sin
    placa ni VIN solo se alcanza por este servicio, y así no se crea otro en cada edición.
    """
    actual = servicio.vehiculo
    if datos.placa or datos.vin or actual.placa or actual.vin:
        return _vehiculo(datos)
    actual.marca, actual.linea, actual.color = (
        datos.marca.strip(),
        datos.linea.strip(),
        datos.color.strip(),
    )
    actual.save(update_fields=["marca", "linea", "color"])
    return actual


def _crear_servicio(solicitud: Solicitud, vehiculo: Vehiculo, referencia: str = "") -> Servicio:
    return Servicio.objects.create(
        solicitud=solicitud, vehiculo=vehiculo, referencia_externa=referencia
    )
