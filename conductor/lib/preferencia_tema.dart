// El tema que eligió el conductor: automático (como el teléfono), claro u oscuro. Se guarda en la
// base local (tabla preferencias) y se aplica de inmediato, sin reiniciar la app.

import 'package:material_ui/material_ui.dart';

import 'base_local.dart';

/// Las opciones, en el orden en que se ofrecen, con su nombre para el conductor.
const opcionesDeTema = [
  (modo: ThemeMode.system, nombre: 'Automático (como el teléfono)'),
  (modo: ThemeMode.light, nombre: 'Claro'),
  (modo: ThemeMode.dark, nombre: 'Oscuro'),
];

/// Cómo se guarda cada modo en la base.
String _datoDe(ThemeMode modo) => switch (modo) {
  ThemeMode.system => 'automatico',
  ThemeMode.light => 'claro',
  ThemeMode.dark => 'oscuro',
};

/// Lo guardado; automático si no hay nada o no se reconoce.
ThemeMode _modoDe(String? dato) => switch (dato) {
  'claro' => ThemeMode.light,
  'oscuro' => ThemeMode.dark,
  _ => ThemeMode.system,
};

class PreferenciaTema extends ValueNotifier<ThemeMode> {
  PreferenciaTema(this._base, [super.value = ThemeMode.system]);

  final BaseLocal _base;

  /// El conductor ya eligió en esta sesión de la app: lo leído después no lo pisa.
  bool _elegido = false;

  /// La app ya no la usa: lo que llegue tarde de la base no se aplica.
  bool _desechada = false;

  /// Lee lo guardado antes de mostrar la app, para que no aparezca un instante con otro tema. Si
  /// la base no responde, la app arranca igual siguiendo al teléfono.
  static Future<PreferenciaTema> cargar(BaseLocal base) async =>
      PreferenciaTema(base, await _leer(base) ?? ThemeMode.system);

  /// Lo guardado, o null si no se pudo leer.
  static Future<ThemeMode?> _leer(BaseLocal base) async {
    try {
      return _modoDe(await base.leerPreferencia(Preferencia.tema));
    } catch (error) {
      debugPrint('No se pudo leer el tema guardado; sigue al teléfono ($error).');
      return null;
    }
  }

  /// Vuelve a leer lo guardado (cuando la app arranca sin haberlo cargado antes).
  Future<void> recargar() async {
    final guardado = await _leer(_base);
    if (guardado != null && !_elegido && !_desechada) value = guardado;
  }

  /// Aplica [modo] de inmediato y lo guarda. Si no se puede guardar, queda aplicado mientras la
  /// app siga abierta: el conductor no recibe un error por esto.
  Future<void> elegir(ThemeMode modo) async {
    _elegido = true;
    value = modo;
    try {
      await _base.escribirPreferencia(Preferencia.tema, _datoDe(modo));
    } catch (error) {
      debugPrint('No se pudo guardar el tema elegido; queda aplicado sin guardar ($error).');
    }
  }

  @override
  void dispose() {
    _desechada = true;
    super.dispose();
  }
}
