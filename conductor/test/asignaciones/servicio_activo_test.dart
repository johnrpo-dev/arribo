// El servicio activo: el que la lista pone arriba ("Ahora") con el botón del paso que sigue.

import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/asignaciones/servicio_activo.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

Servicio servicio(int id, String estado, {bool esperaIda = false}) =>
    Servicio.desdeJson(servicioJson(id: id, estado: estado, esperaIda: esperaIda));

void main() {
  test('sin servicios no hay activo', () {
    expect(servicioActivo([]), isNull);
  });

  test('el primero asignado de la lista es el activo', () {
    expect(servicioActivo([servicio(1, 'asignado'), servicio(2, 'asignado')])?.id, 1);
  });

  test('uno en camino gana aunque haya un asignado antes en la lista', () {
    final lista = [servicio(1, 'asignado'), servicio(2, 'en_camino'), servicio(3, 'asignado')];
    expect(servicioActivo(lista)?.id, 2);
  });

  test('uno recogido gana aunque haya un asignado antes en la lista', () {
    expect(servicioActivo([servicio(1, 'asignado'), servicio(2, 'recogido')])?.id, 2);
  });

  test('entre los que ya empezaron, el primero de la lista', () {
    expect(servicioActivo([servicio(1, 'recogido'), servicio(2, 'en_camino')])?.id, 1);
  });

  test('una novedad nunca es el activo: se salta', () {
    expect(servicioActivo([servicio(1, 'novedad'), servicio(2, 'asignado')])?.id, 2);
    expect(servicioActivo([servicio(1, 'novedad')]), isNull);
  });

  test('un regreso que espera a su ida no es el activo', () {
    final lista = [servicio(1, 'asignado', esperaIda: true), servicio(2, 'asignado')];
    expect(servicioActivo(lista)?.id, 2);
    expect(servicioActivo([servicio(1, 'asignado', esperaIda: true)]), isNull);
  });

  test('entregado, cancelado y pendiente de asignar nunca son el activo', () {
    final lista = [
      servicio(1, 'entregado'),
      servicio(2, 'cancelado'),
      servicio(3, 'pendiente_asignar'),
    ];
    expect(servicioActivo(lista), isNull);
  });
}
