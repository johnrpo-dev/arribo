// La cola de eventos en la base local: cada toque queda guardado con su UUID y su secuencia, y
// solo sale de la cola con una respuesta definitiva del servidor.

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/asignaciones/trayecto.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/evento.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ColaEventos cola;
  final ahora = DateTime.utc(2026, 11, 20, 19, 42, 7);
  const ana = Conductor(id: 3, nombre: 'Ana Gómez', celular: '3001234567');
  const beto = Conductor(id: 8, nombre: 'Beto Ríos', celular: '3009998877');

  Future<void> guardarLista(Map<int, String> estados) =>
      AlmacenAsignaciones(prueba.base).reemplazar(
        servicios: [
          for (final MapEntry(key: id, value: estado) in estados.entries)
            Servicio.desdeJson(servicioJson(id: id, estado: estado, placa: 'ABC$id')),
        ],
        configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
        etag: '"e1"',
        hora: ahora,
      );

  Future<EventoLocal> tocar(
    int servicio,
    String destino, {
    Conductor conductor = ana,
    String? motivo,
    String? placa,
    String? vin,
    String? id,
  }) => cola.encolar(
    conductor: conductor,
    servicioId: servicio,
    destino: destino,
    motivo: motivo,
    placa: placa,
    vin: vin,
    id: id,
    hora: ahora,
  );

  /// El vehículo del servicio en la lista guardada: (placa, VIN).
  Future<(Object?, Object?)> vehiculoGuardado(int servicio) async {
    final fila = (await prueba.base.db.query(
      'servicios',
      where: 'id = ?',
      whereArgs: [servicio],
    )).single;
    return (fila['vehiculo_placa'], fila['vehiculo_vin']);
  }

  /// El servicio llegó en la lista sin placa ni VIN.
  Future<void> sinIdentificar(int servicio) => prueba.base.db.update(
    'servicios',
    {'vehiculo_placa': null, 'vehiculo_vin': null},
    where: 'id = ?',
    whereArgs: [servicio],
  );

  Future<String?> estadoGuardado(int servicio) async {
    final filas = await prueba.base.db.query('servicios', where: 'id = ?', whereArgs: [servicio]);
    return filas.isEmpty ? null : filas.single['estado'] as String?;
  }

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    cola = ColaEventos(prueba.base);
    await prueba.base.escribirJson(Clave.conductor, ana.aJson());
    await guardarLista({41: 'asignado', 42: 'asignado'});
  });
  tearDown(() async => prueba.cerrar());

  group('cada toque es un evento guardado', () {
    test('queda en la base con UUID v4, servicio, destino, secuencia, hora y conductor', () async {
      final evento = await tocar(41, 'en_camino');

      final fila = (await prueba.base.db.query('eventos_pendientes')).single;
      expect(
        fila['id'],
        matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')),
      );
      expect(fila['id'], evento.id);
      expect(fila['servicio_id'], 41);
      expect(fila['destino'], 'en_camino');
      expect(fila['secuencia'], 1);
      expect(fila['hora_dispositivo'], '2026-11-20T19:42:07.000Z');
      expect(fila['conductor_id'], 3);
      expect(fila['conductor_nombre'], 'Ana Gómez');
      expect(fila['vehiculo'], 'ABC41');
      expect(fila['estado_envio'], 'pendiente');
    });

    test('el evento que se envía lleva lo que pide el contrato y nunca al conductor', () async {
      final evento = await tocar(41, 'novedad', motivo: '  Llanta pinchada  ');

      expect(evento.aJson(), {
        'id': evento.id,
        'servicio_id': 41,
        'destino': 'novedad',
        'secuencia': 1,
        'hora_dispositivo': '2026-11-20T19:42:07.000Z',
        'motivo': 'Llanta pinchada',
        'nombre_quien': null,
        'placa': null,
        'vin': null,
        'latitud': null,
        'longitud': null,
      });
    });

    test('la novedad exige motivo', () async {
      await expectLater(tocar(41, 'novedad'), throwsA(isA<ToqueNoValido>()));
      await expectLater(tocar(41, 'novedad', motivo: '   '), throwsA(isA<ToqueNoValido>()));

      expect(await cola.pendientes(3), isEmpty);
    });

    test('cancelar no se encola: no es un botón del conductor', () async {
      await expectLater(tocar(41, 'cancelado'), throwsA(isA<ToqueNoValido>()));

      expect(await cola.pendientes(3), isEmpty);
    });

    test('solo se encola el paso que sigue al estado que ve el conductor', () async {
      await expectLater(tocar(41, 'recogido'), throwsA(isA<ToqueNoValido>()));
      await tocar(41, 'en_camino');
      // Con En camino pendiente, lo que sigue es Recogido.
      await tocar(41, 'recogido');
      await expectLater(tocar(41, 'en_camino'), throwsA(isA<ToqueNoValido>()));

      expect([for (final e in await cola.pendientes(3)) e.destino], ['en_camino', 'recogido']);
    });

    test('dos toques seguidos en el mismo botón no crean dos eventos', () async {
      final toques = await Future.wait([
        tocar(41, 'en_camino').then<Object>((e) => e, onError: (Object e) => e),
        tocar(41, 'en_camino').then<Object>((e) => e, onError: (Object e) => e),
      ]);

      expect(toques.whereType<EventoLocal>(), hasLength(1));
      expect(toques.whereType<ToqueNoValido>(), hasLength(1));
      expect(await cola.pendientes(3), hasLength(1));
    });

    test('un servicio que ya no está en la lista no admite toques', () async {
      await expectLater(tocar(99, 'en_camino'), throwsA(isA<ToqueNoValido>()));
    });

    test('quien llama puede fijar el UUID del evento (las fotos se atan a él)', () async {
      final evento = await tocar(41, 'en_camino', id: '0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e');

      expect(evento.id, '0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e');
    });
  });

  group('placa o VIN digitados al recoger (1a-13b)', () {
    setUp(() async {
      await guardarLista({41: 'en_camino', 42: 'asignado'});
      await sinIdentificar(41);
    });

    test('el Recogido los guarda normalizados y viajan en el evento', () async {
      final evento = await tocar(41, 'recogido', placa: ' abc-123 ', vin: '1hgcm-82633 a004352');

      final fila = (await prueba.base.db.query('eventos_pendientes')).single;
      expect((fila['placa'], fila['vin']), ('ABC123', '1HGCM82633A004352'));
      expect(evento.aJson(), containsPair('placa', 'ABC123'));
      expect(evento.aJson(), containsPair('vin', '1HGCM82633A004352'));
      // El aviso de un conflicto nombra el vehículo con la placa digitada.
      expect(fila['vehiculo'], 'ABC123');
    });

    test('lo que no se digitó viaja vacío', () async {
      final evento = await tocar(41, 'recogido', placa: 'ABC123', vin: '  ');

      expect(evento.aJson(), containsPair('vin', null));
      expect((await prueba.base.db.query('eventos_pendientes')).single['vin'], isNull);
    });

    test('en otro destino se ignoran, como en el servidor', () async {
      final evento = await tocar(42, 'en_camino', placa: 'ABC123', vin: '1HGCM82633A004352');

      expect((evento.placa, evento.vin), (null, null));
      expect(evento.aJson(), containsPair('placa', null));
    });

    test('el Recogido sin enviar no cambia la lista guardada', () async {
      await tocar(41, 'recogido', placa: 'ABC123');

      expect(await vehiculoGuardado(41), (null, null));
    });

    test('aplicado, lo digitado queda en el vehículo de la lista donde le faltaba', () async {
      final evento = await tocar(41, 'recogido', placa: 'ABC123', vin: '1HGCM82633A004352');
      await prueba.base.db.update(
        'servicios',
        {'vehiculo_vin': 'JH4KA8260MC000000'},
        where: 'id = ?',
        whereArgs: [41],
      );

      await cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: 'aplicado')],
        hora: ahora,
      );

      // La placa le faltaba; el VIN que ya tenía no se sobreescribe.
      expect(await vehiculoGuardado(41), ('ABC123', 'JH4KA8260MC000000'));
    });

    test('en conflicto o pendiente por reintentar, el vehículo de la lista no cambia', () async {
      final evento = await tocar(41, 'recogido', placa: 'ABC123');

      await cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: 'reintentar')],
        hora: ahora,
      );
      expect(await vehiculoGuardado(41), (null, null));

      await cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: 'conflicto', motivo: 'servicio_cancelado')],
        hora: ahora,
      );
      expect(await vehiculoGuardado(41), (null, null));

      // Una respuesta tardía de "aplicado" a un evento ya resuelto tampoco lo cambia.
      await cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: 'aplicado')],
        hora: ahora,
      );
      expect(await vehiculoGuardado(41), (null, null));
    });
  });

  group('secuencia del dispositivo', () {
    test('es estrictamente creciente, en el orden de los toques', () async {
      final a = await tocar(41, 'en_camino');
      final b = await tocar(42, 'en_camino');
      final c = await tocar(41, 'recogido');

      expect([a.secuencia, b.secuencia, c.secuencia], [1, 2, 3]);
    });

    test('sigue donde iba después de cerrar y reabrir la app', () async {
      await tocar(41, 'en_camino');
      await tocar(41, 'recogido');

      cola = ColaEventos(await prueba.reabrir());
      final despues = await tocar(42, 'en_camino');

      expect(despues.secuencia, 3);
    });

    test('no se reutiliza al cambiar de conductor ni al borrar la lista', () async {
      await tocar(41, 'en_camino');
      await AlmacenAsignaciones(prueba.base).olvidar();
      await prueba.base.escribirJson(Clave.conductor, beto.aJson());
      await guardarLista({50: 'asignado'});

      final deBeto = await tocar(50, 'en_camino', conductor: beto);

      expect(deBeto.secuencia, 2);
    });

    test('no se reutiliza aunque los eventos ya enviados dejen de estar en la cola', () async {
      final evento = await tocar(41, 'en_camino');
      await cola.registrarResultados(
        [evento],
        [const ResultadoEvento(id: 'x', resultado: 'aplicado')],
        hora: ahora,
      );
      await prueba.base.db.delete('eventos_pendientes');

      expect((await tocar(42, 'en_camino')).secuencia, 2);
    });

    test('si se perdiera el contador, sigue después de la mayor secuencia guardada', () async {
      await tocar(41, 'en_camino');
      await tocar(41, 'recogido');
      await prueba.base.borrar(Clave.ultimaSecuencia);

      expect((await tocar(42, 'en_camino')).secuencia, 3);
    });

    test(
      'la secuencia y el evento se guardan juntos: si el evento no entra, no se gasta',
      () async {
        await expectLater(tocar(41, 'recogido'), throwsA(isA<ToqueNoValido>()));

        expect(await prueba.base.leer(Clave.ultimaSecuencia), isNull);
        expect((await tocar(41, 'en_camino')).secuencia, 1);
      },
    );
  });

  group('pendientes', () {
    test('salen del más antiguo al más nuevo, y un lote toma solo los primeros', () async {
      await tocar(41, 'en_camino');
      await tocar(42, 'en_camino');
      await tocar(41, 'recogido');

      expect([for (final e in await cola.pendientes(3)) e.secuencia], [1, 2, 3]);
      expect([for (final e in await cola.pendientes(3, limite: 2)) e.secuencia], [1, 2]);
    });

    test('cada conductor tiene los suyos', () async {
      await tocar(41, 'en_camino');
      await tocar(42, 'en_camino', conductor: beto);

      expect([for (final e in await cola.pendientes(3)) e.servicioId], [41]);
      expect([for (final e in await cola.pendientes(8)) e.servicioId], [42]);
      final porConductor = await cola.pendientesPorConductor();
      expect(
        [for (final p in porConductor) (p.conductorId, p.nombre, p.cantidad)],
        [(3, 'Ana Gómez', 1), (8, 'Beto Ríos', 1)],
      );
    });
  });

  group('resultados del servidor', () {
    ResultadoEvento resultado(
      EventoLocal evento,
      String resultado, {
      String? motivo,
      String? detalle,
      EstadoRemoto? servicio,
      bool duplicado = false,
    }) => ResultadoEvento(
      id: evento.id,
      resultado: resultado,
      motivo: motivo,
      detalle: detalle,
      servicio: servicio,
      duplicado: duplicado,
    );

    test('aplicado saca el evento de la cola y corrige el estado del servicio', () async {
      final evento = await tocar(41, 'en_camino');

      final resueltos = await cola.registrarResultados(
        [evento],
        [
          resultado(
            evento,
            'aplicado',
            servicio: const EstadoRemoto(id: 41, estado: 'en_camino', enSuRonda: true),
          ),
        ],
        hora: ahora,
      );

      expect(resueltos, 1);
      expect(await cola.pendientes(3), isEmpty);
      expect(await estadoGuardado(41), 'en_camino');
      final fila = (await prueba.base.db.query('eventos_pendientes')).single;
      expect(fila['estado_envio'], 'aplicado');
      expect(fila['resuelto_en'], isNotNull);
    });

    test('un duplicado se trata igual que la primera respuesta', () async {
      final evento = await tocar(41, 'en_camino');

      await cola.registrarResultados(
        [evento],
        [resultado(evento, 'aplicado', duplicado: true)],
        hora: ahora,
      );

      expect(await cola.pendientes(3), isEmpty);
    });

    test('conflicto y rechazado salen de la cola con su motivo y quedan como aviso', () async {
      final a = await tocar(41, 'en_camino');
      final b = await tocar(42, 'en_camino');

      await cola.registrarResultados(
        [a, b],
        [
          resultado(
            a,
            'conflicto',
            motivo: 'servicio_cancelado',
            detalle: 'El servicio ya estaba cancelado.',
          ),
          resultado(
            b,
            'rechazado',
            motivo: 'servicio_desconocido',
            detalle: 'El servicio no existe.',
          ),
        ],
        hora: ahora,
      );

      expect(await cola.pendientes(3), isEmpty);
      final avisos = await cola.avisos(3);
      expect([for (final e in avisos) e.estadoEnvio], ['conflicto', 'rechazado']);
      expect(avisos.first.resultadoMotivo, 'servicio_cancelado');
      expect(avisos.first.resultadoDetalle, 'El servicio ya estaba cancelado.');
      expect(avisos.first.vehiculo, 'ABC41');
    });

    test('reintentar deja el evento en la cola, igual que estaba', () async {
      final evento = await tocar(41, 'en_camino');

      final resueltos = await cola.registrarResultados(
        [evento],
        [resultado(evento, 'reintentar', motivo: 'error_del_servidor')],
        hora: ahora,
      );

      expect(resueltos, 0);
      final pendiente = (await cola.pendientes(3)).single;
      expect(pendiente.id, evento.id);
      expect(pendiente.secuencia, evento.secuencia);
      expect(await estadoGuardado(41), 'asignado');
    });

    test('un resultado que esta versión no conoce deja el evento en la cola', () async {
      final evento = await tocar(41, 'en_camino');

      await cola.registrarResultados([evento], [resultado(evento, 'algo_nuevo')], hora: ahora);

      expect(await cola.pendientes(3), hasLength(1));
    });

    test(
      'el estado del servidor no se usa mientras al servicio le queden eventos pendientes',
      () async {
        final a = await tocar(41, 'en_camino');
        await tocar(41, 'recogido');

        await cola.registrarResultados(
          [a],
          [
            resultado(
              a,
              'aplicado',
              servicio: const EstadoRemoto(id: 41, estado: 'en_camino', enSuRonda: true),
            ),
          ],
          hora: ahora,
        );

        expect(await estadoGuardado(41), 'asignado');
        expect(await AlmacenAsignaciones(prueba.base).etag(), '"e1"');
      },
    );

    test(
      'un servicio que salió de la ronda (entregado, cancelado o reasignado) se quita de la lista',
      () async {
        final a = await tocar(41, 'en_camino');
        final b = await tocar(42, 'en_camino');

        await cola.registrarResultados(
          [a, b],
          [
            resultado(
              a,
              'conflicto',
              servicio: const EstadoRemoto(id: 41, estado: 'cancelado', enSuRonda: false),
            ),
            resultado(
              b,
              'conflicto',
              servicio: const EstadoRemoto(id: 42, estado: null, enSuRonda: false),
            ),
          ],
          hora: ahora,
        );

        expect(await AlmacenAsignaciones(prueba.base).leer(), isEmpty);
      },
    );

    test('al corregir la lista se olvida su ETag: la próxima consulta la trae completa', () async {
      final evento = await tocar(41, 'en_camino');

      await cola.registrarResultados(
        [evento],
        [
          resultado(
            evento,
            'aplicado',
            servicio: const EstadoRemoto(id: 41, estado: 'en_camino', enSuRonda: true),
          ),
        ],
        hora: ahora,
      );

      expect(await AlmacenAsignaciones(prueba.base).etag(), isNull);
    });

    test('la respuesta de los eventos de otro conductor no toca la lista del actual', () async {
      final deAna = await tocar(41, 'en_camino');
      // Ana quedó sin sesión y Beto ingresó: la lista guardada ahora es la de Beto.
      await prueba.base.escribirJson(Clave.conductor, beto.aJson());

      await cola.registrarResultados(
        [deAna],
        [
          resultado(
            deAna,
            'conflicto',
            servicio: const EstadoRemoto(id: 41, estado: null, enSuRonda: false),
          ),
        ],
        hora: ahora,
      );

      expect(await estadoGuardado(41), 'asignado');
      expect(await cola.pendientes(3), isEmpty);
    });

    test('un evento ya resuelto no vuelve a cambiar con otra respuesta', () async {
      final evento = await tocar(41, 'en_camino');
      await cola.registrarResultados([evento], [resultado(evento, 'conflicto')], hora: ahora);

      final resueltos = await cola.registrarResultados(
        [evento],
        [resultado(evento, 'aplicado')],
        hora: ahora,
      );

      expect(resueltos, 0);
      expect(
        (await prueba.base.db.query('eventos_pendientes')).single['estado_envio'],
        'conflicto',
      );
    });

    test('dar por visto un aviso lo quita de los avisos sin borrar el evento', () async {
      final evento = await tocar(41, 'en_camino');
      await cola.registrarResultados([evento], [resultado(evento, 'conflicto')], hora: ahora);

      await cola.marcarVisto(evento.id, hora: ahora);

      expect(await cola.avisos(3), isEmpty);
      final fila = (await prueba.base.db.query('eventos_pendientes')).single;
      expect(fila['estado_envio'], 'conflicto');
      expect(fila['visto_en'], isNotNull);
    });
  });

  group('el regreso espera a su ida', () {
    // 51 es la ida (ya recogida) y 52 su regreso, que según el servidor espera.
    setUp(
      () => AlmacenAsignaciones(prueba.base).reemplazar(
        servicios: [
          Servicio.desdeJson(servicioJson(id: 51, estado: 'recogido', placa: 'EVT101')),
          Servicio.desdeJson(
            servicioJson(id: 52, placa: 'EVT101', tipo: 'evento', regresoDe: 51, esperaIda: true),
          ),
        ],
        configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
        etag: '"e2"',
        hora: ahora,
      ),
    );

    test('no deja arrancar el regreso y no guarda nada', () async {
      await expectLater(
        tocar(52, 'en_camino'),
        throwsA(isA<ToqueNoValido>().having((e) => e.mensaje, 'mensaje', textoEsperaIda)),
      );
      expect(await prueba.base.db.query('eventos_pendientes'), isEmpty);
    });

    test('la novedad del regreso sí se puede reportar', () async {
      await tocar(52, 'novedad', motivo: 'El concesionario cerró');
      expect(await prueba.base.db.query('eventos_pendientes'), hasLength(1));
    });

    test('sin señal, al marcar Entregado en la ida el regreso ya puede arrancar', () async {
      final ida = await tocar(51, 'entregado');
      final regreso = await tocar(52, 'en_camino');
      expect(regreso.secuencia, greaterThan(ida.secuencia)); // el servidor los aplica en ese orden
    });

    test('cuando el servidor confirma la ida entregada, el regreso deja de esperar', () async {
      final ida = await tocar(51, 'entregado');

      await cola.registrarResultados(
        [ida],
        [
          ResultadoEvento(
            id: ida.id,
            resultado: 'aplicado',
            servicio: const EstadoRemoto(id: 51, estado: 'entregado', enSuRonda: false),
          ),
        ],
        hora: ahora,
      );

      final regreso = (await AlmacenAsignaciones(prueba.base).leer()).single;
      expect((regreso.id, regreso.esperaIda), (52, false));
      await tocar(52, 'en_camino');
    });
  });
}
