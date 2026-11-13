// La lista de asignaciones que ve el conductor. Siempre se muestra desde la base local; el
// servidor solo la refresca. Sin señal, el conductor ve lo último guardado y un aviso discreto.

import 'package:flutter/foundation.dart';

import '../api.dart';
import '../ingreso/sesion.dart';
import 'almacen_asignaciones.dart';
import 'servicio.dart';

class ListaAsignaciones extends ChangeNotifier {
  ListaAsignaciones({
    required this.almacen,
    required this.api,
    required this.sesion,
    DateTime Function()? reloj,
  }) : _reloj = reloj ?? DateTime.now;

  final AlmacenAsignaciones almacen;
  final ClienteApi api;
  final Sesion sesion;
  final DateTime Function() _reloj;

  List<Servicio> _servicios = const [];
  ConfiguracionApp? _configuracion;
  DateTime? _ultimaActualizacion;
  bool _cargada = false;
  bool _actualizando = false;
  ErrorApi? _problema;
  Future<void>? _enCurso;

  /// Los servicios en el orden de la ronda.
  List<Servicio> get servicios => _servicios;

  ConfiguracionApp? get configuracion => _configuracion;

  /// Última vez que el servidor confirmó la lista (200 o 304), en UTC. null si nunca.
  DateTime? get ultimaActualizacion => _ultimaActualizacion;

  /// Ya se leyó la base local (aunque esté vacía).
  bool get cargada => _cargada;

  bool get actualizando => _actualizando;

  /// Por qué falló la última actualización; null si salió bien o aún no se intenta.
  ErrorApi? get problema => _problema;

  bool get sinConexion => _problema is ErrorDeRed;

  Servicio? servicio(int id) {
    for (final s in _servicios) {
      if (s.id == id) return s;
    }
    return null;
  }

  /// Lee la base local. No usa la red.
  Future<void> cargarLocal() async {
    await _releer();
    _cargada = true;
    notifyListeners();
  }

  /// Pide la lista al servidor con el último ETag y la guarda. Si ya hay una actualización en
  /// curso, espera esa misma (abrir la app, volver a primer plano y deslizar pueden coincidir).
  Future<void> actualizar() => _enCurso ??= _actualizar().whenComplete(() => _enCurso = null);

  Future<void> _actualizar() async {
    final token = sesion.token;
    if (token == null) return;
    _actualizando = true;
    notifyListeners();
    try {
      final respuesta = await api.asignaciones(token, etag: await almacen.etag());
      // Si mientras tanto se cerró la sesión o ingresó otro conductor, esta respuesta ya no aplica.
      if (sesion.token != token) return;
      final ahora = _reloj().toUtc();
      switch (respuesta) {
        case AsignacionesSinCambios():
          await almacen.confirmarSinCambios(ahora);
        case AsignacionesNuevas(:final servicios, :final configuracion, :final etag):
          await almacen.reemplazar(
            servicios: servicios,
            configuracion: configuracion,
            etag: etag,
            hora: ahora,
          );
      }
      _problema = null;
      await _releer();
    } on SesionCerrada catch (error) {
      _problema = null;
      await sesion.cerrarPorServidor(error, tokenUsado: token);
    } on ErrorApi catch (error) {
      _problema = error;
    } finally {
      _actualizando = false;
      notifyListeners();
    }
  }

  Future<void> _releer() async {
    _servicios = await almacen.leer();
    _configuracion = await almacen.configuracion();
    _ultimaActualizacion = await almacen.ultimaActualizacion();
  }
}
