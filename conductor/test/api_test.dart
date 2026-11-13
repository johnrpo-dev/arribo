// Cliente de la API contra un servidor falso con las respuestas del contrato.

import 'dart:async';

import 'package:arribo_conductor/api.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'ayudas.dart';

void main() {
  Future<Ingreso> ingresar(ServidorFalso servidor, {String pin = '482913'}) =>
      servidor.api().ingresar(
        celular: '300 123 4567',
        pin: pin,
        dispositivoId: '7f0c2a64-3f7e-4b4e-9d55-0b7f1e2c9a10',
        dispositivoNombre: 'Motorola moto g32',
      );

  group('ingresar', () {
    test(
      'el ingreso correcto manda celular, PIN y dispositivo, y devuelve token y conductor',
      () async {
        final servidor = ServidorFalso((_) async => ingresoCorrecto(token: 'q3V9lW0m'));

        final ingreso = await ingresar(servidor);

        expect(ingreso.token, 'q3V9lW0m');
        expect(ingreso.conductor.nombre, 'Ana Gómez');
        final peticion = servidor.peticiones.single;
        expect(peticion.metodo, 'POST');
        expect(peticion.url.toString(), 'http://servidor.prueba/api/v1/ingresar/');
        expect(peticion.cabeceras['Content-Type'], startsWith('application/json'));
        expect(peticion.cabeceras.containsKey('Authorization'), isFalse);
        expect(peticion.json, {
          'celular': '300 123 4567',
          'pin': '482913',
          'dispositivo_id': '7f0c2a64-3f7e-4b4e-9d55-0b7f1e2c9a10',
          'dispositivo_nombre': 'Motorola moto g32',
        });
      },
    );

    test('el PIN va como texto y conserva el cero inicial', () async {
      final servidor = ServidorFalso((_) async => ingresoCorrecto());

      await ingresar(servidor, pin: '012345');

      expect(servidor.peticiones.single.json['pin'], '012345');
    });

    test('sin nombre del dispositivo no se manda el campo opcional', () async {
      final servidor = ServidorFalso((_) async => ingresoCorrecto());

      await servidor.api().ingresar(celular: '3001234567', pin: '482913', dispositivoId: 'x');

      expect(servidor.peticiones.single.json.containsKey('dispositivo_nombre'), isFalse);
    });

    test(
      'un PIN malo es un error del contrato con el detalle del servidor, no una sesión cerrada',
      () async {
        final servidor = ServidorFalso(
          (_) async =>
              errorDelContrato(401, 'credenciales_invalidas', 'Celular o PIN incorrectos.'),
        );

        final error = await ingresar(servidor).then<Object?>((_) => null, onError: (Object e) => e);

        expect(error, isA<ErrorDeContrato>());
        final contrato = error! as ErrorDeContrato;
        expect(contrato.codigo, 'credenciales_invalidas');
        expect(contrato.mensaje, 'Celular o PIN incorrectos.');
      },
    );

    test('el bloqueo por intentos trae el tiempo que informa el servidor', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(
          429,
          'demasiados_intentos',
          'Demasiados intentos fallidos. Intente de nuevo en 15 minutos.',
          extra: {'reintentar_en': 900},
          cabeceras: {'retry-after': '900'},
        ),
      );

      await expectLater(
        ingresar(servidor),
        throwsA(
          isA<ErrorDeContrato>()
              .having((e) => e.codigo, 'codigo', 'demasiados_intentos')
              .having((e) => e.reintentarEn, 'reintentarEn', const Duration(minutes: 15))
              .having((e) => e.detalle, 'detalle', contains('15 minutos')),
        ),
      );
    });

    test('sin reintentar_en en el cuerpo, el bloqueo usa la cabecera Retry-After', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(
          429,
          'demasiados_intentos',
          'Demasiados intentos.',
          cabeceras: {'retry-after': '120'},
        ),
      );

      await expectLater(
        ingresar(servidor),
        throwsA(
          isA<ErrorDeContrato>().having(
            (e) => e.reintentarEn,
            'reintentarEn',
            const Duration(minutes: 2),
          ),
        ),
      );
    });

    test('los datos inválidos traen los errores por campo', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(
          400,
          'datos_invalidos',
          'Revise los datos enviados.',
          extra: {
            'campos': {
              'pin': ['El PIN tiene exactamente 6 dígitos, del 0 al 9.'],
            },
          },
        ),
      );

      await expectLater(
        ingresar(servidor),
        throwsA(
          isA<ErrorDeContrato>().having((e) => e.campos['pin'], 'campos.pin', [
            'El PIN tiene exactamente 6 dígitos, del 0 al 9.',
          ]),
        ),
      );
    });

    test('un conductor inhabilitado responde con el detalle del servidor', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(401, 'conductor_no_habilitado', 'Su usuario está inactivo.'),
      );

      await expectLater(
        ingresar(servidor),
        throwsA(
          isA<ErrorDeContrato>().having((e) => e.mensaje, 'mensaje', 'Su usuario está inactivo.'),
        ),
      );
    });
  });

  group('asignaciones', () {
    test('manda el token Bearer y lee la lista en orden, con configuración y ETag', () async {
      final servidor = ServidorFalso(
        (_) async => listaCorrecta([
          servicioJson(id: 41, ordenRonda: 1),
          servicioJson(id: 39, ordenRonda: 3),
        ], etag: '"3f2a"'),
      );

      final respuesta = await servidor.api().asignaciones('token-ana');

      final peticion = servidor.peticiones.single;
      expect(peticion.metodo, 'GET');
      expect(peticion.url.path, '/api/v1/asignaciones/');
      expect(peticion.cabeceras['Authorization'], 'Bearer token-ana');
      expect(peticion.cabeceras.containsKey('If-None-Match'), isFalse);
      expect(respuesta, isA<AsignacionesNuevas>());
      final nuevas = respuesta as AsignacionesNuevas;
      expect(nuevas.etag, '"3f2a"');
      expect(nuevas.configuracion.minimoFotos, 4);
      expect([for (final s in nuevas.servicios) s.id], [41, 39]);
      final primero = nuevas.servicios.first;
      expect(primero.origen.contactoTelefono, '6044445566');
      expect(primero.programadaPara, DateTime.utc(2026, 11, 20, 19, 30));
    });

    test('con ETag manda If-None-Match y un 304 es "sin cambios"', () async {
      final servidor = ServidorFalso((_) async => http.Response('', 304));

      final respuesta = await servidor.api().asignaciones('token-ana', etag: '"3f2a"');

      expect(servidor.peticiones.single.cabeceras['If-None-Match'], '"3f2a"');
      expect(respuesta, isA<AsignacionesSinCambios>());
    });

    test('un 401 con token es sesión cerrada con el detalle del servidor', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(
          401,
          'sesion_invalida',
          'Su sesión ya no es válida. Ingrese de nuevo.',
        ),
      );

      await expectLater(
        servidor.api().asignaciones('revocado'),
        throwsA(
          isA<SesionCerrada>()
              .having((e) => e.codigo, 'codigo', 'sesion_invalida')
              .having((e) => e.detalle, 'detalle', 'Su sesión ya no es válida. Ingrese de nuevo.'),
        ),
      );
    });

    test('la app ignora los campos que no conoce', () async {
      final servidor = ServidorFalso(
        (_) async => respuestaJson(200, {
          ...listaJson([
            {
              ...servicioJson(),
              'campo_futuro': 'algo',
              'vehiculo_extra': {'x': 1},
            },
          ]),
          'otra_cosa': true,
        }),
      );

      final respuesta = await servidor.api().asignaciones('token-ana') as AsignacionesNuevas;

      expect(respuesta.servicios.single.id, 41);
    });

    test('una respuesta 200 sin un campo indispensable es respuesta inesperada', () async {
      final servidor = ServidorFalso(
        (_) async => respuestaJson(
          200,
          listaJson([
            {...servicioJson()}..remove('estado'),
          ]),
        ),
      );

      await expectLater(
        servidor.api().asignaciones('token-ana'),
        throwsA(isA<RespuestaInesperada>()),
      );
    });

    test('un 500 sin cuerpo JSON es error del servidor', () async {
      final servidor = ServidorFalso((_) async => http.Response('<h1>Server Error</h1>', 500));

      await expectLater(
        servidor.api().asignaciones('token-ana'),
        throwsA(isA<ErrorDelServidor>().having((e) => e.estadoHttp, 'estadoHttp', 500)),
      );
    });
  });

  group('red', () {
    test('sin señal es error de red', () async {
      final servidor = ServidorFalso((_) async => sinSenal());

      await expectLater(servidor.api().asignaciones('token-ana'), throwsA(isA<ErrorDeRed>()));
    });

    test('un servidor que no responde a tiempo es error de red', () async {
      final servidor = ServidorFalso((_) => Completer<http.Response>().future);

      await expectLater(
        servidor.api(tiempoMaximo: const Duration(milliseconds: 50)).asignaciones('token-ana'),
        throwsA(isA<ErrorDeRed>()),
      );
    });
  });

  group('salir', () {
    test('cierra la sesión con el token y acepta el 204', () async {
      final servidor = ServidorFalso((_) async => http.Response('', 204));

      await servidor.api().salir('token-ana');

      final peticion = servidor.peticiones.single;
      expect(peticion.url.path, '/api/v1/salir/');
      expect(peticion.cabeceras['Authorization'], 'Bearer token-ana');
    });

    test('un 401 al salir se toma como sesión ya cerrada', () async {
      final servidor = ServidorFalso(
        (_) async => errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida.'),
      );

      await servidor.api().salir('token-ana');
    });
  });

  test('la dirección del servidor admite barra final', () {
    expect(
      ClienteApi(servidor: 'https://arribo.ejemplo.co/', cliente: http.Client()).servidor,
      'https://arribo.ejemplo.co',
    );
  });
}
