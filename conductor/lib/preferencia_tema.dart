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

  /// Lee lo guardado antes de mostrar la app, para que no aparezca un instante con otro tema.
  static Future<PreferenciaTema> cargar(BaseLocal base) async =>
      PreferenciaTema(base, _modoDe(await base.leerPreferencia(Preferencia.tema)));

  /// Vuelve a leer lo guardado (cuando la app arranca sin haberlo cargado antes).
  Future<void> recargar() async {
    final guardado = _modoDe(await _base.leerPreferencia(Preferencia.tema));
    if (!_elegido) value = guardado;
  }

  /// Aplica [modo] de inmediato y lo guarda.
  Future<void> elegir(ThemeMode modo) async {
    _elegido = true;
    value = modo;
    await _base.escribirPreferencia(Preferencia.tema, _datoDe(modo));
  }
}
