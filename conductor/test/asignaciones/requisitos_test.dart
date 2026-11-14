// Lo que exige la app antes de guardar un Recogido o un Entregado: identificación del vehículo
// (digitada en la pantalla si le falta, 1a-13b) y puesto libre en la grúa (Recogido), mínimo de
// fotos y nombre de quien entrega o recibe (los dos).

import 'package:arribo_conductor/asignaciones/requisitos.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:flutter_test/flutter_test.dart';

const configuracion = ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger');

Servicio servicio(
  int id, {
  String estado = 'en_camino',
  String? estadoPrevio,
  String? placa = 'ABC123',
  String? vin,
  String tipo = 'traslado',
  int capacidad = 1,
  int grua = 2,
}) => Servicio(
  id: id,
  solicitudId: 17,
  estado: estado,
  estadoPrevio: estadoPrevio,
  tipo: tipo,
  vehiculo: Vehiculo(placa: placa, vin: vin),
  grua: Grua(id: grua, placa: 'GRU00$grua', capacidad: capacidad),
);

void main() {
  group('mínimo de fotos y nombre', () {
    test('con menos fotos que el mínimo dice cuántas faltan', () {
      final faltantes = faltantesDelPaso(
        destino: 'recogido',
        fotos: 3,
        minimoFotos: 4,
        nombreQuien: 'Carlos Pérez',
      );

      expect(faltantes, ['Falta 1 foto: lleva 3 de 4.']);
    });

    test('sin ninguna foto dice que faltan todas', () {
      final faltantes = faltantesDelPaso(
        destino: 'entregado',
        fotos: 0,
        minimoFotos: 4,
        nombreQuien: 'Carlos Pérez',
      );

      expect(faltantes, ['Faltan 4 fotos: lleva 0 de 4.']);
    });

    test('Recogido exige el nombre de quien entrega el vehículo', () {
      final faltantes = faltantesDelPaso(
        destino: 'recogido',
        fotos: 4,
        minimoFotos: 4,
        nombreQuien: '   ',
      );

      expect(faltantes, ['Escriba el nombre de quien entrega el vehículo para marcar Recogido.']);
    });

    test('Entregado exige el nombre de quien recibe el vehículo', () {
      final faltantes = faltantesDelPaso(
        destino: 'entregado',
        fotos: 4,
        minimoFotos: 4,
        nombreQuien: null,
      );

      expect(faltantes, ['Escriba el nombre de quien recibe el vehículo para marcar Entregado.']);
    });

    test('con el mínimo de fotos y el nombre no falta nada', () {
      for (final destino in ['recogido', 'entregado']) {
        expect(
          faltantesDelPaso(destino: destino, fotos: 4, minimoFotos: 4, nombreQuien: 'Ana'),
          isEmpty,
        );
        expect(
          faltantesDelPaso(destino: destino, fotos: 6, minimoFotos: 4, nombreQuien: 'Ana'),
          isEmpty,
        );
      }
    });

    test('el mínimo es el de la configuración: con mínimo 0 solo se exige el nombre', () {
      expect(
        faltantesDelPaso(destino: 'recogido', fotos: 0, minimoFotos: 0, nombreQuien: 'Ana'),
        isEmpty,
      );
      expect(
        faltantesDelPaso(destino: 'recogido', fotos: 0, minimoFotos: 0, nombreQuien: ''),
        hasLength(1),
      );
    });

    test('si faltan fotos y nombre, dice las dos cosas', () {
      final faltantes = faltantesDelPaso(
        destino: 'recogido',
        fotos: 1,
        minimoFotos: 4,
        nombreQuien: '',
      );

      expect(faltantes, hasLength(2));
      expect(faltantes.first, 'Faltan 3 fotos: lleva 1 de 4.');
    });
  });

  group('placa o VIN al recoger', () {
    const alAsignar = ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'asignar');
    const vin = '1HGCM82633A004352';

    test('con placa se puede recoger y no se pide digitar nada', () {
      final s = servicio(41);

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
      expect(identificacionPorDigitar(s, configuracion: configuracion), isNull);
    });

    test('con VIN y sin placa se puede recoger un traslado sin digitar nada', () {
      final s = servicio(41, placa: null, vin: vin);

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
      expect(identificacionPorDigitar(s, configuracion: configuracion), isNull);
    });

    // Antes de la 1a-13b este caso bloqueaba el Recogido ("llame a logística") y, sin señal, el
    // conductor no podía recoger el vehículo. Ahora no bloquea: la pantalla del paso le pide
    // digitar la placa o el VIN.
    test('con "al recoger", un traslado sin placa ni VIN no se bloquea: pide placa o VIN', () {
      final s = servicio(41, placa: null);

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
      expect(identificacionPorDigitar(s, configuracion: configuracion), (placa: true, vin: true));
    });

    test('con "al recoger", un desvare sin placa pide solo la placa, aunque tenga VIN', () {
      final s = servicio(41, placa: null, vin: vin, tipo: 'desvare');

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
      expect(identificacionPorDigitar(s, configuracion: configuracion), (placa: true, vin: false));
    });

    test('sin configuración guardada vale la de fábrica: pide digitarla', () {
      final s = servicio(41, placa: null);

      expect(bloqueoDeRecogida(s, [s], configuracion: null), isNull);
      expect(identificacionPorDigitar(s, configuracion: null), isNotNull);
    });

    test('con "al asignar" no se pide: el Recogido se bloquea y dice que llame a logística', () {
      final s = servicio(41, placa: null);

      final bloqueo = bloqueoDeRecogida(s, [s], configuracion: alAsignar)!;

      expect(identificacionPorDigitar(s, configuracion: alAsignar), isNull);
      expect(bloqueo.titulo, 'Falta identificar el vehículo');
      expect(bloqueo.mensaje, contains('El vehículo necesita placa o VIN (al menos uno).'));
      expect(bloqueo.mensaje, contains('Llame a logística'));
      expect(bloqueo.faltanPorEntregar, isEmpty);
    });

    test('con "al asignar", un desvare sin placa se bloquea aunque tenga VIN', () {
      final s = servicio(41, placa: null, vin: vin, tipo: 'desvare');

      final bloqueo = bloqueoDeRecogida(s, [s], configuracion: alAsignar)!;

      expect(bloqueo.mensaje, contains('Un desvare exige la placa del vehículo.'));
    });
  });

  group('placa o VIN digitados', () {
    const vin = '1HGCM82633A004352';
    final sinIdentificar = servicio(41, placa: null);
    final desvare = servicio(41, placa: null, tipo: 'desvare');

    List<String> faltan(Servicio s, {String placa = '', String vin = ''}) =>
        faltantesDeIdentificacion(s, placaDigitada: placa, vinDigitado: vin);

    test('sin digitar nada dice qué falta', () {
      expect(faltan(sinIdentificar), ['El vehículo necesita placa o VIN (al menos uno).']);
      expect(faltan(desvare), ['Un desvare exige la placa del vehículo.']);
    });

    test('una placa digitada basta, escrita como se lea: se normaliza', () {
      expect(faltan(sinIdentificar, placa: 'abc-123'), isEmpty);
      expect(faltan(desvare, placa: ' abc 123 '), isEmpty);
    });

    test('un VIN digitado basta en un traslado, con espacios o guiones', () {
      expect(faltan(sinIdentificar, vin: '1hgcm-82633 a004352'), isEmpty);
    });

    test('un desvare con solo el VIN digitado sigue sin poder recogerse', () {
      expect(faltan(desvare, vin: vin), ['Un desvare exige la placa del vehículo.']);
    });

    test('un VIN mal digitado dice cómo debe ser: 17, sin I, O ni Q', () {
      const formato = 'El VIN debe tener 17 letras o dígitos, sin I, O ni Q.';
      expect(faltan(sinIdentificar, vin: '1HGCM82633A00435'), [formato]);
      expect(faltan(sinIdentificar, vin: '1HGCM82633A0O4352'), [formato]);
      // Aunque la placa ya baste, un VIN mal escrito no se envía.
      expect(faltan(sinIdentificar, placa: 'ABC123', vin: 'MALO'), [formato]);
    });

    test('una placa de más de 10 letras o dígitos no es válida', () {
      expect(faltan(desvare, placa: 'ABCDEFGHIJK'), [
        'La placa debe tener de 1 a 10 letras o dígitos.',
      ]);
      expect(faltan(desvare, placa: 'ABCDEFGHIJ'), isEmpty);
    });
  });

  group('capacidad de la grúa', () {
    test('con la grúa de un puesto ocupada, bloquea y dice qué vehículo falta entregar', () {
      final montado = servicio(41, estado: 'recogido', placa: 'ABC123');
      final siguiente = servicio(42, placa: 'XYZ789');

      final bloqueo = bloqueoDeRecogida(siguiente, [
        montado,
        siguiente,
      ], configuracion: configuracion)!;

      expect(bloqueo.titulo, 'La grúa va llena');
      expect(bloqueo.faltanPorEntregar.map((s) => s.id), [41]);
      expect(bloqueo.mensaje, contains('ABC123'));
      expect(bloqueo.mensaje, contains('Márquelo como Entregado'));
    });

    test('una novedad de un vehículo ya recogido sigue ocupando el puesto', () {
      final montado = servicio(41, estado: 'novedad', estadoPrevio: 'recogido');
      final siguiente = servicio(42, placa: 'XYZ789');

      final bloqueo = bloqueoDeRecogida(siguiente, [
        montado,
        siguiente,
      ], configuracion: configuracion);

      expect(bloqueo?.faltanPorEntregar.map((s) => s.id), [41]);
    });

    test('una novedad antes de recoger, o un vehículo solo asignado, no ocupan puesto', () {
      final enNovedad = servicio(41, estado: 'novedad', estadoPrevio: 'en_camino');
      final asignado = servicio(43, estado: 'asignado', placa: 'JKL456');
      final siguiente = servicio(42, placa: 'XYZ789');

      expect(
        bloqueoDeRecogida(siguiente, [
          enNovedad,
          asignado,
          siguiente,
        ], configuracion: configuracion),
        isNull,
      );
    });

    test('con capacidad 2 permite dos montados y bloquea el tercero diciendo los dos', () {
      final primero = servicio(41, estado: 'recogido', placa: 'ABC123', capacidad: 2);
      final segundo = servicio(42, placa: 'XYZ789', capacidad: 2);
      final tercero = servicio(43, placa: 'JKL456', capacidad: 2);

      expect(
        bloqueoDeRecogida(segundo, [primero, segundo, tercero], configuracion: configuracion),
        isNull,
      );

      final segundoMontado = servicio(42, estado: 'recogido', placa: 'XYZ789', capacidad: 2);
      final bloqueo = bloqueoDeRecogida(tercero, [
        primero,
        segundoMontado,
        tercero,
      ], configuracion: configuracion)!;

      expect(bloqueo.faltanPorEntregar.map((s) => s.id), [41, 42]);
      expect(bloqueo.mensaje, contains('ABC123, XYZ789'));
      expect(bloqueo.mensaje, contains('2 puestos'));
    });

    test('solo cuentan los vehículos montados en la misma grúa', () {
      final enOtraGrua = servicio(41, estado: 'recogido', grua: 9);
      final siguiente = servicio(42, placa: 'XYZ789');

      expect(
        bloqueoDeRecogida(siguiente, [enOtraGrua, siguiente], configuracion: configuracion),
        isNull,
      );
    });

    test('con "al asignar", la identificación se revisa antes que la capacidad', () {
      final montado = servicio(41, estado: 'recogido');
      final sinPlaca = servicio(42, placa: null);
      const alAsignar = ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'asignar');

      final bloqueo = bloqueoDeRecogida(sinPlaca, [montado, sinPlaca], configuracion: alAsignar)!;

      expect(bloqueo.titulo, 'Falta identificar el vehículo');
    });

    test('con "al recoger", un vehículo sin placa ni VIN se bloquea igual por la grúa llena', () {
      final montado = servicio(41, estado: 'recogido');
      final sinPlaca = servicio(42, placa: null);

      final bloqueo = bloqueoDeRecogida(sinPlaca, [
        montado,
        sinPlaca,
      ], configuracion: configuracion)!;

      expect(bloqueo.titulo, 'La grúa va llena');
    });
  });
}
