// Las asignaciones en la base local: lo último que mandó el servidor, para mostrarlo sin señal.

import 'package:sqflite/sqflite.dart';

import '../base_local.dart';
import 'servicio.dart';

class AlmacenAsignaciones {
  AlmacenAsignaciones(this.base);

  final BaseLocal base;

  /// Reemplaza la lista guardada por la que mandó el servidor, con su configuración, su ETag y la
  /// hora, todo en una sola transacción: si la app muere a mitad, queda la lista anterior completa
  /// con su ETag anterior (nunca un ETag nuevo con datos viejos, que haría que un 304 escondiera
  /// los cambios). Los servicios que ya no vienen se quitan de la lista; lo que tengan pendiente
  /// por enviar vive en otras tablas y no se toca.
  Future<void> reemplazar({
    required List<Servicio> servicios,
    required ConfiguracionApp configuracion,
    required String? etag,
    required DateTime hora,
  }) {
    return base.db.transaction((txn) async {
      await txn.delete('servicios');
      final lote = txn.batch();
      for (final (posicion, servicio) in servicios.indexed) {
        lote.insert('servicios', servicio.aFila(posicion));
      }
      await lote.commit(noResult: true);
      await base.escribirJson(Clave.configuracion, configuracion.aJson(), en: txn);
      if (etag == null) {
        await base.borrar(Clave.etag, en: txn);
      } else {
        await base.escribir(Clave.etag, etag, en: txn);
      }
      await base.escribir(Clave.ultimaActualizacion, hora.toUtc().toIso8601String(), en: txn);
    });
  }

  /// El servidor dijo que nada cambió (304): solo se anota la hora de la consulta.
  Future<void> confirmarSinCambios(DateTime hora) =>
      base.escribir(Clave.ultimaActualizacion, hora.toUtc().toIso8601String());

  /// Los servicios guardados en el orden de la ronda (el de la lista del servidor).
  Future<List<Servicio>> leer({DatabaseExecutor? en}) async {
    final filas = await (en ?? base.db).query('servicios', orderBy: 'posicion');
    return [for (final fila in filas) Servicio.desdeFila(fila)];
  }

  Future<ConfiguracionApp?> configuracion() async {
    final json = await base.leerJson(Clave.configuracion);
    return json == null ? null : ConfiguracionApp.desdeJson(json);
  }

  Future<String?> etag() => base.leer(Clave.etag);

  Future<DateTime?> ultimaActualizacion() async {
    final texto = await base.leer(Clave.ultimaActualizacion);
    return texto == null ? null : DateTime.tryParse(texto)?.toUtc();
  }

  /// Borra la lista de otro conductor (al ingresar uno distinto en este celular). La cola de
  /// eventos y las fotos pendientes no se tocan.
  Future<void> olvidar({DatabaseExecutor? en}) async {
    final ejecutor = en ?? base.db;
    await ejecutor.delete('servicios');
    await base.borrar(Clave.etag, en: ejecutor);
    await base.borrar(Clave.ultimaActualizacion, en: ejecutor);
    await base.borrar(Clave.configuracion, en: ejecutor);
  }
}
