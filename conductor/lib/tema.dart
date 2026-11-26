// Tema de la app: sobrio y legible bajo el sol, con letra grande y botones altos para usar con
// una mano. Hay dos paletas: clara (fondo claro, texto casi negro) y oscura (para la noche). Los
// colores son los mismos tonos del panel web (backend/panel/static/panel/arribo.css), ajustados
// para que se lean al sol directo o de noche: el texto de cada estado sobre su fondo tiene
// contraste de al menos 7:1 en las dos (lo vigila test/tema_test.dart).
// Sin gradientes, sombras ni ilustraciones.
//
// Las pantallas toman los colores del tema con `context.colores`, nunca de una constante: así
// cambian solos al pasar de claro a oscuro.

import 'package:material_ui/material_ui.dart';

/// Texto y fondo de una etiqueta de estado.
typedef ColoresDeEstado = ({Color texto, Color fondo});

/// Los colores propios de Arribo, como extensión del tema.
@immutable
class ColoresArribo extends ThemeExtension<ColoresArribo> {
  const ColoresArribo({
    required this.fondo,
    required this.superficie,
    required this.borde,
    required this.texto,
    required this.textoSecundario,
    required this.acento,
    required this.acentoFondo,
    required this.peligro,
    required this.peligroFondo,
    required this.aviso,
    required this.avisoFondo,
    required this.regreso,
    required this.regresoFondo,
    required this.pista,
    required this.asignado,
    required this.enCamino,
    required this.recogido,
    required this.entregado,
    required this.novedad,
    required this.otroEstado,
  });

  /// La paleta para el sol.
  static const claro = ColoresArribo(
    fondo: Color(0xFFEEF0F3),
    superficie: Color(0xFFFFFFFF),
    borde: Color(0xFFB9C0C9),
    texto: Color(0xFF1B1F24),
    textoSecundario: Color(0xFF49515B),
    acento: Color(0xFF1F4FBF),
    acentoFondo: Color(0xFFE8EEFB),
    peligro: Color(0xFFB3261E),
    peligroFondo: Color(0xFFFBE9E8),
    aviso: Color(0xFF774600),
    avisoFondo: Color(0xFFFCF1E1),
    regreso: Color(0xFF08564F),
    regresoFondo: Color(0xFFE1F4F1),
    pista: Color(0xFF808892),
    asignado: (texto: Color(0xFF1A3F99), fondo: Color(0xFFE8EEFB)),
    enCamino: (texto: Color(0xFF553180), fondo: Color(0xFFF2ECF8)),
    recogido: (texto: Color(0xFF774600), fondo: Color(0xFFFCF1E1)),
    entregado: (texto: Color(0xFF12603A), fondo: Color(0xFFEEF8F2)),
    novedad: (texto: Color(0xFF8C1D18), fondo: Color(0xFFFBE9E8)),
    otroEstado: (texto: Color(0xFF3F4650), fondo: Color(0xFFEEF0F3)),
  );

  /// La paleta para la noche: fondos oscuros y los mismos tonos, claros.
  static const oscuro = ColoresArribo(
    fondo: Color(0xFF121417),
    superficie: Color(0xFF1C1F24),
    borde: Color(0xFF5E6670),
    texto: Color(0xFFECEEF1),
    textoSecundario: Color(0xFFB8BEC6),
    acento: Color(0xFFA8C2FF),
    acentoFondo: Color(0xFF1E2A4A),
    peligro: Color(0xFFFFB4AB),
    peligroFondo: Color(0xFF3D1A18),
    aviso: Color(0xFFFFD08A),
    avisoFondo: Color(0xFF3A2A10),
    regreso: Color(0xFF8EE3D6),
    regresoFondo: Color(0xFF10332F),
    pista: Color(0xFF8A929C),
    asignado: (texto: Color(0xFFB9CCFF), fondo: Color(0xFF1E2A4A)),
    enCamino: (texto: Color(0xFFDCC6FF), fondo: Color(0xFF2E2340)),
    recogido: (texto: Color(0xFFFFD08A), fondo: Color(0xFF3A2A10)),
    entregado: (texto: Color(0xFF9EE6BC), fondo: Color(0xFF143323)),
    novedad: (texto: Color(0xFFFFB8B0), fondo: Color(0xFF3D1A18)),
    otroEstado: (texto: Color(0xFFD5DAE0), fondo: Color(0xFF2A2F36)),
  );

  final Color fondo;
  final Color superficie;
  final Color borde;
  final Color texto;
  final Color textoSecundario;
  final Color acento;
  final Color acentoFondo;
  final Color peligro;
  final Color peligroFondo;
  final Color aviso;
  final Color avisoFondo;

  /// Regreso de un evento (el mismo verde azulado del panel).
  final Color regreso;
  final Color regresoFondo;

  /// Lo que falta de una barra de avance: se distingue (3:1) del fondo y de las tarjetas.
  final Color pista;

  final ColoresDeEstado asignado;
  final ColoresDeEstado enCamino;
  final ColoresDeEstado recogido;
  final ColoresDeEstado entregado;

  /// Novedad y cancelado.
  final ColoresDeEstado novedad;

  /// Pendiente de asignar y cualquier estado que la app no conozca.
  final ColoresDeEstado otroEstado;

  /// Texto y fondo de la etiqueta de [estado] (contraste de al menos 7:1).
  ColoresDeEstado deEstado(String estado) => switch (estado) {
    'asignado' => asignado,
    'en_camino' => enCamino,
    'recogido' => recogido,
    'entregado' => entregado,
    'novedad' || 'cancelado' => novedad,
    _ => otroEstado,
  };

  @override
  ColoresArribo copyWith({
    Color? fondo,
    Color? superficie,
    Color? borde,
    Color? texto,
    Color? textoSecundario,
    Color? acento,
    Color? acentoFondo,
    Color? peligro,
    Color? peligroFondo,
    Color? aviso,
    Color? avisoFondo,
    Color? regreso,
    Color? regresoFondo,
    Color? pista,
    ColoresDeEstado? asignado,
    ColoresDeEstado? enCamino,
    ColoresDeEstado? recogido,
    ColoresDeEstado? entregado,
    ColoresDeEstado? novedad,
    ColoresDeEstado? otroEstado,
  }) => ColoresArribo(
    fondo: fondo ?? this.fondo,
    superficie: superficie ?? this.superficie,
    borde: borde ?? this.borde,
    texto: texto ?? this.texto,
    textoSecundario: textoSecundario ?? this.textoSecundario,
    acento: acento ?? this.acento,
    acentoFondo: acentoFondo ?? this.acentoFondo,
    peligro: peligro ?? this.peligro,
    peligroFondo: peligroFondo ?? this.peligroFondo,
    aviso: aviso ?? this.aviso,
    avisoFondo: avisoFondo ?? this.avisoFondo,
    regreso: regreso ?? this.regreso,
    regresoFondo: regresoFondo ?? this.regresoFondo,
    pista: pista ?? this.pista,
    asignado: asignado ?? this.asignado,
    enCamino: enCamino ?? this.enCamino,
    recogido: recogido ?? this.recogido,
    entregado: entregado ?? this.entregado,
    novedad: novedad ?? this.novedad,
    otroEstado: otroEstado ?? this.otroEstado,
  );

  @override
  ColoresArribo lerp(ColoresArribo? other, double t) {
    if (other == null) return this;
    Color c(Color a, Color b) => Color.lerp(a, b, t)!;
    ColoresDeEstado e(ColoresDeEstado a, ColoresDeEstado b) =>
        (texto: c(a.texto, b.texto), fondo: c(a.fondo, b.fondo));
    return ColoresArribo(
      fondo: c(fondo, other.fondo),
      superficie: c(superficie, other.superficie),
      borde: c(borde, other.borde),
      texto: c(texto, other.texto),
      textoSecundario: c(textoSecundario, other.textoSecundario),
      acento: c(acento, other.acento),
      acentoFondo: c(acentoFondo, other.acentoFondo),
      peligro: c(peligro, other.peligro),
      peligroFondo: c(peligroFondo, other.peligroFondo),
      aviso: c(aviso, other.aviso),
      avisoFondo: c(avisoFondo, other.avisoFondo),
      regreso: c(regreso, other.regreso),
      regresoFondo: c(regresoFondo, other.regresoFondo),
      pista: c(pista, other.pista),
      asignado: e(asignado, other.asignado),
      enCamino: e(enCamino, other.enCamino),
      recogido: e(recogido, other.recogido),
      entregado: e(entregado, other.entregado),
      novedad: e(novedad, other.novedad),
      otroEstado: e(otroEstado, other.otroEstado),
    );
  }
}

extension ColoresDelTema on BuildContext {
  /// Los colores de Arribo del tema vigente (claro u oscuro).
  ColoresArribo get colores => Theme.of(this).extension<ColoresArribo>() ?? ColoresArribo.claro;
}

/// Alto mínimo de los botones: más que los 48 dp de Material, para tocarlos con el pulgar.
const double altoBoton = 56;

/// Esquinas de las tarjetas.
const double radioTarjeta = 12;

/// Esquinas de los botones y de los campos de texto.
const double radioControl = 10;

/// Cuánto dura una transición dentro de una pantalla (la franja sin señal, el recuadro de estado,
/// el cambio de la tarjeta activa): 250 ms, o nada si en Android se quitaron las animaciones.
/// Todas las animaciones de la app usan esta; las transiciones entre pantallas no se tocan.
Duration duracionDeTransicion(BuildContext context) =>
    MediaQuery.disableAnimationsOf(context) ? Duration.zero : const Duration(milliseconds: 250);

/// La placa (o el VIN) en grande: la cifra de ancho fijo para leerla y compararla de un vistazo.
/// Sin color: toma el del texto del tema.
const estiloPlaca = TextStyle(
  fontSize: 30,
  fontWeight: FontWeight.w700,
  letterSpacing: 1.5,
  fontFeatures: [FontFeature.tabularFigures()],
);

/// Borde de los campos de texto: se distingue del fondo en las dos paletas.
const _bordeCampo = Color(0xFF8A929C);

/// El tema claro ([Brightness.light], el de siempre) o el oscuro.
ThemeData temaArribo([Brightness brillo = Brightness.light]) {
  final oscuro = brillo == Brightness.dark;
  final c = oscuro ? ColoresArribo.oscuro : ColoresArribo.claro;
  final esquema = oscuro
      ? ColorScheme.dark(
          primary: c.acento,
          onPrimary: const Color(0xFF0B1F4D),
          primaryContainer: c.acentoFondo,
          onPrimaryContainer: c.texto,
          secondary: c.acento,
          onSecondary: const Color(0xFF0B1F4D),
          surface: c.superficie,
          onSurface: c.texto,
          onSurfaceVariant: c.textoSecundario,
          surfaceContainerLowest: c.fondo,
          surfaceContainerLow: c.fondo,
          surfaceContainer: c.superficie,
          surfaceContainerHigh: c.superficie,
          surfaceContainerHighest: c.superficie,
          outline: _bordeCampo,
          outlineVariant: c.borde,
          error: c.peligro,
          onError: const Color(0xFF410E0B),
          // Los avisos flotantes (SnackBar) van claros sobre la pantalla oscura.
          inverseSurface: c.texto,
          onInverseSurface: c.fondo,
          inversePrimary: ColoresArribo.claro.acento,
          surfaceTint: Colors.transparent,
        )
      : ColorScheme.light(
          primary: c.acento,
          onPrimary: Colors.white,
          primaryContainer: c.acentoFondo,
          onPrimaryContainer: c.texto,
          secondary: c.acento,
          onSecondary: Colors.white,
          surface: c.superficie,
          onSurface: c.texto,
          onSurfaceVariant: c.textoSecundario,
          surfaceContainerLowest: c.superficie,
          surfaceContainerLow: c.fondo,
          surfaceContainer: c.fondo,
          surfaceContainerHigh: c.superficie,
          surfaceContainerHighest: c.superficie,
          outline: _bordeCampo,
          outlineVariant: c.borde,
          error: c.peligro,
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
      .apply(bodyColor: c.texto, displayColor: c.texto);

  const forma = RoundedRectangleBorder(
    borderRadius: BorderRadius.all(Radius.circular(radioControl)),
  );

  return base.copyWith(
    scaffoldBackgroundColor: c.fondo,
    textTheme: textos,
    extensions: [c],
    appBarTheme: AppBarTheme(
      backgroundColor: c.superficie,
      foregroundColor: c.texto,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: c.texto),
      shape: Border(bottom: BorderSide(color: c.borde)),
    ),
    cardTheme: CardThemeData(
      color: c.superficie,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: c.borde),
        borderRadius: const BorderRadius.all(Radius.circular(radioTarjeta)),
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
        foregroundColor: c.acento,
        textStyle: textos.labelLarge,
        side: BorderSide(color: c.acento, width: 1.5),
        shape: forma,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(64, 52),
        foregroundColor: c.acento,
        textStyle: textos.labelLarge,
        shape: forma,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: c.superficie,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: const OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(radioControl)),
      ),
      enabledBorder: const OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(radioControl)),
        borderSide: BorderSide(color: _bordeCampo),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: const BorderRadius.all(Radius.circular(radioControl)),
        borderSide: BorderSide(color: c.acento, width: 2),
      ),
      labelStyle: TextStyle(fontSize: 18, color: c.textoSecundario),
      floatingLabelStyle: TextStyle(fontSize: 18, color: c.acento),
      errorStyle: TextStyle(fontSize: 15, color: c.peligro),
      helperStyle: TextStyle(fontSize: 15, color: c.textoSecundario),
    ),
    dividerTheme: DividerThemeData(color: c.borde, space: 1, thickness: 1),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: c.acento),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      contentTextStyle: textos.bodyLarge?.copyWith(
        color: oscuro ? esquema.onInverseSurface : Colors.white,
      ),
    ),
  );
}
