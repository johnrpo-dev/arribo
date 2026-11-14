// La lista de asignaciones que ve el conductor. Siempre se muestra desde la base local; el
// servidor solo la refresca. Sin señal, el conductor ve lo último guardado y un aviso discreto.
//
// El estado de cada servicio es el que confirmó el servidor más los toques del conductor que aún no
// se han enviado (la cola de eventos): un toque se ve de inmediato, marcado como pendiente.

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api.dart';
import '../cola/cola_eventos.dart';
import '../cola/evento.dart';
import '../cola/fila.dart';
import '../cola/sincronizador.dart';
import '../ingreso/sesion.dart';
import 'almacen_asignaciones.dart';
import 'estados.dart';
import 'servicio.dart';

class ListaAsignaciones extends ChangeNotifier {
  ListaAsignaciones({
    required this.almacen,
    required this.api,
    required this.sesion,
    Sincronizador? sincronizador,
    DateTime Function()? reloj,
  }) : _reloj = reloj ?? DateTime.now,
       sincronizador =
           sincronizador ??
           Sincronizador(cola: ColaEventos(almacen.base), api: api, sesion: sesion, reloj: reloj) {
    _enviosVistos = this.sincronizador.enviosCorrectos;
    this.sincronizador.addListener(_alCambiarLaCola);
  }

  final AlmacenAsignaciones almacen;
  final ClienteApi api;
  final Sesion sesion;

  /// Quien envía la cola de eventos. La lista le pide enviar antes de refrescarse y vuelve a leer
  /// la base cada vez que la cola cambia.
  final Sincronizador sincronizador;
  final DateTime Function() _reloj;

  List<Servicio> _servicios = const [];
  Map<int, int> _pendientes = const {};
  ConfiguracionApp? _configuracion;
  DateTime? _ultimaActualizacion;
  bool _cargada = false;
  bool _actualizando = false;
  ErrorApi? _problema;
  Future<void>? _enCurso;
  final Fila _relecturas = Fila();
  int _enviosVistos = 0;

  /// Los servicios en el orden de la ronda, con el estado que ve el conductor: el confirmado por
  /// el servidor más sus toques pendientes por enviar.
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

  /// Cuántos toques de ese servicio están pendientes por enviar.
  int pendientesDe(int servicioId) => _pendientes[servicioId] ?? 0;

  /// Lee la base local. No usa la red.
  Future<void> cargarLocal() async {
    await sincronizador.cargar();
    await _recargar();
    _cargada = true;
    notifyListeners();
  }

  /// Un toque del conductor en un botón de estado. Cuando termina, el evento ya está guardado en la
  /// cola y la lista muestra el estado nuevo como pendiente por enviar; el envío sigue por su
  /// cuenta. Lanza [ToqueNoValido] si ese paso no corresponde (y no guarda nada).
  Future<EventoLocal> marcar(
    int servicioId,
    String destino, {
    String? motivo,
    String? nombreQuien,
    String? idEvento,
  }) async {
    final evento = await sincronizador.registrar(
      servicioId: servicioId,
      destino: destino,
      motivo: motivo,
      nombreQuien: nombreQuien,
      id: idEvento,
    );
    await _recargar();
    return evento;
  }

  /// Envía lo pendiente y después pide la lista al servidor con el último ETag y la guarda. Si ya
  /// hay una actualización en curso, espera esa misma (abrir la app, volver a primer plano y
  /// deslizar pueden coincidir).
  Future<void> actualizar() => _enCurso ??= _actualizar().whenComplete(() => _enCurso = null);

  Future<void> _actualizar() async {
    final token = sesion.token;
    if (token == null) return;
    _actualizando = true;
    notifyListeners();
    try {
      // Primero lo que hizo el conductor; después la lista, que ya vendrá con esos cambios.
      final fallo = await sincronizador.enviar();
      // Si el envío recibió un 401, la sesión ya se cerró.
      if (sesion.token != token) return;
      if (fallo is ErrorDeRed) {
        // No hay red: la lista fallaría igual. Se ahorra la espera de otra petición.
        _problema = fallo;
        return;
      }
      await sincronizador.enTurno(() => _pedirLista(token));
    } finally {
      _actualizando = false;
      notifyListeners();
    }
  }

  Future<void> _pedirLista(String token) async {
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
      await _recargar();
    } on SesionCerrada catch (error) {
      _problema = null;
      await sesion.cerrarPorServidor(error, tokenUsado: token);
    } on ErrorApi catch (error) {
      _problema = error;
    }
  }

  /// La cola cambió (un toque nuevo, o el servidor respondió): se vuelve a leer la base. Si la
  /// lista estaba sin conexión y un envío acaba de llegar al servidor, además se refresca.
  void _alCambiarLaCola() {
    final envios = sincronizador.enviosCorrectos;
    final volvioLaConexion = envios != _enviosVistos && _problema != null;
    _enviosVistos = envios;
    unawaited(_recargar());
    if (volvioLaConexion) unawaited(actualizar());
  }

  /// Vuelve a leer la base y avisa a las pantallas. Las lecturas van una tras otra, en el orden en
  /// que se pidieron: cuando esta termina, la lista refleja la base de ese momento o de después.
  Future<void> _recargar() => _relecturas.ejecutar(() async {
    await _releer();
    notifyListeners();
  });

  Future<void> _releer() async {
    final conductor = sesion.conductor;
    // En una transacción: los servicios y la cola se leen del mismo instante (si no, un resultado
    // que llega entre las dos lecturas mostraría por un momento el estado anterior).
    final (servicios, pendientes) = await almacen.base.db.transaction((txn) async {
      final servicios = await almacen.leer(en: txn);
      final pendientes = conductor == null
          ? const <EventoLocal>[]
          : await sincronizador.cola.pendientes(conductor.id, en: txn);
      return (servicios, pendientes);
    });
    final destinos = <int, List<String>>{};
    for (final evento in pendientes) {
      destinos.putIfAbsent(evento.servicioId, () => []).add(evento.destino);
    }
    _servicios = [
      for (final servicio in servicios)
        if (destinos[servicio.id] case final suyos?) _conPendientes(servicio, suyos) else servicio,
    ];
    _pendientes = {for (final MapEntry(:key, :value) in destinos.entries) key: value.length};
    _configuracion = await almacen.configuracion();
    _ultimaActualizacion = await almacen.ultimaActualizacion();
  }

  static Servicio _conPendientes(Servicio servicio, List<String> destinos) {
    final visto = EstadoDeServicio(servicio.estado, servicio.estadoPrevio).conPendientes(destinos);
    return servicio.conEstado(
      estado: visto.estado,
      estadoPrevio: visto.estadoPrevio,
      aBordo: visto.aBordo,
    );
  }

  @override
  void dispose() {
    sincronizador.removeListener(_alCambiarLaCola);
    super.dispose();
  }
}
