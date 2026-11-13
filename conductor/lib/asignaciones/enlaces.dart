// Enlaces de un toque: llamar al contacto y abrir la dirección en Google Maps o Waze.
//
// Se usan enlaces https universales: Android los abre en la app de Maps o de Waze si está
// instalada y, si no, en el navegador. Llamar abre el marcador del teléfono con el número escrito
// (no llama solo ni pide el permiso de llamadas).

import 'package:url_launcher/url_launcher.dart';

import 'servicio.dart';

/// Abre un enlace fuera de la app. Devuelve false si ninguna app lo pudo abrir.
typedef AbrirEnlace = Future<bool> Function(Uri enlace);

Future<bool> abrirEnlaceExterno(Uri enlace) async {
  try {
    return await launchUrl(enlace, mode: LaunchMode.externalApplication);
  } on Exception {
    return false;
  }
}

typedef Coordenadas = ({double latitud, double longitud});

/// `tel:` con el número, o null si no hay teléfono.
Uri? enlaceLlamar(String? telefono) {
  final numero = telefono?.replaceAll(RegExp(r'[^0-9+]'), '') ?? '';
  return numero.isEmpty ? null : Uri(scheme: 'tel', path: numero);
}

/// Google Maps: coordenadas si la ubicación las trae; si no, el enlace que escribió logística
/// (por ejemplo, uno corto de maps.app.goo.gl); si no, la dirección como búsqueda.
Uri? enlaceGoogleMaps(Lugar lugar) {
  final coordenadas = coordenadasDe(lugar.ubicacion);
  if (coordenadas != null) {
    return _busquedaGoogle('${coordenadas.latitud},${coordenadas.longitud}');
  }
  final web = _enlaceWeb(lugar.ubicacion);
  if (web != null) return web;
  final direccion = lugar.direccion;
  return direccion == null ? null : _busquedaGoogle(direccion);
}

/// Waze: coordenadas si la ubicación las trae; si no, la dirección como búsqueda. Un enlace de
/// Google sin coordenadas no le sirve a Waze.
Uri? enlaceWaze(Lugar lugar) {
  final coordenadas = coordenadasDe(lugar.ubicacion);
  if (coordenadas != null) {
    return Uri.https('waze.com', '/ul', {
      'll': '${coordenadas.latitud},${coordenadas.longitud}',
      'navigate': 'yes',
    });
  }
  final direccion = lugar.direccion;
  return direccion == null
      ? null
      : Uri.https('waze.com', '/ul', {'q': direccion, 'navigate': 'yes'});
}

Uri _busquedaGoogle(String consulta) =>
    Uri.https('www.google.com', '/maps/search/', {'api': '1', 'query': consulta});

/// Solo enlaces http o https: nunca otros esquemas que vengan escritos en la ubicación.
Uri? _enlaceWeb(String? ubicacion) {
  if (ubicacion == null) return null;
  final enlace = Uri.tryParse(ubicacion.trim());
  if (enlace == null || enlace.host.isEmpty) return null;
  return enlace.scheme == 'https' || enlace.scheme == 'http' ? enlace : null;
}

final _coordenadasSueltas = RegExp(
  r'^(?:geo:)?\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*(?:[?;].*)?$',
);
final _coordenadasEnEnlace = RegExp(
  r'(?:[@]|[?&](?:q|query|ll|destination|daddr)=)(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)',
);

/// Coordenadas escritas como "6.2101,-75.5712", "geo:6.2101,-75.5712" o dentro de un enlace de
/// mapas ("...@6.2101,-75.5712,17z" o "...?q=6.2101,-75.5712"). null si no hay o no son válidas.
Coordenadas? coordenadasDe(String? ubicacion) {
  if (ubicacion == null) return null;
  String texto;
  try {
    texto = Uri.decodeFull(ubicacion.trim());
  } on ArgumentError {
    texto = ubicacion.trim();
  }
  final coincidencia =
      _coordenadasSueltas.firstMatch(texto) ?? _coordenadasEnEnlace.firstMatch(texto);
  if (coincidencia == null) return null;
  final latitud = double.parse(coincidencia.group(1)!);
  final longitud = double.parse(coincidencia.group(2)!);
  if (latitud.abs() > 90 || longitud.abs() > 180) return null;
  return (latitud: latitud, longitud: longitud);
}
