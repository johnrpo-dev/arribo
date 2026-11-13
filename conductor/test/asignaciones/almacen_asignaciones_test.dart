// Las asignaciones en la base local: guardar, leer en orden de ronda y reemplazar todo junto.

import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late AlmacenAsignaciones almacen;
  const configuracion = ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger');
  final hora = DateTime.utc(2026, 11, 20, 15);

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    almacen = AlmacenAsignaciones(prueba.base);
  });
  tearDown(() async => prueba.cerrar());

  Servicio servicio(int id, {int? ordenRonda}) =>
      Servicio.desdeJson(servicioJson(id: id, ordenRonda: ordenRonda));

  test('guarda la lista y la lee igual, con su configuración, ETag y hora', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );

    final leidos = await almacen.leer();
    expect(leidos.single.aFila(0), servicio(41, ordenRonda: 1).aFila(0));
    expect((await almacen.configuracion())?.minimoFotos, 4);
    expect(await almacen.etag(), '"e1"');
    expect(await almacen.ultimaActualizacion(), hora);
  });

  test('lee los servicios en el orden de la ronda del servidor, con huecos y sin número', () async {
    await almacen.reemplazar(
      servicios: [
        servicio(52, ordenRonda: 1),
        servicio(17, ordenRonda: 4),
        servicio(30, ordenRonda: 9),
        servicio(8),
      ],
      configuracion: configuracion,
      etag: null,
      hora: hora,
    );

    expect([for (final s in await almacen.leer()) s.id], [52, 17, 30, 8]);
  });

  test('la lista guardada sobrevive a que el sistema mate la app', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1), servicio(42, ordenRonda: 2)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );

    final base = await prueba.reabrir();

    final despues = AlmacenAsignaciones(base);
    expect([for (final s in await despues.leer()) s.id], [41, 42]);
    expect(await despues.etag(), '"e1"');
  });

  test('reemplazar quita los servicios que ya no vienen del servidor', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1), servicio(42, ordenRonda: 2)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );

    await almacen.reemplazar(
      servicios: [servicio(42, ordenRonda: 1)],
      configuracion: configuracion,
      etag: '"e2"',
      hora: hora,
    );

    expect([for (final s in await almacen.leer()) s.id], [42]);
    expect(await almacen.etag(), '"e2"');
  });

  test('si la escritura falla a mitad no queda ni la lista nueva ni su ETag', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );

    // Dos servicios con el mismo id: la segunda fila falla dentro de la transacción.
    await expectLater(
      almacen.reemplazar(
        servicios: [servicio(50, ordenRonda: 1), servicio(50, ordenRonda: 2)],
        configuracion: configuracion,
        etag: '"e2"',
        hora: hora.add(const Duration(hours: 1)),
      ),
      throwsA(anything),
    );

    expect([for (final s in await almacen.leer()) s.id], [41]);
    expect(await almacen.etag(), '"e1"');
    expect(await almacen.ultimaActualizacion(), hora);
  });

  test('confirmar sin cambios solo anota la hora', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );

    await almacen.confirmarSinCambios(hora.add(const Duration(minutes: 5)));

    expect([for (final s in await almacen.leer()) s.id], [41]);
    expect(await almacen.etag(), '"e1"');
    expect(await almacen.ultimaActualizacion(), hora.add(const Duration(minutes: 5)));
  });

  test('olvidar borra la lista y su ETag, pero no la cola de pendientes', () async {
    await almacen.reemplazar(
      servicios: [servicio(41, ordenRonda: 1)],
      configuracion: configuracion,
      etag: '"e1"',
      hora: hora,
    );
    await prueba.base.db.insert('eventos_pendientes', {
      'id': 'a',
      'conductor_id': 3,
      'servicio_id': 41,
      'destino': 'en_camino',
      'secuencia': 1,
      'hora_dispositivo': '2026-11-20T19:42:07Z',
      'creado_en': '2026-11-20T19:42:07Z',
    });

    await almacen.olvidar();

    expect(await almacen.leer(), isEmpty);
    expect(await almacen.etag(), isNull);
    expect(await prueba.base.pendientesPorEnviar(), 1);
  });
}
