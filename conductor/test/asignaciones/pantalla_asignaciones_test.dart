// Pantallas de la lista y del detalle: se ven sin señal, con un toque para llamar o navegar.

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late Sesion sesion;
  late ListaAsignaciones lista;
  late List<Uri> abiertos;
  // Viernes 20 de noviembre, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => sinSenal());
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    // Lo que quedó guardado la última vez que hubo señal (hace media hora).
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        Servicio.desdeJson(servicioJson(id: 41, ordenRonda: 1)),
        Servicio.desdeJson({
          ...servicioJson(id: 42, ordenRonda: 2, tipo: 'desvare', placa: 'XYZ789'),
          'destino': null,
          'programada_para': null,
        }),
      ],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora.subtract(const Duration(minutes: 30)),
    );
    sesion = Sesion(
      api: servidor.api(),
      base: prueba.base,
      almacenToken: AlmacenTokenEnMemoria('token-ana'),
    );
    await sesion.iniciar();
    lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
    );
    abiertos = [];
  });
  tearDown(() async => prueba.cerrar());

  /// Una pantalla alta (360 × 2400 dp) para ver las dos tarjetas y el detalle completo sin
  /// desplazarse: la lista y el detalle construyen solo lo que está cerca de la vista.
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
        abrirEnlace: (enlace) async {
          abiertos.add(enlace);
          return true;
        },
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('la lista se muestra desde la base local cuando la red falla', (tester) async {
    pantallaAlta(tester);
    await abrirApp(tester);

    expect(find.text('Mis servicios'), findsOneWidget);
    expect(find.text('ABC123'), findsOneWidget);
    expect(find.text('XYZ789'), findsOneWidget);
    expect(find.text('Calle 10 # 43-20, El Poblado'), findsWidgets);
    expect(find.text('Portería Autos del Valle · 604 444 5566'), findsNWidgets(2));
    expect(find.text('Taller Belén · 310 222 3344'), findsOneWidget);
    expect(
      find.text('Sin conexión. Se muestra lo guardado en el celular. Actualizado hoy, 9:30 a. m.'),
      findsOneWidget,
    );
    expect(servidor.peticiones, hasLength(1));
  });

  testWidgets('muestra cada servicio en el orden de la ronda con estado, tipo y hora', (
    tester,
  ) async {
    pantallaAlta(tester);
    await abrirApp(tester);

    final primero = tester.getTopLeft(find.text('ABC123'));
    final segundo = tester.getTopLeft(find.text('XYZ789'));
    expect(primero.dy, lessThan(segundo.dy));
    expect(find.text('Asignado'), findsNWidgets(2));
    expect(find.text('Traslado'), findsOneWidget);
    expect(find.text('Desvare'), findsOneWidget);
    expect(find.text('Hora: Hoy, 2:30 p. m.'), findsOneWidget);
    expect(find.text('Hora: Inmediato'), findsOneWidget);
    expect(find.text('Sin destino registrado.'), findsOneWidget);
  });

  testWidgets('con señal, la lista se refresca al abrir y el aviso desaparece', (tester) async {
    servidor.responder = (_) async =>
        listaCorrecta([servicioJson(id: 50, placa: 'NUE111')], etag: '"e2"');

    await abrirApp(tester);

    expect(find.text('NUE111'), findsOneWidget);
    expect(find.text('ABC123'), findsNothing);
    expect(find.textContaining('Sin conexión'), findsNothing);
    expect(find.text('Actualizado hoy, 10:00 a. m.'), findsOneWidget);
    expect(servidor.peticiones.single.cabeceras['If-None-Match'], '"e1"');
  });

  testWidgets('deslizar hacia abajo vuelve a pedir la lista', (tester) async {
    await abrirApp(tester);
    servidor.responder = (_) async => listaCorrecta([servicioJson(id: 50, placa: 'NUE111')]);

    await tester.fling(find.text('ABC123'), const Offset(0, 400), 1000);
    await tester.pumpAndSettle();

    expect(servidor.peticiones, hasLength(2));
    expect(find.text('NUE111'), findsOneWidget);
  });

  testWidgets('volver a primer plano refresca la lista', (tester) async {
    await abrirApp(tester);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();

    expect(servidor.peticiones, hasLength(2));
  });

  testWidgets('un toque en Llamar abre el marcador con el teléfono del contacto', (tester) async {
    await abrirApp(tester);

    await tester.tap(find.text('Llamar').first);
    await tester.pumpAndSettle();

    expect(abiertos.single.toString(), 'tel:6044445566');
  });

  testWidgets('un toque en Maps y en Waze abre la dirección de recogida', (tester) async {
    await abrirApp(tester);

    await tester.tap(find.text('Maps').first);
    await tester.tap(find.text('Waze').first);
    await tester.pumpAndSettle();

    expect(abiertos[0].toString(), 'https://maps.app.goo.gl/abc123');
    expect(abiertos[1].host, 'waze.com');
    expect(abiertos[1].queryParameters['q'], 'Calle 10 # 43-20, El Poblado');
  });

  testWidgets('si no hay app para abrir el enlace, lo dice', (tester) async {
    await tester.pumpWidget(
      ArriboApp(sesion: sesion, lista: lista, reloj: () => ahora, abrirEnlace: (_) async => false),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Waze').first);
    await tester.pumpAndSettle();

    expect(find.text('No se pudo abrir Waze ni el navegador.'), findsOneWidget);
  });

  testWidgets('tocar un servicio abre su detalle de solo lectura', (tester) async {
    pantallaAlta(tester);
    await abrirApp(tester);

    await tester.tap(find.text('ABC123'));
    await tester.pumpAndSettle();

    expect(find.text('Servicio N.º 41'), findsOneWidget);
    expect(find.text('https://maps.app.goo.gl/abc123'), findsOneWidget);
    expect(find.textContaining('SIN-4471'), findsOneWidget);
    expect(find.textContaining('GRU001'), findsOneWidget);
    expect(find.textContaining('1HGCM82633A004352'), findsOneWidget);

    await tester.tap(find.text('Llamar').last);
    await tester.pumpAndSettle();
    expect(abiertos.single.toString(), 'tel:3102223344');
  });

  testWidgets('con el texto del sistema al 200 % la lista y el detalle no se rompen', (
    tester,
  ) async {
    celularConTextoGrande(tester);
    await abrirApp(tester);
    expect(tester.takeException(), isNull);

    // Recorre la lista completa: las dos tarjetas se construyen y se dibujan sin desbordarse.
    await tester.scrollUntilVisible(find.text('Sin destino registrado.'), 300);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.scrollUntilVisible(find.text('ABC123'), -300);
    await tester.ensureVisible(find.text('ABC123'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ABC123'));
    await tester.pumpAndSettle();
    expect(find.text('Servicio N.º 41'), findsOneWidget);
    // El detalle tiene además el texto seleccionable de la ubicación: se desplaza la lista.
    await tester.scrollUntilVisible(
      find.textContaining('Montado en la grúa'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('un 401 al refrescar vuelve al ingreso con el aviso del servidor', (tester) async {
    servidor.responder = (_) async =>
        errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida. Ingrese de nuevo.');

    await abrirApp(tester);

    expect(find.text('Mis servicios'), findsNothing);
    expect(find.text('Su sesión ya no es válida. Ingrese de nuevo.'), findsOneWidget);
    expect(find.text('Ingresar'), findsOneWidget);
    // El celular del último conductor ya viene escrito.
    expect(find.text('3001234567'), findsOneWidget);
    // Lo local sigue guardado.
    expect(await tester.runAsync(() => AlmacenAsignaciones(prueba.base).leer()), hasLength(2));
  });
}
