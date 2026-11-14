// Envía la cola de eventos al servidor y anota lo que responde.
//
// Reglas (docs/api-conductor.md, "Enviar eventos"):
// - Un solo envío a la vez. Todos los disparadores (abrir la app, volver a primer plano, deslizar
//   la lista, un toque nuevo, el reintento con espera) piden lo mismo: `enviar()`. Si ya hay uno en
//   curso, se espera ese.
// - Cada lote sale desde el evento pendiente más antiguo, en orden de secuencia, con máximo 100.
//   Un evento que quedó en `reintentar` va primero en el lote siguiente, así que nunca se envía
//   uno posterior de su mismo servicio sin él.
// - Reenviar es mandar la misma fila (mismo id, misma secuencia). Si la respuesta se pierde, el
//   reenvío vuelve marcado como duplicado y se trata igual.
// - Cada evento se envía solo con el token de quien lo tocó. Un 401 cierra la sesión y conserva la
//   cola; los eventos de otro conductor esperan a que él vuelva a ingresar.
// - Sin red, o si el servidor falla, la cola queda como está y se reintenta con espera creciente.
//
// El envío de eventos y la consulta de la lista de asignaciones van por turnos (`enTurno`): así una
// lista pedida antes de que el servidor aplicara un evento no se guarda después de su resultado.

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api.dart';
import '../ingreso/sesion.dart';
import 'cola_eventos.dart';
import 'evento.dart';
import 'fila.dart';

/// Esperas entre reintentos cuando un envío falla: crecen hasta el tope y se reinician cuando un
/// envío sale bien. Con la app a la vista el tope es corto (el conductor está esperando); en
/// segundo plano es largo, para no gastar batería buscando señal.
const List<Duration> esperasDeReintento = [
  Duration(seconds: 5),
  Duration(seconds: 10),
  Duration(seconds: 20),
  Duration(seconds: 30),
];
const Duration esperaMaximaEnSegundoPlano = Duration(minutes: 5);

enum _Paso { vacio, resuelto, quedan, fallo, sesionCerrada }

class Sincronizador extends ChangeNotifier {
  Sincronizador({
    required this.cola,
    required this.api,
    required this.sesion,
    DateTime Function()? reloj,
    this.esperas = esperasDeReintento,
    this.esperaMaximaOculta = esperaMaximaEnSegundoPlano,
  }) : _reloj = reloj ?? DateTime.now;

  final ColaEventos cola;
  final ClienteApi api;
  final Sesion sesion;
  final List<Duration> esperas;
  final Duration esperaMaximaOculta;
  final DateTime Function() _reloj;

  List<PendientesDeConductor> _porConductor = const [];
  List<EventoLocal> _avisos = const [];
  bool _enviando = false;
  ErrorApi? _problema;
  int _enviosCorrectos = 0;

  Future<ErrorApi?>? _enCurso;
  bool _hayNuevos = false;
  final Fila _turnos = Fila();
  Timer? _reintento;
  Duration? _esperaDelReintento;
  int _fallosSeguidos = 0;
  bool _enPrimerPlano = true;
  bool _desechado = false;

  /// Cambios sin enviar de cada conductor que los tenga en este celular.
  List<PendientesDeConductor> get pendientesPorConductor => _porConductor;

  /// Cambios sin enviar del conductor de la sesión (o del último que ingresó).
  int get pendientes {
    final id = sesion.conductor?.id;
    return _porConductor.where((p) => p.conductorId == id).fold(0, (suma, p) => suma + p.cantidad);
  }

  /// Cambios sin enviar de otros conductores: no se envían con esta sesión.
  List<PendientesDeConductor> get pendientesAjenos {
    final id = sesion.conductor?.id;
    return [
      for (final p in _porConductor)
        if (p.conductorId != id) p,
    ];
  }

  /// Toques que el servidor no aplicó (conflicto o rechazado) y que el conductor no ha dado por
  /// vistos.
  List<EventoLocal> get avisos => _avisos;

  bool get enviando => _enviando;

  /// Por qué falló el último envío; null si salió bien o no hay nada por enviar.
  ErrorApi? get problema => _problema;

  /// Cuántos lotes ha recibido bien el servidor desde que abrió la app. Quien escucha sabe con esto
  /// que volvió la conexión.
  int get enviosCorrectos => _enviosCorrectos;

  /// Cuánto falta para el reintento programado; null si no hay ninguno.
  Duration? get esperaDelReintento => _reintento == null ? null : _esperaDelReintento;

  /// Lee de la base cuánto hay pendiente y qué avisos hay. No usa la red.
  Future<void> cargar() async {
    await _releer();
    _avisar();
  }

  /// Un toque del conductor: lo guarda en la cola y después pide enviarlo. Cuando este Future
  /// termina, el evento ya está en la base; el envío sigue por su cuenta. Lanza [ToqueNoValido] si
  /// el toque no corresponde (y no guarda nada).
  Future<EventoLocal> registrar({
    required int servicioId,
    required String destino,
    String? motivo,
    String? nombreQuien,
    String? id,
  }) async {
    final conductor = sesion.conductor;
    if (sesion.estado != EstadoSesion.activa || conductor == null) {
      throw const ToqueNoValido('Su sesión se cerró. Ingrese de nuevo para marcar el estado.');
    }
    final evento = await cola.encolar(
      conductor: conductor,
      servicioId: servicioId,
      destino: destino,
      motivo: motivo,
      nombreQuien: nombreQuien,
      id: id,
      hora: _reloj(),
    );
    await _releer();
    _avisar();
    _hayNuevos = true;
    unawaited(enviar());
    return evento;
  }

  /// Envía lo pendiente del conductor de la sesión, lote por lote, hasta vaciar la cola o hasta que
  /// algo falle. Nunca hay dos envíos a la vez: si ya hay uno, devuelve ese. Devuelve el error con
  /// que terminó, o null si no falló (también cuando no había nada o quedó algo por reintentar).
  Future<ErrorApi?> enviar() => _enCurso ??= _enviarTodo();

  Future<ErrorApi?> _enviarTodo() async {
    _cancelarReintento();
    try {
      ErrorApi? fallo;
      do {
        // Un toque que llega mientras se envía ya está en la base: si el último lote no lo alcanzó
        // a leer, se da otra vuelta.
        _hayNuevos = false;
        fallo = await _vaciar();
      } while (_hayNuevos && fallo == null);
      return fallo;
    } finally {
      // En el mismo paso que la última revisión de `_hayNuevos`: un toque que llegue después
      // encuentra el envío terminado y arranca otro.
      _enCurso = null;
    }
  }

  Future<ErrorApi?> _vaciar() async {
    while (true) {
      final token = sesion.token;
      final conductor = sesion.conductor;
      if (sesion.estado != EstadoSesion.activa || token == null || conductor == null) return null;
      switch (await enTurno(() => _enviarLote(token, conductor.id))) {
        case _Paso.vacio:
          return null;
        case _Paso.resuelto:
          _fallosSeguidos = 0;
        case _Paso.quedan:
          _programarReintento();
          return null;
        case _Paso.fallo:
          _programarReintento();
          return _problema;
        case _Paso.sesionCerrada:
          return null;
      }
    }
  }

  Future<_Paso> _enviarLote(String token, int conductorId) async {
    final lote = await cola.pendientes(conductorId, limite: maximoEventosPorLote);
    if (lote.isEmpty) {
      if (_problema != null) {
        _problema = null;
        _avisar();
      }
      return _Paso.vacio;
    }
    _enviando = true;
    _avisar();
    try {
      final resultados = await api.enviarEventos(token, lote);
      final resueltos = await cola.registrarResultados(lote, resultados, hora: _reloj());
      _problema = null;
      _enviosCorrectos++;
      return resueltos == lote.length ? _Paso.resuelto : _Paso.quedan;
    } on SesionCerrada catch (error) {
      // El token ya no sirve. La cola no se toca: se envía cuando este conductor vuelva a ingresar.
      _problema = null;
      await sesion.cerrarPorServidor(error, tokenUsado: token);
      return _Paso.sesionCerrada;
    } on ErrorApi catch (error) {
      // Sin red, tiempo agotado, falla del servidor o respuesta ilegible: la cola queda entera.
      _problema = error;
      return _Paso.fallo;
    } finally {
      _enviando = false;
      await _releer();
      _avisar();
    }
  }

  /// Ejecuta [tarea] cuando terminen las que se pidieron antes. Lo usan el envío de eventos y la
  /// consulta de la lista de asignaciones para no cruzarse.
  Future<T> enTurno<T>(Future<T> Function() tarea) => _turnos.ejecutar(tarea);

  /// El conductor tocó "Entendido" en el aviso de un toque que el servidor no aplicó.
  Future<void> marcarVisto(String id) async {
    await cola.marcarVisto(id, hora: _reloj());
    await _releer();
    _avisar();
  }

  /// La app pasó a segundo plano o volvió. Solo cambia el tope de la espera entre reintentos; al
  /// volver, quien escucha el ciclo de vida pide además un envío.
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
      unawaited(enviar());
    });
  }

  void _cancelarReintento() {
    _reintento?.cancel();
    _reintento = null;
  }

  Future<void> _releer() async {
    _porConductor = await cola.pendientesPorConductor();
    final id = sesion.conductor?.id;
    _avisos = id == null ? const [] : await cola.avisos(id);
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
