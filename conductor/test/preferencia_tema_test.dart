// Tema elegido por el conductor: automático por defecto, claro u oscuro desde el menú de la lista;
// se aplica de inmediato y sigue elegido al volver a abrir la app.

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:arribo_conductor/preferencia_tema.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import 'ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  final ahora = DateTime.utc(2026, 11, 20, 15);

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => sinSenal());
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [Servicio.desdeJson(servicioJson(id: 41))],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora,
    );
  });
  tearDown(() async => prueba.cerrar());

  /// Abre la app con la sesión iniciada, como al encender el celular.
  Future<void> abrirApp(WidgetTester tester, {PreferenciaTema? tema}) async {
    final sesion = Sesion(
      api: servidor.api(),
      base: prueba.base,
      almacenToken: AlmacenTokenEnMemoria('token-ana'),
    );
    await sesion.iniciar();
    final lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
    );
    await tester.pumpWidget(
      ArriboApp(
        // Otra llave: al "reabrir" se arma una app nueva, no se reusa el estado de la anterior.
        key: UniqueKey(),
        sesion: sesion,
        lista: lista,
        reloj: () => ahora,
        abrirEnlace: (_) async => true,
        tema: tema,
      ),
    );
    await tester.pumpAndSettle();
  }

  Brightness brilloDeLaLista(WidgetTester tester) =>
      Theme.of(tester.element(find.text('Mis servicios'))).brightness;

  ThemeMode modoDeLaApp(WidgetTester tester) =>
      tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode!;

  Future<void> elegir(WidgetTester tester, String llave) async {
    await tester.tap(find.byTooltip('Más opciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tema'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(Key(llave)));
    await tester.pumpAndSettle();
  }

  testWidgets('por defecto el tema sigue al teléfono', (tester) async {
    await abrirApp(tester);

    expect(modoDeLaApp(tester), ThemeMode.system);
    expect(brilloDeLaLista(tester), Brightness.light);
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    await tester.pumpAndSettle();
    expect(brilloDeLaLista(tester), Brightness.dark);
  });

  testWidgets('el menú ofrece las tres opciones, con la vigente marcada y de 56 dp o más', (
    tester,
  ) async {
    await abrirApp(tester);
    await tester.tap(find.byTooltip('Más opciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tema'));
    await tester.pumpAndSettle();

    expect(find.text('Automático (como el teléfono)'), findsOneWidget);
    expect(find.text('Claro'), findsOneWidget);
    expect(find.text('Oscuro'), findsOneWidget);
    for (final llave in ['tema-system', 'tema-light', 'tema-dark']) {
      expect(tester.getSize(find.byKey(Key(llave))).height, greaterThanOrEqualTo(56));
    }
    expect(
      tester.widget<RadioGroup<ThemeMode>>(find.byType(RadioGroup<ThemeMode>)).groupValue,
      ThemeMode.system,
    );
  });

  testWidgets('elegir Oscuro lo aplica de inmediato, cierra el diálogo y lo guarda', (
    tester,
  ) async {
    await abrirApp(tester);

    await elegir(tester, 'tema-dark');

    expect(find.byType(AlertDialog), findsNothing);
    expect(modoDeLaApp(tester), ThemeMode.dark);
    expect(brilloDeLaLista(tester), Brightness.dark);
    expect(await prueba.base.leerPreferencia(Preferencia.tema), 'oscuro');
  });

  testWidgets('el tema elegido sigue al cerrar y abrir la app', (tester) async {
    await abrirApp(tester);
    await elegir(tester, 'tema-dark');

    // El sistema mata la app: se arma todo de nuevo sobre la misma base, leyendo lo guardado.
    await tester.pumpWidget(const SizedBox());
    final tema = await PreferenciaTema.cargar(prueba.base);
    expect(tema.value, ThemeMode.dark);
    await abrirApp(tester, tema: tema);

    expect(brilloDeLaLista(tester), Brightness.dark);

    // Sin el tema leído de antemano, la app lo lee sola al abrir.
    await tester.pumpWidget(const SizedBox());
    await abrirApp(tester);
    expect(brilloDeLaLista(tester), Brightness.dark);

    // Y volver a Claro también queda guardado.
    await elegir(tester, 'tema-light');
    expect(brilloDeLaLista(tester), Brightness.light);
    expect((await PreferenciaTema.cargar(prueba.base)).value, ThemeMode.light);
  });
}
