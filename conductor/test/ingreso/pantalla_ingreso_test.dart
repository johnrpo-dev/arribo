// Pantalla de ingreso: validación del PIN de 6 dígitos y errores del servidor en español.

import 'package:arribo_conductor/ingreso/pantalla_ingreso.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:arribo_conductor/tema.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late Sesion sesion;
  // 3:30 p. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 20, 30);

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => ingresoCorrecto());
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: AlmacenTokenEnMemoria());
    await sesion.iniciar();
  });
  tearDown(() async => prueba.cerrar());

  Future<void> mostrar(WidgetTester tester) => tester.pumpWidget(
    MaterialApp(
      theme: temaArribo(),
      home: PantallaIngreso(sesion: sesion, servidor: 'http://127.0.0.1:8000', reloj: () => ahora),
    ),
  );

  Future<void> escribirYEnviar(
    WidgetTester tester, {
    String celular = '300 123 4567',
    required String pin,
  }) async {
    await tester.enterText(find.byKey(const Key('celular')), celular);
    await tester.enterText(find.byKey(const Key('pin')), pin);
    await tester.ensureVisible(find.byKey(const Key('ingresar')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('ingresar')));
    await tester.pumpAndSettle();
  }

  test('el PIN válido tiene exactamente 6 dígitos', () {
    expect(validarPin('482913'), isNull);
    expect(validarPin('012345'), isNull);
    expect(validarPin('12345'), isNotNull);
    expect(validarPin('1234567'), isNotNull);
    expect(validarPin('12a456'), isNotNull);
    expect(validarPin(''), isNotNull);
  });

  testWidgets('un PIN de 5 dígitos muestra el error y no llama al servidor', (tester) async {
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '12345');

    expect(find.text('El PIN tiene 6 dígitos.'), findsOneWidget);
    expect(servidor.peticiones, isEmpty);
  });

  testWidgets('sin celular muestra el error y no llama al servidor', (tester) async {
    await mostrar(tester);

    await escribirYEnviar(tester, celular: '', pin: '482913');

    expect(find.text('Escriba su número de celular.'), findsOneWidget);
    expect(servidor.peticiones, isEmpty);
  });

  testWidgets('el campo del PIN solo admite dígitos y como máximo 6', (tester) async {
    await mostrar(tester);

    await tester.enterText(find.byKey(const Key('pin')), '12a4567890');

    final campo = tester.widget<EditableText>(
      find.descendant(of: find.byKey(const Key('pin')), matching: find.byType(EditableText)),
    );
    expect(campo.controller.text, '124567');
    expect(campo.keyboardType, TextInputType.number);
    expect(campo.obscureText, isTrue);
  });

  testWidgets('con 6 dígitos ingresa y abre la sesión', (tester) async {
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '482913');

    expect(servidor.peticiones.single.json['pin'], '482913');
    expect(sesion.estado, EstadoSesion.activa);
  });

  testWidgets('un PIN malo muestra el texto del servidor y borra el PIN', (tester) async {
    servidor.responder = (_) async =>
        errorDelContrato(401, 'credenciales_invalidas', 'Celular o PIN incorrectos.');
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '000000');

    expect(find.text('Celular o PIN incorrectos.'), findsOneWidget);
    expect(sesion.estado, EstadoSesion.sinSesion);
    final pin = tester.widget<EditableText>(
      find.descendant(of: find.byKey(const Key('pin')), matching: find.byType(EditableText)),
    );
    expect(pin.controller.text, isEmpty);
  });

  testWidgets(
    'el bloqueo por intentos muestra el texto del servidor y apaga el botón hasta la hora',
    (tester) async {
      servidor.responder = (_) async => errorDelContrato(
        429,
        'demasiados_intentos',
        'Demasiados intentos fallidos. Intente de nuevo en 15 minutos.',
        extra: {'reintentar_en': 900},
      );
      await mostrar(tester);

      await escribirYEnviar(tester, pin: '000000');

      expect(
        find.text('Demasiados intentos fallidos. Intente de nuevo en 15 minutos.'),
        findsOneWidget,
      );
      expect(find.text('Espere hasta las 3:45 p. m.'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.byKey(const Key('ingresar'))).onPressed, isNull);

      // Durante el bloqueo, otro intento no llega al servidor.
      await tester.tap(find.byKey(const Key('ingresar')));
      await tester.pump();
      expect(servidor.peticiones, hasLength(1));

      await tester.pump(const Duration(minutes: 15));
      expect(find.text('Ingresar'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.byKey(const Key('ingresar'))).onPressed, isNotNull);
    },
  );

  testWidgets('los errores por campo del servidor se muestran junto al campo', (tester) async {
    servidor.responder = (_) async => errorDelContrato(
      400,
      'datos_invalidos',
      'Revise los datos enviados.',
      extra: {
        'campos': {
          'celular': ['Este campo es requerido.'],
        },
      },
    );
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '482913');

    expect(find.text('Revise los datos enviados.'), findsOneWidget);
    expect(find.text('Este campo es requerido.'), findsOneWidget);
  });

  testWidgets('sin señal lo dice en español', (tester) async {
    servidor.responder = (_) async => sinSenal();
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '482913');

    expect(
      find.text('No hay conexión con el servidor. Revise la señal e intente de nuevo.'),
      findsOneWidget,
    );
  });

  testWidgets('con el texto del sistema al 200 % la pantalla no se rompe', (tester) async {
    celularConTextoGrande(tester);
    await mostrar(tester);

    await escribirYEnviar(tester, pin: '12345');

    expect(tester.takeException(), isNull);
    expect(find.text('El PIN tiene 6 dígitos.'), findsOneWidget);
  });
}
