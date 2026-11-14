// Botones de estado en el detalle del servicio, confirmación, indicador "pendiente por enviar"
// (global y por servicio) y avisos de lo que el servidor no aplicó.

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:material_ui/material_ui.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late ServidorDeEventos eventos;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  late Sincronizador sincronizador;
  late ListaAsignaciones lista;
  var conSenal = false;
  // Viernes 20 de noviembre, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  Future<http.Response> responder(PeticionRecibida peticion) async {
    if (!conSenal) sinSenal();
    return switch (peticion.url.path) {
      '/api/v1/eventos/' => eventos.recibir(peticion),
      '/api/v1/asignaciones/' => listaCorrecta([
        for (final MapEntry(key: id, value: estado) in eventos.estados.entries)
          if (const {'asignado', 'en_camino', 'recogido', 'novedad'}.contains(estado))
            {
              ...servicioJson(id: id, estado: estado, placa: id == 41 ? 'ABC123' : 'XYZ789'),
              'estado_previo': estado == 'novedad' ? eventos.previos[id] : null,
            },
      ], etag: '"${eventos.estados}"'),
      '/api/v1/salir/' => http.Response('', 204),
      '/api/v1/ingresar/' => ingresoCorrecto(token: 'token-ana-2'),
      _ => http.Response('', 404),
    };
  }

  /// Lo que quedó guardado la última vez que hubo señal, igual a lo que tiene el servidor.
  Future<void> guardar(Map<int, String> estados, {String? previo}) async {
    eventos = ServidorDeEventos(estados);
    if (previo != null) eventos.previos[41] = previo;
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        for (final MapEntry(key: id, value: estado) in estados.entries)
          Servicio.desdeJson({
            ...servicioJson(id: id, estado: estado, placa: id == 41 ? 'ABC123' : 'XYZ789'),
            'estado_previo': estado == 'novedad' ? previo : null,
          }),
      ],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora.subtract(const Duration(minutes: 30)),
    );
  }

  void armar() {
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    // Sin reintento con espera: en estas pruebas el envío lo disparan el toque y la lista.
    sincronizador = Sincronizador(
      cola: ColaEventos(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
      esperas: const [],
    );
    lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      sincronizador: sincronizador,
      reloj: () => ahora,
    );
  }

  setUp(() async {
    conSenal = false;
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso(responder);
    token = AlmacenTokenEnMemoria('token-ana');
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await guardar({41: 'asignado', 42: 'asignado'});
    armar();
  });
  tearDown(() async {
    sincronizador.dispose();
    await prueba.cerrar();
  });

  /// Una pantalla alta para ver la lista y el detalle completos sin desplazarse.
  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1080, 7200);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
  }

  Future<void> abrirApp(WidgetTester tester) async {
    await tester.pumpWidget(
      ArriboApp(sesion: sesion, lista: lista, reloj: () => ahora, abrirEnlace: (_) async => true),
    );
    await sesion.iniciar();
    await tester.pumpAndSettle();
  }

  Future<void> abrirDetalle(WidgetTester tester, {String placa = 'ABC123'}) async {
    pantallaAlta(tester);
    await abrirApp(tester);
    await tester.tap(find.text(placa));
    await tester.pumpAndSettle();
  }

  Future<void> tocar(WidgetTester tester, Finder boton) async {
    await tester.tap(boton);
    await tester.pumpAndSettle();
  }

  /// La flecha de volver de la barra superior.
  Future<void> volver(WidgetTester tester) => tocar(tester, find.byType(BackButton));

  Future<List<Map<String, Object?>>> cola(WidgetTester tester) async => (await tester.runAsync(
    () => prueba.base.db.query('eventos_pendientes', orderBy: 'secuencia'),
  ))!;

  group('botones según el estado', () {
    testWidgets('asignado: ofrece En camino y Novedad, nada más', (tester) async {
      await abrirDetalle(tester);

      expect(find.text('Marcar En camino'), findsOneWidget);
      expect(find.text('Reportar novedad'), findsOneWidget);
      expect(find.text('Marcar Recogido'), findsNothing);
      expect(find.text('Marcar Entregado'), findsNothing);
    });

    testWidgets('en camino: ofrece Recogido y Novedad', (tester) async {
      await guardar({41: 'en_camino'});
      await abrirDetalle(tester);

      expect(find.text('Marcar Recogido'), findsOneWidget);
      expect(find.text('Reportar novedad'), findsOneWidget);
      expect(find.text('Marcar En camino'), findsNothing);
      expect(find.text('Marcar Entregado'), findsNothing);
    });

    testWidgets('recogido: ofrece Entregado y Novedad', (tester) async {
      await guardar({41: 'recogido'});
      await abrirDetalle(tester);

      expect(find.text('Marcar Entregado'), findsOneWidget);
      expect(find.text('Reportar novedad'), findsOneWidget);
      expect(find.text('Marcar Recogido'), findsNothing);
    });

    testWidgets('novedad abierta: ningún botón, y explica que la resuelve logística', (
      tester,
    ) async {
      await guardar({41: 'novedad'}, previo: 'en_camino');
      await abrirDetalle(tester);

      expect(find.textContaining('Marcar'), findsNothing);
      expect(find.text('Reportar novedad'), findsNothing);
      expect(
        find.text('Novedad abierta. El servicio sigue cuando logística la resuelva.'),
        findsOneWidget,
      );
      expect(find.text('Estado antes de la novedad: En camino'), findsOneWidget);
    });
  });

  group('marcar un estado', () {
    testWidgets('pide confirmación con el vehículo a la vista; cancelar no guarda nada', (
      tester,
    ) async {
      await abrirDetalle(tester);

      await tocar(tester, find.text('Marcar En camino'));
      expect(find.text('¿Marcar En camino?'), findsOneWidget);
      expect(find.text('ABC123 · Mazda CX-30 Rojo'), findsOneWidget);
      // Todavía no se guardó nada.
      expect(await cola(tester), isEmpty);
      await tocar(tester, find.text('Cancelar'));

      expect(find.text('¿Marcar En camino?'), findsNothing);
      expect(await cola(tester), isEmpty);
      expect(find.text('Asignado'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsNothing);
    });

    testWidgets(
      'sin señal: al confirmar queda en la cola, se ve el estado nuevo y "Pendiente por enviar"',
      (tester) async {
        await abrirDetalle(tester);

        await tocar(tester, find.text('Marcar En camino'));
        await tocar(tester, find.byKey(const Key('confirmar')));

        final evento = (await cola(tester)).single;
        expect(evento['servicio_id'], 41);
        expect(evento['destino'], 'en_camino');
        expect(evento['estado_envio'], 'pendiente');
        expect(evento['conductor_id'], 3);
        expect(evento['hora_dispositivo'], '2026-11-20T15:00:00.000Z');
        // El detalle: estado nuevo, marca de pendiente y el botón del paso que ahora sigue.
        expect(find.text('En camino'), findsOneWidget);
        expect(find.text('Asignado'), findsNothing);
        expect(find.text('Pendiente por enviar'), findsOneWidget);
        expect(find.text('Marcar Recogido'), findsOneWidget);
        expect(find.text('Marcar En camino'), findsNothing);

        // La lista: el servicio marcado y el aviso global con la cantidad.
        await volver(tester);
        expect(find.text('Pendiente por enviar'), findsOneWidget);
        expect(find.text('En camino'), findsOneWidget);
        expect(find.text('Asignado'), findsOneWidget);
        expect(
          find.text('Hay 1 cambio pendiente por enviar. Se envía solo cuando haya señal.'),
          findsOneWidget,
        );
      },
    );

    testWidgets('con señal: se envía solo y no queda nada pendiente', (tester) async {
      conSenal = true;
      await abrirDetalle(tester);

      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(find.text('En camino'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsNothing);
      expect(eventos.estados[41], 'en_camino');
      expect((await cola(tester)).single['estado_envio'], 'aplicado');
      await volver(tester);
      expect(find.byKey(const Key('pendientes')), findsNothing);
    });

    testWidgets('al volver la señal y refrescar, desaparece "Pendiente por enviar"', (
      tester,
    ) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      await volver(tester);
      expect(find.text('Pendiente por enviar'), findsOneWidget);

      conSenal = true;
      // Volver a primer plano.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();

      expect(find.text('Pendiente por enviar'), findsNothing);
      expect(find.byKey(const Key('pendientes')), findsNothing);
      expect(find.text('En camino'), findsOneWidget);
      expect(find.textContaining('Sin conexión'), findsNothing);
      expect(eventos.aplicados, 1);
    });

    testWidgets('Recogido y Entregado se confirman y quedan en la cola, en orden', (tester) async {
      await guardar({41: 'en_camino'});
      await abrirDetalle(tester);

      await tocar(tester, find.text('Marcar Recogido'));
      expect(find.text('¿Marcar Recogido?'), findsOneWidget);
      await tocar(tester, find.byKey(const Key('confirmar')));
      expect(find.text('Recogido'), findsOneWidget);
      expect(find.textContaining('Montado en la grúa: Sí'), findsOneWidget);
      await tocar(tester, find.text('Marcar Entregado'));
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect([for (final e in await cola(tester)) e['destino']], ['recogido', 'entregado']);
      expect([for (final e in await cola(tester)) e['secuencia']], [1, 2]);
      expect(find.text('Entregado'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsOneWidget);
      // Entregado es terminal: ya no hay botones.
      expect(find.textContaining('Marcar'), findsNothing);
      expect(find.text('Reportar novedad'), findsNothing);
      expect(
        find.text('Servicio entregado. Sale de su lista cuando el cambio se envíe.'),
        findsOneWidget,
      );
    });

    testWidgets('la novedad exige motivo y queda guardada con él', (tester) async {
      await abrirDetalle(tester);

      await tocar(tester, find.text('Reportar novedad'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      expect(find.text('Escriba qué pasó para reportar la novedad.'), findsOneWidget);
      expect(await cola(tester), isEmpty);

      await tester.enterText(find.byKey(const Key('motivo')), '  Vía cerrada por derrumbe ');
      await tocar(tester, find.byKey(const Key('confirmar')));

      final evento = (await cola(tester)).single;
      expect(evento['destino'], 'novedad');
      expect(evento['motivo'], 'Vía cerrada por derrumbe');
      expect(find.text('Novedad'), findsOneWidget);
      expect(find.text('Estado antes de la novedad: Asignado'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsOneWidget);
      expect(find.textContaining('Marcar'), findsNothing);
    });

    testWidgets('cancelar la novedad no guarda nada', (tester) async {
      await abrirDetalle(tester);

      await tocar(tester, find.text('Reportar novedad'));
      await tester.enterText(find.byKey(const Key('motivo')), 'Vía cerrada');
      await tocar(tester, find.text('Cancelar'));

      expect(await cola(tester), isEmpty);
      expect(find.text('Asignado'), findsOneWidget);
    });

    testWidgets('el estado pendiente sigue ahí al cerrar y abrir la app sin señal', (tester) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));

      // El sistema mata la app: se arma todo de nuevo sobre la misma base.
      await tester.pumpWidget(const SizedBox());
      sincronizador.dispose();
      armar();
      await abrirApp(tester);

      expect(find.text('Pendiente por enviar'), findsOneWidget);
      expect(find.text('En camino'), findsOneWidget);
      expect(
        find.text('Hay 1 cambio pendiente por enviar. Se envía solo cuando haya señal.'),
        findsOneWidget,
      );
    });
  });

  group('lo que el servidor no aplicó', () {
    testWidgets('un conflicto se muestra con su detalle y que logística lo revisará', (
      tester,
    ) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      // Mientras estaba sin señal, logística canceló el servicio.
      eventos.estados[41] = 'cancelado';
      conSenal = true;

      await lista.actualizar();
      await tester.pumpAndSettle();

      const aviso =
          'ABC123: Su marca de «En camino» quedó guardada, pero el servicio no cambió. '
          'El servicio ya estaba cancelado. Logística ya recibió el aviso y lo revisará.';
      // El detalle abierto: el servicio ya no está en la lista, y el aviso está a la vista.
      expect(find.text('Este servicio ya no está en su lista.'), findsOneWidget);
      expect(find.text(aviso), findsOneWidget);
      expect(find.textContaining('Marcar'), findsNothing);

      await volver(tester);
      expect(find.text(aviso), findsOneWidget);
      expect(find.text('ABC123'), findsNothing);
      expect(find.byKey(const Key('pendientes')), findsNothing);

      await tocar(tester, find.text('Entendido'));
      expect(find.text(aviso), findsNothing);
      // El evento sigue guardado en el celular con su resultado.
      expect((await cola(tester)).single['estado_envio'], 'conflicto');
    });

    testWidgets('un conflicto en un servicio que sigue en la lista se ve en su detalle', (
      tester,
    ) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      // Logística abrió una novedad desde el panel.
      eventos.estados[41] = 'novedad';
      eventos.previos[41] = 'asignado';
      conSenal = true;

      await lista.actualizar();
      await tester.pumpAndSettle();

      expect(find.text('Novedad'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsNothing);
      expect(find.textContaining('quedó guardada, pero el servicio no cambió'), findsOneWidget);
      expect(find.textContaining('novedad abierta que logística debe resolver'), findsOneWidget);
    });

    testWidgets('un rechazado queda igual de visible', (tester) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      servidor.responder = (peticion) async => peticion.url.path == '/api/v1/eventos/'
          ? respuestaEventos([
              resultadoJson(
                eventosDe(peticion).single['id']! as String,
                resultado: 'rechazado',
                motivo: 'servicio_desconocido',
                detalle: 'El servicio no existe.',
              ),
            ])
          : await responder(peticion);
      conSenal = true;

      await lista.actualizar();
      await tester.pumpAndSettle();
      await volver(tester);

      expect(
        find.text(
          'ABC123: El servidor no pudo guardar su marca de «En camino». El servicio no existe. '
          'Logística ya recibió el aviso y lo revisará.',
        ),
        findsOneWidget,
      );
      expect(find.byKey(const Key('pendientes')), findsNothing);
    });
  });

  group('sesión y cola', () {
    testWidgets('con cambios pendientes no deja cerrar sesión y explica por qué', (tester) async {
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      await volver(tester);

      await tocar(tester, find.byTooltip('Más opciones'));
      await tocar(tester, find.text('Cerrar sesión'));

      expect(find.text('Todavía no puede cerrar sesión'), findsOneWidget);
      expect(
        find.text(
          'Hay 1 cambio pendiente por enviar. Se envían con su sesión: si la cierra antes, no '
          'llegarían a su nombre. Busque señal y espere a que se envíen.',
        ),
        findsOneWidget,
      );
      await tocar(tester, find.text('Entendido'));
      expect(find.text('Mis servicios'), findsOneWidget);
      expect(token.token, 'token-ana');
      expect(sesion.estado, EstadoSesion.activa);
      expect([for (final p in servidor.peticiones) p.url.path], isNot(contains('/api/v1/salir/')));
    });

    testWidgets('después de enviarlos sí deja cerrar sesión', (tester) async {
      conSenal = true;
      await abrirDetalle(tester);
      await tocar(tester, find.text('Marcar En camino'));
      await tocar(tester, find.byKey(const Key('confirmar')));
      await volver(tester);

      await tocar(tester, find.byTooltip('Más opciones'));
      await tocar(tester, find.text('Cerrar sesión'));
      await tocar(tester, find.widgetWithText(TextButton, 'Cerrar sesión'));

      expect(find.text('Ingresar'), findsOneWidget);
      expect(token.token, isNull);
    });

    testWidgets(
      'un 401 con cambios pendientes: el ingreso dice de quién son y que saldrán al volver',
      (tester) async {
        await abrirDetalle(tester);
        await tocar(tester, find.text('Marcar En camino'));
        await tocar(tester, find.byKey(const Key('confirmar')));
        servidor.responder = (_) async => errorDelContrato(
          401,
          'sesion_invalida',
          'Su sesión ya no es válida. Ingrese de nuevo.',
        );

        await lista.actualizar();
        await tester.pumpAndSettle();

        expect(find.text('Ingresar'), findsOneWidget);
        expect(find.text('Su sesión ya no es válida. Ingrese de nuevo.'), findsOneWidget);
        expect(
          find.text(
            'Hay 1 cambio sin enviar de Ana Gómez. Se envía cuando Ana Gómez ingrese de nuevo en '
            'este celular.',
          ),
          findsOneWidget,
        );
        expect((await cola(tester)).single['estado_envio'], 'pendiente');
      },
    );

    testWidgets(
      'al volver a ingresar el mismo conductor, lo pendiente se envía solo con su token nuevo',
      (tester) async {
        await abrirDetalle(tester);
        await tocar(tester, find.text('Marcar En camino'));
        await tocar(tester, find.byKey(const Key('confirmar')));
        final evento = (await cola(tester)).single;
        servidor.responder = (_) async => errorDelContrato(
          401,
          'sesion_invalida',
          'Su sesión ya no es válida. Ingrese de nuevo.',
        );
        await lista.actualizar();
        await tester.pumpAndSettle();
        expect(find.text('Ingresar'), findsOneWidget);
        servidor.responder = responder;
        conSenal = true;
        servidor.peticiones.clear();

        await tester.enterText(find.byKey(const Key('pin')), '482913');
        await tester.ensureVisible(find.byKey(const Key('ingresar')));
        await tester.pumpAndSettle();
        await tocar(tester, find.byKey(const Key('ingresar')));

        expect(find.text('Mis servicios'), findsOneWidget);
        final lote = servidor.peticiones.firstWhere((p) => p.url.path == '/api/v1/eventos/');
        expect(lote.cabeceras['Authorization'], 'Bearer token-ana-2');
        expect(eventosDe(lote).single['id'], evento['id']);
        expect(eventos.aplicados, 1);
        expect(find.text('Pendiente por enviar'), findsNothing);
        expect(find.byKey(const Key('pendientes')), findsNothing);
        expect(find.text('En camino'), findsOneWidget);
      },
    );

    testWidgets('otro conductor ve que hay cambios del anterior que no salen con su sesión', (
      tester,
    ) async {
      // Ana dejó un cambio sin enviar; ahora la sesión es de Beto.
      await prueba.base.db.insert('eventos_pendientes', {
        'id': 'a',
        'conductor_id': 3,
        'conductor_nombre': 'Ana Gómez',
        'servicio_id': 77,
        'destino': 'en_camino',
        'secuencia': 1,
        'hora_dispositivo': '2026-11-20T14:00:00Z',
        'creado_en': '2026-11-20T14:00:00Z',
      });
      await prueba.base.escribirJson(Clave.conductor, conductorJson(id: 8, nombre: 'Beto Ríos'));
      token.token = 'token-beto';
      conSenal = true;
      pantallaAlta(tester);

      await abrirApp(tester);

      expect(
        find.text(
          'En este celular hay 1 cambio sin enviar de Ana Gómez. No se envían con su sesión: '
          'saldrán cuando Ana Gómez vuelva a ingresar aquí. Avise a logística.',
        ),
        findsOneWidget,
      );
      expect(find.byKey(const Key('pendientes')), findsNothing);
      expect([
        for (final p in servidor.peticiones) p.url.path,
      ], isNot(contains('/api/v1/eventos/')));
    });
  });

  testWidgets('con el texto del sistema al 200 % los botones y la confirmación no se rompen', (
    tester,
  ) async {
    celularConTextoGrande(tester);
    await abrirApp(tester);
    await tester.ensureVisible(find.text('ABC123'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ABC123'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tocar(tester, find.text('Marcar En camino'));
    expect(tester.takeException(), isNull);
    await tocar(tester, find.byKey(const Key('confirmar')));
    expect(tester.takeException(), isNull);
    expect(find.text('Pendiente por enviar'), findsOneWidget);

    await tocar(tester, find.text('Reportar novedad'));
    expect(tester.takeException(), isNull);
    await tester.enterText(find.byKey(const Key('motivo')), 'Vía cerrada');
    await tester.ensureVisible(find.byKey(const Key('confirmar')));
    await tocar(tester, find.byKey(const Key('confirmar')));
    expect(tester.takeException(), isNull);

    await volver(tester);
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('pendientes')), findsOneWidget);
  });
}
