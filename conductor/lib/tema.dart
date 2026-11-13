// Tema de la app: sobrio y legible bajo el sol. Fondo claro, texto casi negro, letra grande y
// botones altos para usar con una mano. Los colores son los del panel web
// (backend/panel/static/panel/arribo.css), para que los estados se vean igual en los dos lados.
// Sin gradientes, sombras ni ilustraciones.

import 'package:material_ui/material_ui.dart';

abstract final class Colores {
  static const fondo = Color(0xFFF6F7F9);
  static const superficie = Color(0xFFFFFFFF);
  static const borde = Color(0xFFD9DDE3);
  static const texto = Color(0xFF1B1F24);
  static const textoSecundario = Color(0xFF5B6470);
  static const acento = Color(0xFF1F4FBF);
  static const acentoFondo = Color(0xFFE8EEFB);
  static const peligro = Color(0xFFB3261E);
  static const peligroFondo = Color(0xFFFBE9E8);
  static const avisoFondo = Color(0xFFFCF1E1);
  static const aviso = Color(0xFF9A5B00);
}

/// Texto y fondo de la etiqueta de cada estado (los mismos tonos del panel, contraste AA).
({Color texto, Color fondo}) coloresDeEstado(String estado) => switch (estado) {
  'asignado' => (texto: Color(0xFF1F4FBF), fondo: Color(0xFFE8EEFB)),
  'en_camino' => (texto: Color(0xFF6B3FA0), fondo: Color(0xFFF2ECF8)),
  'recogido' => (texto: Color(0xFF9A5B00), fondo: Color(0xFFFCF1E1)),
  'entregado' => (texto: Color(0xFF1A7F4B), fondo: Color(0xFFEEF8F2)),
  'novedad' || 'cancelado' => (texto: Color(0xFFB3261E), fondo: Color(0xFFFBE9E8)),
  _ => (texto: Color(0xFF5B6470), fondo: Color(0xFFEEF0F3)),
};

/// Alto mínimo de los botones: más que los 48 dp de Material, para tocarlos con el pulgar.
const double altoBoton = 56;

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
        bodySmall: const TextStyle(fontSize: 15, height: 1.35),
        labelLarge: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        labelMedium: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
      )
      .apply(bodyColor: Colores.texto, displayColor: Colores.texto);

  const forma = RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8)));

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
        borderRadius: BorderRadius.all(Radius.circular(8)),
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
        minimumSize: const Size(64, 48),
        foregroundColor: Colores.acento,
        textStyle: textos.labelLarge,
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: Colores.superficie,
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(8)),
        borderSide: BorderSide(color: Color(0xFF8A929C)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(8)),
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
