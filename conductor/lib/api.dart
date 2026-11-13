// Cliente de la API del conductor (docs/api-conductor.md, contrato versión 1).
//
// Cada llamada tiene un tiempo máximo corto y nunca bloquea la interfaz: devuelve un Future y, si
// algo falla, lanza un ErrorApi que la pantalla convierte en un mensaje en español. La app decide
// por el código `error` del servidor; `detalle` es el texto para el conductor.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

import 'asignaciones/servicio.dart';

/// Dirección del servidor, sin `/api/v1`. Se cambia sin tocar el código al compilar o correr:
/// `flutter run --dart-define=ARRIBO_API=https://arribo.ejemplo.co`. Por defecto, el backend de
/// desarrollo en el PC, al que el celular llega por USB con `adb reverse tcp:8000 tcp:8000`.
const String servidorConfigurado = String.fromEnvironment(
  'ARRIBO_API',
  defaultValue: 'http://127.0.0.1:8000',
);

/// Tiempo máximo de una petición completa. El ingreso tarda cerca de un segundo en el servidor
/// (revisa el hash del PIN); la lista, mucho menos.
const Duration tiempoMaximoPorDefecto = Duration(seconds: 15);

/// Tiempo máximo para establecer la conexión. Sin señal, falla rápido en vez de dejar al
/// conductor esperando.
const Duration tiempoMaximoConexion = Duration(seconds: 8);

/// Cliente HTTP para el celular, con tiempo máximo de conexión.
http.Client crearClienteHttp() => IOClient(HttpClient()..connectionTimeout = tiempoMaximoConexion);

// ---------- errores ----------

/// Todo lo que puede salir mal en una llamada a la API.
sealed class ErrorApi implements Exception {
  const ErrorApi();

  /// Texto en español para el conductor.
  String get mensaje;

  @override
  String toString() => '$runtimeType: $mensaje';
}

/// Sin señal, sin servidor o tiempo agotado. Lo local sigue sirviendo.
final class ErrorDeRed extends ErrorApi {
  const ErrorDeRed([this.causa]);

  final Object? causa;

  @override
  String get mensaje => 'No hay conexión con el servidor. Revise la señal e intente de nuevo.';
}

/// El servidor falló (500 u otra respuesta sin la forma del contrato). Se reintenta más tarde.
final class ErrorDelServidor extends ErrorApi {
  const ErrorDelServidor(this.estadoHttp);

  final int estadoHttp;

  @override
  String get mensaje => 'El servidor tuvo un problema. Intente de nuevo en un momento.';
}

/// Una respuesta correcta que la app no pudo leer (falta un campo o cambió su tipo). Es un error
/// de la app o del servidor: nada de esa respuesta se guarda.
final class RespuestaInesperada extends ErrorApi {
  const RespuestaInesperada(this.causa);

  final Object causa;

  @override
  String get mensaje => 'El servidor respondió algo que la app no entiende. Avise a logística.';
}

/// Un error con la forma del contrato: `{"version": 1, "error": ..., "detalle": ...}`.
final class ErrorDeContrato extends ErrorApi {
  const ErrorDeContrato({
    required this.estadoHttp,
    required this.codigo,
    required this.detalle,
    this.campos = const {},
    this.reintentarEn,
  });

  final int estadoHttp;

  /// El código `error` del contrato (`credenciales_invalidas`, `demasiados_intentos`...).
  final String codigo;

  /// El texto del servidor para el conductor.
  final String detalle;

  /// Errores por campo, solo en `datos_invalidos`.
  final Map<String, List<String>> campos;

  /// Solo en `demasiados_intentos`: cuánto falta para poder intentar de nuevo.
  final Duration? reintentarEn;

  @override
  String get mensaje => detalle;
}

/// Un 401 en una petición con token: el token ya no sirve (revocado, conductor inhabilitado o
/// sesión cerrada). La app vuelve a la pantalla de ingreso y muestra `detalle`.
final class SesionCerrada extends ErrorApi {
  const SesionCerrada({required this.codigo, required this.detalle});

  final String codigo;
  final String detalle;

  @override
  String get mensaje => detalle;
}

// ---------- respuestas ----------

class Conductor {
  const Conductor({required this.id, required this.nombre, required this.celular});

  final int id;
  final String nombre;
  final String celular;

  factory Conductor.desdeJson(Map<String, Object?> json) {
    final id = json['id'];
    final nombre = json['nombre'];
    final celular = json['celular'];
    if (id is! int || nombre is! String || celular is! String) {
      throw FormatException('Conductor inesperado: $json');
    }
    return Conductor(id: id, nombre: nombre, celular: celular);
  }

  Map<String, Object?> aJson() => {'id': id, 'nombre': nombre, 'celular': celular};
}

class Ingreso {
  const Ingreso({required this.token, required this.conductor});

  final String token;
  final Conductor conductor;
}

sealed class RespuestaAsignaciones {
  const RespuestaAsignaciones();
}

/// 304: nada cambió desde el ETag que mandó la app.
final class AsignacionesSinCambios extends RespuestaAsignaciones {
  const AsignacionesSinCambios();
}

/// 200: la lista completa, en orden de ronda.
final class AsignacionesNuevas extends RespuestaAsignaciones {
  const AsignacionesNuevas({
    required this.configuracion,
    required this.servicios,
    required this.etag,
  });

  final ConfiguracionApp configuracion;
  final List<Servicio> servicios;
  final String? etag;
}

// ---------- cliente ----------

class ClienteApi {
  ClienteApi({
    String servidor = servidorConfigurado,
    http.Client? cliente,
    this.tiempoMaximo = tiempoMaximoPorDefecto,
  }) : servidor = servidor.endsWith('/') ? servidor.substring(0, servidor.length - 1) : servidor,
       _http = cliente ?? crearClienteHttp();

  /// Dirección del servidor, sin barra final.
  final String servidor;
  final Duration tiempoMaximo;
  final http.Client _http;

  Uri _ruta(String ruta) => Uri.parse('$servidor/api/v1/$ruta');

  /// `POST /ingresar/`. Un 401 aquí es `credenciales_invalidas` o `conductor_no_habilitado` y se
  /// lanza como ErrorDeContrato (no como SesionCerrada).
  Future<Ingreso> ingresar({
    required String celular,
    required String pin,
    required String dispositivoId,
    String? dispositivoNombre,
  }) async {
    final respuesta = await _enviar(
      () => _http.post(
        _ruta('ingresar/'),
        headers: _cabeceras(conCuerpo: true),
        body: jsonEncode({
          'celular': celular,
          'pin': pin,
          'dispositivo_id': dispositivoId,
          'dispositivo_nombre': ?dispositivoNombre,
        }),
      ),
    );
    if (respuesta.statusCode != 200) throw _error(respuesta, conToken: false);
    return _leer(respuesta, (json) {
      final token = json['token'];
      final conductor = json['conductor'];
      if (token is! String || token.isEmpty || conductor is! Map<String, Object?>) {
        throw FormatException('Ingreso inesperado: $json');
      }
      return Ingreso(token: token, conductor: Conductor.desdeJson(conductor));
    });
  }

  /// `POST /salir/`. Un 401 significa que la sesión ya estaba cerrada: también cuenta como salida.
  Future<void> salir(String token) async {
    final respuesta = await _enviar(
      () => _http.post(_ruta('salir/'), headers: _cabeceras(token: token)),
    );
    if (respuesta.statusCode == 204 || respuesta.statusCode == 401) return;
    throw _error(respuesta, conToken: true);
  }

  /// `GET /asignaciones/`. Con [etag], el servidor responde 304 si nada cambió.
  Future<RespuestaAsignaciones> asignaciones(String token, {String? etag}) async {
    final respuesta = await _enviar(
      () => _http.get(
        _ruta('asignaciones/'),
        headers: {
          ..._cabeceras(token: token),
          'If-None-Match': ?etag,
        },
      ),
    );
    if (respuesta.statusCode == 304) return const AsignacionesSinCambios();
    if (respuesta.statusCode != 200) throw _error(respuesta, conToken: true);
    return _leer(respuesta, (json) {
      final configuracion = json['configuracion'];
      final servicios = json['servicios'];
      if (configuracion is! Map<String, Object?> || servicios is! List<Object?>) {
        throw FormatException('Lista inesperada: $json');
      }
      return AsignacionesNuevas(
        configuracion: ConfiguracionApp.desdeJson(configuracion),
        servicios: [
          for (final s in servicios)
            if (s is Map<String, Object?>)
              Servicio.desdeJson(s)
            else
              throw FormatException('Servicio inesperado: $s'),
        ],
        etag: respuesta.headers['etag'],
      );
    });
  }

  void cerrar() => _http.close();

  Map<String, String> _cabeceras({String? token, bool conCuerpo = false}) => {
    'Accept': 'application/json',
    if (conCuerpo) 'Content-Type': 'application/json; charset=utf-8',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<http.Response> _enviar(Future<http.Response> Function() peticion) async {
    try {
      return await peticion().timeout(tiempoMaximo);
    } on TimeoutException catch (e) {
      throw ErrorDeRed(e);
    } on SocketException catch (e) {
      throw ErrorDeRed(e);
    } on HandshakeException catch (e) {
      throw ErrorDeRed(e);
    } on HttpException catch (e) {
      throw ErrorDeRed(e);
    } on http.ClientException catch (e) {
      throw ErrorDeRed(e);
    }
  }

  T _leer<T>(http.Response respuesta, T Function(Map<String, Object?> json) leer) {
    try {
      final json = jsonDecode(utf8.decode(respuesta.bodyBytes));
      if (json is! Map<String, Object?>) throw FormatException('Se esperaba un objeto: $json');
      return leer(json);
    } on FormatException catch (e) {
      throw RespuestaInesperada(e);
    }
  }

  ErrorApi _error(http.Response respuesta, {required bool conToken}) {
    final estado = respuesta.statusCode;
    Map<String, Object?>? json;
    try {
      final decodificado = jsonDecode(utf8.decode(respuesta.bodyBytes));
      if (decodificado is Map<String, Object?>) json = decodificado;
    } on FormatException {
      json = null;
    }
    final codigo = json?['error'];
    final detalle = json?['detalle'];
    if (json == null || codigo is! String) {
      // Sin la forma del contrato: un 500, un proxy, o una ruta que no existe (404 de Django).
      if (estado == 401 && conToken) {
        return const SesionCerrada(
          codigo: 'no_autenticado',
          detalle: 'Su sesión se cerró. Ingrese de nuevo.',
        );
      }
      return ErrorDelServidor(estado);
    }
    final texto = detalle is String && detalle.trim().isNotEmpty
        ? detalle
        : 'El servidor rechazó la petición ($codigo).';
    if (estado == 401 && conToken) return SesionCerrada(codigo: codigo, detalle: texto);
    return ErrorDeContrato(
      estadoHttp: estado,
      codigo: codigo,
      detalle: texto,
      campos: _campos(json['campos']),
      reintentarEn: _reintentarEn(json['reintentar_en'], respuesta.headers['retry-after']),
    );
  }

  static Map<String, List<String>> _campos(Object? campos) {
    if (campos is! Map<String, Object?>) return const {};
    return {
      for (final MapEntry(:key, :value) in campos.entries)
        key: value is List ? [for (final m in value) '$m'] : ['$value'],
    };
  }

  static Duration? _reintentarEn(Object? cuerpo, String? cabecera) {
    final segundos = cuerpo is int ? cuerpo : int.tryParse(cabecera ?? '');
    return segundos == null || segundos < 0 ? null : Duration(seconds: segundos);
  }
}
