// Cliente de la API: envío de lotes de eventos (POST /api/v1/eventos/, docs/api-conductor.md).

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/cola/evento.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'ayudas.dart';

void main() {
  final hora = DateTime.utc(2026, 11, 20, 19, 42, 7);
  EventoLocal evento(
    String id, {
    int servicio = 41,
    int secuencia = 118,
    String destino = 'en_camino',
  }) => EventoLocal(
    id: id,
    conductorId: 3,
    servicioId: servicio,
    destino: destino,
    secuencia: secuencia,
    horaDispositivo: hora,
    creadoEn: hora,
  );
  const a = '0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e';
  const b = '9a3c5d1e-0c2a-4f7e-8b4e-9d550b7f1e2c';

  test(
    'manda el lote con el token Bearer y los campos del contrato, sin conductor ni valores',
    () async {
      final servidor = ServidorFalso((_) async => respuestaEventos([resultadoJson(a)]));

      await servidor.api().enviarEventos('token-ana', [evento(a)]);

      final peticion = servidor.peticiones.single;
      expect(peticion.metodo, 'POST');
      expect(peticion.url.path, '/api/v1/eventos/');
      expect(peticion.cabeceras['Authorization'], 'Bearer token-ana');
      expect(peticion.cabeceras['Content-Type'], startsWith('application/json'));
      expect(peticion.json, {
        'eventos': [
          {
            'id': a,
            'servicio_id': 41,
            'destino': 'en_camino',
            'secuencia': 118,
            'hora_dispositivo': '2026-11-20T19:42:07.000Z',
            'motivo': null,
            'nombre_quien': null,
            'latitud': null,
            'longitud': null,
          },
        ],
      });
    },
  );

  test('lee un resultado por evento, en el mismo orden, con el estado del servicio', () async {
    final servidor = ServidorFalso(
      (_) async => respuestaEventos([
        resultadoJson(a, servicio: servicioRemotoJson(41, estado: 'en_camino')),
        resultadoJson(
          b,
          resultado: 'conflicto',
          motivo: 'servicio_cancelado',
          detalle: 'El servicio ya estaba cancelado.',
          servicio: servicioRemotoJson(42, estado: 'cancelado'),
        ),
      ]),
    );

    final resultados = await servidor.api().enviarEventos('t', [
      evento(a),
      evento(b, servicio: 42),
    ]);

    expect(resultados[0].resultado, 'aplicado');
    expect(resultados[0].duplicado, isFalse);
    expect(resultados[0].servicio!.estado, 'en_camino');
    expect(resultados[0].servicio!.enSuRonda, isTrue);
    expect(resultados[1].resultado, 'conflicto');
    expect(resultados[1].motivo, 'servicio_cancelado');
    expect(resultados[1].detalle, 'El servicio ya estaba cancelado.');
    expect(resultados[1].servicio!.estado, 'cancelado');
    expect(resultados[1].servicio!.enSuRonda, isFalse);
  });

  test('un servicio que ya no es del conductor llega sin estado y fuera de su ronda', () async {
    final servidor = ServidorFalso(
      (_) async => respuestaEventos([
        resultadoJson(a, resultado: 'conflicto', servicio: servicioRemotoJson(41, estado: null)),
      ]),
    );

    final resultado = (await servidor.api().enviarEventos('t', [evento(a)])).single;

    expect(resultado.servicio!.estado, isNull);
    expect(resultado.servicio!.enSuRonda, isFalse);
  });

  test('ignora los campos que no conoce y acepta el id en mayúsculas', () async {
    final servidor = ServidorFalso(
      (_) async => respuestaEventos([
        {...resultadoJson(a.toUpperCase(), duplicado: true), 'campo_nuevo': 1},
      ]),
    );

    final resultado = (await servidor.api().enviarEventos('t', [evento(a)])).single;

    expect(resultado.resultado, 'aplicado');
    expect(resultado.duplicado, isTrue);
    expect(resultado.servicio, isNull);
  });

  test('si faltan resultados, no se usa ninguno', () async {
    final servidor = ServidorFalso((_) async => respuestaEventos([resultadoJson(a)]));

    await expectLater(
      servidor.api().enviarEventos('t', [evento(a), evento(b, secuencia: 119)]),
      throwsA(isA<RespuestaInesperada>()),
    );
  });

  test('si un resultado no es del evento de su posición, no se usa ninguno', () async {
    final servidor = ServidorFalso(
      (_) async => respuestaEventos([resultadoJson(b), resultadoJson(a)]),
    );

    await expectLater(
      servidor.api().enviarEventos('t', [evento(a), evento(b, secuencia: 119)]),
      throwsA(isA<RespuestaInesperada>()),
    );
  });

  test('un resultado sin su campo `resultado` no se usa', () async {
    final servidor = ServidorFalso(
      (_) async => respuestaEventos([
        {'id': a, 'duplicado': false},
      ]),
    );

    await expectLater(
      servidor.api().enviarEventos('t', [evento(a)]),
      throwsA(isA<RespuestaInesperada>()),
    );
  });

  test('un 401 es sesión cerrada; un 500, error del servidor; sin señal, error de red', () async {
    final servidor = ServidorFalso(
      (_) async => errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida.'),
    );
    await expectLater(
      servidor.api().enviarEventos('t', [evento(a)]),
      throwsA(isA<SesionCerrada>()),
    );

    servidor.responder = (_) async => http.Response('', 500);
    await expectLater(
      servidor.api().enviarEventos('t', [evento(a)]),
      throwsA(isA<ErrorDelServidor>()),
    );

    servidor.responder = (_) async => sinSenal();
    await expectLater(servidor.api().enviarEventos('t', [evento(a)]), throwsA(isA<ErrorDeRed>()));
  });

  test('el tope de un lote es el del contrato: 100 eventos', () {
    expect(maximoEventosPorLote, 100);
  });
}
