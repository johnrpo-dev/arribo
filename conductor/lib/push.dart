// Avisos push (1a-14): el token de Firebase de este celular, registrado en el servidor con la
// sesión, y qué hace la app cuando llega un aviso.
//
// Un aviso solo trae el número del servicio y un texto fijo (docs/api-conductor.md, "Avisos
// push"). La lista del servidor sigue siendo la verdad: el aviso solo hace que la app la pida
// antes. Por eso nada de aquí bloquea ni cambia la lista; si algo falla, la app sigue igual.

import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'api.dart';
import 'asignaciones/lista_asignaciones.dart';
import 'cola/fila.dart';
import 'ingreso/sesion.dart';

/// Lo que la app usa de un aviso push: su tipo (`asignado` o `retirado`) y el servicio.
class MensajePush {
  const MensajePush({this.tipo, this.servicioId});

  /// Desde los datos del mensaje de FCM, que siempre son textos.
  factory MensajePush.desdeDatos(Map<String, Object?> datos) {
    final tipo = datos['tipo'];
    return MensajePush(
      tipo: tipo is String ? tipo : null,
      servicioId: int.tryParse('${datos['servicio_id'] ?? ''}'),
    );
  }

  final String? tipo;
  final int? servicioId;
}

/// Lo que la app usa de Firebase Cloud Messaging. En las pruebas se cambia por uno falso.
abstract interface class MensajeriaPush {
  /// Pide el permiso de mostrar notificaciones (Android 13 o superior; en los anteriores ya está
  /// concedido). Devuelve si quedó concedido.
  Future<bool> pedirPermiso();

  /// El token de push de este celular. Puede lanzar (por ejemplo, sin señal la primera vez).
  Future<String?> token();

  /// Cada vez que Firebase cambia el token de este celular.
  Stream<String> get tokensNuevos;

  /// Los avisos que llegan con la app abierta (Android no los muestra como notificación).
  Stream<MensajePush> get avisosConLaAppAbierta;

  /// Las notificaciones que el conductor tocó, con la app en segundo plano o cerrada (la que
  /// abrió la app viene primero).
  Stream<MensajePush> get avisosTocados;

  /// Borra el token de este celular en Firebase: un aviso viejo dirigido a él ya no llega.
  Future<void> borrarToken();
}

/// La de verdad. Exige `Firebase.initializeApp()` antes (lo hace main.dart).
///
/// Usa el token de FCM (`getToken`, `onTokenRefresh`, `deleteToken`), que es lo que el servidor
/// manda en la API HTTP v1 (`message.token`). firebase_messaging 17 los marca obsoletos a favor del
/// registro por identificador de instalación (`register`, `onRegistered`), que cambiaría también
/// el envío del servidor: queda anotado como riesgo en PROGRESS.md (1a-14).
class MensajeriaFirebase implements MensajeriaPush {
  MensajeriaFirebase([FirebaseMessaging? mensajeria])
    : _mensajeria = mensajeria ?? FirebaseMessaging.instance;

  final FirebaseMessaging _mensajeria;

  @override
  Future<bool> pedirPermiso() async {
    final ajustes = await _mensajeria.requestPermission();
    return ajustes.authorizationStatus == AuthorizationStatus.authorized ||
        ajustes.authorizationStatus == AuthorizationStatus.provisional;
  }

  @override
  // ignore: deprecated_member_use
  Future<String?> token() => _mensajeria.getToken();

  @override
  // ignore: deprecated_member_use
  Stream<String> get tokensNuevos => _mensajeria.onTokenRefresh;

  @override
  Stream<MensajePush> get avisosConLaAppAbierta => FirebaseMessaging.onMessage.map(_leer);

  @override
  Stream<MensajePush> get avisosTocados async* {
    final inicial = await _mensajeria.getInitialMessage();
    if (inicial != null) yield _leer(inicial);
    yield* FirebaseMessaging.onMessageOpenedApp.map(_leer);
  }

  @override
  // ignore: deprecated_member_use
  Future<void> borrarToken() => _mensajeria.deleteToken();

  static MensajePush _leer(RemoteMessage mensaje) => MensajePush.desdeDatos(mensaje.data);
}

/// Registra el token de push en el servidor (`PUT /push/`) con cada sesión: al ingresar, al abrir
/// la app con sesión guardada y cada vez que Firebase lo cambia. Si no hay señal, lo reintenta la
/// próxima vez que el servidor responda la lista. Al cerrarse la sesión borra el token en
/// Firebase (en el servidor lo borra `POST /salir/`). Con un aviso y la app abierta, refresca la
/// lista.
class RegistroPush {
  RegistroPush({
    required this.mensajeria,
    required this.api,
    required this.sesion,
    required this.lista,
  });

  final MensajeriaPush mensajeria;
  final ClienteApi api;
  final Sesion sesion;
  final ListaAsignaciones lista;

  /// Registrar y borrar no se cruzan: van uno tras otro.
  final Fila _fila = Fila();
  final List<StreamSubscription<Object?>> _suscripciones = [];

  /// El token de la API con que se trabaja ahora (null sin sesión).
  String? _sesionVista;

  /// Qué par (token de la API, token de push) ya confirmó el servidor.
  ({String sesion, String push})? _registrado;

  /// Falta registrar (falló por la red o Firebase no dio el token): se reintenta cuando el
  /// servidor responda la lista.
  bool _pendiente = false;
  bool _permisoPedido = false;
  DateTime? _ultimaListaVista;
  bool _iniciado = false;

  /// Queda registrado, ya confirmado por el servidor, este token de push.
  String? get tokenRegistrado => _registrado?.push;

  bool get pendiente => _pendiente;

  /// Empieza a escuchar la sesión, a Firebase y a la lista. Se llama una vez, antes de
  /// `sesion.iniciar()`.
  void iniciar() {
    if (_iniciado) return;
    _iniciado = true;
    _ultimaListaVista = lista.ultimaActualizacion;
    sesion.addListener(_alCambiarLaSesion);
    lista.addListener(_alCambiarLaLista);
    _suscripciones
      ..add(mensajeria.tokensNuevos.listen((nuevo) => _encolar(() => _registrar(nuevo))))
      ..add(mensajeria.avisosConLaAppAbierta.listen(_alLlegarUnAviso));
    _alCambiarLaSesion();
  }

  Future<void> cerrar() async {
    sesion.removeListener(_alCambiarLaSesion);
    lista.removeListener(_alCambiarLaLista);
    for (final suscripcion in _suscripciones) {
      await suscripcion.cancel();
    }
    _suscripciones.clear();
  }

  /// Espera a que termine lo que ya está pedido (para las pruebas).
  Future<void> get listo => _fila.ejecutar(() async {});

  void _alCambiarLaSesion() {
    final token = sesion.token;
    if (token == _sesionVista) return;
    final habiaSesion = _sesionVista != null;
    _sesionVista = token;
    if (token == null) {
      _registrado = null;
      _pendiente = false;
      if (habiaSesion) _encolar(_olvidar);
    } else {
      _encolar(_registrar);
    }
  }

  /// El servidor respondió la lista (200 o 304): hay conexión. Si quedó pendiente, se reintenta.
  void _alCambiarLaLista() {
    final hora = lista.ultimaActualizacion;
    if (hora == _ultimaListaVista) return;
    _ultimaListaVista = hora;
    if (_pendiente && sesion.token != null) {
      _pendiente = false;
      _encolar(_registrar);
    }
  }

  void _alLlegarUnAviso(MensajePush aviso) {
    if (sesion.token == null) return;
    unawaited(lista.actualizar());
  }

  void _encolar(Future<void> Function() tarea) {
    unawaited(
      _fila.ejecutar(tarea).catchError((Object error) {
        debugPrint('Push: error inesperado ($error).');
      }),
    );
  }

  Future<void> _registrar([String? tokenPush]) async {
    final tokenApi = sesion.token;
    if (tokenApi == null) return;
    if (!_permisoPedido) {
      _permisoPedido = true;
      try {
        // Sin permiso el aviso no se muestra, pero el token sirve igual: con la app abierta, el
        // aviso refresca la lista.
        await mensajeria.pedirPermiso();
      } catch (error) {
        debugPrint('Push: no se pudo pedir el permiso de notificaciones ($error).');
      }
    }
    String? push = tokenPush;
    if (push == null) {
      try {
        push = await mensajeria.token();
      } catch (error) {
        debugPrint('Push: Firebase no dio el token ($error); se reintenta.');
        _pendiente = sesion.token == tokenApi;
        return;
      }
    }
    if (sesion.token != tokenApi) return;
    if (push == null || push.isEmpty) {
      _pendiente = true;
      return;
    }
    if (_registrado == (sesion: tokenApi, push: push)) return;
    try {
      await api.registrarPush(tokenApi, push);
      if (sesion.token == tokenApi) {
        _registrado = (sesion: tokenApi, push: push);
        _pendiente = false;
      }
    } on SesionCerrada catch (error) {
      await sesion.cerrarPorServidor(error, tokenUsado: tokenApi);
    } on ErrorDeContrato catch (error) {
      // El servidor no acepta este token: reintentar no lo arregla.
      debugPrint('Push: el servidor rechazó el token (${error.codigo}).');
    } on ErrorApi {
      // Sin señal o falla del servidor: se reintenta cuando la lista vuelva a llegar.
      _pendiente = sesion.token == tokenApi;
    }
  }

  Future<void> _olvidar() async {
    try {
      await mensajeria.borrarToken();
    } catch (error) {
      debugPrint('Push: no se pudo borrar el token de Firebase ($error).');
    }
  }
}
