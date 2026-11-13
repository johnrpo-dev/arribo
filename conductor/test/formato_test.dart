// Fechas en hora de Colombia y textos para el conductor.

import 'package:arribo_conductor/formato.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Viernes 20 de noviembre de 2026, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  test('muestra la hora de Colombia (UTC−5) sin importar la zona del celular', () {
    expect(horaCorta(DateTime.utc(2026, 11, 20, 19, 30)), '2:30 p. m.');
    expect(horaCorta(DateTime.utc(2026, 11, 20, 5, 5)), '12:05 a. m.');
    expect(horaCorta(DateTime.utc(2026, 11, 20, 17)), '12:00 p. m.');
  });

  test('una hora de la madrugada en UTC es del día anterior en Colombia', () {
    // 02:00 UTC del 21 = 9:00 p. m. del 20 en Colombia: sigue siendo "hoy".
    expect(fechaYHora(DateTime.utc(2026, 11, 21, 2), ahora: ahora), 'Hoy, 9:00 p. m.');
  });

  test('dice hoy, mañana o ayer, y si no, el día y el mes', () {
    expect(fechaYHora(DateTime.utc(2026, 11, 21, 13), ahora: ahora), 'Mañana, 8:00 a. m.');
    expect(fechaYHora(DateTime.utc(2026, 11, 19, 13), ahora: ahora), 'Ayer, 8:00 a. m.');
    expect(
      fechaYHora(DateTime.utc(2026, 11, 24, 19, 30), ahora: ahora),
      'mar. 24 nov., 2:30 p. m.',
    );
    expect(fechaYHora(DateTime.utc(2027, 1, 4, 14), ahora: ahora), 'lun. 4 ene. 2027, 9:00 a. m.');
  });

  test('sin fecha programada el servicio es inmediato', () {
    expect(textoProgramada(null, ahora: ahora), 'Inmediato');
  });

  test('dice cuándo se actualizó la lista', () {
    expect(textoUltimaActualizacion(null, ahora: ahora), 'La lista aún no se ha descargado.');
    expect(
      textoUltimaActualizacion(DateTime.utc(2026, 11, 20, 14, 45), ahora: ahora),
      'Actualizado hoy, 9:45 a. m.',
    );
    expect(
      textoUltimaActualizacion(DateTime.utc(2026, 11, 17, 14, 45), ahora: ahora),
      'Actualizado el mar. 17 nov., 9:45 a. m.',
    );
  });

  test('los teléfonos se leen en grupos', () {
    expect(telefonoLegible('3102223344'), '310 222 3344');
    expect(telefonoLegible('4445566'), '444 5566');
    expect(telefonoLegible('123'), '123');
  });

  test('nombra los estados y tipos en español', () {
    expect(nombreEstado('en_camino'), 'En camino');
    expect(nombreEstado('novedad'), 'Novedad');
    expect(nombreTipo('desvare'), 'Desvare');
  });
}
