// Los colores de la app se leen al sol directo: contraste de al menos 7:1 (WCAG AAA).

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

void main() {
  test('la fórmula de contraste da 21:1 entre negro y blanco', () {
    expect(contraste(const Color(0xFF000000), const Color(0xFFFFFFFF)), closeTo(21, 0.01));
  });

  test('el texto de cada estado sobre su fondo tiene contraste de al menos 7:1', () {
    for (final estado in [
      'pendiente_asignar',
      'asignado',
      'en_camino',
      'recogido',
      'entregado',
      'novedad',
      'cancelado',
      'desconocido',
    ]) {
      final colores = coloresDeEstado(estado);
      expect(
        contraste(colores.texto, colores.fondo),
        greaterThanOrEqualTo(7.0),
        reason: estado,
      );
    }
  });

  test('el texto secundario tiene contraste de al menos 7:1 en tarjetas y en el fondo', () {
    expect(contraste(Colores.textoSecundario, Colores.superficie), greaterThanOrEqualTo(7.0));
    expect(contraste(Colores.textoSecundario, Colores.fondo), greaterThanOrEqualTo(7.0));
  });

  test('el aviso sobre su fondo tiene contraste de al menos 7:1', () {
    expect(contraste(Colores.aviso, Colores.avisoFondo), greaterThanOrEqualTo(7.0));
  });
}
