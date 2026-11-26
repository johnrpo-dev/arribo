// Los colores de la app se leen al sol directo y de noche: contraste de al menos 7:1 (WCAG AAA)
// en las dos paletas. La clara no cambia al agregar la oscura.

import 'package:arribo_conductor/tema.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

/// Contraste WCAG entre dos colores opacos: (L1 + 0,05) / (L2 + 0,05), con L1 la más clara.
double contraste(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final (clara, oscura) = la > lb ? (la, lb) : (lb, la);
  return (clara + 0.05) / (oscura + 0.05);
}

const estados = [
  'pendiente_asignar',
  'asignado',
  'en_camino',
  'recogido',
  'entregado',
  'novedad',
  'cancelado',
  'desconocido',
];

void main() {
  test('la fórmula de contraste da 21:1 entre negro y blanco', () {
    expect(contraste(const Color(0xFF000000), const Color(0xFFFFFFFF)), closeTo(21, 0.01));
  });

  for (final (nombre, paleta) in [
    ('clara', ColoresArribo.claro),
    ('oscura', ColoresArribo.oscuro),
  ]) {
    group('paleta $nombre', () {
      test('el texto de cada estado sobre su fondo tiene contraste de al menos 7:1', () {
        for (final estado in estados) {
          final colores = paleta.deEstado(estado);
          expect(
            contraste(colores.texto, colores.fondo),
            greaterThanOrEqualTo(7.0),
            reason: estado,
          );
        }
      });

      test('el texto secundario tiene contraste de al menos 7:1 en tarjetas y en el fondo', () {
        expect(contraste(paleta.textoSecundario, paleta.superficie), greaterThanOrEqualTo(7.0));
        expect(contraste(paleta.textoSecundario, paleta.fondo), greaterThanOrEqualTo(7.0));
      });

      test('el aviso sobre su fondo tiene contraste de al menos 7:1', () {
        expect(contraste(paleta.aviso, paleta.avisoFondo), greaterThanOrEqualTo(7.0));
      });

      test('lo que falta de la barra de avance se distingue (3:1) del fondo y de las tarjetas', () {
        expect(contraste(paleta.pista, paleta.fondo), greaterThanOrEqualTo(3.0));
        expect(contraste(paleta.pista, paleta.superficie), greaterThanOrEqualTo(3.0));
      });
    });
  }

  test('en el tema oscuro, el texto de los botones llenos y de error se lee (7:1)', () {
    final esquema = temaArribo(Brightness.dark).colorScheme;
    expect(contraste(esquema.onPrimary, esquema.primary), greaterThanOrEqualTo(7.0));
    expect(contraste(esquema.onError, esquema.error), greaterThanOrEqualTo(7.0));
    expect(contraste(esquema.onInverseSurface, esquema.inverseSurface), greaterThanOrEqualTo(7.0));
  });

  test('la paleta clara conserva los valores de siempre', () {
    const c = ColoresArribo.claro;
    expect(
      [
        c.fondo,
        c.superficie,
        c.borde,
        c.texto,
        c.textoSecundario,
        c.acento,
        c.acentoFondo,
        c.peligro,
        c.peligroFondo,
        c.aviso,
        c.avisoFondo,
        c.regreso,
        c.regresoFondo,
      ],
      const [
        Color(0xFFEEF0F3),
        Color(0xFFFFFFFF),
        Color(0xFFB9C0C9),
        Color(0xFF1B1F24),
        Color(0xFF49515B),
        Color(0xFF1F4FBF),
        Color(0xFFE8EEFB),
        Color(0xFFB3261E),
        Color(0xFFFBE9E8),
        Color(0xFF774600),
        Color(0xFFFCF1E1),
        Color(0xFF08564F),
        Color(0xFFE1F4F1),
      ],
    );
    expect(c.deEstado('asignado'), (
      texto: const Color(0xFF1A3F99),
      fondo: const Color(0xFFE8EEFB),
    ));
    expect(c.deEstado('en_camino'), (
      texto: const Color(0xFF553180),
      fondo: const Color(0xFFF2ECF8),
    ));
    expect(c.deEstado('recogido'), (
      texto: const Color(0xFF774600),
      fondo: const Color(0xFFFCF1E1),
    ));
    expect(c.deEstado('entregado'), (
      texto: const Color(0xFF12603A),
      fondo: const Color(0xFFEEF8F2),
    ));
    expect(c.deEstado('cancelado'), (
      texto: const Color(0xFF8C1D18),
      fondo: const Color(0xFFFBE9E8),
    ));
    expect(c.deEstado('otro'), (texto: const Color(0xFF3F4650), fondo: const Color(0xFFEEF0F3)));
    final claro = temaArribo();
    expect(claro.brightness, Brightness.light);
    expect(claro.colorScheme.onPrimary, const Color(0xFFFFFFFF));
    expect(claro.scaffoldBackgroundColor, c.fondo);
    expect(claro.extension<ColoresArribo>(), same(c));
  });

  test('el tema oscuro es oscuro y lleva su paleta', () {
    final oscuro = temaArribo(Brightness.dark);
    expect(oscuro.brightness, Brightness.dark);
    expect(oscuro.scaffoldBackgroundColor, ColoresArribo.oscuro.fondo);
    expect(oscuro.extension<ColoresArribo>(), same(ColoresArribo.oscuro));
    expect(oscuro.textTheme.bodyLarge?.color, ColoresArribo.oscuro.texto);
  });
}
