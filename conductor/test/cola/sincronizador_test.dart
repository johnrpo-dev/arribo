// El envío de la cola: no pierde eventos, no los duplica, respeta la secuencia, hace un solo envío
// a la vez y sobrevive a que el sistema mate la app en cualquier punto.

import 'dart:async';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/evento.dart';
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
  final desechables = <Sincronizador>[];
  final ahora = DateTime.utc(2026, 11, 20, 19, 42, 7);

  /// Sin reintento automático salvo que la prueba lo pida: cada envío lo dispara la prueba.
  Sincronizador nuevoSincronizador(BaseLocal base, {List<Duration> esperas = const []}) {
    final nuevo = Sincronizador(
      cola: ColaEventos(base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
      esperas: esperas,
    );
    desechables.add(nuevo);
    return nuevo;
  }

  Future<void> guardarLista(Map<int, String> estados) =>
      AlmacenAsignaciones(prueba.base).reemplazar(
        servicios: [
          for (final MapEntry(key: id, value: estado) in estados.entries)
            Servicio.desdeJson(servicioJson(id: id, estado: estado, placa: 'ABC$id')),
        ],
        configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
        etag: '"e1"',
        hora: ahora,
      );

  Future<String?> estadoGuardado(int servicio) async {
    final filas = await prueba.base.db.query('servicios', where: 'id = ?', whereArgs: [servicio]);
    return filas.isEmpty ? null : filas.single['estado'] as String?;
  }

  /// Un toque sin señal: queda en la cola y el intento de envío falla.
  Future<EventoLocal> tocarSinSenal(int servicio, String destino, {String? motivo}) async {
    final responder = servidor.responder;
    servidor.responder = (_) async => sinSenal();
    final evento = await sincronizador.registrar(
      servicioId: servicio,
      destino: destino,
      motivo: motivo,
    );
    await sincronizador.enviar();
    servidor.responder = responder;
    return evento;
  }

  /// El sistema mata la app: se pierde todo lo que estaba en memoria y se abre de nuevo.
  Future<void> matarYReabrir() async {
    final base = await prueba.reabrir();
    sesion = Sesion(api: servidor.api(), base: base, almacenToken: token);
    await sesion.iniciar();
    sincronizador = nuevoSincronizador(base);
    await sincronizador.cargar();
  }

  List<PeticionRecibida> lotesEnviados() => [
    for (final p in servidor.peticiones)
      if (p.url.path == '/api/v1/eventos/') p,
  ];

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    eventos = ServidorDeEventos({41: 'asignado', 42: 'asignado', 43: 'asignado'});
    servidor = ServidorFalso((peticion) async => eventos.recibir(peticion));
    token = AlmacenTokenEnMemoria('token-ana');
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await guardarLista({41: 'asignado', 42: 'asignado', 43: 'asignado'});
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    await sesion.iniciar();
    sincronizador = nuevoSincronizador(prueba.base);
  });
  tearDown(() async {
    // Lo que quedó en marcha termina antes de cerrar la base.
    await pumpEventQueue();
    for (final s in desechables) {
      s.dispose();
    }
    desechables.clear();
    await prueba.cerrar();
  });

  group('cada toque', () {
    test('queda guardado en la cola antes de cualquier intento de red', () async {
      List<Map<String, Object?>>? enLaBaseAlLlegar;
      servidor.responder = (peticion) async {
        enLaBaseAlLlegar = await prueba.base.db.query('eventos_pendientes');
        return eventos.recibir(peticion);
      };

      final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();

      expect(enLaBaseAlLlegar!.single['id'], evento.id);
      expect(enLaBaseAlLlegar!.single['estado_envio'], 'pendiente');
    });

    test(
      'con señal se envía solo, con el token de quien lo tocó, y deja de estar pendiente',
      () async {
        final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
        expect(sincronizador.pendientes, 1);
        await sincronizador.enviar();

        final lote = lotesEnviados().single;
        expect(lote.cabeceras['Authorization'], 'Bearer token-ana');
        expect(eventosDe(lote).single, evento.aJson());
        expect(sincronizador.pendientes, 0);
        expect(sincronizador.problema, isNull);
        expect(eventos.estados[41], 'en_camino');
      },
    );

    test('sin sesión no se registra', () async {
      await sesion.cerrarPorServidor(
        const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
        tokenUsado: 'token-ana',
      );

      await expectLater(
        sincronizador.registrar(servicioId: 41, destino: 'en_camino'),
        throwsA(isA<ToqueNoValido>()),
      );
      expect(await prueba.base.db.query('eventos_pendientes'), isEmpty);
    });
  });

  group('la cola no pierde eventos', () {
    test('sin señal el evento queda pendiente y sale cuando vuelve la señal', () async {
      final evento = await tocarSinSenal(41, 'en_camino');
      expect(sincronizador.pendientes, 1);
      expect(sincronizador.problema, isA<ErrorDeRed>());
      expect(eventos.lotes, isEmpty);

      expect(await sincronizador.enviar(), isNull);

      expect(sincronizador.pendientes, 0);
      expect(eventosDe(lotesEnviados().last).single['id'], evento.id);
      expect(eventos.estados[41], 'en_camino');
    });

    test('si el servidor falla (500), la cola queda entera y se reintenta', () async {
      servidor.responder = (_) async => http.Response('', 500);
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      expect(await sincronizador.enviar(), isA<ErrorDelServidor>());
      expect(sincronizador.pendientes, 1);

      servidor.responder = (peticion) async => eventos.recibir(peticion);
      await sincronizador.enviar();

      expect(sincronizador.pendientes, 0);
    });

    test('si el servidor rechaza el lote completo (400), la cola queda entera', () async {
      servidor.responder = (_) async =>
          errorDelContrato(400, 'datos_invalidos', 'Revise los datos enviados.');
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');

      expect(await sincronizador.enviar(), isA<ErrorDeContrato>());
      expect(sincronizador.pendientes, 1);
    });

    test('una respuesta que no trae un resultado por evento no se usa', () async {
      servidor.responder = (_) async => respuestaEventos([]);
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');

      expect(await sincronizador.enviar(), isA<RespuestaInesperada>());
      expect(sincronizador.pendientes, 1);
    });

    test('un resultado que no es del evento de su posición no se usa', () async {
      servidor.responder = (_) async =>
          respuestaEventos([resultadoJson('00000000-0000-4000-8000-000000000000')]);
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');

      expect(await sincronizador.enviar(), isA<RespuestaInesperada>());
      expect(sincronizador.pendientes, 1);
    });

    test('varios toques sin señal salen todos al volver, en un lote y en orden', () async {
      await tocarSinSenal(41, 'en_camino');
      await tocarSinSenal(42, 'en_camino');
      await tocarSinSenal(41, 'recogido');

      await sincronizador.enviar();

      expect([for (final e in eventos.lotes.single) e['secuencia']], [1, 2, 3]);
      expect(sincronizador.pendientes, 0);
      expect(eventos.estados, {41: 'recogido', 42: 'en_camino', 43: 'asignado'});
    });
  });

  group('la cola no duplica eventos', () {
    test('el reintento manda el mismo UUID y la misma secuencia', () async {
      final intentos = <Map<String, Object?>>[];
      servidor.responder = (peticion) async {
        intentos.add(eventosDe(peticion).single);
        return intentos.length < 3 ? sinSenal() : eventos.recibir(peticion);
      };
      final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();
      await sincronizador.enviar();
      await sincronizador.enviar();

      expect(intentos, hasLength(3));
      expect({for (final e in intentos) e['id']}, {evento.id});
      expect({for (final e in intentos) e['secuencia']}, {evento.secuencia});
      expect(sincronizador.pendientes, 0);
    });

    test(
      'si la respuesta se pierde, el reenvío llega como duplicado y cuenta como enviado',
      () async {
        // El servidor aplica el evento, pero la respuesta no llega al celular (tiempo agotado).
        servidor.responder = (peticion) async {
          eventos.recibir(peticion);
          return sinSenal();
        };
        final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
        await sincronizador.enviar();
        expect(eventos.estados[41], 'en_camino');
        expect(sincronizador.pendientes, 1);

        Map<String, Object?>? respuesta;
        servidor.responder = (peticion) async {
          final r = eventos.recibir(peticion);
          respuesta =
              (respuestaComoJson(r)['resultados']! as List<Object?>).single!
                  as Map<String, Object?>;
          return r;
        };
        await sincronizador.enviar();

        expect(respuesta!['duplicado'], isTrue);
        expect(respuesta!['id'], evento.id);
        expect(sincronizador.pendientes, 0);
        expect(sincronizador.avisos, isEmpty);
        expect(eventos.aplicados, 1);
        expect(await estadoGuardado(41), 'en_camino');
      },
    );

    test('un evento ya confirmado no se vuelve a enviar', () async {
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();

      await sincronizador.enviar();
      await sincronizador.enviar();

      expect(lotesEnviados(), hasLength(1));
    });
  });

  group('secuencia y orden', () {
    test('cada lote sale desde el pendiente más antiguo, en orden de secuencia', () async {
      await tocarSinSenal(42, 'en_camino');
      await tocarSinSenal(41, 'en_camino');
      await tocarSinSenal(42, 'recogido');
      await tocarSinSenal(41, 'novedad', motivo: 'Vía cerrada');

      await sincronizador.enviar();

      final lote = eventos.lotes.single;
      expect([for (final e in lote) e['secuencia']], [1, 2, 3, 4]);
      expect([for (final e in lote) e['servicio_id']], [42, 41, 42, 41]);
      expect(lote.last['motivo'], 'Vía cerrada');
    });

    test('con más de 100 pendientes salen lotes de 100, los más antiguos primero', () async {
      // 250 eventos puestos directamente en la cola (no hay tantos pasos válidos en tres servicios).
      final lote = prueba.base.db.batch();
      for (var n = 1; n <= 250; n++) {
        lote.insert(
          'eventos_pendientes',
          EventoLocal(
            id: 'evento-${n.toString().padLeft(3, '0')}',
            conductorId: 3,
            servicioId: 1000 + n,
            destino: 'en_camino',
            secuencia: n,
            horaDispositivo: ahora,
            creadoEn: ahora,
          ).aFila(),
        );
      }
      await lote.commit(noResult: true);
      final recibidos = <List<Object?>>[];
      servidor.responder = (peticion) async {
        final lote = eventosDe(peticion);
        recibidos.add([for (final e in lote) e['secuencia']]);
        return respuestaEventos([for (final e in lote) resultadoJson(e['id']! as String)]);
      };

      await sincronizador.enviar();

      expect([for (final r in recibidos) r.length], [100, 100, 50]);
      expect(recibidos[0].first, 1);
      expect(recibidos[0].last, 100);
      expect(recibidos[1].first, 101);
      expect(recibidos[2].last, 250);
      expect(sincronizador.pendientes, 0);
    });

    test(
      'un evento en reintentar va primero en el lote siguiente; los posteriores de su servicio no '
      'salen sin él',
      () async {
        final a = await tocarSinSenal(41, 'en_camino');
        await tocarSinSenal(42, 'en_camino');
        final c = await tocarSinSenal(41, 'recogido');
        eventos.fallan.add(a.id);

        // Primer lote: el servidor no pudo guardar `a`; `c` (mismo servicio) espera; `b` se aplica.
        expect(await sincronizador.enviar(), isNull);
        expect([for (final e in await sincronizador.cola.pendientes(3)) e.id], [a.id, c.id]);
        expect(eventos.estados, {41: 'asignado', 42: 'en_camino', 43: 'asignado'});
        expect(sincronizador.avisos, isEmpty);

        // Un toque nuevo mientras `a` sigue detenido: sale después de `a` y de `c`, nunca antes.
        final d = await sincronizador.registrar(servicioId: 43, destino: 'en_camino');
        await sincronizador.enviar();
        expect([for (final e in eventos.lotes.last) e['id']], [a.id, c.id, d.id]);
        expect(eventos.estados[41], 'asignado');

        eventos.fallan.clear();
        await sincronizador.enviar();

        expect([for (final e in eventos.lotes.last) e['id']], [a.id, c.id]);
        for (final lote in eventos.lotes) {
          final ids = [for (final e in lote) e['id']];
          if (ids.contains(c.id)) expect(ids.indexOf(a.id), lessThan(ids.indexOf(c.id)));
        }
        expect(eventos.estados, {41: 'recogido', 42: 'en_camino', 43: 'en_camino'});
        expect(sincronizador.pendientes, 0);
        expect(sincronizador.avisos, isEmpty);
      },
    );

    test(
      'con un evento en reintentar no insiste de inmediato: espera al siguiente disparador',
      () async {
        final a = await tocarSinSenal(41, 'en_camino');
        eventos.fallan.add(a.id);

        await sincronizador.enviar();

        expect(eventos.lotes, hasLength(1));
        expect(sincronizador.pendientes, 1);
      },
    );
  });

  group('un solo envío a la vez', () {
    test('varios disparadores a la vez hacen una sola petición', () async {
      await tocarSinSenal(41, 'en_camino');
      final respuesta = Completer<void>();
      var enVuelo = 0;
      var maximo = 0;
      servidor.responder = (peticion) async {
        enVuelo++;
        if (enVuelo > maximo) maximo = enVuelo;
        await respuesta.future;
        enVuelo--;
        return eventos.recibir(peticion);
      };
      servidor.peticiones.clear();

      // Abrir la app, volver a primer plano y deslizar la lista, todo a la vez.
      final envios = [sincronizador.enviar(), sincronizador.enviar(), sincronizador.enviar()];
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(lotesEnviados(), hasLength(1));
      respuesta.complete();
      await Future.wait(envios);

      expect(lotesEnviados(), hasLength(1));
      expect(maximo, 1);
      expect(eventos.aplicados, 1);
    });

    test('un toque durante un envío sale en el lote siguiente, nunca a la vez', () async {
      final primera = Completer<void>();
      var enVuelo = 0;
      var maximo = 0;
      servidor.responder = (peticion) async {
        enVuelo++;
        if (enVuelo > maximo) maximo = enVuelo;
        if (!primera.isCompleted) await primera.future;
        enVuelo--;
        return eventos.recibir(peticion);
      };

      final a = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(lotesEnviados(), hasLength(1));
      // El primer lote sigue en vuelo.
      final b = await sincronizador.registrar(servicioId: 42, destino: 'en_camino');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(lotesEnviados(), hasLength(1));
      primera.complete();
      await sincronizador.enviar();
      await sincronizador.enviar();

      expect(maximo, 1);
      expect(
        [
          for (final lote in eventos.lotes) [for (final e in lote) e['id']],
        ],
        [
          [a.id],
          [b.id],
        ],
      );
      expect(sincronizador.pendientes, 0);
    });

    test('el envío y otra tarea por turnos (la lista) no se cruzan', () async {
      final respuesta = Completer<void>();
      servidor.responder = (peticion) async {
        await respuesta.future;
        return eventos.recibir(peticion);
      };
      final pasos = <String>[];

      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      final lista = sincronizador.enTurno(() async {
        pasos.add('lista: pendientes ${sincronizador.pendientes}');
      });
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(pasos, isEmpty);
      respuesta.complete();
      await lista;

      expect(pasos, ['lista: pendientes 0']);
    });
  });

  group('conflicto y rechazado', () {
    test(
      'un conflicto sale de la cola, no se reintenta y queda a la vista con su detalle',
      () async {
        await tocarSinSenal(41, 'en_camino');
        // Mientras estaba sin señal, logística canceló el servicio.
        eventos.estados[41] = 'cancelado';

        await sincronizador.enviar();
        await sincronizador.enviar();

        expect(eventos.lotes, hasLength(1));
        expect(sincronizador.pendientes, 0);
        final aviso = sincronizador.avisos.single;
        expect(aviso.estadoEnvio, 'conflicto');
        expect(aviso.resultadoMotivo, 'servicio_cancelado');
        expect(aviso.resultadoDetalle, 'El servicio ya estaba cancelado.');
        expect(aviso.vehiculo, 'ABC41');
        // El servicio cancelado sale de la lista; el evento sigue guardado en el celular.
        expect(await estadoGuardado(41), isNull);
        expect(await prueba.base.db.query('eventos_pendientes'), hasLength(1));
      },
    );

    test('un rechazado sale de la cola, no se reintenta y queda igual de visible', () async {
      await tocarSinSenal(41, 'en_camino');
      servidor.peticiones.clear();
      servidor.responder = (peticion) async => respuestaEventos([
        resultadoJson(
          eventosDe(peticion).single['id']! as String,
          resultado: 'rechazado',
          motivo: 'servicio_desconocido',
          detalle: 'El servicio no existe.',
        ),
      ]);

      await sincronizador.enviar();
      await sincronizador.enviar();

      expect(lotesEnviados(), hasLength(1));
      expect(sincronizador.pendientes, 0);
      final aviso = sincronizador.avisos.single;
      expect(aviso.estadoEnvio, 'rechazado');
      expect(aviso.resultadoDetalle, 'El servicio no existe.');
    });

    test('un conflicto no detiene a los demás eventos del lote', () async {
      await tocarSinSenal(41, 'en_camino');
      await tocarSinSenal(42, 'en_camino');
      eventos.estados[41] = 'cancelado';

      await sincronizador.enviar();

      expect(eventos.estados[42], 'en_camino');
      expect(sincronizador.pendientes, 0);
      expect(sincronizador.avisos, hasLength(1));
    });

    test(
      'el aviso sobrevive a cerrar y abrir la app, hasta que el conductor lo da por visto',
      () async {
        await tocarSinSenal(41, 'en_camino');
        eventos.estados[41] = 'cancelado';
        await sincronizador.enviar();

        await matarYReabrir();
        final aviso = sincronizador.avisos.single;
        await sincronizador.marcarVisto(aviso.id);

        expect(sincronizador.avisos, isEmpty);
        expect(
          (await prueba.base.db.query('eventos_pendientes')).single['estado_envio'],
          'conflicto',
        );
      },
    );
  });

  group('sesión', () {
    Future<void> ingresar(
      String tokenNuevo, {
      int conductorId = 3,
      String nombre = 'Ana Gómez',
    }) async {
      final responder = servidor.responder;
      servidor.responder = (_) async =>
          ingresoCorrecto(token: tokenNuevo, conductorId: conductorId, nombre: nombre);
      await sesion.ingresar(celular: '3001234567', pin: '482913');
      servidor.responder = responder;
    }

    test('un 401 cierra la sesión y conserva la cola', () async {
      await tocarSinSenal(41, 'en_camino');
      servidor.responder = (_) async =>
          errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida. Ingrese de nuevo.');

      await sincronizador.enviar();

      expect(sesion.estado, EstadoSesion.sinSesion);
      expect(sesion.aviso, 'Su sesión ya no es válida. Ingrese de nuevo.');
      expect(token.token, isNull);
      expect(sincronizador.pendientes, 1);
      expect(
        (await prueba.base.db.query('eventos_pendientes')).single['estado_envio'],
        'pendiente',
      );
    });

    test('sin sesión no se envía nada', () async {
      await tocarSinSenal(41, 'en_camino');
      await sesion.cerrarPorServidor(
        const SesionCerrada(codigo: 'sesion_invalida', detalle: 'x'),
        tokenUsado: 'token-ana',
      );
      servidor.peticiones.clear();

      await sincronizador.enviar();

      expect(servidor.peticiones, isEmpty);
      expect(sincronizador.pendientes, 1);
    });

    test('al volver a ingresar el mismo conductor, lo pendiente sale con su token nuevo', () async {
      final evento = await tocarSinSenal(41, 'en_camino');
      servidor.responder = (_) async => errorDelContrato(401, 'sesion_invalida', 'x');
      await sincronizador.enviar();
      servidor.responder = (peticion) async => eventos.recibir(peticion);

      await ingresar('token-ana-2');
      await sincronizador.enviar();

      final lote = lotesEnviados().last;
      expect(lote.cabeceras['Authorization'], 'Bearer token-ana-2');
      expect(eventosDe(lote).single['id'], evento.id);
      expect(sincronizador.pendientes, 0);
      expect(eventos.aplicados, 1);
    });

    test('otro conductor en el mismo celular no envía los eventos del primero', () async {
      final deAna = await tocarSinSenal(41, 'en_camino');
      servidor.responder = (_) async => errorDelContrato(401, 'sesion_invalida', 'x');
      await sincronizador.enviar();
      servidor.responder = (peticion) async => eventos.recibir(peticion);
      servidor.peticiones.clear();

      await ingresar('token-beto', conductorId: 8, nombre: 'Beto Ríos');
      await sincronizador.cargar();
      await sincronizador.enviar();

      expect(lotesEnviados(), isEmpty);
      expect(sincronizador.pendientes, 0);
      final ajenos = sincronizador.pendientesAjenos.single;
      expect((ajenos.conductorId, ajenos.nombre, ajenos.cantidad), (3, 'Ana Gómez', 1));
      expect((await prueba.base.db.query('eventos_pendientes')).single['id'], deAna.id);

      // Los eventos de Beto sí salen, con su token, sin arrastrar los de Ana.
      await guardarLista({50: 'asignado'});
      eventos.estados[50] = 'asignado';
      final deBeto = await sincronizador.registrar(servicioId: 50, destino: 'en_camino');
      await sincronizador.enviar();

      final lote = lotesEnviados().single;
      expect(lote.cabeceras['Authorization'], 'Bearer token-beto');
      expect([for (final e in eventosDe(lote)) e['id']], [deBeto.id]);
      expect(deBeto.secuencia, greaterThan(deAna.secuencia));
      expect(sincronizador.pendientesAjenos.single.cantidad, 1);
    });

    test('los eventos del primero salen cuando él vuelve a ingresar, con su token', () async {
      final deAna = await tocarSinSenal(41, 'en_camino');
      servidor.responder = (_) async => errorDelContrato(401, 'sesion_invalida', 'x');
      await sincronizador.enviar();
      servidor.responder = (peticion) async => eventos.recibir(peticion);
      await ingresar('token-beto', conductorId: 8, nombre: 'Beto Ríos');
      await sincronizador.enviar();
      // Lo pendiente de Ana no le impide a Beto cerrar su sesión.
      servidor.responder = (_) async => http.Response('', 204);
      expect(await sesion.salir(), ResultadoSalida.cerrada);
      servidor.responder = (peticion) async => eventos.recibir(peticion);
      servidor.peticiones.clear();

      await ingresar('token-ana-2');
      await sincronizador.enviar();

      final lote = lotesEnviados().single;
      expect(lote.cabeceras['Authorization'], 'Bearer token-ana-2');
      expect(eventosDe(lote).single['id'], deAna.id);
      expect(sincronizador.pendientesPorConductor, isEmpty);
    });

    test('no se puede cerrar sesión con eventos pendientes; después de enviarlos, sí', () async {
      await tocarSinSenal(41, 'en_camino');

      expect(await sesion.salir(), ResultadoSalida.hayPendientes);
      expect(sesion.estado, EstadoSesion.activa);
      expect(token.token, 'token-ana');

      await sincronizador.enviar();
      servidor.responder = (_) async => http.Response('', 204);
      expect(await sesion.salir(), ResultadoSalida.cerrada);
    });

    test('un conflicto ya respondido no impide cerrar sesión', () async {
      await tocarSinSenal(41, 'en_camino');
      eventos.estados[41] = 'cancelado';
      await sincronizador.enviar();

      servidor.responder = (_) async => http.Response('', 204);
      expect(await sesion.salir(), ResultadoSalida.cerrada);
    });
  });

  group('reconciliación con el servidor', () {
    test('aplicado: la lista local queda con el estado que devolvió el servidor', () async {
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();

      expect(await estadoGuardado(41), 'en_camino');
      expect(await estadoGuardado(42), 'asignado');
    });

    test('entregado confirmado: el servicio sale de la lista', () async {
      await guardarLista({41: 'recogido'});
      eventos.estados[41] = 'recogido';

      await sincronizador.registrar(servicioId: 41, destino: 'entregado');
      await sincronizador.enviar();

      expect(await estadoGuardado(41), isNull);
      expect(sincronizador.avisos, isEmpty);
    });

    test(
      'reasignado mientras estaba sin señal: conflicto a la vista y el servicio sale de la lista',
      () async {
        await tocarSinSenal(41, 'en_camino');
        eventos.estados.remove(41);

        await sincronizador.enviar();

        expect(await estadoGuardado(41), isNull);
        expect(sincronizador.avisos.single.resultadoMotivo, 'servicio_no_asignado');
      },
    );

    test('novedad aplicada: queda en novedad recordando el estado previo', () async {
      await sincronizador.registrar(servicioId: 41, destino: 'novedad', motivo: 'Vía cerrada');
      await sincronizador.enviar();

      final fila = (await prueba.base.db.query('servicios', where: 'id = 41')).single;
      expect(fila['estado'], 'novedad');
      expect(fila['estado_previo'], 'asignado');
    });
  });

  group('si el sistema mata la app', () {
    test('entre guardar y enviar: al abrir, el evento sale con el mismo UUID', () async {
      servidor.responder = (_) async => sinSenal();
      final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();
      servidor.responder = (peticion) async => eventos.recibir(peticion);

      await matarYReabrir();
      expect(sincronizador.pendientes, 1);
      await sincronizador.enviar();

      final enviado = eventos.lotes.single.single;
      expect(enviado['id'], evento.id);
      expect(enviado['secuencia'], evento.secuencia);
      expect(sincronizador.pendientes, 0);
      expect(eventos.aplicados, 1);
    });

    test('entre enviar y recibir: el reenvío no aplica el evento dos veces', () async {
      // El servidor aplicó, pero la app murió antes de leer la respuesta.
      servidor.responder = (peticion) async {
        eventos.recibir(peticion);
        return sinSenal();
      };
      final evento = await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();
      servidor.responder = (peticion) async => eventos.recibir(peticion);

      await matarYReabrir();
      await sincronizador.enviar();

      expect([for (final lote in eventos.lotes) lote.single['id']], [evento.id, evento.id]);
      expect(eventos.aplicados, 1);
      expect(eventos.estados[41], 'en_camino');
      expect(sincronizador.pendientes, 0);
      expect(sincronizador.avisos, isEmpty);
      expect(await estadoGuardado(41), 'en_camino');
    });

    test('entre recibir y anotar: la respuesta se pierde entera y el reenvío la repite', () async {
      // La respuesta llegó, pero la app murió antes de guardarla: la base sigue como estaba.
      final evento = await tocarSinSenal(41, 'en_camino');
      final resultados = await servidor.api().enviarEventos('token-ana', [evento]);
      expect(resultados.single.resultado, 'aplicado');
      expect(
        (await prueba.base.db.query('eventos_pendientes')).single['estado_envio'],
        'pendiente',
      );

      await matarYReabrir();
      await sincronizador.enviar();

      expect(eventos.aplicados, 1);
      expect(sincronizador.pendientes, 0);
      expect(await estadoGuardado(41), 'en_camino');
    });

    test('con varios toques pendientes: salen todos, en orden, una sola vez', () async {
      final a = await tocarSinSenal(41, 'en_camino');
      await matarYReabrir();
      final b = await tocarSinSenal(41, 'recogido');
      await matarYReabrir();
      final c = await tocarSinSenal(42, 'en_camino');
      await matarYReabrir();

      await sincronizador.enviar();

      expect([for (final e in eventos.lotes.single) e['id']], [a.id, b.id, c.id]);
      expect([a.secuencia, b.secuencia, c.secuencia], [1, 2, 3]);
      expect(eventos.aplicados, 3);
      expect(sincronizador.pendientes, 0);
    });

    test('después de reabrir no se puede repetir un toque que ya está en la cola', () async {
      await tocarSinSenal(41, 'en_camino');
      await matarYReabrir();

      await expectLater(
        sincronizador.registrar(servicioId: 41, destino: 'en_camino'),
        throwsA(isA<ToqueNoValido>()),
      );
      expect(sincronizador.pendientes, 1);
    });
  });

  group('reintento con espera creciente', () {
    test('si el envío falla, se reintenta solo y el evento termina saliendo', () async {
      sincronizador = nuevoSincronizador(
        prueba.base,
        esperas: const [Duration(milliseconds: 30), Duration(milliseconds: 60)],
      );
      var intentos = 0;
      servidor.responder = (peticion) async {
        intentos++;
        return intentos < 3 ? sinSenal() : eventos.recibir(peticion);
      };

      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();
      expect(intentos, 1);
      expect(sincronizador.esperaDelReintento, const Duration(milliseconds: 30));
      // Nadie vuelve a pedir el envío: lo hace el reintento programado.
      await esperarHasta(
        () => sincronizador.esperaDelReintento == const Duration(milliseconds: 60),
      );
      expect(intentos, 2);
      await esperarHasta(() => sincronizador.pendientes == 0);

      expect(intentos, 3);
      expect(sincronizador.pendientes, 0);
      expect(sincronizador.esperaDelReintento, isNull);
    });

    test('la espera crece hasta el tope y vuelve al principio cuando un envío sale bien', () async {
      sincronizador = nuevoSincronizador(
        prueba.base,
        esperas: const [Duration(minutes: 1), Duration(minutes: 2), Duration(minutes: 3)],
      );
      servidor.responder = (_) async => sinSenal();
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      final vistas = <Duration?>[];
      for (var n = 0; n < 5; n++) {
        await sincronizador.enviar();
        vistas.add(sincronizador.esperaDelReintento);
      }
      expect(vistas, const [
        Duration(minutes: 1),
        Duration(minutes: 2),
        Duration(minutes: 3),
        Duration(minutes: 3),
        Duration(minutes: 3),
      ]);

      servidor.responder = (peticion) async => eventos.recibir(peticion);
      await sincronizador.enviar();
      expect(sincronizador.esperaDelReintento, isNull);
      servidor.responder = (_) async => sinSenal();
      await sincronizador.registrar(servicioId: 42, destino: 'en_camino');
      await sincronizador.enviar();

      expect(sincronizador.esperaDelReintento, const Duration(minutes: 1));
    });

    test('en segundo plano la espera sigue creciendo hasta un tope más largo', () async {
      sincronizador = nuevoSincronizador(prueba.base, esperas: const [Duration(seconds: 30)]);
      sincronizador.enPrimerPlano = false;
      servidor.responder = (_) async => sinSenal();
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      final vistas = <Duration?>[];
      for (var n = 0; n < 6; n++) {
        await sincronizador.enviar();
        vistas.add(sincronizador.esperaDelReintento);
      }

      expect(vistas, const [
        Duration(seconds: 30),
        Duration(seconds: 60),
        Duration(seconds: 120),
        Duration(seconds: 240),
        Duration(minutes: 5),
        Duration(minutes: 5),
      ]);
    });

    test('sin nada pendiente no queda ningún reintento programado', () async {
      sincronizador = nuevoSincronizador(prueba.base, esperas: const [Duration(minutes: 1)]);
      servidor.responder = (_) async => sinSenal();

      await sincronizador.enviar();

      expect(sincronizador.esperaDelReintento, isNull);
      expect(servidor.peticiones, isEmpty);
    });

    test('un 401 no deja reintentos programados', () async {
      sincronizador = nuevoSincronizador(prueba.base, esperas: const [Duration(minutes: 1)]);
      servidor.responder = (_) async => errorDelContrato(401, 'sesion_invalida', 'x');
      await sincronizador.registrar(servicioId: 41, destino: 'en_camino');
      await sincronizador.enviar();

      expect(sincronizador.esperaDelReintento, isNull);
    });
  });
}
