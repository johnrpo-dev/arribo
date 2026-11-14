// La cámara del celular para las fotos de evidencia.
//
// Se usa la cámara del sistema (image_picker), no una vista de cámara dentro de la app: así la
// cámara corre en otro proceso y la app no retiene en memoria ni la vista previa ni la foto. El
// costo es que, en un celular con poca memoria, Android puede matar la app mientras la cámara está
// abierta; por eso la pantalla se guarda en la base local antes de abrirla, y la foto que quedó
// sin entregar se recupera al volver ([Camara.recuperarFotoPerdida]).
//
// La foto se achica y se comprime en disco antes de llegar a Dart: el plugin lo hace en código
// nativo, en un hilo aparte, decodificando ya reducida (`inSampleSize`), y entrega solo la ruta
// del JPEG resultante. Dart nunca lee los bytes de la foto.

import 'dart:io';

import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

/// Lado más largo de la foto comprimida, en píxeles. Suficiente para leer una placa o ver un
/// rayón, y con [calidadJpeg] deja la foto en unos cientos de KB: muy por debajo de los 5 MB que
/// acepta el servidor.
const double ladoMaximoFoto = 1600;

/// Calidad del JPEG comprimido (0 a 100).
const int calidadJpeg = 80;

/// La cámara no se pudo abrir o falló. [mensaje] es el texto para el conductor.
class ErrorDeCamara implements Exception {
  const ErrorDeCamara(this.mensaje);

  final String mensaje;

  @override
  String toString() => 'ErrorDeCamara: $mensaje';
}

abstract class Camara {
  /// Abre la cámara y espera a que el conductor tome la foto. Devuelve la ruta del JPEG ya
  /// comprimido, en un archivo temporal de la app, o null si el conductor canceló.
  Future<String?> tomarFoto();

  /// La foto de una llamada a [tomarFoto] que no alcanzó a responder porque Android mató la app
  /// con la cámara abierta. Devuelve su ruta (ya comprimida) o null si no hay ninguna. Cada foto
  /// perdida se entrega una sola vez.
  Future<String?> recuperarFotoPerdida();
}

class CamaraDelSistema implements Camara {
  CamaraDelSistema([ImagePicker? selector]) : _selector = selector ?? ImagePicker();

  final ImagePicker _selector;

  @override
  Future<String?> tomarFoto() async {
    try {
      final foto = await _selector.pickImage(
        source: ImageSource.camera,
        maxWidth: ladoMaximoFoto,
        maxHeight: ladoMaximoFoto,
        imageQuality: calidadJpeg,
        requestFullMetadata: false,
      );
      return foto == null ? null : _sinOriginal(foto.path);
    } on PlatformException catch (error) {
      throw ErrorDeCamara(_mensaje(error));
    } on MissingPluginException {
      throw const ErrorDeCamara('Este celular no tiene cámara disponible para la app.');
    }
  }

  @override
  Future<String?> recuperarFotoPerdida() async {
    try {
      final perdida = await _selector.retrieveLostData();
      if (perdida.isEmpty) return null;
      final foto = perdida.file ?? perdida.files?.firstOrNull;
      return foto == null ? null : _sinOriginal(foto.path);
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  /// El plugin deja dos archivos en la caché de la app: el original de la cámara (varios MB) y el
  /// comprimido, `scaled_<original>`. Solo sirve el comprimido: el original se borra para que no
  /// ocupe espacio.
  String _sinOriginal(String ruta) {
    final archivo = File(ruta);
    final nombre = archivo.uri.pathSegments.last;
    const prefijo = 'scaled_';
    if (nombre.startsWith(prefijo)) {
      try {
        final original = File('${archivo.parent.path}/${nombre.substring(prefijo.length)}');
        if (original.existsSync()) original.deleteSync();
      } on FileSystemException {
        // Queda en la caché; Android la vacía cuando necesita espacio.
      }
    }
    return ruta;
  }

  static String _mensaje(PlatformException error) => switch (error.code) {
    'camera_access_denied' =>
      'La app no tiene permiso para usar la cámara. Actívelo en los ajustes del celular.',
    'no_available_camera' => 'No se encontró una cámara en este celular.',
    _ => 'No se pudo abrir la cámara. Intente de nuevo.',
  };
}
