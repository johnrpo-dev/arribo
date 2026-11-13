// Recorrido completo: abrir sin sesión, ingresar y ver la lista; cerrar sesión.

import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:material_ui/material_ui.dart';

import 'ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  late ListaAsignaciones lista;
  final ahora = DateTime.utc(2026, 11, 20, 15);

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((peticion) async {
      return switch (peticion.url.path) {
        '/api/v1/ingresar/' => ingresoCorrecto(),
        '/api/v1/asignaciones/' => listaCorrecta([servicioJson(id: 41)]),
        '/api/v1/salir/' => http.Response('', 204),
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
  });
  tearDown(() async => prueba.cerrar());

  Future<void> abrirApp(WidgetTester tester) async {
    await tester.pumpWidget(
      ArriboApp(sesion: sesion, lista: lista, reloj: () => ahora, abrirEnlace: (_) async => true),
    );
    await sesion.iniciar();
    await tester.pumpAndSettle();
  }

  testWidgets('sin sesión abre el ingreso; al ingresar muestra la lista del servidor', (
    tester,
  ) async {
    await abrirApp(tester);
    expect(find.text('Ingresar'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('celular')), '300 123 4567');
    await tester.enterText(find.byKey(const Key('pin')), '482913');
    await tester.tap(find.byKey(const Key('ingresar')));
    await tester.pumpAndSettle();

    expect(find.text('Mis servicios'), findsOneWidget);
    expect(find.text('ABC123'), findsOneWidget);
    expect(token.token, 'token-ana');
    expect(servidor.peticiones.last.cabeceras['Authorization'], 'Bearer token-ana');
  });

  testWidgets('cerrar sesión pide confirmación y vuelve al ingreso', (tester) async {
    token.token = 'token-ana';
    await abrirApp(tester);
    expect(find.text('Mis servicios'), findsOneWidget);

    await tester.tap(find.byTooltip('Más opciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cerrar sesión'));
    await tester.pumpAndSettle();
    expect(find.text('¿Cerrar sesión?'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Cerrar sesión'));
    await tester.pumpAndSettle();

    expect(find.text('Ingresar'), findsOneWidget);
    expect(token.token, isNull);
    expect(servidor.peticiones.last.url.path, '/api/v1/salir/');
  });

  testWidgets('un 401 con el detalle abierto cierra el detalle y vuelve al ingreso', (
    tester,
  ) async {
    token.token = 'token-ana';
    await abrirApp(tester);
    await tester.tap(find.text('ABC123'));
    await tester.pumpAndSettle();
    expect(find.text('Servicio N.º 41'), findsOneWidget);
    servidor.responder = (_) async =>
        errorDelContrato(401, 'sesion_invalida', 'Su sesión se cerró.');

    await lista.actualizar();
    await tester.pumpAndSettle();

    expect(find.text('Servicio N.º 41'), findsNothing);
    expect(find.text('Su sesión se cerró.'), findsOneWidget);
  });
}
