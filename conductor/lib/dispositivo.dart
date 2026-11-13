// Nombre del celular para reconocerlo en el admin (`dispositivo_nombre` del contrato), por
// ejemplo "Motorola moto g32". Lo da MainActivity.kt por un canal propio, sin dependencias.

import 'package:flutter/services.dart';

const _canal = MethodChannel('co.arribo/dispositivo');

/// El nombre del celular, o null si no se puede saber (el campo es opcional en el contrato).
Future<String?> nombreDelDispositivo() async {
  try {
    final nombre = (await _canal.invokeMethod<String>('nombre'))?.trim();
    if (nombre == null || nombre.isEmpty) return null;
    // El contrato admite hasta 100 caracteres.
    return nombre.length > 100 ? nombre.substring(0, 100) : nombre;
  } on MissingPluginException {
    return null;
  } on PlatformException {
    return null;
  }
}
