// Tema de la app: sobrio y legible bajo el sol. Fondo claro, texto casi negro, letra grande y
// botones altos para usar con una mano. Los colores son los mismos tonos del panel web
// (backend/panel/static/panel/arribo.css), más oscuros para que se lean al sol directo: el texto
// de cada estado sobre su fondo tiene contraste de al menos 7:1 (lo vigila test/tema_test.dart).
// Sin gradientes, sombras ni ilustraciones.

import 'package:material_ui/material_ui.dart';

abstract final class Colores {
  static const fondo = Color(0xFFEEF0F3);
  static const superficie = Color(0xFFFFFFFF);
  static const borde = Color(0xFFB9C0C9);
  static const texto = Color(0xFF1B1F24);
  static const textoSecundario = Color(0xFF49515B);
  static const acento = Color(0xFF1F4FBF);
  static const acentoFondo = Color(0xFFE8EEFB);
  static const peligro = Color(0xFFB3261E);
  static const peligroFondo = Color(0xFFFBE9E8);
  static const avisoFondo = Color(0xFFFCF1E1);
  static const aviso = Color(0xFF774600);

  /// Regreso de un evento (el mismo verde azulado del panel).
  static const regreso = Color(0xFF08564F);
  static const regresoFondo = Color(0xFFE1F4F1);
}

/// Texto y fondo de la etiqueta de cada estado: los tonos del panel, más oscuros para el sol
/// (contraste de al menos 7:1).
({Color texto, Color fondo}) coloresDeEstado(String estado) => switch (estado) {
  'asignado' => (texto: Color(0xFF1A3F99), fondo: Color(0xFFE8EEFB)),
  'en_camino' => (texto: Color(0xFF553180), fondo: Color(0xFFF2ECF8)),
  'recogido' => (texto: Color(0xFF774600), fondo: Color(0xFFFCF1E1)),
  'entregado' => (texto: Color(0xFF12603A), fondo: Color(0xFFEEF8F2)),
  'novedad' || 'cancelado' => (texto: Color(0xFF8C1D18), fondo: Color(0xFFFBE9E8)),
  _ => (texto: Color(0xFF3F4650), fondo: Color(0xFFEEF0F3)),
};

/// Alto mínimo de los botones: más que los 48 dp de Material, para tocarlos con el pulgar.
const double altoBoton = 56;

/// Esquinas de las tarjetas.
const double radioTarjeta = 12;

/// Esquinas de los botones y de los campos de texto.
const double radioControl = 10;

/// La placa (o el VIN) en grande: la cifra de ancho fijo para leerla y compararla de un vistazo.
const estiloPlaca = TextStyle(
  fontSize: 30,
  fontWeight: FontWeight.w700,
  letterSpacing: 1.5,
  fontFeatures: [FontFeature.tabularFigures()],
  color: Colores.texto,
);

ThemeData temaArribo() {
  const esquema = ColorScheme.light(
    primary: Colores.acento,
    onPrimary: Colors.white,
    primaryContainer: Colores.acentoFondo,
    onPrimaryContainer: Colores.texto,
    secondary: Colores.acento,
    onSecondary: Colors.white,
    surface: Colores.superficie,
    onSurface: Colores.texto,
    onSurfaceVariant: Colores.textoSecundario,
    surfaceContainerLowest: Colores.superficie,
    surfaceContainerLow: Colores.fondo,
    surfaceContainer: Colores.fondo,
    surfaceContainerHigh: Colores.superficie,
    surfaceContainerHighest: Colores.superficie,
    outline: Color(0xFF8A929C),
    outlineVariant: Colores.borde,
    error: Colores.peligro,
    onError: Colors.white,
    surfaceTint: Colors.transparent,
  );

  final base = ThemeData(colorScheme: esquema, useMaterial3: true);
  final textos = base.textTheme
      .copyWith(
        headlineSmall: const TextStyle(fontSize: 26, fontWeight: FontWeight.w600, height: 1.25),
        titleLarge: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600, height: 1.25),
        titleMedium: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600, height: 1.3),
        bodyLarge: const TextStyle(fontSize: 18, height: 1.4),
        bodyMedium: const TextStyle(fontSize: 17, height: 1.4),
        bodySmall: const TextStyle(fontSize: 16, height: 1.35),
        labelLarge: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        labelMedium: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      )
      .apply(bodyColor: Colores.texto, displayColor: Colores.texto);

  const forma = RoundedRectangleBorder(
    borderRadius: BorderRadius.all(Radius.circular(radioControl)),
  );

  return base.copyWith(
    scaffoldBackgroundColor: Colores.fondo,
    textTheme: textos,
    appBarTheme: const AppBarTheme(
      backgroundColor: Colores.superficie,
      foregroundColor: Colores.texto,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: Colores.texto),
      shape: Border(bottom: BorderSide(color: Colores.borde)),
    ),
    cardTheme: const CardThemeData(
      color: Colores.superficie,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: Colores.borde),
        borderRadius: BorderRadius.all(Radius.circular(radioTarjeta)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(64, altoBoton),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        textStyle: textos.labelLarge,
        shape: forma,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, altoBoton),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        foregroundColor: Colores.acento,
        textStyle: textos.labelLarge,
        side: const BorderSide(color: Colores.acento, width: 1.5),
        shape: forma,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(64, 52),
        foregroundColor: Colores.acento,
        textStyle: textos.labelLarge,
        shape: forma,
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: Colores.superficie,
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(radioControl))),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(radioControl)),
        borderSide: BorderSide(color: Color(0xFF8A929C)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(radioControl)),
        borderSide: BorderSide(color: Colores.acento, width: 2),
      ),
      labelStyle: TextStyle(fontSize: 18, color: Colores.textoSecundario),
      floatingLabelStyle: TextStyle(fontSize: 18, color: Colores.acento),
      errorStyle: TextStyle(fontSize: 15, color: Colores.peligro),
      helperStyle: TextStyle(fontSize: 15, color: Colores.textoSecundario),
    ),
    dividerTheme: const DividerThemeData(color: Colores.borde, space: 1, thickness: 1),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: Colores.acento),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      contentTextStyle: textos.bodyLarge?.copyWith(color: Colors.white),
    ),
  );
}
