// Las copias de las reglas del servidor que tiene la app (estados, capacidad, identificación del
// vehículo y límites de las fotos) cumplen los casos de docs/casos-reglas.json, el mismo archivo
// que recorre backend/tests/nucleo/test_casos_compartidos.py. Si una regla cambia en el servidor y
// no en la app, esta prueba falla.

import 'dart:convert';
import 'dart:io';

import 'package:arribo_conductor/asignaciones/capacidad.dart';
import 'package:arribo_conductor/asignaciones/estados.dart';
import 'package:arribo_conductor/asignaciones/identificacion.dart';
import 'package:arribo_conductor/fotos/foto.dart';
import 'package:flutter_test/flutter_test.dart';

/// `flutter test` corre desde conductor/; el archivo está en docs/, en la raíz del repositorio.
final Map<String, Object?> casos =
    jsonDecode(File('../docs/casos-reglas.json').readAsStringSync()) as Map<String, Object?>;

List<Map<String, Object?>> lista(Object? valor) => (valor! as List<Object?>).cast();

void main() {
  final estados = casos['estados']! as Map<String, Object?>;
  final identificacion = casos['identificacion']! as Map<String, Object?>;
  final evidencia = casos['evidencia']! as Map<String, Object?>;

  group('estados', () {
    final transiciones = lista(estados['transiciones']);
    final todos = (estados['todos']! as List<Object?>).cast<String>();

    test('el archivo trae cada par de estado y destino', () {
      final pares = {for (final caso in transiciones) '${caso['estado']}>${caso['destino']}'};
      expect(pares, {
        for (final estado in todos)
          for (final destino in todos) '$estado>$destino',
      });
    });

    test('los destinos que se marcan desde la app son los del servidor', () {
      expect(destinosDesdeLaApp, (estados['destinos_desde_la_app']! as List<Object?>).toSet());
    });

    test('la app permite marcar exactamente las transiciones que el servidor acepta de la app', () {
      for (final caso in transiciones) {
        final estado = caso['estado']! as String;
        final destino = caso['destino']! as String;
        expect(puedeMarcar(estado, destino), caso['desde_la_app'], reason: '$estado → $destino');
      }
    });

    test('después de marcar, el estado y el estado previo quedan como en el servidor', () {
      for (final caso in transiciones) {
        final estado = caso['estado']! as String;
        final destino = caso['destino']! as String;
        final queda = caso['queda'] as Map<String, Object?>?;
        final marcado = EstadoDeServicio(estado).marcar(destino);
        expect(marcado.estado, queda?['estado'] ?? estado, reason: '$estado → $destino');
        expect(marcado.estadoPrevio, queda?['estado_previo'], reason: '$estado → $destino');
      }
    });

    test('el paso que ofrece la app es el único avance que el servidor acepta', () {
      for (final estado in todos) {
        final avances = [
          for (final caso in transiciones)
            if (caso['estado'] == estado &&
                caso['desde_la_app'] == true &&
                caso['destino'] != Estado.novedad)
              caso['destino'],
        ];
        expect(avances.length, lessThanOrEqualTo(1), reason: estado);
        expect(siguientePaso(estado), avances.firstOrNull, reason: estado);
        final novedad = transiciones.firstWhere(
          (caso) => caso['estado'] == estado && caso['destino'] == Estado.novedad,
        );
        expect(admiteNovedad(estado), novedad['desde_la_app'], reason: estado);
      }
    });

    test('va montado (a bordo) en los mismos estados que en el servidor', () {
      for (final caso in lista(estados['a_bordo'])) {
        final estado = EstadoDeServicio(
          caso['estado']! as String,
          caso['estado_previo'] as String?,
        );
        expect(estado.aBordo, caso['a_bordo'], reason: '$caso');
      }
    });
  });

  group('capacidad', () {
    for (final caso in lista(casos['capacidad'])) {
      test('${caso['nombre']}', () {
        final montados = [
          for (final otro in lista(caso['otros']))
            if (EstadoDeServicio(
              otro['estado']! as String,
              otro['estado_previo'] as String?,
            ).aBordo)
              otro['id']! as String,
        ];

        final excedida = verificarRecogida(caso['capacidad']! as int, montados);

        expect(excedida != null, caso['bloquea']);
        expect(excedida?.pendientesDeEntregar ?? const <String>[], caso['faltan_por_entregar']);
      });
    }

    test('una capacidad menor que 1 no es válida', () {
      for (final capacidad in (casos['capacidad_invalida']! as List<Object?>).cast<int>()) {
        expect(() => verificarRecogida(capacidad, const <String>[]), throwsArgumentError);
      }
    });
  });

  group('identificación del vehículo', () {
    test('la placa se normaliza igual que en el servidor', () {
      for (final caso in lista(identificacion['placas'])) {
        expect(normalizarPlaca(caso['texto'] as String?), caso['normalizada'], reason: '$caso');
      }
    });

    test('el VIN se normaliza y se valida igual: 17 caracteres sin I, O ni Q', () {
      for (final caso in lista(identificacion['vin'])) {
        final vin = normalizarVin(caso['texto'] as String?);
        expect(vin, caso['normalizado'], reason: '$caso');
        expect(vinValido(vin), caso['valido'], reason: '$caso');
      }
    });

    test('placa o VIN, al menos uno; el desvare exige placa', () {
      for (final caso in lista(identificacion['vehiculo'])) {
        final falta = identificacionFaltante(
          placa: caso['placa'] as String?,
          vin: caso['vin'] as String?,
          tipo: caso['tipo']! as String,
        );
        expect(falta == null, caso['completa'], reason: '$caso');
      }
    });

    test('al recoger se exige siempre; al asignar, según la configuración', () {
      for (final caso in lista(identificacion['exigida'])) {
        expect(
          identificacionExigida(caso['configurado']! as String, caso['momento']! as String),
          caso['exigida'],
          reason: '$caso',
        );
      }
    });
  });

  group('fotos', () {
    test('el tope de tamaño es el del servidor', () {
      expect(tamanoMaximoFoto, evidencia['tamano_maximo_bytes']);
      for (final caso in lista(evidencia['tamanos'])) {
        expect(excedeElTamano(caso['bytes']! as int), caso['excede'], reason: '$caso');
      }
    });

    test('solo es JPEG lo que empieza como un JPEG', () {
      for (final caso in lista(evidencia['jpeg'])) {
        final bytes = (caso['primeros_bytes']! as List<Object?>).cast<int>();
        expect(esJpeg(bytes), caso['es_jpeg'], reason: '$caso');
      }
    });

    test('la foto de recogida acompaña al Recogido y la de entrega al Entregado', () {
      for (final caso in lista(evidencia['acompana'])) {
        expect(
          acompana(caso['tipo']! as String, caso['destino']! as String),
          caso['acompana'],
          reason: '$caso',
        );
      }
      expect(TipoFoto.eventoQueAcompana.keys.toList()..sort(), evidencia['tipos_desde_la_app']);
      expect(TipoFoto.para(Estado.recogido), TipoFoto.recogida);
      expect(TipoFoto.para(Estado.entregado), TipoFoto.entrega);
    });
  });
}
