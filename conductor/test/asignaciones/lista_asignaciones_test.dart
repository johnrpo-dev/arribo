// La lista que ve el conductor: siempre desde la base local; el servidor solo la refresca.

import 'dart:async';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  final ahora = DateTime.utc(2026, 11, 20, 15);

  ListaAsignaciones nuevaLista(BaseLocal base) => ListaAsignaciones(
    almacen: AlmacenAsignaciones(base),
    api: servidor.api(),
    sesion: sesion,
    reloj: () => ahora,
  );

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => listaCorrecta([servicioJson(id: 41)]));
    token = AlmacenTokenEnMemoria('token-ana');
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await sesion.iniciar();
  });
  tearDown(() async => prueba.cerrar());

  test('al actualizar guarda la lista del servidor y la muestra en orden de ronda', () async {
    servidor.responder = (_) async =>
        listaCorrecta([servicioJson(id: 41, ordenRonda: 1), servicioJson(id: 39, ordenRonda: 2)]);
    final lista = nuevaLista(prueba.base);

    await lista.cargarLocal();
    await lista.actualizar();

    expect([for (final s in lista.servicios) s.id], [41, 39]);
    expect(lista.ultimaActualizacion, ahora);
    expect(lista.problema, isNull);
    expect(lista.configuracion?.minimoFotos, 4);
  });

  test('la lista se muestra desde la base local cuando la red falla', () async {
    await nuevaLista(prueba.base).actualizar();
    // El sistema mata la app y se abre sin señal.
    final base = await prueba.reabrir();
    sesion = Sesion(api: servidor.api(), base: base, almacenToken: token);
    await sesion.iniciar();
    servidor.responder = (_) async => sinSenal();
    final lista = nuevaLista(base);

    await lista.cargarLocal();
    await lista.actualizar();

    expect([for (final s in lista.servicios) s.id], [41]);
    expect(lista.servicios.single.origen.contactoTelefono, '6044445566');
    expect(lista.sinConexion, isTrue);
    expect(lista.ultimaActualizacion, ahora);
  });

  test('un 304 no reescribe la lista guardada', () async {
    final lista = nuevaLista(prueba.base);
    await lista.actualizar();
    final despues = ahora.add(const Duration(minutes: 10));
    final etagsEnviados = <String>[];
    servidor.responder = (peticion) async {
      etagsEnviados.add(peticion.cabeceras['If-None-Match'] ?? '');
      return http.Response('', 304);
    };
    // Una marca que solo existe en la base: si el 304 reescribiera la lista, desaparecería.
    await prueba.base.db.update('servicios', {'estado': 'en_camino'}, where: 'id = 41');
    final lista2 = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => despues,
    );

    await lista2.actualizar();

    expect(etagsEnviados, ['"e1"']);
    expect(lista2.servicios.single.estado, 'en_camino');
    expect(lista2.ultimaActualizacion, despues);
    expect(await AlmacenAsignaciones(prueba.base).etag(), '"e1"');
  });

  test('un 401 cierra la sesión, borra el token y conserva la lista local', () async {
    final lista = nuevaLista(prueba.base);
    await lista.actualizar();
    servidor.responder = (_) async =>
        errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida. Ingrese de nuevo.');

    await lista.actualizar();

    expect(sesion.estado, EstadoSesion.sinSesion);
    expect(sesion.aviso, 'Su sesión ya no es válida. Ingrese de nuevo.');
    expect(token.token, isNull);
    expect([for (final s in await AlmacenAsignaciones(prueba.base).leer()) s.id], [41]);
  });

  test('un error del servidor deja la lista guardada y lo informa', () async {
    final lista = nuevaLista(prueba.base);
    await lista.actualizar();
    servidor.responder = (_) async => http.Response('', 500);

    await lista.actualizar();

    expect([for (final s in lista.servicios) s.id], [41]);
    expect(lista.problema, isA<ErrorDelServidor>());
    expect(lista.sinConexion, isFalse);
  });

  test('actualizaciones simultáneas hacen una sola petición', () async {
    final respuesta = Completer<http.Response>();
    servidor.responder = (_) => respuesta.future;
    final lista = nuevaLista(prueba.base);

    final primera = lista.actualizar();
    final segunda = lista.actualizar();
    respuesta.complete(listaCorrecta([servicioJson(id: 41)]));
    await Future.wait([primera, segunda]);

    expect(servidor.peticiones, hasLength(1));
  });

  test('la respuesta que llega después de cerrar la sesión no se guarda', () async {
    final respuesta = Completer<http.Response>();
    servidor.responder = (_) => respuesta.future;
    final lista = nuevaLista(prueba.base);

    final enCurso = lista.actualizar();
    await sesion.cerrarPorServidor(
      const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
      tokenUsado: 'token-ana',
    );
    respuesta.complete(listaCorrecta([servicioJson(id: 99)]));
    await enCurso;

    expect(await AlmacenAsignaciones(prueba.base).leer(), isEmpty);
  });

  test('sin sesión no pide nada al servidor', () async {
    await sesion.cerrarPorServidor(
      const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
      tokenUsado: 'token-ana',
    );

    await nuevaLista(prueba.base).actualizar();

    expect(servidor.peticiones, isEmpty);
  });
}
