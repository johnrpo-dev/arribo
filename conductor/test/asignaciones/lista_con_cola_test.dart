// La lista con la cola de eventos: el estado que ve el conductor es el confirmado por el servidor
// más sus toques pendientes, y se reconcilia con lo que el servidor responde.

import 'dart:async';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late ServidorDeEventos eventos;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  late Sincronizador sincronizador;
  late ListaAsignaciones lista;
  var conSenal = true;
  final ahora = DateTime.utc(2026, 11, 20, 15);

  /// El servidor completo: la lista sale del estado que tienen los servicios en el servidor.
  Future<http.Response> responder(PeticionRecibida peticion) async {
    if (!conSenal) sinSenal();
    return switch (peticion.url.path) {
      '/api/v1/eventos/' => eventos.recibir(peticion),
      '/api/v1/asignaciones/' => listaCorrecta([
        for (final MapEntry(key: id, value: estado) in eventos.estados.entries)
          if (const {'asignado', 'en_camino', 'recogido', 'novedad'}.contains(estado))
            {
              ...servicioJson(id: id, estado: estado, placa: 'ABC$id'),
              'estado_previo': estado == 'novedad' ? eventos.previos[id] : null,
            },
      ], etag: '"${eventos.estados}"'),
      _ => http.Response('', 404),
    };
  }

  void armar(BaseLocal base) {
    sincronizador = Sincronizador(
      cola: ColaEventos(base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
      esperas: const [],
    );
    lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(base),
      api: servidor.api(),
      sesion: sesion,
      sincronizador: sincronizador,
      reloj: () => ahora,
    );
  }

  List<String> rutas() => [for (final p in servidor.peticiones) p.url.path];

  setUp(() async {
    conSenal = true;
    prueba = await BaseDePrueba.crear();
    eventos = ServidorDeEventos({41: 'asignado', 42: 'asignado'});
    servidor = ServidorFalso(responder);
    token = AlmacenTokenEnMemoria('token-ana');
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    await sesion.iniciar();
    armar(prueba.base);
    await lista.cargarLocal();
    await lista.actualizar();
    servidor.peticiones.clear();
  });
  tearDown(() async {
    // Lo que quedó en marcha (relecturas de la lista) termina antes de cerrar la base.
    await pumpEventQueue();
    sincronizador.dispose();
    await prueba.cerrar();
  });

  group('estado optimista', () {
    test(
      'sin señal, el toque se ve de inmediato y queda marcado como pendiente por enviar',
      () async {
        conSenal = false;

        await lista.marcar(41, 'en_camino');

        expect(lista.servicio(41)!.estado, 'en_camino');
        expect(lista.pendientesDe(41), 1);
        expect(lista.pendientesDe(42), 0);
        expect(lista.servicio(42)!.estado, 'asignado');
        expect(sincronizador.pendientes, 1);
        // Lo confirmado por el servidor no se toca: el estado nuevo sale de sumar la cola.
        final guardado = await AlmacenAsignaciones(prueba.base).leer();
        expect(guardado.firstWhere((s) => s.id == 41).estado, 'asignado');
      },
    );

    test(
      'varios toques sin señal se suman en orden, y el vehículo recogido cuenta como montado',
      () async {
        conSenal = false;

        await lista.marcar(41, 'en_camino');
        await lista.marcar(41, 'recogido');

        expect(lista.servicio(41)!.estado, 'recogido');
        expect(lista.servicio(41)!.aBordo, isTrue);
        expect(lista.pendientesDe(41), 2);
      },
    );

    test('una novedad pendiente recuerda el estado previo', () async {
      conSenal = false;

      await lista.marcar(41, 'novedad', motivo: 'Vía cerrada');

      expect(lista.servicio(41)!.estado, 'novedad');
      expect(lista.servicio(41)!.estadoPrevio, 'asignado');
    });

    test('el estado pendiente sobrevive a cerrar y abrir la app sin señal', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await sincronizador.enviar();

      // El sistema mata la app (lo que estuviera leyendo la lista vieja termina antes).
      await pumpEventQueue();
      sincronizador.dispose();
      final base = await prueba.reabrir();
      sesion = Sesion(api: servidor.api(), base: base, almacenToken: token);
      await sesion.iniciar();
      armar(base);
      await lista.cargarLocal();

      expect(lista.servicio(41)!.estado, 'en_camino');
      expect(lista.pendientesDe(41), 1);
      expect(sincronizador.pendientes, 1);
    });

    test('un toque que no corresponde no cambia nada', () async {
      await expectLater(lista.marcar(41, 'entregado'), throwsA(isA<ToqueNoValido>()));

      expect(lista.servicio(41)!.estado, 'asignado');
      expect(lista.pendientesDe(41), 0);
    });
  });

  group('reconciliación', () {
    test(
      'cuando el servidor lo aplica, deja de estar pendiente y el estado queda confirmado',
      () async {
        await lista.marcar(41, 'en_camino');
        await sincronizador.enviar();
        await lista.cargarLocal();

        expect(lista.servicio(41)!.estado, 'en_camino');
        expect(lista.pendientesDe(41), 0);
        expect(sincronizador.pendientes, 0);
        final guardado = await AlmacenAsignaciones(prueba.base).leer();
        expect(guardado.firstWhere((s) => s.id == 41).estado, 'en_camino');
      },
    );

    test(
      'la lista avisa a las pantallas cuando llega la respuesta, sin que nadie se lo pida',
      () async {
        conSenal = false;
        await lista.marcar(41, 'en_camino');
        await sincronizador.enviar();
        expect(lista.pendientesDe(41), 1);

        conSenal = true;
        await sincronizador.enviar();
        await esperarHasta(() => lista.pendientesDe(41) == 0);

        expect(lista.servicio(41)!.estado, 'en_camino');
      },
    );

    test(
      'al volver la señal, un envío que llega refresca también la lista y quita el aviso',
      () async {
        conSenal = false;
        await lista.marcar(41, 'en_camino');
        await lista.actualizar();
        expect(lista.sinConexion, isTrue);

        conSenal = true;
        // El reintento con espera es el único disparador: nadie desliza la lista.
        await sincronizador.enviar();
        await esperarHasta(() => !lista.sinConexion && !lista.actualizando);

        expect(lista.problema, isNull);
        expect(lista.servicio(41)!.estado, 'en_camino');
        expect(lista.pendientesDe(41), 0);
      },
    );

    test('un conflicto muestra el estado del servidor y deja el aviso a la vista', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await lista.marcar(42, 'en_camino');
      await sincronizador.enviar();
      // Mientras tanto logística puso el 41 en novedad desde el panel.
      eventos.estados[41] = 'novedad';
      eventos.previos[41] = 'asignado';

      conSenal = true;
      await lista.actualizar();

      expect(lista.servicio(41)!.estado, 'novedad');
      expect(lista.pendientesDe(41), 0);
      expect(lista.servicio(42)!.estado, 'en_camino');
      final aviso = sincronizador.avisos.single;
      expect(aviso.servicioId, 41);
      expect(aviso.resultadoMotivo, 'novedad_abierta');
    });

    test('cancelado mientras estaba sin señal: sale de la lista y el aviso queda', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await sincronizador.enviar();
      eventos.estados[41] = 'cancelado';

      conSenal = true;
      await lista.actualizar();

      expect(lista.servicio(41), isNull);
      expect([for (final s in lista.servicios) s.id], [42]);
      expect(sincronizador.avisos.single.resultadoDetalle, 'El servicio ya estaba cancelado.');
      expect(sincronizador.avisos.single.vehiculo, 'ABC41');
    });

    test('entregado y confirmado: el servicio sale de la lista', () async {
      await lista.marcar(41, 'en_camino');
      await lista.marcar(41, 'recogido');
      await lista.marcar(41, 'entregado');
      await lista.actualizar();

      expect([for (final s in lista.servicios) s.id], [42]);
      expect(sincronizador.pendientes, 0);
      expect(eventos.estados[41], 'entregado');
    });

    test(
      'una lista más vieja que el toque no lo pisa: sigue viéndose el estado pendiente',
      () async {
        // El servidor no logra guardar el evento (500), pero sí responde la lista, todavía sin él.
        servidor.responder = (peticion) async => peticion.url.path == '/api/v1/eventos/'
            ? http.Response('', 500)
            : await responder(peticion);

        await lista.marcar(41, 'en_camino');
        await lista.actualizar();

        expect(rutas().last, '/api/v1/asignaciones/');
        final guardado = await AlmacenAsignaciones(prueba.base).leer();
        expect(guardado.firstWhere((s) => s.id == 41).estado, 'asignado');
        expect(lista.servicio(41)!.estado, 'en_camino');
        expect(lista.pendientesDe(41), 1);
      },
    );

    test(
      'si la respuesta se perdió y la lista ya llegó con el cambio, no se suma dos veces',
      () async {
        // El servidor aplica En camino, pero al celular le llega un error; la lista sí llega, y ya
        // viene en camino.
        var perder = true;
        servidor.responder = (peticion) async {
          if (peticion.url.path == '/api/v1/eventos/' && perder) {
            eventos.recibir(peticion);
            return http.Response('', 502);
          }
          return responder(peticion);
        };
        await lista.marcar(41, 'en_camino');
        await lista.actualizar();
        final guardado = await AlmacenAsignaciones(prueba.base).leer();
        expect(guardado.firstWhere((s) => s.id == 41).estado, 'en_camino');
        expect(lista.servicio(41)!.estado, 'en_camino');
        expect(lista.pendientesDe(41), 1);

        // Con ese evento aún pendiente, el conductor marca Recogido: es el paso que sigue.
        await lista.marcar(41, 'recogido');
        await sincronizador.enviar();
        expect(lista.servicio(41)!.estado, 'recogido');

        perder = false;
        await lista.actualizar();

        expect(lista.servicio(41)!.estado, 'recogido');
        expect(lista.pendientesDe(41), 0);
        expect(sincronizador.avisos, isEmpty);
        expect(eventos.aplicados, 2);
      },
    );
  });

  group('orden entre el envío y la lista', () {
    test('al actualizar, primero se envía lo pendiente y después se pide la lista', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await sincronizador.enviar();
      conSenal = true;
      servidor.peticiones.clear();

      await lista.actualizar();

      expect(rutas(), ['/api/v1/eventos/', '/api/v1/asignaciones/']);
      // Después de corregir la lista con el resultado, se pide completa (sin ETag).
      expect(servidor.peticiones.last.cabeceras.containsKey('If-None-Match'), isFalse);
      expect(lista.servicio(41)!.estado, 'en_camino');
      expect(lista.pendientesDe(41), 0);
    });

    test('sin red al enviar no se pide la lista: una sola petición fallida', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await sincronizador.enviar();
      servidor.peticiones.clear();

      await lista.actualizar();

      expect(rutas(), ['/api/v1/eventos/']);
      expect(lista.sinConexion, isTrue);
      expect(lista.servicio(41)!.estado, 'en_camino');
    });

    test('un 401 al enviar cierra la sesión, conserva la cola y no pide la lista', () async {
      conSenal = false;
      await lista.marcar(41, 'en_camino');
      await sincronizador.enviar();
      conSenal = true;
      servidor.responder = (_) async =>
          errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida.');
      servidor.peticiones.clear();

      await lista.actualizar();

      expect(rutas(), ['/api/v1/eventos/']);
      expect(sesion.estado, EstadoSesion.sinSesion);
      expect(sincronizador.pendientes, 1);
    });

    test('un toque mientras se pide la lista: la lista vieja no deja el servicio en su estado anterior', () async {
      // La lista sale del servidor antes del toque y llega después.
      final soltar = Completer<void>();
      servidor.responder = (peticion) async {
        if (peticion.url.path != '/api/v1/asignaciones/') return responder(peticion);
        final vieja = await responder(peticion);
        await soltar.future;
        return vieja;
      };

      final actualizando = lista.actualizar();
      await esperarHasta(() => rutas().contains('/api/v1/asignaciones/'));
      await lista.marcar(41, 'en_camino');
      // El toque ya se ve; el envío espera su turno y no sale mientras la lista está en camino.
      expect(lista.servicio(41)!.estado, 'en_camino');
      await Future<void>.delayed(const Duration(milliseconds: 30));
      expect(rutas(), ['/api/v1/asignaciones/']);
      soltar.complete();
      await actualizando;
      await sincronizador.enviar();
      await lista.cargarLocal();

      expect(rutas(), ['/api/v1/asignaciones/', '/api/v1/eventos/']);
      expect(lista.servicio(41)!.estado, 'en_camino');
      expect(lista.pendientesDe(41), 0);
      final guardado = await AlmacenAsignaciones(prueba.base).leer();
      expect(guardado.firstWhere((s) => s.id == 41).estado, 'en_camino');
    });

    test('la lista que llega después de cerrarse la sesión (ya en camino) no se guarda', () async {
      final respuesta = Completer<http.Response>();
      servidor.responder = (_) => respuesta.future;
      final antes = await AlmacenAsignaciones(prueba.base).leer();

      final enCurso = lista.actualizar();
      await esperarHasta(() => rutas().contains('/api/v1/asignaciones/'));
      await sesion.cerrarPorServidor(
        const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
        tokenUsado: 'token-ana',
      );
      respuesta.complete(listaCorrecta([servicioJson(id: 99)]));
      await enCurso;

      final despues = await AlmacenAsignaciones(prueba.base).leer();
      expect([for (final s in despues) s.id], [for (final s in antes) s.id]);
    });
  });
}
