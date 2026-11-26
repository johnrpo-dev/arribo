// Etiqueta de estado (icono + nombre, leída una vez por TalkBack) y barra de avance del servicio.

import 'package:arribo_conductor/asignaciones/componentes.dart';
import 'package:arribo_conductor/tema.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

Future<void> mostrar(WidgetTester tester, Widget hijo, {Brightness brillo = Brightness.light}) =>
    tester.pumpWidget(
      MaterialApp(
        theme: temaArribo(brillo),
        home: Scaffold(body: Center(child: hijo)),
      ),
    );

/// El color de cada uno de los tres tramos de la barra.
List<Color?> coloresDeTramos(WidgetTester tester) => [
  for (var i = 0; i < 3; i++)
    (tester.widget<Container>(find.byKey(Key('avance-$i'))).decoration! as BoxDecoration).color,
];

void main() {
  group('etiqueta de estado', () {
    const casos = {
      'pendiente_asignar': ('Pendiente de asignar', Icons.schedule),
      'asignado': ('Asignado', Icons.assignment_ind_outlined),
      'en_camino': ('En camino', Icons.local_shipping_outlined),
      'recogido': ('Recogido', Icons.directions_car_filled_outlined),
      'entregado': ('Entregado', Icons.check_circle_outline),
      'novedad': ('Novedad', Icons.report_problem_outlined),
      'cancelado': ('Cancelado', Icons.cancel_outlined),
      'otro': ('otro', Icons.help_outline),
    };

    for (final MapEntry(key: estado, value: (nombre, icono)) in casos.entries) {
      testWidgets('$estado: muestra "$nombre" con su icono y el color del estado', (tester) async {
        await mostrar(tester, EtiquetaEstado(estado));

        expect(find.text(nombre), findsOneWidget);
        final icon = tester.widget<Icon>(find.byType(Icon));
        expect(icon.icon, icono);
        expect(icon.color, ColoresArribo.claro.deEstado(estado).texto);
        expect(
          tester.widget<Text>(find.text(nombre)).style?.color,
          ColoresArribo.claro.deEstado(estado).texto,
        );
      });
    }

    testWidgets('en el tema oscuro usa los colores oscuros del estado', (tester) async {
      await mostrar(tester, const EtiquetaEstado('recogido'), brillo: Brightness.dark);

      final oscuro = ColoresArribo.oscuro.deEstado('recogido');
      expect(tester.widget<Icon>(find.byType(Icon)).color, oscuro.texto);
      expect(tester.widget<Text>(find.text('Recogido')).style?.color, oscuro.texto);
      final caja = tester.widget<Container>(
        find.descendant(of: find.byType(EtiquetaEstado), matching: find.byType(Container)),
      );
      expect((caja.decoration! as ShapeDecoration).color, oscuro.fondo);
    });

    testWidgets('TalkBack la lee una sola vez como "Estado: …"', (tester) async {
      final semantica = tester.ensureSemantics();
      await mostrar(tester, const EtiquetaEstado('en_camino'));

      expect(find.bySemanticsLabel('Estado: En camino'), findsOneWidget);
      expect(find.bySemanticsLabel('En camino'), findsNothing);
      semantica.dispose();
    });

    testWidgets('las marcas de pendiente, fotos y espera tienen la misma forma de pastilla', (
      tester,
    ) async {
      await mostrar(
        tester,
        const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            EtiquetaEstado('asignado'),
            EtiquetaPendiente(),
            EtiquetaFotosPendientes(3),
            EtiquetaEsperaIda(),
          ],
        ),
      );

      final formas = [
        for (final caja in tester.widgetList<Container>(
          find.descendant(of: find.byType(Column), matching: find.byType(Container)),
        ))
          if (caja.decoration is ShapeDecoration) caja,
      ];
      expect(formas, hasLength(4));
      for (final caja in formas) {
        final forma = (caja.decoration! as ShapeDecoration).shape as StadiumBorder;
        expect(forma.side.width, 1.5);
        expect(caja.padding, const EdgeInsets.symmetric(horizontal: 12, vertical: 6));
      }
      expect(find.text('Pendiente por enviar'), findsOneWidget);
      expect(find.text('3 fotos por subir'), findsOneWidget);
      expect(find.text('Espera la ida'), findsOneWidget);
      expect(find.byKey(const Key('espera-ida')), findsOneWidget);
    });
  });

  group('barra de avance', () {
    test('cuenta los pasos cumplidos: asignado 0, en camino 1, recogido 2, entregado 3', () {
      expect(pasosCumplidos('pendiente_asignar'), 0);
      expect(pasosCumplidos('asignado'), 0);
      expect(pasosCumplidos('en_camino'), 1);
      expect(pasosCumplidos('recogido'), 2);
      expect(pasosCumplidos('entregado'), 3);
    });

    test('en una novedad cuenta hasta el estado que tenía antes; sin él, ninguno', () {
      expect(pasosCumplidos('novedad', estadoPrevio: 'recogido'), 2);
      expect(pasosCumplidos('novedad', estadoPrevio: 'asignado'), 0);
      expect(pasosCumplidos('novedad'), 0);
    });

    final vacio = ColoresArribo.claro.pista;
    final lleno = ColoresArribo.claro.acento;
    final casos = {
      'asignado': [vacio, vacio, vacio],
      'en_camino': [lleno, vacio, vacio],
      'recogido': [lleno, lleno, vacio],
      'entregado': [lleno, lleno, lleno],
    };
    for (final MapEntry(key: estado, value: esperados) in casos.entries) {
      testWidgets('$estado: llena ${esperados.where((c) => c == lleno).length} de 3 tramos', (
        tester,
      ) async {
        await mostrar(tester, BarraDeAvance(estado));

        expect(coloresDeTramos(tester), esperados);
      });
    }

    testWidgets('novedad: llena en rojo hasta donde iba', (tester) async {
      await mostrar(tester, const BarraDeAvance('novedad', estadoPrevio: 'en_camino'));

      expect(coloresDeTramos(tester), [ColoresArribo.claro.peligro, vacio, vacio]);
    });

    testWidgets('en el tema oscuro llena con el acento oscuro y deja vacíos con la pista oscura', (
      tester,
    ) async {
      await mostrar(tester, const BarraDeAvance('en_camino'), brillo: Brightness.dark);

      const o = ColoresArribo.oscuro;
      expect(coloresDeTramos(tester), [o.acento, o.pista, o.pista]);
    });

    testWidgets('cancelado: no muestra la barra', (tester) async {
      final semantica = tester.ensureSemantics();
      await mostrar(tester, const BarraDeAvance('cancelado'));

      expect(find.byKey(const Key('avance-0')), findsNothing);
      expect(find.bySemanticsLabel(RegExp('^Avance')), findsNothing);
      semantica.dispose();
    });

    testWidgets('TalkBack lee la barra una sola vez con el paso y su nombre', (tester) async {
      final semantica = tester.ensureSemantics();
      await mostrar(tester, const BarraDeAvance('recogido'));
      expect(find.bySemanticsLabel('Avance: paso 2 de 3, Recogido'), findsOneWidget);
      expect(find.bySemanticsLabel('Entregado'), findsNothing);

      await mostrar(tester, const BarraDeAvance('novedad', estadoPrevio: 'recogido'));
      expect(find.bySemanticsLabel('Avance: paso 2 de 3, Recogido, con novedad'), findsOneWidget);

      await mostrar(tester, const BarraDeAvance('asignado'));
      expect(find.bySemanticsLabel('Avance: paso 0 de 3'), findsOneWidget);
      semantica.dispose();
    });

    testWidgets('nombra los tres pasos debajo de los tramos', (tester) async {
      await mostrar(tester, const BarraDeAvance('en_camino'));

      for (final paso in ['En camino', 'Recogido', 'Entregado']) {
        expect(find.text(paso, findRichText: true), findsOneWidget);
      }
    });

    testWidgets('con el texto al 200 % en 360 dp cada paso cabe entero en una línea', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.reset);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      await mostrar(
        tester,
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16),
          child: BarraDeAvance('recogido'),
        ),
      );

      expect(tester.takeException(), isNull);
      for (final (i, paso) in ['En camino', 'Recogido', 'Entregado'].indexed) {
        final nombre = find.text(paso, findRichText: true);
        final texto = tester.widget<RichText>(nombre);
        final parrafo = tester.renderObject<RenderParagraph>(nombre);
        // El nombre completo en una sola línea, sin cortarse.
        final unaLinea = TextPainter(
          text: texto.text,
          textScaler: texto.textScaler,
          textDirection: TextDirection.ltr,
        )..layout();
        addTearDown(unaLinea.dispose);
        expect(parrafo.didExceedMaxLines, isFalse, reason: paso);
        expect(parrafo.size.height, unaLinea.height, reason: paso);
        expect(parrafo.size.width, closeTo(unaLinea.width, 0.01), reason: paso);
        // Y, achicado si hace falta, no se sale de su tramo.
        final ajustado = find.ancestor(of: nombre, matching: find.byType(FittedBox));
        expect(
          tester.getSize(ajustado).width,
          lessThanOrEqualTo(tester.getSize(find.byKey(Key('avance-$i'))).width),
          reason: paso,
        );
      }
    });
  });
}
