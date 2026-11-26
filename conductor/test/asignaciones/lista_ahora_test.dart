// La lista con el servicio activo arriba ("Ahora", con el botón del paso que sigue) y los demás
// compactos debajo ("Después"); y el recuadro único de estado arriba de la lista.

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/componentes.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/pantalla_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:arribo_conductor/tema.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late Sesion sesion;
  late Sincronizador sincronizador;
  late ListaAsignaciones lista;
  // Viernes 20 de noviembre, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  /// Lo que quedó guardado la última vez que hubo señal. Sin señal desde entonces.
  Future<void> guardar(List<Map<String, Object?>> servicios) async {
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [for (final json in servicios) Servicio.desdeJson(json)],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora.subtract(const Duration(minutes: 30)),
    );
  }

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => sinSenal());
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await guardar([servicioJson(id: 41), servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789')]);
    sesion = Sesion(
      api: servidor.api(),
      base: prueba.base,
      almacenToken: AlmacenTokenEnMemoria('token-ana'),
    );
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
  });
  tearDown(() async {
    sincronizador.dispose();
    await prueba.cerrar();
  });

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1080, 7200);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
  }

  Future<void> abrirApp(WidgetTester tester) async {
    await tester.pumpWidget(
      ArriboApp(
        sesion: sesion,
        lista: lista,
        reloj: () => ahora,
        abrirEnlace: (_) async => true,
        camara: CamaraFalsa(prueba.carpeta),
      ),
    );
    await sesion.iniciar();
    await tester.pumpAndSettle();
  }

  Future<void> tocar(WidgetTester tester, Finder boton) async {
    await tester.tap(boton);
    await tester.pumpAndSettle();
  }

  Finder tarjeta(int id) => find.byKey(ValueKey('tarjeta-$id'));
  Finder en(int id, Finder finder) => find.descendant(of: tarjeta(id), matching: finder);

  Future<List<Map<String, Object?>>> cola(WidgetTester tester) async => (await tester.runAsync(
    () => prueba.base.db.query('eventos_pendientes', orderBy: 'secuencia'),
  ))!;

  group('Ahora y Después', () {
    testWidgets('el activo va arriba con su botón; los demás debajo, compactos', (tester) async {
      pantallaAlta(tester);
      await abrirApp(tester);

      expect(find.text('Ahora'), findsOneWidget);
      expect(find.text('Después'), findsOneWidget);
      expect(tester.getTopLeft(find.text('Ahora')).dy, lessThan(tester.getTopLeft(tarjeta(41)).dy));
      expect(
        tester.getTopLeft(find.text('Después')).dy,
        lessThan(tester.getTopLeft(tarjeta(42)).dy),
      );
      expect(tester.getTopLeft(tarjeta(41)).dy, lessThan(tester.getTopLeft(tarjeta(42)).dy));
      // Solo la tarjeta activa tiene el botón del paso, la franja y la barra de avance.
      expect(find.byKey(const Key('tarjeta-marcar-en_camino')), findsOneWidget);
      expect(en(41, find.byKey(const Key('tarjeta-marcar-en_camino'))), findsOneWidget);
      expect(en(41, find.byKey(const Key('franja-activa'))), findsOneWidget);
      expect(find.byKey(const Key('franja-activa')), findsOneWidget);
      expect(en(41, find.byType(BarraDeAvance)), findsOneWidget);
      expect(find.byType(BarraDeAvance), findsOneWidget);
      expect(tester.widget<Text>(find.text('ABC123')).style, estiloPlaca);
      // Novedad se reporta solo desde el detalle.
      expect(find.text('Reportar novedad'), findsNothing);
      // La compacta: sin botones de un toque, con dónde recoger en una línea y su detalle.
      for (final enlace in ['Llamar', 'Maps', 'Waze']) {
        expect(en(41, find.text(enlace)), findsWidgets);
        expect(en(42, find.text(enlace)), findsNothing);
      }
      expect(en(42, find.text('Recoger en: Calle 10 # 43-20, El Poblado')), findsOneWidget);
      expect(en(42, find.text('Ver detalle')), findsOneWidget);
      expect(en(41, find.text('Ver detalle')), findsOneWidget);
    });

    testWidgets('el que ya empezó va en Ahora aunque haya otro antes en la ronda', (tester) async {
      await guardar([
        servicioJson(id: 41),
        servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789', estado: 'en_camino'),
      ]);
      pantallaAlta(tester);
      await abrirApp(tester);

      expect(en(42, find.byKey(const Key('tarjeta-marcar-recogido'))), findsOneWidget);
      expect(find.byKey(const Key('tarjeta-marcar-en_camino')), findsNothing);
      expect(tester.getTopLeft(tarjeta(42)).dy, lessThan(tester.getTopLeft(tarjeta(41)).dy));
    });

    testWidgets('sin servicio activo, la lista de siempre: sin títulos ni botón', (tester) async {
      await guardar([
        servicioJson(id: 41, estado: 'novedad'),
        servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789', esperaIda: true, regresoDe: 41),
      ]);
      pantallaAlta(tester);
      await abrirApp(tester);

      expect(find.text('ABC123'), findsOneWidget);
      expect(find.text('XYZ789'), findsOneWidget);
      expect(find.text('Ahora'), findsNothing);
      expect(find.text('Después'), findsNothing);
      expect(find.textContaining('Marcar'), findsNothing);
      expect(find.byKey(const Key('franja-activa')), findsNothing);
    });

    testWidgets('una novedad y un regreso que espera no son el activo ni tienen botón', (
      tester,
    ) async {
      await guardar([
        servicioJson(id: 41, estado: 'novedad'),
        servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789', esperaIda: true, regresoDe: 41),
        servicioJson(id: 43, ordenRonda: 3, placa: 'QWE456'),
      ]);
      pantallaAlta(tester);
      await abrirApp(tester);

      expect(find.byKey(const Key('tarjeta-marcar-en_camino')), findsOneWidget);
      expect(en(43, find.byKey(const Key('tarjeta-marcar-en_camino'))), findsOneWidget);
      expect(en(41, find.textContaining('Marcar')), findsNothing);
      expect(en(42, find.textContaining('Marcar')), findsNothing);
    });

    testWidgets('una tarjeta activa de un regreso que espera a su ida no ofrece el paso', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: temaArribo(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: TarjetaServicio(
                servicio: Servicio.desdeJson(
                  servicioJson(id: 42, esperaIda: true, regresoDe: 41, tipo: 'evento'),
                ),
                ahora: ahora,
                abrirEnlace: (_) async => true,
                alTocar: () {},
                activa: true,
                lista: lista,
              ),
            ),
          ),
        ),
      );

      expect(find.byKey(const Key('espera-ida')), findsOneWidget);
      expect(find.textContaining('Marcar'), findsNothing);
      expect(find.byKey(const Key('franja-activa')), findsOneWidget);
    });
  });

  group('el botón de la tarjeta activa', () {
    testWidgets('En camino pide confirmación y queda en la cola, como en el detalle', (
      tester,
    ) async {
      pantallaAlta(tester);
      await abrirApp(tester);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      expect(find.text('¿Marcar En camino?'), findsOneWidget);
      expect(find.text('ABC123 · Mazda CX-30 Rojo'), findsOneWidget);
      expect(await cola(tester), isEmpty);
      await tocar(tester, find.byKey(const Key('confirmar')));

      final evento = (await cola(tester)).single;
      expect(evento['servicio_id'], 41);
      expect(evento['destino'], 'en_camino');
      expect(evento['estado_envio'], 'pendiente');
      expect(evento['conductor_id'], 3);
      expect(evento['hora_dispositivo'], '2026-11-20T15:00:00.000Z');
      // La tarjeta sigue arriba, ya en camino, con el paso que ahora sigue.
      expect(en(41, find.text('En camino')), findsOneWidget);
      expect(en(41, find.text('Pendiente por enviar')), findsOneWidget);
      expect(en(41, find.byKey(const Key('tarjeta-marcar-recogido'))), findsOneWidget);
    });

    testWidgets('cancelar la confirmación no guarda nada', (tester) async {
      pantallaAlta(tester);
      await abrirApp(tester);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      await tocar(tester, find.text('Cancelar'));

      expect(await cola(tester), isEmpty);
      expect(en(41, find.text('Asignado')), findsOneWidget);
    });

    testWidgets('dos toques seguidos piden una sola confirmación y guardan un solo evento', (
      tester,
    ) async {
      pantallaAlta(tester);
      await abrirApp(tester);

      // Los dos toques llegan antes de que se dibuje la confirmación.
      final boton = tester.widget<FilledButton>(find.byKey(const Key('tarjeta-marcar-en_camino')));
      boton.onPressed!();
      boton.onPressed!();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('confirmar'), skipOffstage: false), findsOneWidget);
      await tocar(tester, find.byKey(const Key('confirmar')));

      // No queda otra confirmación abierta debajo, y en la cola hay un solo evento.
      expect(find.text('¿Marcar En camino?', skipOffstage: false), findsNothing);
      expect(await cola(tester), hasLength(1));
    });

    testWidgets('Recogido abre la pantalla de fotos y nombre', (tester) async {
      await guardar([
        servicioJson(id: 41, estado: 'en_camino'),
        servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789'),
      ]);
      pantallaAlta(tester);
      await abrirApp(tester);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-recogido')));

      expect(find.byKey(const Key('tomar-foto')), findsOneWidget);
      expect(await cola(tester), isEmpty);
    });
  });

  group('el recuadro de estado', () {
    testWidgets('sin conexión y con cambios pendientes, un solo recuadro con las dos filas', (
      tester,
    ) async {
      pantallaAlta(tester);
      await abrirApp(tester);
      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      await tocar(tester, find.byKey(const Key('confirmar')));

      final panel = find.byKey(const Key('estado-de-la-lista'));
      expect(panel, findsOneWidget);
      expect(find.descendant(of: panel, matching: find.byKey(const Key('pendientes'))), findsOne);
      expect(
        find.descendant(
          of: find.byKey(const Key('pendientes')),
          matching: find.text(
            'Hay 1 cambio pendiente por enviar. Se envía solo cuando haya señal.',
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: panel,
          matching: find.text(
            'Sin conexión. Se muestra lo guardado en el celular. Actualizado hoy, 9:30 a. m.',
          ),
        ),
        findsOneWidget,
      );
      // Una línea entre las dos filas, nada más.
      expect(find.descendant(of: panel, matching: find.byType(Divider)), findsOneWidget);
    });

    testWidgets('sin nada que contar, solo la línea de la última actualización', (tester) async {
      servidor.responder = (_) async => listaCorrecta([servicioJson(id: 41)], etag: '"e2"');
      await abrirApp(tester);

      expect(find.byKey(const Key('estado-de-la-lista')), findsNothing);
      expect(find.text('Actualizado hoy, 10:00 a. m.'), findsOneWidget);
    });
  });

  testWidgets('con el texto al 200 % en 360 dp, la tarjeta activa y el estado no se desbordan', (
    tester,
  ) async {
    celularConTextoGrande(tester);
    await abrirApp(tester);
    expect(tester.takeException(), isNull);

    await tester.scrollUntilVisible(find.byKey(const Key('tarjeta-marcar-en_camino')), 300);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
    await tester.ensureVisible(find.byKey(const Key('confirmar')));
    await tocar(tester, find.byKey(const Key('confirmar')));
    expect(tester.takeException(), isNull);

    // Arriba: el recuadro con la fila de pendientes y la de sin conexión.
    await tester.scrollUntilVisible(find.byKey(const Key('estado-de-la-lista')), -300);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pendientes')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
