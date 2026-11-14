// Las fotos de evidencia en el celular: el paso (Recogido o Entregado) que el conductor está
// preparando, y la cola de fotos por subir.
//
// Reglas:
// - De cada foto la base guarda solo la ruta. El JPEG, ya comprimido, vive en una carpeta privada
//   de la app (junto a la base, no en la caché, que Android puede vaciar). Aquí nunca se leen sus
//   bytes: solo se mueve, se mide y se borra el archivo.
// - La pantalla de Recogido o Entregado se guarda a medida que avanza (`pasos_en_curso` y las
//   fotos en borrador): si Android mata la app al abrir la cámara, al volver todo está aquí.
// - Al marcar el paso, en la misma transacción que guarda el evento, sus fotos entran a la cola
//   (dejan de ser borrador) y el paso se borra. Sin el mínimo de fotos o sin el nombre de quien
//   entrega o recibe, el evento no se guarda.
// - Una foto se sube después de que su evento tuvo respuesta definitiva, solo con el token de
//   quien la tomó, y su archivo se borra solo después de confirmada la subida.
//
// Aquí no hay red: de subir se encarga `subidor_fotos.dart`.

import 'dart:io';

import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

import '../asignaciones/requisitos.dart';
import '../base_local.dart';
import '../cola/cola_eventos.dart';
import '../cola/evento.dart';
import 'foto.dart';

/// Lo que hay de fotos en el celular, para los indicadores.
class ResumenDeFotos {
  const ResumenDeFotos({
    this.pendientes = 0,
    this.listas = 0,
    this.ajenas = 0,
    this.porServicio = const {},
    this.conProblema = const [],
  });

  /// Fotos del conductor que aún no están en el servidor.
  final int pendientes;

  /// De esas, las que ya se pueden subir (su evento ya tuvo respuesta definitiva).
  final int listas;

  /// Fotos sin subir de otros conductores: no se suben con la sesión actual.
  final int ajenas;

  /// Fotos pendientes del conductor por servicio.
  final Map<int, int> porServicio;

  /// Fotos del conductor que el servidor rechazó y que él no ha dado por vistas.
  final List<FotoLocal> conProblema;
}

/// Solo las fotos que ya se pueden subir: pasaron de borrador a la cola y su evento ya no está
/// pendiente por enviar. Así la foto llega cuando el servidor ya conoce el toque del conductor.
const String _listaParaSubir =
    "f.borrador = 0 AND f.estado_envio = 'pendiente' AND NOT EXISTS ("
    'SELECT 1 FROM eventos_pendientes e '
    "WHERE e.id = f.evento_id AND e.estado_envio = 'pendiente')";

class AlmacenFotos {
  AlmacenFotos(this.base, {String? carpeta}) : _carpetaFija = carpeta;

  final BaseLocal base;
  final String? _carpetaFija;

  /// Donde se guardan los JPEG: una carpeta `fotos` junto a la base local, en el almacenamiento
  /// privado de la app.
  String get carpeta => _carpetaFija ?? '${File(base.db.path).parent.path}/fotos';

  // ---------- el paso en curso ----------

  /// El paso de [destino] que [conductorId] está preparando para ese servicio. Si no había, lo
  /// crea con el UUID que llevará el evento.
  Future<PasoEnCurso> abrirPaso({
    required int conductorId,
    required int servicioId,
    required String destino,
    required DateTime hora,
  }) {
    // Solo Recogido y Entregado llevan fotos.
    TipoFoto.para(destino);
    return base.db.transaction((txn) async {
      final guardado = await _leerPaso(txn, conductorId, servicioId, destino);
      if (guardado != null) return guardado;
      final eventoId = const Uuid().v4();
      await txn.insert('pasos_en_curso', {
        'conductor_id': conductorId,
        'servicio_id': servicioId,
        'destino': destino,
        'evento_id': eventoId,
        'creado_en': hora.toUtc().toIso8601String(),
      });
      return PasoEnCurso(
        conductorId: conductorId,
        servicioId: servicioId,
        destino: destino,
        eventoId: eventoId,
      );
    });
  }

  /// El paso guardado con sus fotos, o null si no hay ninguno en curso.
  Future<PasoEnCurso?> leerPaso({
    required int conductorId,
    required int servicioId,
    required String destino,
  }) => _leerPaso(base.db, conductorId, servicioId, destino);

  Future<PasoEnCurso?> _leerPaso(
    DatabaseExecutor en,
    int conductorId,
    int servicioId,
    String destino,
  ) async {
    final filas = await en.query(
      'pasos_en_curso',
      where: 'conductor_id = ? AND servicio_id = ? AND destino = ?',
      whereArgs: [conductorId, servicioId, destino],
    );
    if (filas.isEmpty) return null;
    final fila = filas.first;
    final eventoId = fila['evento_id']! as String;
    final fotos = await en.query(
      'fotos_pendientes',
      where: 'evento_id = ? AND borrador = 1',
      whereArgs: [eventoId],
      orderBy: 'creado_en, rowid',
    );
    return PasoEnCurso(
      conductorId: conductorId,
      servicioId: servicioId,
      destino: destino,
      eventoId: eventoId,
      nombreQuien: fila['nombre_quien']! as String,
      fotos: [for (final foto in fotos) FotoLocal.desdeFila(foto)],
    );
  }

  /// Guarda el nombre de quien entrega o recibe tal como va escrito.
  Future<void> guardarNombre(PasoEnCurso paso, String nombre) => base.db.update(
    'pasos_en_curso',
    {'nombre_quien': nombre},
    where: 'evento_id = ?',
    whereArgs: [paso.eventoId],
  );

  /// Se va a abrir la cámara desde este paso. Si Android mata la app mientras está abierta, la
  /// foto se le entrega a este paso al volver ([entregarFotoPerdida]).
  Future<void> camaraAbierta(PasoEnCurso paso, {required DateTime hora}) => base.db.update(
    'pasos_en_curso',
    {'camara_abierta_en': hora.toUtc().toIso8601String()},
    where: 'evento_id = ?',
    whereArgs: [paso.eventoId],
  );

  /// La cámara se cerró sin foto (el conductor canceló).
  Future<void> camaraCerrada(PasoEnCurso paso) => base.db.update(
    'pasos_en_curso',
    {'camara_abierta_en': null},
    where: 'evento_id = ?',
    whereArgs: [paso.eventoId],
  );

  /// Agrega al paso la foto que la cámara dejó, ya comprimida, en [rutaTemporal]: comprueba que
  /// sea un JPEG bajo el tope del servidor, le da su UUID y la mueve a la carpeta de fotos. Lanza
  /// [FotoNoValida] (y borra el archivo temporal) si no sirve.
  Future<FotoLocal> agregarFoto(
    PasoEnCurso paso,
    String rutaTemporal, {
    required DateTime hora,
  }) async {
    final temporal = File(rutaTemporal);
    _comprobar(temporal);
    final id = const Uuid().v4();
    final destino = File('$carpeta/$id.jpg');
    // Primero el archivo y después la fila: una fila nunca apunta a una foto que no está.
    _mover(temporal, destino);
    try {
      return await base.db.transaction((txn) async {
        final abierto = await txn.query(
          'pasos_en_curso',
          columns: ['evento_id'],
          where: 'evento_id = ?',
          whereArgs: [paso.eventoId],
        );
        if (abierto.isEmpty) {
          throw const FotoNoValida('Ese paso ya se marcó: la foto no se agregó.');
        }
        final servicio = await txn.query(
          'servicios',
          columns: ['vehiculo_placa', 'vehiculo_vin'],
          where: 'id = ?',
          whereArgs: [paso.servicioId],
        );
        final fila = {
          'id': id,
          'conductor_id': paso.conductorId,
          'servicio_id': paso.servicioId,
          'evento_id': paso.eventoId,
          'tipo': TipoFoto.para(paso.destino),
          'ruta': destino.path,
          'estado_envio': EstadoFoto.pendiente,
          'borrador': 1,
          'vehiculo': servicio.isEmpty
              ? null
              : servicio.first['vehiculo_placa'] ?? servicio.first['vehiculo_vin'],
          'creado_en': hora.toUtc().toIso8601String(),
        };
        await txn.insert('fotos_pendientes', fila);
        await txn.update(
          'pasos_en_curso',
          {'camara_abierta_en': null},
          where: 'evento_id = ?',
          whereArgs: [paso.eventoId],
        );
        return FotoLocal.desdeFila(fila);
      });
    } catch (_) {
      _borrar(destino);
      rethrow;
    }
  }

  /// Quita una foto del paso que aún no se ha marcado (por ejemplo, salió movida) y borra su
  /// archivo. Una foto que ya entró a la cola no se quita.
  Future<void> quitarFoto(FotoLocal foto) async {
    final quitadas = await base.db.delete(
      'fotos_pendientes',
      where: 'id = ? AND borrador = 1',
      whereArgs: [foto.id],
    );
    if (quitadas > 0) _borrar(File(foto.ruta));
  }

  /// La cámara entregó en [ruta] una foto que nadie esperaba: Android mató la app con la cámara
  /// abierta y la foto llegó al volver. Se agrega al paso desde el que se abrió la cámara. Con
  /// [ruta] en null no había foto perdida: solo se olvida que la cámara estaba abierta.
  Future<FotoLocal?> entregarFotoPerdida(String? ruta, {required DateTime hora}) async {
    final filas = await base.db.query(
      'pasos_en_curso',
      where: 'camara_abierta_en IS NOT NULL',
      orderBy: 'camara_abierta_en DESC',
    );
    if (filas.isEmpty) {
      // Nadie la espera: no se sabe de qué paso es.
      if (ruta != null) _borrar(File(ruta));
      return null;
    }
    final fila = filas.first;
    final paso = PasoEnCurso(
      conductorId: fila['conductor_id']! as int,
      servicioId: fila['servicio_id']! as int,
      destino: fila['destino']! as String,
      eventoId: fila['evento_id']! as String,
    );
    if (ruta == null) {
      await base.db.update('pasos_en_curso', {'camara_abierta_en': null});
      return null;
    }
    try {
      return await agregarFoto(paso, ruta, hora: hora);
    } on FotoNoValida {
      await camaraCerrada(paso);
      return null;
    }
  }

  /// Parte de la transacción que guarda el evento de un Recogido o un Entregado (ver
  /// `ColaEventos.encolar`): comprueba el mínimo de fotos y el nombre, pasa las fotos del paso a
  /// la cola de subida y borra el paso. Si falta algo lanza [ToqueNoValido] y no se guarda nada.
  Future<void> confirmar(Transaction txn, EventoLocal evento, {required int minimoFotos}) async {
    final paso = await txn.query(
      'pasos_en_curso',
      columns: ['evento_id'],
      where: 'evento_id = ? AND conductor_id = ? AND servicio_id = ? AND destino = ?',
      whereArgs: [evento.id, evento.conductorId, evento.servicioId, evento.destino],
    );
    if (paso.isEmpty) {
      throw const ToqueNoValido(
        'Ese paso ya no está abierto. Vuelva al servicio e intente de nuevo.',
      );
    }
    final fotos =
        Sqflite.firstIntValue(
          await txn.rawQuery(
            'SELECT COUNT(*) FROM fotos_pendientes WHERE evento_id = ? AND borrador = 1',
            [evento.id],
          ),
        ) ??
        0;
    final faltantes = faltantesDelPaso(
      destino: evento.destino,
      fotos: fotos,
      minimoFotos: minimoFotos,
      nombreQuien: evento.nombreQuien,
    );
    if (faltantes.isNotEmpty) throw ToqueNoValido(faltantes.join(' '));
    await txn.update(
      'fotos_pendientes',
      {'borrador': 0},
      where: 'evento_id = ? AND borrador = 1',
      whereArgs: [evento.id],
    );
    await txn.delete('pasos_en_curso', where: 'evento_id = ?', whereArgs: [evento.id]);
  }

  // ---------- la cola de subida ----------

  /// La foto de [conductorId] que sigue por subir (la más antigua de las que ya se pueden subir), o
  /// null si no hay.
  Future<FotoLocal?> siguientePorSubir(int conductorId) async {
    final filas = await base.db.rawQuery(
      'SELECT f.* FROM fotos_pendientes f WHERE f.conductor_id = ? AND $_listaParaSubir '
      'ORDER BY f.creado_en, f.rowid LIMIT 1',
      [conductorId],
    );
    return filas.isEmpty ? null : FotoLocal.desdeFila(filas.first);
  }

  /// El servidor confirmó que tiene la foto (201 guardada o 200 repetida). El archivo se borra
  /// después, con [borrarArchivosSubidos].
  Future<void> marcarSubida(String id, {required DateTime hora}) => base.db.update(
    'fotos_pendientes',
    {'estado_envio': EstadoFoto.subida, 'error': null, 'subida_en': hora.toUtc().toIso8601String()},
    where: "id = ? AND estado_envio = 'pendiente'",
    whereArgs: [id],
  );

  /// El servidor rechazó la foto de forma definitiva: no se reintenta y queda a la vista con
  /// [mensaje]. El archivo se conserva (la subida no se confirmó).
  Future<void> marcarError(String id, String mensaje) => base.db.update(
    'fotos_pendientes',
    {'estado_envio': EstadoFoto.error, 'error': mensaje},
    where: "id = ? AND estado_envio = 'pendiente'",
    whereArgs: [id],
  );

  /// Borra del celular los archivos de las fotos cuya subida ya confirmó el servidor, y solo esos.
  /// Si la app muere entre confirmar y borrar, se borran en la siguiente pasada. Devuelve cuántos
  /// borró.
  Future<int> borrarArchivosSubidos({required DateTime hora}) async {
    final filas = await base.db.query(
      'fotos_pendientes',
      columns: ['id', 'ruta'],
      where: "estado_envio = 'subida' AND archivo_borrado_en IS NULL",
    );
    for (final fila in filas) {
      _borrar(File(fila['ruta']! as String));
      await base.db.update(
        'fotos_pendientes',
        {'archivo_borrado_en': hora.toUtc().toIso8601String()},
        where: 'id = ?',
        whereArgs: [fila['id']],
      );
    }
    return filas.length;
  }

  /// El conductor tocó "Entendido" en el aviso de una foto rechazada. La foto sigue guardada.
  Future<void> marcarVista(String id, {required DateTime hora}) => base.db.update(
    'fotos_pendientes',
    {'visto_en': hora.toUtc().toIso8601String()},
    where: 'id = ? AND visto_en IS NULL',
    whereArgs: [id],
  );

  /// Lo que hay por subir y lo que el servidor rechazó, para el conductor [conductorId] (el de la
  /// sesión, o el último que ingresó). Todo de un mismo instante.
  Future<ResumenDeFotos> resumen(int? conductorId) {
    return base.db.transaction((txn) async {
      final porConductor = await txn.rawQuery(
        'SELECT conductor_id, servicio_id, COUNT(*) AS cantidad FROM fotos_pendientes '
        "WHERE borrador = 0 AND estado_envio = 'pendiente' GROUP BY conductor_id, servicio_id",
      );
      var ajenas = 0;
      final porServicio = <int, int>{};
      for (final fila in porConductor) {
        final cantidad = fila['cantidad']! as int;
        if (fila['conductor_id'] == conductorId) {
          porServicio[fila['servicio_id']! as int] = cantidad;
        } else {
          ajenas += cantidad;
        }
      }
      if (conductorId == null) return ResumenDeFotos(ajenas: ajenas);
      final listas = Sqflite.firstIntValue(
        await txn.rawQuery(
          'SELECT COUNT(*) FROM fotos_pendientes f WHERE f.conductor_id = ? AND $_listaParaSubir',
          [conductorId],
        ),
      );
      final conProblema = await txn.query(
        'fotos_pendientes',
        where: "estado_envio = 'error' AND visto_en IS NULL AND conductor_id = ?",
        whereArgs: [conductorId],
        orderBy: 'creado_en, rowid',
      );
      return ResumenDeFotos(
        pendientes: porServicio.values.fold(0, (suma, cantidad) => suma + cantidad),
        listas: listas ?? 0,
        ajenas: ajenas,
        porServicio: porServicio,
        conProblema: [for (final fila in conProblema) FotoLocal.desdeFila(fila)],
      );
    });
  }

  // ---------- archivos ----------
  //
  // Operaciones cortas y síncronas sobre el archivo (existe, cuánto pesa, moverlo, borrarlo). Los
  // bytes de la foto no pasan por aquí, salvo los tres primeros, para saber si es un JPEG.

  void _comprobar(File archivo) {
    if (!archivo.existsSync()) {
      throw const FotoNoValida('La cámara no dejó la foto. Tómela de nuevo.');
    }
    final tamano = archivo.lengthSync();
    final lector = archivo.openSync();
    final List<int> cabecera;
    try {
      cabecera = lector.readSync(marcaJpeg.length);
    } finally {
      lector.closeSync();
    }
    if (!esJpeg(cabecera)) {
      _borrar(archivo);
      throw const FotoNoValida('La foto no quedó guardada como JPEG. Tómela de nuevo.');
    }
    if (excedeElTamano(tamano)) {
      _borrar(archivo);
      throw const FotoNoValida('La foto pesa demasiado para enviarla. Tómela de nuevo.');
    }
  }

  void _mover(File origen, File destino) {
    destino.parent.createSync(recursive: true);
    try {
      origen.renameSync(destino.path);
    } on FileSystemException {
      // Otro sistema de archivos: se copia (lo hace el sistema, sin cargarla en memoria) y se
      // borra el original.
      origen.copySync(destino.path);
      _borrar(origen);
    }
  }

  void _borrar(File archivo) {
    try {
      if (archivo.existsSync()) archivo.deleteSync();
    } on FileSystemException {
      // No se pudo borrar ahora: no es motivo para fallar. Queda ocupando espacio.
    }
  }
}
