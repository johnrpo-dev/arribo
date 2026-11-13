// El modelo local del servicio: lo que se guarda y lo que nunca se guarda (valores de cobro).

import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

/// Palabras de cobro que no pueden aparecer en el modelo ni en la base (CLAUDE.md: el conductor
/// nunca recibe valores).
final _palabrasDeCobro = RegExp(
  r'valor|tarifa|cobro|factura|pagador|precio|pago|total|monto',
  caseSensitive: false,
);

void main() {
  test('el modelo local no tiene campos de valor de cobro', () {
    final fila = Servicio.desdeJson(servicioJson()).aFila(0);

    expect(fila.keys.where(_palabrasDeCobro.hasMatch), isEmpty);
  });

  test('la tabla local de servicios no tiene columnas de valor de cobro', () async {
    final prueba = await BaseDePrueba.crear();
    addTearDown(prueba.cerrar);

    final columnas = await prueba.base.db.rawQuery('PRAGMA table_info(servicios)');

    final nombres = [for (final c in columnas) c['name']! as String];
    expect(nombres, isNotEmpty);
    expect(nombres.where(_palabrasDeCobro.hasMatch), isEmpty);
  });

  test('ninguna tabla de la base local tiene columnas de valor de cobro', () async {
    final prueba = await BaseDePrueba.crear();
    addTearDown(prueba.cerrar);

    final todas = <String>[];
    for (final tabla in ['estado_local', 'servicios', 'eventos_pendientes', 'fotos_pendientes']) {
      final columnas = await prueba.base.db.rawQuery('PRAGMA table_info($tabla)');
      todas.addAll([for (final c in columnas) '$tabla.${c['name']}']);
    }
    expect(todas.where(_palabrasDeCobro.hasMatch), isEmpty);
  });

  test('un valor de cobro que llegara por error en la API no se guarda en ninguna parte', () async {
    final prueba = await BaseDePrueba.crear();
    addTearDown(prueba.cerrar);
    final json = {
      ...servicioJson(),
      'valor': '250000.00',
      'tarifa': 180000,
      'pagador': 'Aseguradora',
    };

    final fila = Servicio.desdeJson(json).aFila(0);
    await prueba.base.db.insert('servicios', fila);

    final guardado = await prueba.base.db.query('servicios');
    final textos = guardado.single.values.map((v) => '$v').join('|');
    expect(textos, isNot(contains('250000')));
    expect(textos, isNot(contains('180000')));
    expect(textos, isNot(contains('Aseguradora')));
  });

  test('lo que se guarda en la base vuelve igual al leerlo', () async {
    final prueba = await BaseDePrueba.crear();
    addTearDown(prueba.cerrar);
    final original = Servicio.desdeJson(servicioJson());

    await prueba.base.db.insert('servicios', original.aFila(0));
    final leido = Servicio.desdeFila((await prueba.base.db.query('servicios')).single);

    expect(leido.aFila(0), original.aFila(0));
    expect(leido.programadaPara, DateTime.utc(2026, 11, 20, 19, 30));
    expect(leido.programadaPara!.isUtc, isTrue);
    expect(leido.vehiculo.descripcion, 'Mazda CX-30 Rojo');
    expect(leido.grua?.placa, 'GRU001');
  });

  test('un desvare sin destino y sin contacto se lee con el destino vacío', () {
    final json = {
      ...servicioJson(tipo: 'desvare'),
      'destino': {'direccion': null, 'ubicacion': null, 'contacto': null},
      'programada_para': null,
    };

    final servicio = Servicio.desdeJson(json);

    expect(servicio.destino.vacio, isTrue);
    expect(servicio.programadaPara, isNull);
  });

  test('un texto en blanco se trata como sin dato', () {
    final json = {...servicioJson(), 'referencia_externa': '   '};

    expect(Servicio.desdeJson(json).referenciaExterna, isNull);
  });

  test('un campo indispensable con otro tipo rechaza el servicio', () {
    expect(
      () => Servicio.desdeJson({...servicioJson(), 'id': '41'}),
      throwsA(isA<FormatException>()),
    );
  });

  test('la configuración se guarda y se lee', () {
    final configuracion = ConfiguracionApp.desdeJson({
      'minimo_fotos': 6,
      'momento_placa_vin': 'asignar',
    });

    expect(ConfiguracionApp.desdeJson(configuracion.aJson()).aJson(), {
      'minimo_fotos': 6,
      'momento_placa_vin': 'asignar',
    });
    expect(Clave.configuracion, 'configuracion');
  });
}
