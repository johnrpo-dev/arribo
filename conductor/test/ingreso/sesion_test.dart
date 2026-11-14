// La sesión del conductor en el celular: ingresar, cierre por el servidor (401) y salir.

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late AlmacenTokenEnMemoria token;

  Sesion nuevaSesion() => Sesion(
    api: servidor.api(),
    base: prueba.base,
    almacenToken: token,
    nombreDispositivo: () async => 'Motorola moto g32',
  );

  Future<void> guardarLista(List<int> ids) => AlmacenAsignaciones(prueba.base).reemplazar(
    servicios: [for (final id in ids) Servicio.desdeJson(servicioJson(id: id))],
    configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
    etag: '"e1"',
    hora: DateTime.utc(2026, 11, 20, 15),
  );

  Future<void> agregarEventoPendiente() => prueba.base.db.insert('eventos_pendientes', {
    'id': 'a',
    'conductor_id': 3,
    'servicio_id': 41,
    'destino': 'en_camino',
    'secuencia': 1,
    'hora_dispositivo': '2026-11-20T19:42:07Z',
    'creado_en': '2026-11-20T19:42:07Z',
  });

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => ingresoCorrecto());
    token = AlmacenTokenEnMemoria();
  });
  tearDown(() async => prueba.cerrar());

  test('sin token guardado, la app abre en el ingreso', () async {
    final sesion = nuevaSesion();

    await sesion.iniciar();

    expect(sesion.estado, EstadoSesion.sinSesion);
  });

  test('con token guardado, la app entra directo aunque no haya señal', () async {
    token.token = 'token-ana';
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    servidor.responder = (_) async => sinSenal();
    final sesion = nuevaSesion();

    await sesion.iniciar();

    expect(sesion.estado, EstadoSesion.activa);
    expect(sesion.conductor?.nombre, 'Ana Gómez');
    expect(servidor.peticiones, isEmpty);
  });

  test('ingresar guarda el token en el almacén seguro y el conductor en la base local', () async {
    final sesion = nuevaSesion();
    await sesion.iniciar();

    await sesion.ingresar(celular: ' 300 123 4567 ', pin: '482913');

    expect(sesion.estado, EstadoSesion.activa);
    expect(token.token, 'token-ana');
    expect(sesion.token, 'token-ana');
    expect(await prueba.base.leerJson(Clave.conductor), conductorJson());
    expect(await prueba.base.leer('token'), isNull);
    final enviado = servidor.peticiones.single.json;
    expect(enviado['celular'], '300 123 4567');
    expect(enviado['dispositivo_id'], await prueba.base.dispositivoId());
    expect(enviado['dispositivo_nombre'], 'Motorola moto g32');
  });

  test('el token nunca se guarda en la base local', () async {
    final sesion = nuevaSesion();
    await sesion.iniciar();

    await sesion.ingresar(celular: '3001234567', pin: '482913');

    final filas = await prueba.base.db.query('estado_local');
    expect(filas.map((f) => '${f['dato']}').join('|'), isNot(contains('token-ana')));
  });

  test('un PIN malo deja la sesión cerrada y no guarda nada', () async {
    servidor.responder = (_) async =>
        errorDelContrato(401, 'credenciales_invalidas', 'Celular o PIN incorrectos.');
    final sesion = nuevaSesion();
    await sesion.iniciar();

    await expectLater(
      sesion.ingresar(celular: '3001234567', pin: '000000'),
      throwsA(isA<ErrorDeContrato>()),
    );

    expect(sesion.estado, EstadoSesion.sinSesion);
    expect(token.token, isNull);
    expect(await prueba.base.leer(Clave.conductor), isNull);
  });

  test('el mismo conductor que vuelve a ingresar conserva su lista guardada', () async {
    await prueba.base.escribirJson(Clave.conductor, conductorJson(id: 3));
    await guardarLista([41]);
    final sesion = nuevaSesion();
    await sesion.iniciar();

    await sesion.ingresar(celular: '3001234567', pin: '482913');

    expect([for (final s in await AlmacenAsignaciones(prueba.base).leer()) s.id], [41]);
  });

  test(
    'otro conductor en el mismo celular no ve la lista del anterior, y lo pendiente se conserva',
    () async {
      await prueba.base.escribirJson(Clave.conductor, conductorJson(id: 3));
      await guardarLista([41]);
      await agregarEventoPendiente();
      servidor.responder = (_) async =>
          ingresoCorrecto(token: 'token-beto', conductorId: 8, nombre: 'Beto');
      final sesion = nuevaSesion();
      await sesion.iniciar();

      await sesion.ingresar(celular: '3009998877', pin: '111111');

      final almacen = AlmacenAsignaciones(prueba.base);
      expect(await almacen.leer(), isEmpty);
      expect(await almacen.etag(), isNull);
      expect(await prueba.base.pendientesPorEnviar(), 1);
      expect(sesion.conductor?.nombre, 'Beto');
    },
  );

  test(
    'un 401 del servidor borra el token, vuelve al ingreso con el detalle y conserva lo local',
    () async {
      token.token = 'token-ana';
      await prueba.base.escribirJson(Clave.conductor, conductorJson());
      await guardarLista([41]);
      await agregarEventoPendiente();
      final sesion = nuevaSesion();
      await sesion.iniciar();

      await sesion.cerrarPorServidor(
        const SesionCerrada(codigo: 'sesion_invalida', detalle: 'Su sesión ya no es válida.'),
        tokenUsado: 'token-ana',
      );

      expect(sesion.estado, EstadoSesion.sinSesion);
      expect(sesion.aviso, 'Su sesión ya no es válida.');
      expect(token.token, isNull);
      expect(sesion.conductor?.celular, '3001234567');
      expect([for (final s in await AlmacenAsignaciones(prueba.base).leer()) s.id], [41]);
      expect(await prueba.base.pendientesPorEnviar(), 1);
    },
  );

  test('un 401 de una petición con un token viejo no cierra la sesión nueva', () async {
    final sesion = nuevaSesion();
    await sesion.iniciar();
    await sesion.ingresar(celular: '3001234567', pin: '482913');

    await sesion.cerrarPorServidor(
      const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
      tokenUsado: 'token-anterior',
    );

    expect(sesion.estado, EstadoSesion.activa);
    expect(token.token, 'token-ana');
  });

  test('cerrar sesión avisa al servidor y borra el token', () async {
    token.token = 'token-ana';
    servidor.responder = (_) async => http.Response('', 204);
    final sesion = nuevaSesion();
    await sesion.iniciar();

    final resultado = await sesion.salir();

    expect(resultado, ResultadoSalida.cerrada);
    expect(servidor.peticiones.single.url.path, '/api/v1/salir/');
    expect(token.token, isNull);
    expect(sesion.estado, EstadoSesion.sinSesion);
  });

  test('sin señal, cerrar sesión borra el token del celular igual', () async {
    token.token = 'token-ana';
    servidor.responder = (_) async => sinSenal();
    final sesion = nuevaSesion();
    await sesion.iniciar();

    expect(await sesion.salir(), ResultadoSalida.cerrada);
    expect(token.token, isNull);
  });

  test('no se cierra sesión con eventos pendientes por enviar', () async {
    token.token = 'token-ana';
    await agregarEventoPendiente();
    final sesion = nuevaSesion();
    await sesion.iniciar();

    final resultado = await sesion.salir();

    expect(resultado, ResultadoSalida.hayPendientes);
    expect(servidor.peticiones, isEmpty);
    expect(token.token, 'token-ana');
    expect(sesion.estado, EstadoSesion.activa);
  });

  test('lo pendiente de otro conductor no impide cerrar la sesión del actual', () async {
    // El evento es de Ana (3); quien tiene la sesión es Beto (8).
    token.token = 'token-beto';
    await prueba.base.escribirJson(Clave.conductor, conductorJson(id: 8, nombre: 'Beto'));
    await agregarEventoPendiente();
    servidor.responder = (_) async => http.Response('', 204);
    final sesion = nuevaSesion();
    await sesion.iniciar();

    expect(await sesion.salir(), ResultadoSalida.cerrada);
    expect(token.token, isNull);
    // El evento de Ana sigue en la cola.
    expect(await prueba.base.pendientesPorEnviar(), 1);
    expect(await prueba.base.pendientesPorEnviar(conductorId: 3), 1);
  });

  test('con eventos propios pendientes no se cierra sesión, aunque el servidor responda', () async {
    token.token = 'token-ana';
    await prueba.base.escribirJson(Clave.conductor, conductorJson(id: 3));
    await agregarEventoPendiente();
    servidor.responder = (_) async => http.Response('', 204);
    final sesion = nuevaSesion();
    await sesion.iniciar();

    expect(await sesion.salir(), ResultadoSalida.hayPendientes);
    expect(servidor.peticiones, isEmpty);
    expect(sesion.token, 'token-ana');
  });
}
