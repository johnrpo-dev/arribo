// Una foto de evidencia guardada en el celular, y el paso (Recogido o Entregado) que el conductor
// está preparando.
//
// De la foto, la base solo guarda la ruta del JPEG en el disco: los bytes nunca entran a la base
// ni se retienen en memoria. Los límites (solo JPEG, máximo 5 MB, a qué evento acompaña cada tipo)
// son copia de backend/nucleo/evidencia.py y cumplen los casos de docs/casos-reglas.json.

import '../asignaciones/estados.dart';

/// Tope del servidor para una foto (`TAMANO_MAXIMO_FOTO`). La app comprime muy por debajo.
const int tamanoMaximoFoto = 5 * 1024 * 1024;

/// Como empieza un JPEG (`MARCA_JPEG`).
const List<int> marcaJpeg = [0xFF, 0xD8, 0xFF];

/// Se mira el contenido, no el nombre del archivo (`es_jpeg`).
bool esJpeg(List<int> primerosBytes) {
  if (primerosBytes.length < marcaJpeg.length) return false;
  for (var i = 0; i < marcaJpeg.length; i++) {
    if (primerosBytes[i] != marcaJpeg[i]) return false;
  }
  return true;
}

bool excedeElTamano(int bytes) => bytes > tamanoMaximoFoto;

/// El `tipo` de `PUT /api/v1/evidencias/<uuid>/`.
abstract final class TipoFoto {
  static const recogida = 'recogida';
  static const entrega = 'entrega';

  /// Tipo de foto → evento al que acompaña (`EVENTO_QUE_ACOMPANA`).
  static const eventoQueAcompana = {recogida: Estado.recogido, entrega: Estado.entregado};

  /// El tipo de las fotos de un Recogido o de un Entregado.
  static String para(String destino) => switch (destino) {
    Estado.recogido => recogida,
    Estado.entregado => entrega,
    _ => throw ArgumentError.value(destino, 'destino', 'Solo Recogido y Entregado llevan fotos'),
  };
}

/// ¿Una foto de ese [tipo] acompaña a un evento con ese [destino]? (`acompana`)
bool acompana(String tipo, String destino) => TipoFoto.eventoQueAcompana[tipo] == destino;

/// En qué va la subida de una foto (`estado_envio`).
abstract final class EstadoFoto {
  /// Aún no está en el servidor: se sube (o se vuelve a subir) cuando haya señal.
  static const pendiente = 'pendiente';

  /// El servidor confirmó que la tiene. Solo entonces se borra el archivo del celular.
  static const subida = 'subida';

  /// El servidor la rechazó de forma definitiva (por ejemplo 413 o 409): no se reintenta, queda a
  /// la vista como problema y el archivo sigue en el celular.
  static const error = 'error';
}

class FotoLocal {
  const FotoLocal({
    required this.id,
    required this.conductorId,
    required this.servicioId,
    required this.eventoId,
    required this.tipo,
    required this.ruta,
    required this.creadoEn,
    this.estadoEnvio = EstadoFoto.pendiente,
    this.borrador = false,
    this.vehiculo,
    this.error,
    this.subidaEn,
    this.archivoBorradoEn,
    this.vistoEn,
  });

  /// UUID v4 generado en el celular al tomar la foto: el de la ruta `PUT /evidencias/<id>/`.
  final String id;

  /// Quien la tomó. Solo se sube con el token de ese conductor.
  final int conductorId;
  final int servicioId;

  /// El evento de Recogido o Entregado al que acompaña.
  final String eventoId;

  /// `recogida` o `entrega`.
  final String tipo;

  /// Dónde está el JPEG comprimido, en el almacenamiento privado de la app.
  final String ruta;

  final String estadoEnvio;

  /// El conductor todavía no ha marcado el paso: la foto es de la pantalla de Recogido o Entregado
  /// y no se sube.
  final bool borrador;

  /// Placa o VIN del vehículo al tomarla, para nombrarlo aunque el servicio salga de la lista.
  final String? vehiculo;

  /// Por qué el servidor la rechazó, en español.
  final String? error;

  final DateTime creadoEn;
  final DateTime? subidaEn;

  /// Cuándo se borró el archivo del celular (después de confirmada la subida).
  final DateTime? archivoBorradoEn;

  /// Cuándo el conductor dio por visto el aviso de una foto rechazada.
  final DateTime? vistoEn;

  factory FotoLocal.desdeFila(Map<String, Object?> fila) => FotoLocal(
    id: fila['id']! as String,
    conductorId: fila['conductor_id']! as int,
    servicioId: fila['servicio_id']! as int,
    eventoId: fila['evento_id']! as String,
    tipo: fila['tipo']! as String,
    ruta: fila['ruta']! as String,
    estadoEnvio: fila['estado_envio']! as String,
    borrador: fila['borrador'] == 1,
    vehiculo: fila['vehiculo'] as String?,
    error: fila['error'] as String?,
    creadoEn: DateTime.parse(fila['creado_en']! as String).toUtc(),
    subidaEn: _fecha(fila['subida_en']),
    archivoBorradoEn: _fecha(fila['archivo_borrado_en']),
    vistoEn: _fecha(fila['visto_en']),
  );
}

DateTime? _fecha(Object? texto) => texto is String ? DateTime.tryParse(texto)?.toUtc() : null;

/// La pantalla de Recogido o Entregado tal como va: las fotos tomadas y el nombre escrito. Vive en
/// la base local desde que se abre, para que nada se pierda si Android mata la app al abrir la
/// cámara.
class PasoEnCurso {
  const PasoEnCurso({
    required this.conductorId,
    required this.servicioId,
    required this.destino,
    required this.eventoId,
    this.nombreQuien = '',
    this.fotos = const [],
  });

  final int conductorId;
  final int servicioId;

  /// `recogido` o `entregado`.
  final String destino;

  /// El UUID que llevará el evento cuando se marque: las fotos se atan a él desde que se toman.
  final String eventoId;

  /// Quien entrega (Recogido) o recibe (Entregado) el vehículo, como va escrito.
  final String nombreQuien;

  /// Las fotos tomadas, de la más antigua a la más nueva.
  final List<FotoLocal> fotos;
}

/// La foto no se guardó: no es un JPEG, pesa demasiado o el archivo no está. [mensaje] es el texto
/// para el conductor.
class FotoNoValida implements Exception {
  const FotoNoValida(this.mensaje);

  final String mensaje;

  @override
  String toString() => 'FotoNoValida: $mensaje';
}
