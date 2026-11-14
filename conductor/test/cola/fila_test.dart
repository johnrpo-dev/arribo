// Tareas que no se deben cruzar (el envío de eventos y la consulta de la lista).

import 'dart:async';

import 'package:arribo_conductor/cola/fila.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('las tareas corren una tras otra, en el orden en que se pidieron', () async {
    final fila = Fila();
    final pasos = <String>[];
    final primera = Completer<void>();

    final a = fila.ejecutar(() async {
      pasos.add('a empieza');
      await primera.future;
      pasos.add('a termina');
    });
    final b = fila.ejecutar(() async => pasos.add('b'));
    final c = fila.ejecutar(() async => pasos.add('c'));
    await Future<void>.delayed(Duration.zero);
    expect(pasos, ['a empieza']);
    primera.complete();
    await Future.wait([a, b, c]);

    expect(pasos, ['a empieza', 'a termina', 'b', 'c']);
  });

  test(
    'una tarea que falla no detiene a las siguientes y su error llega a quien la pidió',
    () async {
      final fila = Fila();

      final falla = fila.ejecutar<void>(() async => throw StateError('falló'));
      final sigue = fila.ejecutar(() async => 'sigue');

      await expectLater(falla, throwsStateError);
      expect(await sigue, 'sigue');
    },
  );

  test('devuelve el resultado de la tarea', () async {
    expect(await Fila().ejecutar(() async => 7), 7);
  });
}
