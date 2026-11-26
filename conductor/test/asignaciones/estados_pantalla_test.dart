// Los estados de las pantallas: la lista vacía, lo que se ve mientras se lee lo guardado, la franja
// de sin señal fija arriba (lista, detalle y pantalla del paso) y el cambio de la tarjeta activa.

import 'dart:async';

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/componentes.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/pantalla_paso.dart';
import 'package:arribo_conductor/asignaciones/pantalla_servicio.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:arribo_conductor/tema.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
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

  const sinConexionEnLaLista =
      'Sin conexión. Se muestra lo guardado en el celular. Actualizado hoy, 9:30 a. m.';
  final franja = find.byKey(const Key('franja-sin-senal'));
  final botonActualizar = find.byKey(const Key('vacia-actualizar'));

  /// Lo que quedó guardado la última vez que hubo señal (hace media hora).
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

  Widget app() => ArriboApp(
    sesion: sesion,
    lista: lista,
    reloj: () => ahora,
    abrirEnlace: (_) async => true,
    camara: CamaraFalsa(prueba.carpeta),
  );

  Future<void> abrirApp(WidgetTester tester) async {
    await tester.pumpWidget(app());
    await sesion.iniciar();
    await tester.pumpAndSettle();
  }

  Future<void> tocar(WidgetTester tester, Finder boton) async {
    await tester.tap(boton);
    await tester.pumpAndSettle();
  }

  Finder tarjeta(int id) => find.byKey(ValueKey('tarjeta-$id'));
  Finder activa(int id, String estado) => find.byKey(ValueKey('activa-$id-$estado'));

  /// El encabezado (para TalkBack) que contiene [texto].
  Finder encabezado(String texto) => find.ancestor(
    of: find.text(texto),
    matching: find.byWidgetPredicate((w) => w is Semantics && (w.properties.header ?? false)),
  );

  group('la lista vacía', () {
    testWidgets('sin haber recibido nunca la lista, dice que aún no hay servicios y "Actualizar" '
        'la vuelve a pedir', (tester) async {
      await abrirApp(tester);

      expect(find.text('Aún no hay servicios en el celular'), findsOneWidget);
      expect(encabezado('Aún no hay servicios en el celular'), findsOneWidget);
      expect(find.text('Cuando haya señal aparecerán aquí sus servicios.'), findsOneWidget);
      expect(find.text('No tiene servicios asignados.'), findsNothing);

      final pedidas = servidor.peticiones.length;
      await tester.ensureVisible(botonActualizar);
      await tester.pumpAndSettle();
      await tocar(tester, botonActualizar);

      expect(servidor.peticiones, hasLength(pedidas + 1));
    });

    testWidgets('ya actualizada y sin servicios, dice que no tiene servicios asignados', (
      tester,
    ) async {
      servidor.responder = (_) async => listaCorrecta([]);
      await abrirApp(tester);

      expect(find.text('No tiene servicios asignados.'), findsOneWidget);
      expect(encabezado('No tiene servicios asignados.'), findsOneWidget);
      expect(find.text('Cuando le asignen uno, aparecerá aquí.'), findsOneWidget);
      expect(find.text('Aún no hay servicios en el celular'), findsNothing);
      expect(botonActualizar, findsOneWidget);
    });

    testWidgets('sigue dentro de la lista: deslizar hacia abajo también la pide', (tester) async {
      await abrirApp(tester);
      final pedidas = servidor.peticiones.length;

      await tester.fling(
        find.text('Aún no hay servicios en el celular'),
        const Offset(0, 400),
        1000,
      );
      await tester.pumpAndSettle();

      expect(servidor.peticiones, hasLength(pedidas + 1));
    });

    testWidgets('mientras actualiza, el botón dice "Actualizando…" y no responde', (tester) async {
      servidor.responder = (_) async => listaCorrecta([]);
      await abrirApp(tester);
      final respuesta = Completer<http.Response>();
      servidor.responder = (_) => respuesta.future;
      final pedidas = servidor.peticiones.length;

      await tester.tap(botonActualizar);
      await tester.pump();

      expect(
        find.descendant(of: botonActualizar, matching: find.text('Actualizando…')),
        findsOneWidget,
      );
      expect(tester.widget<OutlinedButton>(botonActualizar).enabled, isFalse);
      await tester.tap(botonActualizar, warnIfMissed: false);
      await tester.pump();
      expect(servidor.peticiones, hasLength(pedidas + 1));

      respuesta.complete(listaCorrecta([]));
      await tester.pumpAndSettle();
      expect(find.descendant(of: botonActualizar, matching: find.text('Actualizar')), findsOne);
      expect(tester.widget<OutlinedButton>(botonActualizar).enabled, isTrue);
    });
  });

  group('la franja sin señal', () {
    testWidgets('en la lista va fuera de lo que se desplaza y sigue a la vista al bajar por la '
        'lista; el recuadro de estado no repite el aviso', (tester) async {
      await guardar([
        for (var i = 1; i <= 6; i++) servicioJson(id: 40 + i, ordenRonda: i, placa: 'PLA00$i'),
      ]);
      await abrirApp(tester);

      expect(franja, findsOneWidget);
      expect(find.ancestor(of: franja, matching: find.byType(Scrollable)), findsNothing);
      expect(find.text(sinConexionEnLaLista), findsOneWidget);
      expect(find.descendant(of: franja, matching: find.text(sinConexionEnLaLista)), findsOne);
      expect(find.byKey(const Key('estado-de-la-lista')), findsNothing);

      final arriba = tester.getTopLeft(franja);
      await tester.drag(find.byType(ListView), const Offset(0, -500));
      await tester.pumpAndSettle();

      expect(
        tester.state<ScrollableState>(desplazableDelContenido).position.pixels,
        greaterThan(0),
      );
      expect(tester.getTopLeft(franja), arriba);
      expect(franja.hitTestable(), findsOneWidget);
    });

    testWidgets('con conexión, la lista no la muestra', (tester) async {
      servidor.responder = (_) async => listaCorrecta([servicioJson(id: 41)]);
      await abrirApp(tester);

      expect(franja, findsNothing);
      expect(find.textContaining('Sin conexión'), findsNothing);
    });

    testWidgets('al volver la señal desaparece de la lista', (tester) async {
      await guardar([servicioJson(id: 41)]);
      await abrirApp(tester);
      expect(franja, findsOneWidget);

      servidor.responder = (_) async => listaCorrecta([servicioJson(id: 41)], etag: '"e2"');
      await lista.actualizar();
      await tester.pumpAndSettle();

      expect(franja, findsNothing);
      expect(find.textContaining('Sin conexión'), findsNothing);
    });

    group('en el detalle y en la pantalla del paso', () {
      Finder franjaEn<T>() => find.descendant(of: find.byType(T), matching: franja);

      Future<void> abrirDetalle(WidgetTester tester) async {
        pantallaAlta(tester);
        await abrirApp(tester);
        await abrirDetalleDe(tester, 'ABC123');
      }

      testWidgets('sin conexión, el detalle la muestra fuera de lo que se desplaza', (
        tester,
      ) async {
        await guardar([servicioJson(id: 41)]);
        await abrirDetalle(tester);

        expect(find.text('Servicio N.º 41'), findsOneWidget);
        expect(franjaEn<PantallaServicio>(), findsOneWidget);
        expect(
          find.descendant(
            of: franjaEn<PantallaServicio>(),
            matching: find.text(textoSinSenalAlMarcar),
          ),
          findsOneWidget,
        );
        expect(
          find.text('Sin conexión. Lo que marque se envía cuando vuelva la señal.'),
          findsOneWidget,
        );
        expect(
          find.ancestor(of: franjaEn<PantallaServicio>(), matching: find.byType(Scrollable)),
          findsNothing,
        );
      });

      testWidgets('con conexión, el detalle no la muestra', (tester) async {
        servidor.responder = (_) async => listaCorrecta([servicioJson(id: 41)]);
        await abrirDetalle(tester);

        expect(find.text('Servicio N.º 41'), findsOneWidget);
        expect(franjaEn<PantallaServicio>(), findsNothing);
        expect(find.textContaining('Sin conexión'), findsNothing);
      });

      testWidgets('sin conexión, la pantalla del paso la muestra', (tester) async {
        await guardar([servicioJson(id: 41, estado: 'en_camino')]);
        await abrirDetalle(tester);
        await tocar(tester, find.byKey(const Key('marcar-recogido')));

        expect(find.byKey(const Key('tomar-foto')), findsOneWidget);
        expect(franjaEn<PantallaPaso>(), findsOneWidget);
        expect(
          find.descendant(of: franjaEn<PantallaPaso>(), matching: find.text(textoSinSenalAlMarcar)),
          findsOneWidget,
        );
      });

      testWidgets('con conexión, la pantalla del paso no la muestra', (tester) async {
        servidor.responder = (_) async =>
            listaCorrecta([servicioJson(id: 41, estado: 'en_camino')]);
        await abrirDetalle(tester);
        await tocar(tester, find.byKey(const Key('marcar-recogido')));

        expect(find.byKey(const Key('tomar-foto')), findsOneWidget);
        expect(franjaEn<PantallaPaso>(), findsNothing);
        expect(find.textContaining('Sin conexión'), findsNothing);
      });
    });
  });

  group('mientras lee lo guardado', () {
    testWidgets('la lista dice "Cargando sus servicios…", como un solo elemento para TalkBack', (
      tester,
    ) async {
      final semantica = tester.ensureSemantics();
      await guardar([servicioJson(id: 41)]);
      await sesion.iniciar();

      // El primer cuadro, antes de que termine de leer la base.
      await tester.pumpWidget(app());

      expect(find.text('Cargando sus servicios…'), findsOneWidget);
      expect(find.bySemanticsLabel('Cargando sus servicios…'), findsOneWidget);
      expect(find.text('ABC123'), findsNothing);

      await tester.pumpAndSettle();
      expect(find.text('Cargando sus servicios…'), findsNothing);
      expect(find.text('ABC123'), findsOneWidget);
      semantica.dispose();
    });

    testWidgets('el detalle dice "Cargando el servicio…"', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: temaArribo(),
          home: PantallaServicio(id: 41, lista: lista, abrirEnlace: (_) async => true),
        ),
      );

      expect(find.text('Cargando el servicio…'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('la pantalla del paso dice "Preparando el paso…"', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: temaArribo(),
          home: PantallaPaso(
            servicioId: 41,
            destino: 'recogido',
            lista: lista,
            camara: CamaraFalsa(prueba.carpeta),
          ),
        ),
      );

      expect(find.text('Preparando el paso…'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });
  });

  group('el cambio de la tarjeta activa', () {
    setUp(() async {
      await guardar([servicioJson(id: 41), servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789')]);
    });

    testWidgets('al marcar En camino desde la tarjeta activa, al terminar el cambio queda una sola '
        'tarjeta activa, con el estado nuevo', (tester) async {
      pantallaAlta(tester);
      await abrirApp(tester);
      expect(activa(41, 'asignado'), findsOneWidget);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(tester.takeException(), isNull);
      expect(activa(41, 'asignado'), findsNothing);
      expect(activa(41, 'en_camino'), findsOneWidget);
      expect(tarjeta(41), findsOneWidget);
      expect(find.byKey(const Key('franja-activa')), findsOneWidget);
      final etiqueta = find.descendant(of: tarjeta(41), matching: find.byType(EtiquetaEstado));
      expect(tester.widget<EtiquetaEstado>(etiqueta).estado, 'en_camino');
      expect(find.byKey(const Key('tarjeta-marcar-recogido')), findsOneWidget);
    });

    testWidgets('con animaciones, la anterior se desvanece mientras aparece la nueva, sin claves '
        'repetidas, y solo la nueva recibe toques', (tester) async {
      pantallaAlta(tester);
      await abrirApp(tester);

      await lista.marcar(41, 'en_camino');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(tester.takeException(), isNull);
      expect(activa(41, 'asignado'), findsOneWidget);
      expect(activa(41, 'en_camino'), findsOneWidget);
      // La que sale no recibe toques: su botón de En camino ya no responde.
      expect(find.byKey(const Key('tarjeta-marcar-en_camino')).hitTestable(), findsNothing);

      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(activa(41, 'asignado'), findsNothing);
      expect(activa(41, 'en_camino'), findsOneWidget);
      expect(tarjeta(41), findsOneWidget);
    });

    testWidgets('sin animaciones en el celular, el cambio es inmediato', (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(
        disableAnimations: true,
      );
      addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
      pantallaAlta(tester);
      await abrirApp(tester);
      expect(activa(41, 'asignado'), findsOneWidget);

      await lista.marcar(41, 'en_camino');
      await tester.pump();

      expect(tester.takeException(), isNull);
      expect(activa(41, 'asignado'), findsNothing);
      expect(activa(41, 'en_camino'), findsOneWidget);
      expect(tarjeta(41), findsOneWidget);
    });
  });

  testWidgets('con el texto del sistema al 200 %, la lista vacía y la franja no se desbordan', (
    tester,
  ) async {
    celularConTextoGrande(tester);
    await abrirApp(tester);
    expect(tester.takeException(), isNull);
    expect(franja, findsOneWidget);
    expect(find.text('Aún no hay servicios en el celular'), findsOneWidget);

    await tester.scrollUntilVisible(botonActualizar, 100, scrollable: desplazableDelContenido);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  group('con el texto del sistema al 200 % en 360 dp', () {
    /// La cuarta parte del alto de la pantalla (800 dp).
    const altoMaximo = 800 * 0.25;

    testWidgets('en la lista, la franja no pasa del 25 % del alto, el contenido sigue a la vista '
        'y TalkBack lee el aviso completo', (tester) async {
      final semantica = tester.ensureSemantics();
      celularConTextoGrande(tester);
      await guardar([servicioJson(id: 41), servicioJson(id: 42, ordenRonda: 2, placa: 'XYZ789')]);
      await abrirApp(tester);

      expect(tester.takeException(), isNull);
      expect(tester.getSize(franja).height, lessThanOrEqualTo(altoMaximo));
      expect(find.text('Ahora').hitTestable(), findsOneWidget);
      expect(
        tester.getTopLeft(find.text('Ahora')).dy,
        greaterThanOrEqualTo(tester.getBottomLeft(franja).dy),
      );
      expect(find.bySemanticsLabel(sinConexionEnLaLista), findsOneWidget);
      // El aviso no cabe: se desplaza dentro de la franja, con la barra a la vista.
      final textoDeLaFranja = find.descendant(of: franja, matching: find.byType(Scrollable));
      expect(
        tester.state<ScrollableState>(textoDeLaFranja).position.maxScrollExtent,
        greaterThan(0),
      );
      expect(find.descendant(of: franja, matching: find.byType(Scrollbar)), findsOneWidget);
      semantica.dispose();
    });

    testWidgets('en el detalle, la franja no pasa del 25 % del alto y el contenido sigue a la '
        'vista', (tester) async {
      celularConTextoGrande(tester);
      await guardar([servicioJson(id: 41)]);
      await abrirApp(tester);
      await abrirDetalleDe(tester, 'ABC123');

      expect(tester.takeException(), isNull);
      final franjaDelDetalle = find.descendant(of: find.byType(PantallaServicio), matching: franja);
      expect(tester.getSize(franjaDelDetalle).height, lessThanOrEqualTo(altoMaximo));
      expect(find.byType(EtiquetaEstado).hitTestable(), findsOneWidget);
    });

    testWidgets('a escala normal la franja no se desplaza: el texto cabe completo', (tester) async {
      await guardar([servicioJson(id: 41)]);
      await abrirApp(tester);

      final desplazable = find.descendant(
        of: franja,
        matching: find.byWidgetPredicate((w) => w is Scrollable),
      );
      expect(tester.state<ScrollableState>(desplazable).position.maxScrollExtent, 0);
      expect(tester.getSize(franja).height, lessThan(altoMaximo));
    });
  });
}
