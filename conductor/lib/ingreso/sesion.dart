// La sesión del conductor en este celular: si hay token, de quién es, y por qué se cerró.
//
// El token vive en el almacenamiento seguro; aquí se guarda una copia en memoria solo para no
// leer el Keystore en cada petición. El conductor (id, nombre, celular) va en la base local.

import 'package:flutter/foundation.dart';
import 'package:sqflite/sqflite.dart';

import '../api.dart';
import '../asignaciones/almacen_asignaciones.dart';
import '../base_local.dart';
import 'almacen_token.dart';

enum EstadoSesion { iniciando, sinSesion, activa }

enum ResultadoSalida {
  cerrada,

  /// Hay eventos o fotos sin enviar: no se cierra la sesión (el servidor toma como conductor del
  /// evento al dueño del token con que llega).
  hayPendientes,
}

class Sesion extends ChangeNotifier {
  Sesion({
    required this.api,
    required this.base,
    required this.almacenToken,
    Future<String?> Function()? nombreDispositivo,
  }) : _nombreDispositivo = nombreDispositivo ?? _sinNombre;

  final ClienteApi api;
  final BaseLocal base;
  final AlmacenToken almacenToken;
  final Future<String?> Function() _nombreDispositivo;

  static Future<String?> _sinNombre() async => null;

  EstadoSesion _estado = EstadoSesion.iniciando;
  Conductor? _conductor;
  String? _token;
  String? _aviso;

  EstadoSesion get estado => _estado;

  /// El conductor que ingresó por última vez en este celular (también después de que su sesión
  /// se cierre, para proponer su celular en la pantalla de ingreso).
  Conductor? get conductor => _conductor;

  /// El token vigente, o null sin sesión.
  String? get token => _token;

  /// Por qué se cerró la sesión, con el texto del servidor (por ejemplo, un token revocado).
  String? get aviso => _aviso;

  /// Lee lo guardado al abrir la app: con token, entra directo a la lista (aunque no haya señal).
  Future<void> iniciar() async {
    final token = await almacenToken.leer();
    _conductor = await _conductorGuardado();
    _token = token;
    _estado = token == null ? EstadoSesion.sinSesion : EstadoSesion.activa;
    notifyListeners();
  }

  /// `POST /ingresar/`. Si falla, lanza el ErrorApi para que la pantalla muestre el motivo.
  Future<void> ingresar({required String celular, required String pin}) async {
    final ingreso = await api.ingresar(
      celular: celular.trim(),
      pin: pin,
      dispositivoId: await base.dispositivoId(),
      dispositivoNombre: await _nombreDispositivo(),
    );
    final nuevo = ingreso.conductor;
    await base.db.transaction((txn) async {
      final anterior = await _conductorGuardado(en: txn);
      if (anterior != null && anterior.id != nuevo.id) {
        // La lista era de otro conductor. Lo pendiente por enviar no se toca.
        await AlmacenAsignaciones(base).olvidar(en: txn);
      }
      await base.escribirJson(Clave.conductor, nuevo.aJson(), en: txn);
    });
    // El token se guarda al final: si la app muere antes, al abrirla se pide ingresar de nuevo.
    await almacenToken.guardar(ingreso.token);
    _token = ingreso.token;
    _conductor = nuevo;
    _aviso = null;
    _estado = EstadoSesion.activa;
    notifyListeners();
  }

  /// El servidor respondió 401 a una petición hecha con [tokenUsado]: el token ya no sirve. Se
  /// borra y se vuelve al ingreso mostrando el `detalle`. Nada local se borra (ni la lista ni lo
  /// pendiente por enviar). Si entre tanto ya se ingresó con otro token, no hace nada.
  Future<void> cerrarPorServidor(SesionCerrada error, {required String tokenUsado}) async {
    if (_estado != EstadoSesion.activa || _token != tokenUsado) return;
    _token = null;
    _aviso = error.detalle;
    _estado = EstadoSesion.sinSesion;
    notifyListeners();
    await almacenToken.borrar();
  }

  /// Cerrar sesión a pedido del conductor. No se permite con eventos o fotos pendientes. Sin señal,
  /// el token se borra del celular igual; en el servidor queda revocado cuando se vuelva a ingresar
  /// en este celular (o desde el admin).
  Future<ResultadoSalida> salir() async {
    if (await base.pendientesPorEnviar() > 0) return ResultadoSalida.hayPendientes;
    final token = _token;
    if (token != null) {
      try {
        await api.salir(token);
      } on ErrorApi {
        // Sin señal o falla del servidor: se cierra igual en el celular.
      }
    }
    await almacenToken.borrar();
    _token = null;
    _aviso = null;
    _estado = EstadoSesion.sinSesion;
    notifyListeners();
    return ResultadoSalida.cerrada;
  }

  Future<Conductor?> _conductorGuardado({DatabaseExecutor? en}) async {
    try {
      final json = await base.leerJson(Clave.conductor, en: en);
      return json == null ? null : Conductor.desdeJson(json);
    } on FormatException {
      return null;
    }
  }
}
