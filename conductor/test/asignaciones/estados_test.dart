// Los estados del servicio en la app: la misma regla de backend/nucleo/estados.py, para ofrecer
// solo el paso que sigue y mostrar el estado con los toques pendientes.

import 'package:arribo_conductor/asignaciones/estados.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('el paso que sigue es uno solo: sin saltos ni retrocesos', () {
    expect(siguientePaso('asignado'), 'en_camino');
    expect(siguientePaso('en_camino'), 'recogido');
    expect(siguientePaso('recogido'), 'entregado');
  });

  test('entregado, cancelado y novedad no tienen paso siguiente', () {
    expect(siguientePaso('entregado'), isNull);
    expect(siguientePaso('cancelado'), isNull);
    expect(siguientePaso('novedad'), isNull);
    expect(siguientePaso('pendiente_asignar'), isNull);
  });

  test('la novedad se reporta desde asignado, en camino o recogido', () {
    expect(admiteNovedad('asignado'), isTrue);
    expect(admiteNovedad('en_camino'), isTrue);
    expect(admiteNovedad('recogido'), isTrue);
    expect(admiteNovedad('novedad'), isFalse);
    expect(admiteNovedad('entregado'), isFalse);
    expect(admiteNovedad('cancelado'), isFalse);
  });

  test('no se puede marcar un salto, un retroceso ni el mismo estado', () {
    expect(puedeMarcar('asignado', 'recogido'), isFalse);
    expect(puedeMarcar('asignado', 'entregado'), isFalse);
    expect(puedeMarcar('recogido', 'en_camino'), isFalse);
    expect(puedeMarcar('en_camino', 'en_camino'), isFalse);
    expect(puedeMarcar('novedad', 'recogido'), isFalse);
    expect(puedeMarcar('entregado', 'novedad'), isFalse);
  });

  test('desde la app solo se marcan en camino, recogido, entregado y novedad', () {
    expect(destinosDesdeLaApp, {'en_camino', 'recogido', 'entregado', 'novedad'});
    expect(puedeMarcar('asignado', 'cancelado'), isFalse);
    expect(puedeMarcar('pendiente_asignar', 'asignado'), isFalse);
  });

  test('la novedad recuerda el estado previo', () {
    final estado = const EstadoDeServicio('en_camino').marcar('novedad');

    expect(estado.estado, 'novedad');
    expect(estado.estadoPrevio, 'en_camino');
  });

  test('va montado si está recogido, o en novedad que venía de recogido', () {
    expect(const EstadoDeServicio('recogido').aBordo, isTrue);
    expect(const EstadoDeServicio('novedad', 'recogido').aBordo, isTrue);
    expect(const EstadoDeServicio('novedad', 'en_camino').aBordo, isFalse);
    expect(const EstadoDeServicio('en_camino').aBordo, isFalse);
    expect(const EstadoDeServicio('entregado').aBordo, isFalse);
  });

  test('el estado que ve el conductor es el confirmado más sus toques pendientes, en orden', () {
    final visto = const EstadoDeServicio('asignado').conPendientes(['en_camino', 'recogido']);

    expect(visto.estado, 'recogido');
    expect(visto.aBordo, isTrue);
  });

  test('un toque pendiente que el servidor ya aplicó no mueve el estado dos veces', () {
    // La respuesta se perdió: la lista ya llegó en camino y el evento sigue pendiente.
    final visto = const EstadoDeServicio('en_camino').conPendientes(['en_camino', 'recogido']);

    expect(visto.estado, 'recogido');
  });

  test('un toque pendiente que ya no encaja no cambia lo que dijo el servidor', () {
    expect(const EstadoDeServicio('cancelado').conPendientes(['en_camino']).estado, 'cancelado');
    expect(
      const EstadoDeServicio('novedad', 'asignado').conPendientes(['en_camino']).estado,
      'novedad',
    );
  });
}
