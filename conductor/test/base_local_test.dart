// Base local: esquema, migraciones versionadas e identificador del dispositivo.

import 'dart:io';

import 'package:arribo_conductor/base_local.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'ayudas.dart';

Future<Set<String>> tablas(BaseLocal base) async {
  final filas = await base.db.rawQuery(
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
    "AND name != 'android_metadata'",
  );
  return {for (final f in filas) f['name']! as String};
}

Future<Map<String, String>> columnas(BaseLocal base, String tabla) async {
  final filas = await base.db.rawQuery('PRAGMA table_info($tabla)');
  return {for (final f in filas) f['name']! as String: (f['type']! as String).toUpperCase()};
}

void main() {
  late BaseDePrueba prueba;

  setUp(() async => prueba = await BaseDePrueba.crear());
  tearDown(() async => prueba.cerrar());

  test('una base nueva queda en la última versión con todas las tablas', () async {
    expect(await prueba.base.db.getVersion(), migraciones.length);
    expect(await tablas(prueba.base), {
      'estado_local',
      'servicios',
      'eventos_pendientes',
      'fotos_pendientes',
    });
  });

  test('reabrir la base conserva lo guardado y no vuelve a aplicar migraciones', () async {
    await prueba.base.escribir('prueba', 'sigue aquí');

    final base = await prueba.reabrir();

    expect(await base.leer('prueba'), 'sigue aquí');
    expect(await base.db.getVersion(), migraciones.length);
  });

  test('una migración nueva se aplica sobre la base existente sin perder datos', () async {
    await prueba.base.escribir('prueba', 'de la versión 1');
    await prueba.base.cerrar();
    final conNueva = [
      ...migraciones,
      ['ALTER TABLE servicios ADD COLUMN campo_nuevo TEXT'],
    ];

    prueba.base = await BaseLocal.abrir(fabricaDePrueba, prueba.ruta, migraciones: conNueva);

    expect(await prueba.base.db.getVersion(), migraciones.length + 1);
    expect(await prueba.base.leer('prueba'), 'de la versión 1');
    expect((await columnas(prueba.base, 'servicios')).keys, contains('campo_nuevo'));
  });

  test('una migración que falla no avanza la versión', () async {
    await prueba.base.cerrar();
    final conRota = [
      ...migraciones,
      ['ALTER TABLE servicios ADD COLUMN campo_nuevo TEXT', 'ESTO NO ES SQL'],
    ];

    await expectLater(
      BaseLocal.abrir(fabricaDePrueba, prueba.ruta, migraciones: conRota),
      throwsA(isA<DatabaseException>()),
    );

    prueba.base = await BaseLocal.abrir(fabricaDePrueba, prueba.ruta);
    expect(await prueba.base.db.getVersion(), migraciones.length);
    expect((await columnas(prueba.base, 'servicios')).keys, isNot(contains('campo_nuevo')));
  });

  test(
    'abrir con una app más vieja que la base falla en vez de usar un esquema desconocido',
    () async {
      await prueba.base.db.setVersion(migraciones.length + 1);
      await prueba.base.cerrar();

      await expectLater(BaseLocal.abrir(fabricaDePrueba, prueba.ruta), throwsA(anything));

      // Para que tearDown pueda cerrar algo.
      await File(prueba.ruta).delete();
      prueba.base = await BaseLocal.abrir(fabricaDePrueba, prueba.ruta);
    },
  );

  test('el identificador del dispositivo se genera una vez y sobrevive a reabrir la app', () async {
    final primero = await prueba.base.dispositivoId();

    final base = await prueba.reabrir();

    expect(await base.dispositivoId(), primero);
    expect(
      primero,
      matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')),
    );
  });

  group('esquema previsto para la cola (1a-12) y las fotos (1a-13)', () {
    test('la cola de eventos tiene lo que pide el contrato y un estado de envío', () async {
      expect(
        (await columnas(prueba.base, 'eventos_pendientes')).keys,
        containsAll([
          'id',
          'conductor_id',
          'servicio_id',
          'destino',
          'secuencia',
          'hora_dispositivo',
          'motivo',
          'nombre_quien',
          'estado_envio',
        ]),
      );
    });

    test('la cola solo acepta los destinos que se marcan desde la app', () async {
      Future<void> insertar(String id, String destino, int secuencia) =>
          prueba.base.db.insert('eventos_pendientes', {
            'id': id,
            'conductor_id': 3,
            'servicio_id': 41,
            'destino': destino,
            'secuencia': secuencia,
            'hora_dispositivo': '2026-11-20T19:42:07Z',
            'creado_en': '2026-11-20T19:42:07Z',
          });

      await insertar('a', 'en_camino', 1);
      await expectLater(insertar('b', 'cancelado', 2), throwsA(isA<DatabaseException>()));
    });

    test('dos eventos no pueden tener la misma secuencia', () async {
      Future<void> insertar(String id) => prueba.base.db.insert('eventos_pendientes', {
        'id': id,
        'conductor_id': 3,
        'servicio_id': 41,
        'destino': 'en_camino',
        'secuencia': 7,
        'hora_dispositivo': '2026-11-20T19:42:07Z',
        'creado_en': '2026-11-20T19:42:07Z',
      });

      await insertar('a');
      await expectLater(insertar('b'), throwsA(isA<DatabaseException>()));
    });

    test('las fotos pendientes guardan la ruta en disco, nunca los bytes', () async {
      final cols = await columnas(prueba.base, 'fotos_pendientes');
      expect(
        cols.keys,
        containsAll(['id', 'servicio_id', 'evento_id', 'tipo', 'ruta', 'estado_envio']),
      );
      expect(cols.values, isNot(contains('BLOB')));
    });
  });

  test('cuenta lo pendiente por enviar: eventos y fotos sin entregar al servidor', () async {
    expect(await prueba.base.pendientesPorEnviar(), 0);
    await prueba.base.db.insert('eventos_pendientes', {
      'id': 'a',
      'conductor_id': 3,
      'servicio_id': 41,
      'destino': 'en_camino',
      'secuencia': 1,
      'hora_dispositivo': '2026-11-20T19:42:07Z',
      'creado_en': '2026-11-20T19:42:07Z',
    });
    await prueba.base.db.insert('eventos_pendientes', {
      'id': 'b',
      'conductor_id': 3,
      'servicio_id': 41,
      'destino': 'recogido',
      'secuencia': 2,
      'hora_dispositivo': '2026-11-20T19:50:00Z',
      'creado_en': '2026-11-20T19:50:00Z',
      'estado_envio': 'aplicado',
    });
    await prueba.base.db.insert('fotos_pendientes', {
      'id': 'f',
      'conductor_id': 3,
      'servicio_id': 41,
      'evento_id': 'b',
      'tipo': 'recogida',
      'ruta': '/data/user/0/co.arribo.arribo_conductor/files/fotos/f.jpg',
      'creado_en': '2026-11-20T19:50:00Z',
    });

    expect(await prueba.base.pendientesPorEnviar(), 2);
  });
}
