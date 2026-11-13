// Dónde se guarda el token de la API: en el almacenamiento seguro del sistema (Android Keystore),
// nunca en la base local ni en texto plano. Detrás de una interfaz para probar sin el celular.

import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class AlmacenToken {
  Future<String?> leer();
  Future<void> guardar(String token);
  Future<void> borrar();
}

class AlmacenTokenSeguro implements AlmacenToken {
  AlmacenTokenSeguro([FlutterSecureStorage? almacen])
    : _almacen = almacen ?? const FlutterSecureStorage(aOptions: AndroidOptions());

  static const _clave = 'token_api';

  final FlutterSecureStorage _almacen;

  /// Si el Keystore no puede leer el token (por ejemplo, datos restaurados de otro celular), se
  /// trata como sesión cerrada: el conductor ingresa de nuevo y nada local se pierde.
  @override
  Future<String?> leer() async {
    try {
      return await _almacen.read(key: _clave);
    } on PlatformException {
      await borrar();
      return null;
    }
  }

  @override
  Future<void> guardar(String token) => _almacen.write(key: _clave, value: token);

  @override
  Future<void> borrar() async {
    try {
      await _almacen.delete(key: _clave);
    } on PlatformException {
      // Si ni siquiera se puede borrar, no hay nada más que hacer: el token ya no se puede leer.
    }
  }
}
