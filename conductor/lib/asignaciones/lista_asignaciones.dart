// La lista de asignaciones que ve el conductor. Siempre se muestra desde la base local; el
// servidor solo la refresca. Sin señal, el conductor ve lo último guardado y un aviso discreto.
//
// El estado de cada servicio es el que confirmó el servidor más los toques del conductor que aún no
// se han enviado (la cola de eventos): un toque se ve de inmediato, marcado como pendiente. Lo
// mismo la placa o el VIN que digitó en un Recogido sin enviar (1a-13b): el vehículo ya se ve con
// ellos donde le faltaban.

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api.dart';
import '../cola/cola_eventos.dart';
import '../cola/evento.dart';
import '../cola/fila.dart';
import '../cola/sincronizador.dart';
import '../fotos/almacen_fotos.dart';
import '../fotos/foto.dart';
import '../fotos/subidor_fotos.dart';
import '../ingreso/sesion.dart';
import 'almacen_asignaciones.dart';
import 'estados.dart';
import 'identificacion.dart';
import 'requisitos.dart' as requisitos;
import 'requisitos.dart' show BloqueoDeRecogida;
import 'servicio.dart';

class ListaAsignaciones extends ChangeNotifier {
  ListaAsignaciones({
    required this.almacen,
    required this.api,
    required this.sesion,
    Sincronizador? sincronizador,
    SubidorDeFotos? fotos,
    DateTime Function()? reloj,
  }) : _reloj = reloj ?? DateTime.now,
       sincronizador =
           sincronizador ??
           Sincronizador(cola: ColaEventos(almacen.base), api: api, sesion: sesion, reloj: reloj),
       fotos =
           fotos ??
           SubidorDeFotos(
             almacen: AlmacenFotos(almacen.base),
             api: api,
             sesion: sesion,
             reloj: reloj,
           ) {
    _enviosVistos = this.sincronizador.enviosCorrectos;
    this.sincronizador.addListener(_alCambiarLaCola);
    this.fotos.addListener(notifyListeners);
  }

  final AlmacenAsignaciones almacen;
  final ClienteApi api;
  final Sesion sesion;

  /// Quien envía la cola de eventos. La lista le pide enviar antes de refrescarse y vuelve a leer
  /// la base cada vez que la cola cambia.
  final Sincronizador sincronizador;

  /// Quien sube las fotos de evidencia. La lista lo despierta cuando sabe que hay conexión (un
  /// envío de eventos llegó, o el servidor respondió la lista) y avisa a las pantallas cuando la
  /// cola de fotos cambia.
  final SubidorDeFotos fotos;
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
    await fotos.cargar();
    await _recargar();
    _cargada = true;
    notifyListeners();
    fotos.despertar();
  }

  /// Un toque del conductor en un botón de estado. Cuando termina, el evento ya está guardado en la
  /// cola y la lista muestra el estado nuevo como pendiente por enviar; el envío sigue por su
  /// cuenta. Lanza [ToqueNoValido] si ese paso no corresponde (y no guarda nada).
  ///
  /// Las pantallas marcan así En camino y Novedad. Recogido y Entregado van por [confirmarPaso],
  /// que exige sus fotos y el nombre de quien entrega o recibe.
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

  /// Por qué [servicio] no se puede marcar Recogido todavía (le falta la placa o el VIN, o la grúa
  /// va llena), o null si puede. Se calcula con el estado que ve el conductor: lo confirmado más
  /// sus toques sin enviar.
  BloqueoDeRecogida? bloqueoDeRecogida(Servicio servicio) =>
      requisitos.bloqueoDeRecogida(servicio, _servicios, configuracion: _configuracion);

  /// Qué datos le pide digitar la pantalla del Recogido de [servicio] (placa, VIN), o null si
  /// ninguno: el vehículo ya está identificado o la configuración es "al asignar".
  ({bool placa, bool vin})? identificacionPorDigitar(Servicio servicio) =>
      requisitos.identificacionPorDigitar(servicio, configuracion: _configuracion);

  /// Marca el Recogido o el Entregado que el conductor preparó en su pantalla: guarda el evento en
  /// la cola con el UUID del paso y, en la misma transacción, pasa sus fotos a la cola de subida.
  /// Antes vuelve a revisar todo lo que exige el paso (identificación y capacidad en un Recogido;
  /// mínimo de fotos y nombre en los dos). Si falta algo lanza [ToqueNoValido] y no guarda nada.
  ///
  /// [placaDigitada] y [vinDigitado] son lo que el conductor escribió en un Recogido de un vehículo
  /// sin identificar: solo viajan en el evento los datos que la pantalla le pidió.
  Future<EventoLocal> confirmarPaso(
    PasoEnCurso paso, {
    required String nombreQuien,
    String placaDigitada = '',
    String vinDigitado = '',
  }) async {
    final servicio = this.servicio(paso.servicioId);
    if (servicio == null) throw const ToqueNoValido('Este servicio ya no está en su lista.');
    String? placa;
    String? vin;
    if (paso.destino == Estado.recogido) {
      final porDigitar = identificacionPorDigitar(servicio);
      if (porDigitar != null) {
        placa = porDigitar.placa ? placaDigitada : null;
        vin = porDigitar.vin ? vinDigitado : null;
        final faltan = requisitos.faltantesDeIdentificacion(
          servicio,
          placaDigitada: placa ?? '',
          vinDigitado: vin ?? '',
        );
        if (faltan.isNotEmpty) throw ToqueNoValido(faltan.join(' '));
      }
      final bloqueo = bloqueoDeRecogida(servicio);
      if (bloqueo != null) throw ToqueNoValido(bloqueo.mensaje);
    }
    final minimoFotos = _configuracion?.minimoFotos ?? 0;
    final evento = await sincronizador.registrar(
      servicioId: paso.servicioId,
      destino: paso.destino,
      nombreQuien: nombreQuien,
      placa: placa,
      vin: vin,
      id: paso.eventoId,
      alGuardar: (txn, evento) => fotos.almacen.confirmar(txn, evento, minimoFotos: minimoFotos),
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
      // El servidor respondió: hay conexión para las fotos que estén listas.
      fotos.despertar();
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
    final llegoUnEnvio = envios != _enviosVistos;
    final volvioLaConexion = llegoUnEnvio && _problema != null;
    _enviosVistos = envios;
    unawaited(
      _recargar().then((_) {
        // Un lote de eventos llegó al servidor: las fotos de esos eventos ya se pueden subir.
        if (llegoUnEnvio) fotos.despertar();
      }),
    );
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
    final digitados = <int, EventoLocal>{};
    for (final evento in pendientes) {
      destinos.putIfAbsent(evento.servicioId, () => []).add(evento.destino);
      if (evento.placa != null || evento.vin != null) digitados[evento.servicioId] = evento;
    }
    final vistos = [
      for (final servicio in servicios)
        _conDigitado(switch (destinos[servicio.id]) {
          final suyos? => _conPendientes(servicio, suyos),
          null => servicio,
        }, digitados[servicio.id]),
    ];
    // Un regreso deja de esperar en cuanto el conductor marca Entregado en su ida, aunque ese
    // toque aún no haya llegado al servidor (el servidor los aplica en el mismo orden).
    final entregadas = {
      for (final servicio in vistos)
        if (servicio.estado == Estado.entregado) servicio.id,
    };
    _servicios = [
      for (final servicio in vistos)
        servicio.esperaIda && entregadas.contains(servicio.regresoDe)
            ? servicio.sinEsperarIda()
            : servicio,
    ];
    _pendientes = {for (final MapEntry(:key, :value) in destinos.entries) key: value.length};
    _configuracion = await almacen.configuracion();
    _ultimaActualizacion = await almacen.ultimaActualizacion();
    await fotos.releer();
  }

  /// El vehículo con la placa o el VIN que el conductor digitó en un Recogido sin enviar, donde le
  /// falten (como hará el servidor al aplicarlo).
  static Servicio _conDigitado(Servicio servicio, EventoLocal? recogido) {
    if (recogido == null) return servicio;
    final complemento = completarIdentificacion(
      placaGuardada: servicio.vehiculo.placa,
      vinGuardado: servicio.vehiculo.vin,
      placaDigitada: recogido.placa,
      vinDigitado: recogido.vin,
    );
    if (complemento.nuevos.isEmpty) return servicio;
    return servicio.conIdentificacion(
      placa: complemento.nuevos.contains(CampoIdentificacion.placa) ? complemento.placa : '',
      vin: complemento.nuevos.contains(CampoIdentificacion.vin) ? complemento.vin : '',
    );
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
    fotos.removeListener(notifyListeners);
    super.dispose();
  }
}
