"""Operaciones sobre servicios: la única forma de cambiar su estado, su conductor o su grúa.

Cada función corre en su propia transacción, bloquea la fila del servicio (`select_for_update`) y
deja exactamente un EventoEstado por cambio. Las reglas son las de `nucleo/`: aquí solo se cargan
los datos, se llama al núcleo y se guarda lo que decide.

- Panel: `asignar`, `reasignar`, `cambiar_estado`, `resolver_novedad`, y `mover_en_ronda` (el
  orden en que el conductor atiende sus servicios; no es un cambio de estado). Si una regla no se cumple,
  lanzan la excepción del núcleo (TransicionInvalida, CapacidadExcedida, IdentificacionIncompleta)
  o una de este módulo, y no queda ni evento ni cambio.
- App del conductor: `aplicar_evento_del_conductor` y `aplicar_lote_del_conductor`. Nunca rechazan
  lo que el conductor hizo: si no encaja, el evento se guarda como conflicto y el servicio sigue
  igual.

Cuando un servicio queda Entregado (desde el panel o la app) se envía `senales.servicio_entregado`
en la misma transacción; `cobros` la escucha para crear la línea de cobro sin que esta app lo importe.
"""
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import F

from configuracion.models import configuracion_vigente
from flota.models import Conductor, Grua, grua_vigente
from nucleo.capacidad import CapacidadExcedida, verificar_recogida
from nucleo.estados import (
    TERMINALES,
    Estado,
    Resolucion,
    TransicionInvalida,
    a_bordo,
    transicionar,
)
from nucleo.estados import Servicio as ServicioNucleo
from nucleo.estados import reasignar as reasignar_en_nucleo
from nucleo.estados import resolver_novedad as resolver_novedad_en_nucleo
from nucleo.identificacion import (
    IdentificacionIncompleta,
    MomentoIdentificacion,
    identificacion_exigida,
    validar_identificacion,
)
from nucleo.ronda import MovimientoInvalido, numerar, siguiente_orden
from nucleo.ronda import mover as mover_en_nucleo
from nucleo.sincronizacion import Evento, Resultado, aplicar_evento, ordenar

from .disponibilidad import motivos_de_bloqueo
from .models import (
    VALORES_EN_RONDA,
    EstadoRegistro,
    EventoEstado,
    OrigenEvento,
    ResultadoEvento,
    Servicio,
    Solicitud,
)
from .senales import servicio_entregado


class ConductorBloqueado(Exception):
    """El conductor no puede recibir asignaciones nuevas (ver `disponibilidad.motivos_de_bloqueo`)."""


class SinGruaVigente(ConductorBloqueado):
    """El conductor no tiene una grúa asignada en este momento."""


class SolicitudNoAsignable(Exception):
    """La solicitud es un borrador o no se concretó: sus servicios no se asignan."""


class MismoConductor(Exception):
    """Se intentó reasignar un servicio al conductor que ya lo tiene."""


def identificacion_exigida_al_asignar() -> bool:
    """¿Se exige placa o VIN ya al asignar? Lo decide la opción "Momento en que se exige placa o
    VIN" de la configuración (por defecto "Al recoger"); la regla es `identificacion_exigida`."""
    return identificacion_exigida(
        configuracion_vigente().momento_placa_vin, MomentoIdentificacion.AL_ASIGNAR
    )


# --- Panel -------------------------------------------------------------------------------------


def asignar(servicio, conductor, *, actor, motivo=None) -> EventoEstado:
    """Pendiente de asignar → Asignado. La grúa sale de la asignación vigente del conductor y
    queda guardada en el servicio (si después el conductor cambia de grúa, el servicio no cambia).
    El servicio entra al final de la ronda del conductor. Un conductor bloqueado (sin grúa, grúa
    fuera de servicio o inactiva, conductor inactivo) no recibe asignaciones.
    """
    with transaction.atomic():
        bloqueado = _bloquear(servicio)
        nuevo = transicionar(bloqueado.como_nucleo(), Estado.ASIGNADO)
        _exigir_solicitud_asignable(bloqueado)
        if identificacion_exigida_al_asignar():
            _exigir_identificacion(bloqueado)
        _pasar_al_conductor(bloqueado, conductor)
        evento = _guardar_desde_el_panel(bloqueado, nuevo, actor=actor, motivo=motivo)
    _refrescar(servicio)
    return evento


def reasignar(servicio, conductor, *, actor, motivo=None) -> EventoEstado:
    """Pasar el servicio a otro conductor antes de recoger el vehículo (queda Asignado, con la
    grúa vigente del nuevo conductor y al final de su ronda)."""
    with transaction.atomic():
        bloqueado = _bloquear(servicio)
        nuevo = reasignar_en_nucleo(bloqueado.como_nucleo())
        if bloqueado.conductor_id == _pk(conductor):
            raise MismoConductor("El servicio ya es de ese conductor: elija otro para reasignar.")
        _pasar_al_conductor(bloqueado, conductor)
        evento = _guardar_desde_el_panel(bloqueado, nuevo, actor=actor, motivo=motivo)
    _refrescar(servicio)
    return evento


def mover_en_ronda(servicio, direccion) -> list[int]:
    """Sube o baja el servicio un puesto en la ronda de su conductor y la numera de nuevo 1, 2,
    3... Devuelve la ronda (llaves de los servicios) en el orden nuevo. El orden no es un cambio de
    estado: no deja evento."""
    with transaction.atomic():
        actual = Servicio.objects.filter(pk=_pk(servicio)).values("conductor_id", "estado").get()
        if actual["conductor_id"] is None or actual["estado"] not in VALORES_EN_RONDA:
            raise MovimientoInvalido("El servicio no está en la ronda de ningún conductor.")
        # Mismo orden de bloqueo que asignar y reasignar: primero el conductor.
        Conductor.objects.select_for_update().get(pk=actual["conductor_id"])
        ronda = list(
            _ronda(actual["conductor_id"]).select_for_update().values_list("pk", flat=True)
        )
        nueva = mover_en_nucleo(ronda, _pk(servicio), direccion)
        _numerar(nueva)
    return nueva


def ronda_de(conductor) -> list[Servicio]:
    """Los servicios no terminales del conductor en el orden en que los atiende."""
    return list(_ronda(_pk(conductor)).select_related("vehiculo", "solicitud"))


def cambiar_estado(servicio, destino, *, actor, motivo=None, nombre_quien=None) -> EventoEstado:
    """Cambio de estado hecho desde el panel: cancelar o abrir una novedad (con motivo), o marcar
    en camino, recogido o entregado en nombre del conductor.

    Recogido exige la placa o el VIN del vehículo y que la grúa tenga un puesto libre.
    """
    destino = Estado(destino)
    if destino == Estado.ASIGNADO:
        raise TransicionInvalida("Para asignar un servicio se usa asignar(), que exige conductor.")
    with transaction.atomic():
        bloqueado = _bloquear(servicio)
        nuevo = transicionar(bloqueado.como_nucleo(), destino, motivo=motivo)
        if destino == Estado.RECOGIDO:
            _exigir_identificacion(bloqueado)
            _verificar_capacidad(bloqueado)
        evento = _guardar_desde_el_panel(
            bloqueado, nuevo, actor=actor, motivo=motivo, nombre_quien=nombre_quien
        )
    _refrescar(servicio)
    return evento


def resolver_novedad(servicio, resolucion, *, actor, motivo=None) -> EventoEstado:
    """Salir de una novedad: reanudar (vuelve al estado previo), reasignar (vuelve a la cola, sin
    conductor ni grúa) o cancelar (con motivo)."""
    resolucion = Resolucion(resolucion)
    with transaction.atomic():
        bloqueado = _bloquear(servicio)
        nuevo = resolver_novedad_en_nucleo(bloqueado.como_nucleo(), resolucion, motivo=motivo)
        evento = _guardar_desde_el_panel(bloqueado, nuevo, actor=actor, motivo=motivo)
    _refrescar(servicio)
    return evento


# --- App del conductor -------------------------------------------------------------------------


@dataclass(frozen=True)
class EventoDelConductor(Evento):
    """Un toque del conductor tal como llega de la app.

    Lo que el núcleo usa para decidir está en `nucleo.sincronizacion.Evento`; esto agrega lo que
    solo se guarda.
    """

    nombre_quien: str | None = None
    latitud: float | None = None
    longitud: float | None = None


def aplicar_evento_del_conductor(
    *,
    id,
    servicio,
    conductor,
    destino,
    secuencia,
    hora_dispositivo,
    motivo=None,
    nombre_quien=None,
    latitud=None,
    longitud=None,
) -> Resultado:
    """Aplica un evento de la app una sola vez y devuelve aplicado, duplicado o conflicto.

    `servicio` y `conductor` pueden ser instancias o llaves primarias. Un conflicto se guarda igual
    (con resultado "conflicto") y no cambia el servicio; la alerta a logística sale de esos eventos.
    """
    return _aplicar_evento(
        _preparar(
            id=id,
            servicio=servicio,
            conductor=conductor,
            destino=destino,
            secuencia=secuencia,
            hora_dispositivo=hora_dispositivo,
            motivo=motivo,
            nombre_quien=nombre_quien,
            latitud=latitud,
            longitud=longitud,
        )
    )


def aplicar_lote_del_conductor(eventos: Iterable[Mapping]) -> list[tuple[str, Resultado]]:
    """Aplica un lote en el orden de la secuencia del dispositivo, no en el de llegada ni el de la
    hora del celular. Cada evento va en su propia transacción. Devuelve (id, resultado) por evento.
    """
    preparados = [_preparar(**datos) for datos in eventos]
    return [(evento.id, _aplicar_evento(evento)) for evento in ordenar(preparados)]


def _preparar(
    *,
    id,
    servicio,
    conductor,
    destino,
    secuencia,
    hora_dispositivo,
    motivo=None,
    nombre_quien=None,
    latitud=None,
    longitud=None,
) -> EventoDelConductor:
    return EventoDelConductor(
        id=str(uuid.UUID(str(id))),
        servicio_id=str(_pk(servicio)),
        conductor_id=str(_pk(conductor)),
        destino=Estado(destino),
        secuencia=int(secuencia),
        hora_dispositivo=hora_dispositivo,
        motivo=motivo,
        nombre_quien=nombre_quien,
        latitud=latitud,
        longitud=longitud,
    )


def _ya_recibido(evento_id: uuid.UUID) -> bool:
    return EventoEstado.objects.filter(pk=evento_id).exists()


def _aplicar_evento(evento: EventoDelConductor) -> Resultado:
    """Idempotencia ante reenvíos y ante peticiones simultáneas con el mismo id:

    1. Si el id ya está guardado, es duplicado (el caso común: el celular reenvía el lote).
    2. Se bloquea la fila del servicio y se vuelve a mirar: dos peticiones con el mismo id sobre el
       mismo servicio quedan en fila, y la segunda ve el evento que la primera ya guardó.
    3. La garantía final es la llave primaria del evento (el id del celular): si dos peticiones
       llegan a guardarlo a la vez, la base deja entrar una sola; la otra se deshace entera, sin
       evento ni cambio de estado, y responde duplicado.
    """
    evento_id = uuid.UUID(evento.id)
    if _ya_recibido(evento_id):
        return Resultado.DUPLICADO
    conductor = Conductor.objects.get(pk=evento.conductor_id)
    try:
        with transaction.atomic():
            servicio = _bloquear(evento.servicio_id)
            recibidos = {evento.id} if _ya_recibido(evento_id) else set()
            asignado = str(servicio.conductor_id) if servicio.conductor_id is not None else None
            nuevo, resultado = aplicar_evento(servicio.como_nucleo(), asignado, evento, recibidos)
            if resultado == Resultado.DUPLICADO:
                return resultado
            capacidad_excedida = False
            if resultado == Resultado.APLICADO and evento.destino == Estado.RECOGIDO:
                try:
                    _exigir_identificacion(servicio)
                except IdentificacionIncompleta:
                    resultado = Resultado.CONFLICTO
                else:
                    try:
                        _verificar_capacidad(servicio)
                    except CapacidadExcedida:
                        # El vehículo ya está montado: el hecho físico manda. La app lo bloquea
                        # antes; esto solo pasa con un celular desactualizado.
                        capacidad_excedida = True
            EventoEstado.objects.create(
                id=evento_id,
                servicio=servicio,
                destino=evento.destino.value,
                origen=OrigenEvento.APP,
                conductor=conductor,
                secuencia=evento.secuencia,
                hora_dispositivo=evento.hora_dispositivo,
                latitud=evento.latitud,
                longitud=evento.longitud,
                motivo=(evento.motivo or "").strip(),
                nombre_quien=(evento.nombre_quien or "").strip(),
                resultado=ResultadoEvento(resultado.value),
                capacidad_excedida=capacidad_excedida,
            )
            if resultado == Resultado.APLICADO:
                _cambiar(servicio, nuevo)
    except IntegrityError:
        # Otra petición guardó el mismo id mientras esta trabajaba: esta transacción ya se
        # deshizo completa (ni evento ni cambio de estado). Se confirma en la base que el evento
        # existe; si el error fue otro, no se esconde.
        if EventoEstado.objects.filter(pk=evento_id).exists():
            return Resultado.DUPLICADO
        raise
    return resultado


# --- Apoyo -------------------------------------------------------------------------------------


def _pk(objeto):
    return getattr(objeto, "pk", objeto)


def _bloquear(servicio) -> Servicio:
    """La fila del servicio, bloqueada hasta el fin de la transacción (solo esa fila)."""
    return (
        Servicio.objects.select_for_update(of=("self",))
        .select_related("solicitud", "vehiculo")
        .get(pk=_pk(servicio))
    )


def _refrescar(servicio):
    """Quien llamó con una instancia la ve ya con el estado nuevo."""
    if isinstance(servicio, Servicio):
        servicio.refresh_from_db()


def _exigir_solicitud_asignable(servicio):
    # Se lee de nuevo, ya con la fila del servicio bloqueada: si otra petición cerró la solicitud
    # como no concretada mientras se esperaba el bloqueo, aquí se ve (cerrarla bloquea también
    # las filas de sus servicios).
    registro = (
        Solicitud.objects.filter(pk=servicio.solicitud_id)
        .values_list("estado_registro", flat=True)
        .get()
    )
    if registro == EstadoRegistro.BORRADOR:
        raise SolicitudNoAsignable(
            "La solicitud es un borrador: complete los datos obligatorios antes de asignar."
        )
    if registro == EstadoRegistro.NO_CONCRETADA:
        raise SolicitudNoAsignable("La solicitud no se concretó: sus servicios no se asignan.")


def _exigir_identificacion(servicio):
    vehiculo = servicio.vehiculo
    validar_identificacion(vehiculo.placa, vehiculo.vin, servicio.solicitud.tipo)


def _grua_vigente_o_error(conductor) -> Grua:
    grua = grua_vigente(conductor)
    if grua is None:
        nombre = conductor if isinstance(conductor, Conductor) else f"El conductor {conductor}"
        raise SinGruaVigente(
            f"{nombre} no tiene una grúa asignada en este momento. Asígnele una grúa en Flota "
            "antes de asignarle servicios."
        )
    return grua


def _pasar_al_conductor(servicio: Servicio, conductor):
    """Conductor, grúa vigente y puesto al final de la ronda, con la fila del conductor bloqueada
    (dos asignaciones simultáneas al mismo conductor toman puestos distintos)."""
    conductor = Conductor.objects.select_for_update().get(pk=_pk(conductor))
    grua = _grua_vigente_o_error(conductor)
    motivos = motivos_de_bloqueo(conductor, grua)
    if motivos:
        raise ConductorBloqueado(f"{conductor} no puede recibir servicios: {' '.join(motivos)}")
    servicio.conductor = conductor
    servicio.grua = grua
    servicio.orden_ronda = siguiente_orden(
        _ronda(conductor.pk).exclude(pk=servicio.pk).values_list("orden_ronda", flat=True)
    )


def _ronda(conductor_id):
    return Servicio.objects.filter(conductor_id=conductor_id, estado__in=VALORES_EN_RONDA).order_by(
        F("orden_ronda").asc(nulls_last=True), "pk"
    )


def _numerar(ronda: list[int]):
    """Fija los puestos 1, 2, 3... Primero se vacían, para no chocar con la restricción de puesto
    único mientras se renumera."""
    Servicio.objects.filter(pk__in=ronda).update(orden_ronda=None)
    for pk, puesto in numerar(ronda).items():
        Servicio.objects.filter(pk=pk).update(orden_ronda=puesto)


def _verificar_capacidad(servicio):
    """Antes de marcar Recogido: la grúa del servicio no lleva ya tantos vehículos como puestos.

    Se bloquea la grúa para que dos recogidas simultáneas en la misma grúa se cuenten una tras otra.
    """
    grua = Grua.objects.select_for_update().get(pk=servicio.grua_id)
    # Un servicio terminado nunca está a bordo; entre los demás, decide nucleo.estados.a_bordo.
    activos = (
        Servicio.objects.filter(grua=grua)
        .exclude(pk=servicio.pk)
        .exclude(estado__in=[estado.value for estado in TERMINALES])
        .select_related("vehiculo")
        .order_by("pk")
    )
    montados = [str(otro) for otro in activos if a_bordo(otro.como_nucleo())]
    verificar_recogida(grua.capacidad, montados)


def _cambiar(servicio: Servicio, nuevo: ServicioNucleo, *, actor=None):
    """El punto único donde se guarda un cambio de estado (panel y app).

    Al quedar Entregado avisa con `servicio_entregado` dentro de la misma transacción: si un
    receptor falla (por ejemplo, la creación de la línea de cobro), todo se deshace.
    """
    queda_entregado = nuevo.estado == Estado.ENTREGADO and servicio.estado != Estado.ENTREGADO
    servicio.estado = nuevo.estado.value
    servicio.estado_previo = nuevo.estado_previo.value if nuevo.estado_previo else ""
    if nuevo.estado == Estado.PENDIENTE_ASIGNAR:
        servicio.conductor = None
        servicio.grua = None
        servicio.orden_ronda = None  # vuelve a la cola: deja la ronda
    servicio._guardar_cambio_operativo()
    if queda_entregado:
        servicio_entregado.send(sender=Servicio, servicio=servicio, actor=actor)


def _guardar_desde_el_panel(
    servicio: Servicio, nuevo: ServicioNucleo, *, actor, motivo=None, nombre_quien=None
) -> EventoEstado:
    _cambiar(servicio, nuevo, actor=actor)
    return EventoEstado.objects.create(
        servicio=servicio,
        destino=nuevo.estado.value,
        origen=OrigenEvento.PANEL,
        actor=actor,
        conductor_id=servicio.conductor_id,
        motivo=(motivo or "").strip(),
        nombre_quien=(nombre_quien or "").strip(),
        resultado=ResultadoEvento.APLICADO,
    )
