// Sube al servidor las fotos de la cola y anota lo que responde.
//
// Reglas (docs/api-conductor.md, "Subir una foto"):
// - Una foto a la vez, de la más antigua a la más nueva, y solo las que ya se pueden subir: su
//   evento ya tuvo respuesta definitiva (ver `almacen_fotos.dart`). Los eventos no esperan a las
//   fotos.
// - `PUT` idempotente por UUID: si la subida se corta o la respuesta se pierde, se sube la foto
//   completa otra vez con el mismo UUID; el servidor responde 200 y no la duplica.
// - Sin red, o si el servidor falla, la foto queda en la cola y se reintenta con espera creciente.
// - Si el servidor la rechaza de forma definitiva (413, 409, 400, 404, 415), no se reintenta: queda
//   marcada con el motivo, a la vista del conductor, y su archivo se conserva.
// - El archivo del celular se borra solo después de que el servidor confirma la subida.
// - Cada foto se sube solo con el token de quien la tomó. Un 401 cierra la sesión y conserva la
//   cola.

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../api.dart';
import '../cola/sincronizador.dart' show esperaMaximaEnSegundoPlano, esperasDeReintento;
import '../ingreso/sesion.dart';
import 'almacen_fotos.dart';
import 'foto.dart';

/// Respuestas con las que no sirve reintentar: la misma foto daría el mismo error.
const Set<int> _rechazosDefinitivos = {400, 404, 409, 413, 415};

class SubidorDeFotos extends ChangeNotifier {
  SubidorDeFotos({
    required this.almacen,
    required this.api,
    required this.sesion,
    DateTime Function()? reloj,
    this.esperas = esperasDeReintento,
    this.esperaMaximaOculta = esperaMaximaEnSegundoPlano,
  }) : _reloj = reloj ?? DateTime.now;

  final AlmacenFotos almacen;
  final ClienteApi api;
  final Sesion sesion;
  final List<Duration> esperas;
  final Duration esperaMaximaOculta;
  final DateTime Function() _reloj;

  ResumenDeFotos _resumen = const ResumenDeFotos();
  bool _subiendo = false;
  ErrorApi? _problema;
  int _subidas = 0;

  Future<void>? _enCurso;
  Timer? _reintento;
  Duration? _esperaDelReintento;
  int _fallosSeguidos = 0;
  bool _enPrimerPlano = true;
  bool _desechado = false;

  /// Fotos del conductor de la sesión (o del último que ingresó) que aún no están en el servidor.
  int get pendientes => _resumen.pendientes;

  /// Fotos pendientes de ese servicio.
  int pendientesDe(int servicioId) => _resumen.porServicio[servicioId] ?? 0;

  /// Fotos sin subir de otros conductores: no se suben con esta sesión.
  int get ajenas => _resumen.ajenas;

  /// Fotos que el servidor rechazó y que el conductor no ha dado por vistas.
  List<FotoLocal> get conProblema => _resumen.conProblema;

  bool get subiendo => _subiendo;

  /// Por qué falló la última subida; null si salió bien o no hay nada por subir.
  ErrorApi? get problema => _problema;

  /// Cuántas fotos ha confirmado el servidor desde que abrió la app.
  int get subidas => _subidas;

  /// Cuánto falta para el reintento programado; null si no hay ninguno.
  Duration? get esperaDelReintento => _reintento == null ? null : _esperaDelReintento;

  /// Al abrir la app: borra los archivos de fotos ya confirmadas que hubieran quedado (la app
  /// murió entre confirmar y borrar) y lee cuánto hay pendiente. No usa la red.
  Future<void> cargar() async {
    await almacen.borrarArchivosSubidos(hora: _reloj());
    await releer();
  }

  /// Vuelve a leer de la base cuánto hay pendiente y qué fotos tienen problema.
  Future<void> releer() async {
    _resumen = await almacen.resumen(sesion.conductor?.id);
    _avisar();
  }

  /// Arranca la subida si la última lectura encontró fotos listas para subir. No espera a que
  /// termine ni toca la base si no hay nada.
  void despertar() {
    if (_resumen.listas > 0) unawaited(subir());
  }

  /// Sube las fotos listas del conductor de la sesión, una tras otra, hasta que no queden o hasta
  /// que una falle por la red o el servidor. Nunca hay dos subidas a la vez: si ya hay una, devuelve
  /// esa.
  Future<void> subir() => _enCurso ??= _subirTodo().whenComplete(() => _enCurso = null);

  Future<void> _subirTodo() async {
    _cancelarReintento();
    while (!_desechado) {
      final token = sesion.token;
      final conductor = sesion.conductor;
      if (sesion.estado != EstadoSesion.activa || token == null || conductor == null) return;
      final foto = await almacen.siguientePorSubir(conductor.id);
      if (foto == null) {
        if (_problema != null) {
          _problema = null;
          _avisar();
        }
        return;
      }
      if (!await _subirUna(token, foto)) return;
    }
  }

  /// Sube una foto. Devuelve true si se puede seguir con la siguiente (se subió, o quedó marcada
  /// como rechazada) y false si hay que esperar (sin red, falla del servidor o sesión cerrada).
  Future<bool> _subirUna(String token, FotoLocal foto) async {
    _subiendo = true;
    _avisar();
    try {
      if (!File(foto.ruta).existsSync()) {
        await almacen.marcarError(foto.id, 'El archivo de la foto ya no está en el celular.');
        return true;
      }
      await api.subirFoto(token, foto);
      // Primero queda anotada como subida; solo entonces se borra el archivo.
      await almacen.marcarSubida(foto.id, hora: _reloj());
      await almacen.borrarArchivosSubidos(hora: _reloj());
      _problema = null;
      _fallosSeguidos = 0;
      _subidas++;
      return true;
    } on SesionCerrada catch (error) {
      // El token ya no sirve. La cola no se toca: se sube cuando este conductor vuelva a ingresar.
      _problema = null;
      await sesion.cerrarPorServidor(error, tokenUsado: token);
      return false;
    } on ErrorDeContrato catch (error) {
      if (!_rechazosDefinitivos.contains(error.estadoHttp)) return _esperar(error);
      await almacen.marcarError(foto.id, error.detalle);
      return true;
    } on ErrorDelServidor catch (error) {
      // Un 413 sin la forma del contrato lo da un servidor intermedio con un tope más bajo: esa
      // foto tampoco pasará la próxima vez.
      if (error.estadoHttp != 413) return _esperar(error);
      await almacen.marcarError(foto.id, 'La foto pesa más de lo que el servidor recibe.');
      return true;
    } on ErrorApi catch (error) {
      // Sin red, tiempo agotado o respuesta ilegible: la foto sigue en la cola.
      return _esperar(error);
    } on FileSystemException {
      await almacen.marcarError(foto.id, 'No se pudo leer el archivo de la foto en el celular.');
      return true;
    } finally {
      _subiendo = false;
      await releer();
    }
  }

  bool _esperar(ErrorApi error) {
    _problema = error;
    _programarReintento();
    return false;
  }

  /// El conductor tocó "Entendido" en el aviso de una foto rechazada.
  Future<void> marcarVista(String id) async {
    await almacen.marcarVista(id, hora: _reloj());
    await releer();
  }

  /// La app pasó a segundo plano o volvió. Solo cambia el tope de la espera entre reintentos.
  set enPrimerPlano(bool valor) => _enPrimerPlano = valor;

  void _programarReintento() {
    _cancelarReintento();
    if (_desechado || esperas.isEmpty) return;
    final paso = _fallosSeguidos < esperas.length ? _fallosSeguidos : esperas.length - 1;
    var espera = esperas[paso];
    if (!_enPrimerPlano && _fallosSeguidos >= esperas.length) {
      // En segundo plano la espera sigue doblándose hasta su tope.
      final dobles = _fallosSeguidos - esperas.length + 1;
      espera = espera * (1 << (dobles > 10 ? 10 : dobles));
      if (espera > esperaMaximaOculta) espera = esperaMaximaOculta;
    }
    _fallosSeguidos++;
    _esperaDelReintento = espera;
    _reintento = Timer(espera, () {
      _reintento = null;
      unawaited(subir());
    });
  }

  void _cancelarReintento() {
    _reintento?.cancel();
    _reintento = null;
  }

  void _avisar() {
    if (!_desechado) notifyListeners();
  }

  @override
  void dispose() {
    _desechado = true;
    _cancelarReintento();
    super.dispose();
  }
}
