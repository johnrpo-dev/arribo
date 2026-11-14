// Base local SQLite del celular: lo que el conductor necesita para trabajar sin señal.
//
// Todo lo importante vive aquí y no solo en memoria: el sistema puede matar la app en cualquier
// momento (por ejemplo, al abrir la cámara en un celular con poca memoria). El token de la API no
// va aquí: va en el almacenamiento seguro del sistema (ver `ingreso/almacen_token.dart`).
//
// Migraciones versionadas: la versión de la base es la cantidad de migraciones. Una migración ya
// publicada no se cambia nunca (puede estar aplicada en un celular); un cambio es una migración
// nueva al final de la lista.

import 'dart:convert';

import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

/// Migraciones en orden. La versión N de la base es la que tiene aplicadas las N primeras.
const List<List<String>> migraciones = [
  // Versión 1 (1a-11): estado local, asignaciones, y el esquema previsto para la cola de eventos
  // (1a-12) y las fotos pendientes (1a-13).
  [
    // Datos sueltos del celular, por clave: dispositivo_id, conductor, etag, ultima_actualizacion,
    // configuracion y, desde la 1a-12, ultima_secuencia. (La columna se llama `dato` y no `valor`
    // para que ninguna columna de la base se confunda con un valor de cobro.)
    '''
    CREATE TABLE estado_local (
      clave TEXT PRIMARY KEY NOT NULL,
      dato TEXT NOT NULL
    )
    ''',
    // Los servicios de la ronda tal como los mandó GET /api/v1/asignaciones/. `posicion` es el
    // puesto en la lista del servidor (que ya viene en orden de ronda); `orden_ronda` puede tener
    // huecos o venir vacío. Sin columnas de cobro: la API no manda valores y aquí no se guardan.
    '''
    CREATE TABLE servicios (
      id INTEGER PRIMARY KEY NOT NULL,
      posicion INTEGER NOT NULL,
      solicitud_id INTEGER NOT NULL,
      estado TEXT NOT NULL,
      estado_previo TEXT,
      tipo TEXT NOT NULL,
      es_regreso INTEGER NOT NULL CHECK (es_regreso IN (0, 1)),
      orden_ronda INTEGER,
      vehiculo_placa TEXT,
      vehiculo_vin TEXT,
      vehiculo_marca TEXT,
      vehiculo_linea TEXT,
      vehiculo_color TEXT,
      origen_direccion TEXT,
      origen_ubicacion TEXT,
      origen_contacto_nombre TEXT,
      origen_contacto_telefono TEXT,
      destino_direccion TEXT,
      destino_ubicacion TEXT,
      destino_contacto_nombre TEXT,
      destino_contacto_telefono TEXT,
      referencia_externa TEXT,
      programada_para TEXT,
      grua_id INTEGER,
      grua_placa TEXT,
      grua_capacidad INTEGER,
      a_bordo INTEGER NOT NULL CHECK (a_bordo IN (0, 1))
    )
    ''',
    // Cola de eventos (la usa la 1a-12). Cada toque del conductor es una fila que se escribe antes
    // de mostrar el cambio en pantalla. `id` es el UUID v4 generado en el celular; `secuencia` sale
    // del contador persistente `ultima_secuencia` de estado_local (solo crece, no se reinicia al
    // cerrar sesión). `conductor_id` es quien lo tocó: se envía solo con su token. La hora del
    // celular va en ISO 8601 UTC con Z. Ver conductor/README.md.
    '''
    CREATE TABLE eventos_pendientes (
      id TEXT PRIMARY KEY NOT NULL,
      conductor_id INTEGER NOT NULL,
      servicio_id INTEGER NOT NULL,
      destino TEXT NOT NULL
        CHECK (destino IN ('en_camino', 'recogido', 'entregado', 'novedad')),
      secuencia INTEGER NOT NULL UNIQUE,
      hora_dispositivo TEXT NOT NULL,
      motivo TEXT,
      nombre_quien TEXT,
      latitud REAL,
      longitud REAL,
      estado_envio TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_envio IN ('pendiente', 'aplicado', 'conflicto', 'rechazado')),
      resultado_motivo TEXT,
      resultado_detalle TEXT,
      creado_en TEXT NOT NULL,
      resuelto_en TEXT
    )
    ''',
    'CREATE INDEX eventos_pendientes_envio ON eventos_pendientes (estado_envio, secuencia)',
    // Fotos por subir (la usa la 1a-13). Solo la ruta del JPEG en el disco del celular: los bytes
    // nunca entran a la base ni se retienen en memoria. `id` es el UUID de la ruta
    // PUT /api/v1/evidencias/<id>/ y `evento_id` el del evento al que acompaña.
    '''
    CREATE TABLE fotos_pendientes (
      id TEXT PRIMARY KEY NOT NULL,
      conductor_id INTEGER NOT NULL,
      servicio_id INTEGER NOT NULL,
      evento_id TEXT NOT NULL,
      tipo TEXT NOT NULL CHECK (tipo IN ('recogida', 'entrega')),
      ruta TEXT NOT NULL,
      estado_envio TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_envio IN ('pendiente', 'subida', 'error')),
      error TEXT,
      creado_en TEXT NOT NULL,
      subida_en TEXT
    )
    ''',
    'CREATE INDEX fotos_pendientes_envio ON fotos_pendientes (estado_envio, creado_en)',
  ],
  // Versión 2 (1a-12): lo que la cola necesita para avisar sin depender de la lista, que puede
  // cambiar o borrarse antes de que el evento se envíe.
  [
    // Placa o VIN del vehículo al tocar: un conflicto se le muestra al conductor aunque el
    // servicio ya no esté en su lista (cancelado o reasignado).
    'ALTER TABLE eventos_pendientes ADD COLUMN vehiculo TEXT',
    // Nombre de quien lo tocó: si después ingresa otro conductor, se le dice de quién son los
    // cambios que siguen sin enviar.
    'ALTER TABLE eventos_pendientes ADD COLUMN conductor_nombre TEXT',
    // Cuándo el conductor tocó "Entendido" en el aviso de un conflicto o de un rechazo. El evento
    // no se borra: solo deja de mostrarse.
    'ALTER TABLE eventos_pendientes ADD COLUMN visto_en TEXT',
  ],
];

/// Nombre del archivo de la base en la carpeta de bases de datos de la app.
const String nombreArchivoBase = 'arribo.db';

/// Claves de la tabla estado_local.
abstract final class Clave {
  static const dispositivoId = 'dispositivo_id';
  static const conductor = 'conductor';
  static const etag = 'etag';
  static const ultimaActualizacion = 'ultima_actualizacion';
  static const configuracion = 'configuracion';

  /// La secuencia del último evento que se encoló en este celular. Solo crece: no se toca al
  /// cerrar sesión ni al cambiar de conductor (ver `cola/cola_eventos.dart`).
  static const ultimaSecuencia = 'ultima_secuencia';
}

class BaseLocal {
  BaseLocal._(this.db);

  final Database db;

  /// Abre (o crea) la base y aplica las migraciones que falten, cada una en la transacción de
  /// apertura de sqflite: si el celular se apaga a mitad, la versión no avanza.
  static Future<BaseLocal> abrir(
    DatabaseFactory fabrica,
    String ruta, {
    List<List<String>> migraciones = migraciones,
  }) async {
    Future<void> aplicar(Database db, int desde, int hasta) async {
      for (var version = desde; version < hasta; version++) {
        for (final sentencia in migraciones[version]) {
          await db.execute(sentencia);
        }
      }
    }

    final db = await fabrica.openDatabase(
      ruta,
      options: OpenDatabaseOptions(
        version: migraciones.length,
        onCreate: (db, version) => aplicar(db, 0, version),
        onUpgrade: (db, anterior, nueva) => aplicar(db, anterior, nueva),
        // Bajar de versión (instalar un APK más viejo encima) no se soporta: falla en vez de
        // trabajar con un esquema que la app no conoce.
        onDowngrade: _negarBajada,
      ),
    );
    return BaseLocal._(db);
  }

  static Future<void> _negarBajada(Database db, int anterior, int nueva) {
    throw StateError(
      'La base local está en la versión $anterior y esta app solo conoce hasta la $nueva. '
      'Instale la versión más reciente de la app.',
    );
  }

  Future<void> cerrar() => db.close();

  // ---------- estado_local ----------

  Future<String?> leer(String clave, {DatabaseExecutor? en}) async {
    final filas = await (en ?? db).query(
      'estado_local',
      columns: ['dato'],
      where: 'clave = ?',
      whereArgs: [clave],
    );
    return filas.isEmpty ? null : filas.first['dato'] as String;
  }

  Future<void> escribir(String clave, String dato, {DatabaseExecutor? en}) async {
    await (en ?? db).insert('estado_local', {
      'clave': clave,
      'dato': dato,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> borrar(String clave, {DatabaseExecutor? en}) async {
    await (en ?? db).delete('estado_local', where: 'clave = ?', whereArgs: [clave]);
  }

  Future<Map<String, Object?>?> leerJson(String clave, {DatabaseExecutor? en}) async {
    final texto = await leer(clave, en: en);
    if (texto == null) return null;
    final valor = jsonDecode(texto);
    return valor is Map<String, Object?> ? valor : null;
  }

  Future<void> escribirJson(String clave, Map<String, Object?> valor, {DatabaseExecutor? en}) =>
      escribir(clave, jsonEncode(valor), en: en);

  /// Identificador del celular para el contrato (`dispositivo_id`): un UUID que se genera la
  /// primera vez y se guarda. Es el mismo en cada ingreso; solo cambia si se borran los datos de la
  /// app o se reinstala.
  Future<String> dispositivoId() {
    return db.transaction((txn) async {
      final guardado = await leer(Clave.dispositivoId, en: txn);
      if (guardado != null) return guardado;
      final nuevo = const Uuid().v4();
      await escribir(Clave.dispositivoId, nuevo, en: txn);
      return nuevo;
    });
  }

  /// Eventos y fotos que el celular aún no ha entregado al servidor. Con [conductorId], solo los de
  /// ese conductor: mientras tenga alguno, la app no le cierra la sesión (el servidor toma como
  /// conductor del evento al dueño del token). Los de otro conductor no cuentan para eso: solo se
  /// envían cuando él vuelva a ingresar, y para eso este tiene que poder salir.
  Future<int> pendientesPorEnviar({int? conductorId}) async {
    final filtro = conductorId == null ? '' : ' AND conductor_id = ?';
    final argumentos = [?conductorId];
    final eventos = Sqflite.firstIntValue(
      await db.rawQuery(
        "SELECT COUNT(*) FROM eventos_pendientes WHERE estado_envio = 'pendiente'$filtro",
        argumentos,
      ),
    );
    final fotos = Sqflite.firstIntValue(
      await db.rawQuery(
        "SELECT COUNT(*) FROM fotos_pendientes WHERE estado_envio = 'pendiente'$filtro",
        argumentos,
      ),
    );
    return (eventos ?? 0) + (fotos ?? 0);
  }
}
