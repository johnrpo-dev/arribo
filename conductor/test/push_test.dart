// Avisos push (1a-14): registrar el token de push con la sesión, reintentarlo sin señal, borrarlo
// al cerrar sesión y refrescar la lista cuando llega o se toca un aviso. Con un Firebase falso:
// ninguna prueba usa Firebase ni la red.

import 'dart:async';

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:arribo_conductor/push.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'ayudas.dart';

/// Firebase falso: da el token que se le pida y deja emitir avisos y cambios de token.
class MensajeriaFalsa implements MensajeriaPush {
  String? tokenActual = 'fcm-1';

  /// Si no es null, `token()` lo lanza (Firebase sin señal la primera vez).
  Object? errorAlDarToken;
  int permisosPedidos = 0;
  int tokensBorrados = 0;

  final _tokensNuevos = StreamController<String>.broadcast();
  final _conLaAppAbierta = StreamController<MensajePush>.broadcast();
  final _tocados = StreamController<MensajePush>.broadcast();

  void cambiarToken(String nuevo) {
    tokenActual = nuevo;
    _tokensNuevos.add(nuevo);
  }

  void llegaAviso(MensajePush aviso) => _conLaAppAbierta.add(aviso);

  void tocarAviso(MensajePush aviso) => _tocados.add(aviso);

  @override
  Future<bool> pedirPermiso() async {
    permisosPedidos++;
    return true;
  }

  @override
  Future<String?> token() async {
    final error = errorAlDarToken;
    if (error != null) throw error;
    return tokenActual;
  }

  @override
  Stream<String> get tokensNuevos => _tokensNuevos.stream;

  @override
  Stream<MensajePush> get avisosConLaAppAbierta => _conLaAppAbierta.stream;

  @override
  Stream<MensajePush> get avisosTocados => _tocados.stream;

  @override
  Future<void> borrarToken() async {
    tokensBorrados++;
    tokenActual = 'fcm-despues-de-borrar';
  }
}

const asignado = MensajePush(tipo: 'asignado', servicioId: 41);

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  late ListaAsignaciones lista;
  late MensajeriaFalsa firebase;
  late RegistroPush registro;
  late http.Response Function() respuestaPush;
  final ahora = DateTime.utc(2026, 11, 20, 15);

  List<PeticionRecibida> peticionesA(String ruta) => [
    for (final p in servidor.peticiones)
      if (p.url.path == ruta) p,
  ];

  List<PeticionRecibida> registros() => peticionesA('/api/v1/push/');

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    respuestaPush = () => http.Response('', 204);
    servidor = ServidorFalso((peticion) async {
      return switch (peticion.url.path) {
        '/api/v1/ingresar/' => ingresoCorrecto(),
        '/api/v1/asignaciones/' => listaCorrecta([servicioJson(id: 41)]),
        '/api/v1/salir/' => http.Response('', 204),
        '/api/v1/push/' => respuestaPush(),
        _ => http.Response('', 404),
      };
    });
    token = AlmacenTokenEnMemoria();
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
    );
    firebase = MensajeriaFalsa();
    registro = RegistroPush(mensajeria: firebase, api: servidor.api(), sesion: sesion, lista: lista)
      ..iniciar();
  });
  tearDown(() async {
    await registro.cerrar();
    await prueba.cerrar();
  });

  group('registro del token', () {
    test('al ingresar registra el token de push con el token de la sesión', () async {
      await sesion.iniciar();
      expect(registros(), isEmpty); // sin sesión no se registra nada

      await sesion.ingresar(celular: '3001234567', pin: '482913');
      await registro.listo;

      final peticion = registros().single;
      expect(peticion.metodo, 'PUT');
      expect(peticion.cabeceras['Authorization'], 'Bearer token-ana');
      expect(peticion.json, {'token': 'fcm-1'});
      expect(registro.tokenRegistrado, 'fcm-1');
      expect(firebase.permisosPedidos, 1);
    });

    test('al abrir la app con sesión guardada lo registra otra vez', () async {
      token.token = 'token-ana';

      await sesion.iniciar();
      await registro.listo;

      expect(registros().single.cabeceras['Authorization'], 'Bearer token-ana');
      expect(registro.pendiente, isFalse);
    });

    test('cuando Firebase cambia el token registra el nuevo', () async {
      token.token = 'token-ana';
      await sesion.iniciar();
      await registro.listo;

      firebase.cambiarToken('fcm-2');
      await esperarHasta(() => registros().length == 2);
      await registro.listo;

      expect(registros().last.json, {'token': 'fcm-2'});
      expect(registro.tokenRegistrado, 'fcm-2');
      expect(firebase.permisosPedidos, 1); // el permiso se pide una sola vez
    });

    test('el mismo token no se vuelve a enviar en la misma sesión', () async {
      token.token = 'token-ana';
      await sesion.iniciar();
      await registro.listo;

      firebase.cambiarToken('fcm-1');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await registro.listo;

      expect(registros(), hasLength(1));
    });

    test('un token nuevo sin sesión no se envía', () async {
      await sesion.iniciar();

      firebase.cambiarToken('fcm-2');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await registro.listo;

      expect(registros(), isEmpty);
    });
  });

  group('sin señal', () {
    test(
      'si el registro falla por la red, se reintenta cuando el servidor responde la lista',
      () async {
        respuestaPush = sinSenal;
        token.token = 'token-ana';
        await sesion.iniciar();
        await registro.listo;
        expect(registro.pendiente, isTrue);
        expect(registro.tokenRegistrado, isNull);

        respuestaPush = () => http.Response('', 204);
        await lista.actualizar();
        await esperarHasta(() => registro.tokenRegistrado == 'fcm-1');

        expect(registros(), hasLength(2));
        expect(registro.pendiente, isFalse);
      },
    );

    test('si Firebase no da el token, se reintenta cuando el servidor responde la lista', () async {
      firebase.errorAlDarToken = Exception('SERVICE_NOT_AVAILABLE');
      token.token = 'token-ana';
      await sesion.iniciar();
      await registro.listo;
      expect(registro.pendiente, isTrue);
      expect(registros(), isEmpty);

      firebase.errorAlDarToken = null;
      await lista.actualizar();
      await esperarHasta(() => registro.tokenRegistrado == 'fcm-1');
    });

    test('un token que el servidor rechaza (400) no se reintenta', () async {
      respuestaPush = () => errorDelContrato(
        400,
        'datos_invalidos',
        'Revise los datos enviados.',
        extra: {
          'campos': {
            'token': ['El token de push no lleva espacios.'],
          },
        },
      );
      token.token = 'token-ana';
      await sesion.iniciar();
      await registro.listo;

      await lista.actualizar();
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await registro.listo;

      expect(registros(), hasLength(1));
      expect(registro.pendiente, isFalse);
      expect(sesion.estado, EstadoSesion.activa);
    });
  });

  group('cierre de sesión', () {
    test('al cerrar sesión borra el token en Firebase; el servidor lo borra con /salir/', () async {
      token.token = 'token-ana';
      await prueba.base.escribirJson(Clave.conductor, conductorJson());
      await sesion.iniciar();
      await registro.listo;

      expect(await sesion.salir(), ResultadoSalida.cerrada);
      await registro.listo;

      expect(firebase.tokensBorrados, 1);
      expect(peticionesA('/api/v1/salir/'), hasLength(1));
      expect(registro.tokenRegistrado, isNull);

      // Un token nuevo después de salir no se manda: no hay sesión.
      firebase.cambiarToken('fcm-3');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await registro.listo;
      expect(registros(), hasLength(1));
    });

    test('al volver a ingresar registra el token nuevo con la sesión nueva', () async {
      token.token = 'token-viejo';
      await prueba.base.escribirJson(Clave.conductor, conductorJson());
      await sesion.iniciar();
      await registro.listo;
      await sesion.salir();

      await sesion.ingresar(celular: '3001234567', pin: '482913');
      await registro.listo;

      expect(registros().last.cabeceras['Authorization'], 'Bearer token-ana');
      expect(registros().last.json, {'token': 'fcm-despues-de-borrar'});
    });

    test('un 401 al registrar cierra la sesión y borra el token en Firebase', () async {
      respuestaPush = () => errorDelContrato(401, 'sesion_invalida', 'Su sesión se cerró.');
      token.token = 'token-ana';

      await sesion.iniciar();
      await registro.listo;
      await registro.listo;

      expect(sesion.estado, EstadoSesion.sinSesion);
      expect(sesion.aviso, 'Su sesión se cerró.');
      expect(token.token, isNull);
      expect(firebase.tokensBorrados, 1);
    });
  });

  group('avisos', () {
    test('un aviso con la app abierta refresca la lista', () async {
      token.token = 'token-ana';
      await sesion.iniciar();
      await registro.listo;
      expect(peticionesA('/api/v1/asignaciones/'), isEmpty);

      firebase.llegaAviso(asignado);
      await esperarHasta(() => lista.ultimaActualizacion != null);

      expect(peticionesA('/api/v1/asignaciones/'), hasLength(1));
      expect([for (final s in lista.servicios) s.id], [41]);
    });

    test('un aviso sin sesión no pide nada al servidor', () async {
      await sesion.iniciar();

      firebase.llegaAviso(asignado);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(servidor.peticiones, isEmpty);
    });

    test('los datos del aviso se leen como los manda el servidor (textos)', () {
      final aviso = MensajePush.desdeDatos({'tipo': 'retirado', 'servicio_id': '41'});
      expect((aviso.tipo, aviso.servicioId), ('retirado', 41));

      final raro = MensajePush.desdeDatos({'servicio_id': 'cuarenta'});
      expect((raro.tipo, raro.servicioId), (null, null));
    });

    testWidgets('tocar una notificación cierra lo que está abierto y refresca la lista', (
      tester,
    ) async {
      token.token = 'token-ana';
      await tester.pumpWidget(
        ArriboApp(
          sesion: sesion,
          lista: lista,
          reloj: () => ahora,
          abrirEnlace: (_) async => true,
          avisosTocados: firebase.avisosTocados,
        ),
      );
      await tester.runAsync(sesion.iniciar);
      await tester.pumpAndSettle();
      await tester.runAsync(lista.actualizar);
      await tester.pumpAndSettle();
      await tester.tap(find.text('ABC123'));
      await tester.pumpAndSettle();
      expect(find.text('Servicio N.º 41'), findsOneWidget);
      final antes = peticionesA('/api/v1/asignaciones/').length;

      firebase.tocarAviso(asignado);
      await tester.pumpAndSettle();
      await tester.runAsync(() => esperarHasta(() => !lista.actualizando));
      await tester.pumpAndSettle();

      expect(find.text('Servicio N.º 41'), findsNothing);
      expect(find.text('Mis servicios'), findsOneWidget);
      expect(peticionesA('/api/v1/asignaciones/').length, greaterThan(antes));
    });
  });
}
