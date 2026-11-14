// Un toque del conductor (En camino, Recogido, Entregado o Novedad) guardado en la cola local.
//
// Es una fila de `eventos_pendientes`. El `id` (UUID v4) y la `secuencia` se fijan una sola vez, al
// tocar, y no cambian en ningún reenvío: así el servidor reconoce el mismo toque y no lo aplica dos
// veces. Nunca lleva valores de cobro.

/// En qué va el envío de un evento (`estado_envio`).
abstract final class EstadoEnvio {
  /// Aún no hay respuesta definitiva del servidor: se envía (o se reenvía) en el siguiente lote.
  static const pendiente = 'pendiente';

  /// El servidor lo guardó y cambió el servicio.
  static const aplicado = 'aplicado';

  /// El servidor lo guardó en el historial pero no cambió el servicio; logística recibió una alerta.
  static const conflicto = 'conflicto';

  /// El servidor no lo pudo guardar y no lo guardará; logística recibió una alerta.
  static const rechazado = 'rechazado';
}

class EventoLocal {
  const EventoLocal({
    required this.id,
    required this.conductorId,
    required this.servicioId,
    required this.destino,
    required this.secuencia,
    required this.horaDispositivo,
    required this.creadoEn,
    this.conductorNombre,
    this.vehiculo,
    this.motivo,
    this.nombreQuien,
    this.estadoEnvio = EstadoEnvio.pendiente,
    this.resultadoMotivo,
    this.resultadoDetalle,
    this.resueltoEn,
    this.vistoEn,
  });

  /// UUID v4 generado en el celular al tocar el botón.
  final String id;

  /// Quien lo tocó. Solo se envía con el token de ese conductor.
  final int conductorId;
  final String? conductorNombre;

  final int servicioId;

  /// Placa o VIN del vehículo al tocar, para nombrarlo aunque el servicio salga de la lista.
  final String? vehiculo;

  /// `en_camino`, `recogido`, `entregado` o `novedad`.
  final String destino;

  /// Contador del celular: da el orden de los toques, no la hora.
  final int secuencia;

  /// Hora del celular al tocar, en UTC.
  final DateTime horaDispositivo;

  /// Obligatorio en una novedad.
  final String? motivo;

  /// Quien entrega o recibe el vehículo (1a-13).
  final String? nombreQuien;

  final String estadoEnvio;

  /// El `motivo` y el `detalle` con que respondió el servidor (en un conflicto o un rechazo).
  final String? resultadoMotivo;
  final String? resultadoDetalle;

  final DateTime creadoEn;
  final DateTime? resueltoEn;

  /// Cuándo el conductor dio por visto el aviso de un conflicto o de un rechazo.
  final DateTime? vistoEn;

  bool get pendiente => estadoEnvio == EstadoEnvio.pendiente;

  /// El servidor respondió que este toque no cambió el servicio: se le muestra al conductor.
  bool get sinAplicar =>
      estadoEnvio == EstadoEnvio.conflicto || estadoEnvio == EstadoEnvio.rechazado;

  /// El evento como lo pide `POST /api/v1/eventos/`. El conductor no va: es el del token.
  Map<String, Object?> aJson() => {
    'id': id,
    'servicio_id': servicioId,
    'destino': destino,
    'secuencia': secuencia,
    'hora_dispositivo': horaDispositivo.toUtc().toIso8601String(),
    'motivo': motivo,
    'nombre_quien': nombreQuien,
    'latitud': null,
    'longitud': null,
  };

  Map<String, Object?> aFila() => {
    'id': id,
    'conductor_id': conductorId,
    'conductor_nombre': conductorNombre,
    'servicio_id': servicioId,
    'vehiculo': vehiculo,
    'destino': destino,
    'secuencia': secuencia,
    'hora_dispositivo': horaDispositivo.toUtc().toIso8601String(),
    'motivo': motivo,
    'nombre_quien': nombreQuien,
    'estado_envio': estadoEnvio,
    'resultado_motivo': resultadoMotivo,
    'resultado_detalle': resultadoDetalle,
    'creado_en': creadoEn.toUtc().toIso8601String(),
    'resuelto_en': resueltoEn?.toUtc().toIso8601String(),
    'visto_en': vistoEn?.toUtc().toIso8601String(),
  };

  factory EventoLocal.desdeFila(Map<String, Object?> fila) => EventoLocal(
    id: fila['id']! as String,
    conductorId: fila['conductor_id']! as int,
    conductorNombre: fila['conductor_nombre'] as String?,
    servicioId: fila['servicio_id']! as int,
    vehiculo: fila['vehiculo'] as String?,
    destino: fila['destino']! as String,
    secuencia: fila['secuencia']! as int,
    horaDispositivo: DateTime.parse(fila['hora_dispositivo']! as String).toUtc(),
    motivo: fila['motivo'] as String?,
    nombreQuien: fila['nombre_quien'] as String?,
    estadoEnvio: fila['estado_envio']! as String,
    resultadoMotivo: fila['resultado_motivo'] as String?,
    resultadoDetalle: fila['resultado_detalle'] as String?,
    creadoEn: DateTime.parse(fila['creado_en']! as String).toUtc(),
    resueltoEn: _fecha(fila['resuelto_en']),
    vistoEn: _fecha(fila['visto_en']),
  );
}

DateTime? _fecha(Object? texto) => texto is String ? DateTime.tryParse(texto)?.toUtc() : null;

/// Los cambios sin enviar de un conductor en este celular.
class PendientesDeConductor {
  const PendientesDeConductor({required this.conductorId, required this.cantidad, this.nombre});

  final int conductorId;
  final String? nombre;
  final int cantidad;
}
