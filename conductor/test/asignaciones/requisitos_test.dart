// Lo que exige la app antes de guardar un Recogido o un Entregado: identificación del vehículo y
// puesto libre en la grúa (Recogido), mínimo de fotos y nombre de quien entrega o recibe (los dos).

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
    test('con placa se puede recoger', () {
      final s = servicio(41);

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
    });

    test('con VIN y sin placa se puede recoger un traslado', () {
      final s = servicio(41, placa: null, vin: '1HGCM82633A004352');

      expect(bloqueoDeRecogida(s, [s], configuracion: configuracion), isNull);
    });

    test('sin placa ni VIN no se puede recoger, y dice que lo registre logística', () {
      final s = servicio(41, placa: null);

      final bloqueo = bloqueoDeRecogida(s, [s], configuracion: configuracion)!;

      expect(bloqueo.titulo, 'Falta identificar el vehículo');
      expect(bloqueo.mensaje, contains('El vehículo necesita placa o VIN (al menos uno).'));
      expect(bloqueo.mensaje, contains('Llame a logística'));
      expect(bloqueo.faltanPorEntregar, isEmpty);
    });

    test('un desvare exige la placa aunque tenga VIN', () {
      final s = servicio(41, placa: null, vin: '1HGCM82633A004352', tipo: 'desvare');

      final bloqueo = bloqueoDeRecogida(s, [s], configuracion: configuracion)!;

      expect(bloqueo.mensaje, contains('Un desvare exige la placa del vehículo.'));
    });

    test('al recoger se exige siempre, también con la configuración "al asignar"', () {
      final s = servicio(41, placa: null);
      const alAsignar = ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'asignar');

      expect(bloqueoDeRecogida(s, [s], configuracion: alAsignar), isNotNull);
      expect(bloqueoDeRecogida(s, [s], configuracion: null), isNotNull);
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

    test('la identificación se revisa antes que la capacidad', () {
      final montado = servicio(41, estado: 'recogido');
      final sinPlaca = servicio(42, placa: null);

      final bloqueo = bloqueoDeRecogida(sinPlaca, [
        montado,
        sinPlaca,
      ], configuracion: configuracion)!;

      expect(bloqueo.titulo, 'Falta identificar el vehículo');
    });
  });
}
