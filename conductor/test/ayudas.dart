// Utilidades de las pruebas: base SQLite real (ffi, sin celular), token en memoria, servidor falso
// y respuestas de ejemplo con la forma del contrato (docs/api-conductor.md).

import 'dart:convert';
import 'dart:io';
import 'dart:ui' show Size;

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/ingreso/almacen_token.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Sin aislado aparte: las consultas terminan en microtareas y funcionan también dentro de
/// testWidgets (reloj falso).
DatabaseFactory get fabricaDePrueba {
  sqfliteFfiInit();
  return databaseFactoryFfiNoIsolate;
}

/// Una base local en un archivo temporal propio (se borra al final de la prueba con [cerrar]).
class BaseDePrueba {
  BaseDePrueba._(this.carpeta, this.ruta, this.base);

  final Directory carpeta;
  final String ruta;
  BaseLocal base;

  static Future<BaseDePrueba> crear() async {
    final carpeta = await Directory.systemTemp.createTemp('arribo_prueba_');
    final ruta = '${carpeta.path}/$nombreArchivoBase';
    final base = await BaseLocal.abrir(fabricaDePrueba, ruta);
    return BaseDePrueba._(carpeta, ruta, base);
  }

  /// Cierra y vuelve a abrir el mismo archivo, como si el sistema hubiera matado la app.
  Future<BaseLocal> reabrir() async {
    await base.cerrar();
    base = await BaseLocal.abrir(fabricaDePrueba, ruta);
    return base;
  }

  Future<void> cerrar() async {
    await base.cerrar();
    await carpeta.delete(recursive: true);
  }
}

class AlmacenTokenEnMemoria implements AlmacenToken {
  AlmacenTokenEnMemoria([this.token]);

  String? token;

  @override
  Future<String?> leer() async => token;

  @override
  Future<void> guardar(String token) async => this.token = token;

  @override
  Future<void> borrar() async => token = null;
}

/// Una petición que recibió el servidor falso.
class PeticionRecibida {
  PeticionRecibida(this.metodo, this.url, this.cabeceras, this.cuerpo);

  final String metodo;
  final Uri url;
  final Map<String, String> cabeceras;
  final String cuerpo;

  Map<String, Object?> get json => jsonDecode(cuerpo) as Map<String, Object?>;
}

/// Servidor falso: responde con [responder] y anota cada petición.
class ServidorFalso {
  ServidorFalso(this.responder);

  Future<http.Response> Function(PeticionRecibida peticion) responder;
  final List<PeticionRecibida> peticiones = [];

  http.Client get cliente => MockClient((request) async {
    final peticion = PeticionRecibida(request.method, request.url, request.headers, request.body);
    peticiones.add(peticion);
    return responder(peticion);
  });

  ClienteApi api({Duration tiempoMaximo = const Duration(seconds: 2)}) =>
      ClienteApi(servidor: 'http://servidor.prueba', cliente: cliente, tiempoMaximo: tiempoMaximo);
}

http.Response respuestaJson(
  int estado,
  Object? cuerpo, {
  Map<String, String> cabeceras = const {},
}) => http.Response.bytes(
  utf8.encode(jsonEncode(cuerpo)),
  estado,
  headers: {'content-type': 'application/json', ...cabeceras},
);

http.Response errorDelContrato(
  int estado,
  String error,
  String detalle, {
  Map<String, Object?> extra = const {},
  Map<String, String> cabeceras = const {},
}) => respuestaJson(estado, {
  'version': 1,
  'error': error,
  'detalle': detalle,
  ...extra,
}, cabeceras: cabeceras);

Map<String, Object?> conductorJson({int id = 3, String nombre = 'Ana Gómez'}) => {
  'id': id,
  'nombre': nombre,
  'celular': '3001234567',
};

http.Response ingresoCorrecto({
  String token = 'token-ana',
  int conductorId = 3,
  String nombre = 'Ana Gómez',
}) => respuestaJson(200, {
  'version': 1,
  'token': token,
  'conductor': conductorJson(id: conductorId, nombre: nombre),
});

/// Un servicio como lo manda GET /asignaciones/ (el ejemplo del contrato).
Map<String, Object?> servicioJson({
  int id = 41,
  int? ordenRonda = 1,
  String estado = 'asignado',
  String? placa = 'ABC123',
  String tipo = 'traslado',
}) => {
  'id': id,
  'solicitud_id': 17,
  'estado': estado,
  'estado_previo': null,
  'tipo': tipo,
  'es_regreso': false,
  'orden_ronda': ordenRonda,
  'vehiculo': {
    'placa': placa,
    'vin': '1HGCM82633A004352',
    'marca': 'Mazda',
    'linea': 'CX-30',
    'color': 'Rojo',
  },
  'origen': {
    'direccion': 'Calle 10 # 43-20, El Poblado',
    'ubicacion': 'https://maps.app.goo.gl/abc123',
    'contacto': {'nombre': 'Portería Autos del Valle', 'telefono': '6044445566'},
  },
  'destino': {
    'direccion': 'Carrera 70 # 1-50, Belén',
    'ubicacion': null,
    'contacto': {'nombre': 'Taller Belén', 'telefono': '3102223344'},
  },
  'referencia_externa': 'SIN-4471',
  'programada_para': '2026-11-20T19:30:00Z',
  'grua': {'id': 2, 'placa': 'GRU001', 'capacidad': 1},
  'a_bordo': false,
};

Map<String, Object?> listaJson(List<Map<String, Object?>> servicios, {int minimoFotos = 4}) => {
  'version': 1,
  'configuracion': {'minimo_fotos': minimoFotos, 'momento_placa_vin': 'recoger'},
  'servicios': servicios,
};

http.Response listaCorrecta(List<Map<String, Object?>> servicios, {String etag = '"e1"'}) =>
    respuestaJson(200, listaJson(servicios), cabeceras: {'etag': etag});

/// Un celular de gama media (360 × 800 dp) con el texto del sistema al 200 %.
void celularConTextoGrande(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3;
  tester.platformDispatcher.textScaleFactorTestValue = 2;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
}

/// Sin señal: el cliente HTTP falla antes de llegar al servidor.
Never sinSenal() => throw const SocketException('Network is unreachable');
