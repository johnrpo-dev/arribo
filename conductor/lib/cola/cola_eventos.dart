// La cola de eventos en la base local: cada toque del conductor queda escrito aquí antes de
// cualquier intento de red y antes de que cambie la pantalla.
//
// Reglas (CLAUDE.md, "Eventos idempotentes"; docs/api-conductor.md, "Enviar eventos"):
// - El id (UUID v4) y la secuencia se fijan al tocar, en la misma transacción que guarda el evento,
//   y no cambian nunca: reenviar es mandar la misma fila otra vez.
// - La secuencia solo crece. Sale del contador `ultima_secuencia` de estado_local, que no se toca
//   al cerrar sesión ni al cambiar de conductor, y nunca queda por debajo de la mayor guardada.
// - Un evento solo sale de la cola con una respuesta definitiva del servidor (aplicado, conflicto o
//   rechazado). Nada se borra: la fila queda con su resultado.
// - Cada evento es de quien lo tocó (`conductor_id`): se envía solo con su token.
//
// Aquí no hay red: de enviar se encarga `sincronizador.dart`.

import 'dart:math' as math;

import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

import '../api.dart';
import '../asignaciones/estados.dart';
import '../base_local.dart';
import 'evento.dart';

/// El toque no se guardó porque no corresponde: no es el paso que sigue, le falta el motivo o el
/// servicio ya no está en la lista. [mensaje] es el texto para el conductor.
class ToqueNoValido implements Exception {
  const ToqueNoValido(this.mensaje);

  final String mensaje;

  @override
  String toString() => 'ToqueNoValido: $mensaje';
}

class ColaEventos {
  ColaEventos(this.base);

  final BaseLocal base;

  /// Guarda un toque de [conductor] como evento pendiente y lo devuelve con su id y su secuencia.
  ///
  /// Todo ocurre en una transacción: se comprueba que [destino] sea el paso que sigue al estado
  /// que ve el conductor (el confirmado más sus toques sin enviar), se toma la secuencia y se
  /// inserta la fila. Dos toques seguidos en el mismo botón no crean dos eventos: el segundo ya no
  /// es el paso que sigue y lanza [ToqueNoValido].
  ///
  /// [id] permite a quien llama fijar el UUID antes (la 1a-13 lo necesita para atar las fotos al
  /// evento); si no llega, se genera aquí.
  Future<EventoLocal> encolar({
    required Conductor conductor,
    required int servicioId,
    required String destino,
    required DateTime hora,
    String? motivo,
    String? nombreQuien,
    String? id,
  }) async {
    final motivoLimpio = _limpio(motivo);
    if (!destinosDesdeLaApp.contains(destino)) {
      throw const ToqueNoValido('Ese cambio de estado no se hace desde la app.');
    }
    if (destino == Estado.novedad && motivoLimpio == null) {
      throw const ToqueNoValido('Escriba qué pasó para reportar la novedad.');
    }
    return base.db.transaction((txn) async {
      final filas = await txn.query(
        'servicios',
        columns: ['estado', 'estado_previo', 'vehiculo_placa', 'vehiculo_vin'],
        where: 'id = ?',
        whereArgs: [servicioId],
      );
      if (filas.isEmpty) {
        throw const ToqueNoValido('Este servicio ya no está en su lista.');
      }
      final servicio = filas.first;
      final anteriores = await pendientes(conductor.id, servicioId: servicioId, en: txn);
      final actual = EstadoDeServicio(
        servicio['estado']! as String,
        servicio['estado_previo'] as String?,
      ).conPendientes([for (final evento in anteriores) evento.destino]);
      if (!puedeMarcar(actual.estado, destino)) {
        throw const ToqueNoValido('Ese paso ya no corresponde al estado del servicio.');
      }

      final secuencia = await _siguienteSecuencia(txn);
      final ahora = hora.toUtc();
      final evento = EventoLocal(
        id: id ?? const Uuid().v4(),
        conductorId: conductor.id,
        conductorNombre: conductor.nombre,
        servicioId: servicioId,
        vehiculo: (servicio['vehiculo_placa'] ?? servicio['vehiculo_vin']) as String?,
        destino: destino,
        secuencia: secuencia,
        horaDispositivo: ahora,
        motivo: motivoLimpio,
        nombreQuien: _limpio(nombreQuien),
        creadoEn: ahora,
      );
      await txn.insert('eventos_pendientes', evento.aFila());
      return evento;
    });
  }

  /// La secuencia del evento que se va a guardar, dentro de su transacción. Parte del contador
  /// guardado y de la mayor secuencia que haya en la cola, por si alguno de los dos se perdiera.
  Future<int> _siguienteSecuencia(Transaction txn) async {
    final guardada = int.tryParse(await base.leer(Clave.ultimaSecuencia, en: txn) ?? '') ?? 0;
    final mayor =
        Sqflite.firstIntValue(
          await txn.rawQuery('SELECT MAX(secuencia) FROM eventos_pendientes'),
        ) ??
        0;
    final secuencia = math.max(guardada, mayor) + 1;
    await base.escribir(Clave.ultimaSecuencia, '$secuencia', en: txn);
    return secuencia;
  }

  /// Los eventos de [conductorId] que aún no tienen respuesta definitiva, del más antiguo al más
  /// nuevo por secuencia. Con [limite], solo los primeros (un lote).
  Future<List<EventoLocal>> pendientes(
    int conductorId, {
    int? servicioId,
    int? limite,
    DatabaseExecutor? en,
  }) async {
    final filas = await (en ?? base.db).query(
      'eventos_pendientes',
      where:
          "estado_envio = 'pendiente' AND conductor_id = ?"
          '${servicioId == null ? '' : ' AND servicio_id = ?'}',
      whereArgs: [conductorId, ?servicioId],
      orderBy: 'secuencia',
      limit: limite,
    );
    return [for (final fila in filas) EventoLocal.desdeFila(fila)];
  }

  /// Cuántos cambios sin enviar hay en el celular, por conductor.
  Future<List<PendientesDeConductor>> pendientesPorConductor() async {
    final filas = await base.db.rawQuery(
      'SELECT conductor_id, MAX(conductor_nombre) AS nombre, COUNT(*) AS cantidad '
      "FROM eventos_pendientes WHERE estado_envio = 'pendiente' "
      'GROUP BY conductor_id ORDER BY MIN(secuencia)',
    );
    return [
      for (final fila in filas)
        PendientesDeConductor(
          conductorId: fila['conductor_id']! as int,
          nombre: fila['nombre'] as String?,
          cantidad: fila['cantidad']! as int,
        ),
    ];
  }

  /// Los eventos de [conductorId] que el servidor no aplicó (conflicto o rechazado) y que el
  /// conductor todavía no ha dado por vistos, del más antiguo al más nuevo.
  Future<List<EventoLocal>> avisos(int conductorId) async {
    final filas = await base.db.query(
      'eventos_pendientes',
      where: "estado_envio IN ('conflicto', 'rechazado') AND visto_en IS NULL AND conductor_id = ?",
      whereArgs: [conductorId],
      orderBy: 'secuencia',
    );
    return [for (final fila in filas) EventoLocal.desdeFila(fila)];
  }

  /// El conductor tocó "Entendido" en el aviso. El evento sigue guardado con su resultado.
  Future<void> marcarVisto(String id, {required DateTime hora}) => base.db.update(
    'eventos_pendientes',
    {'visto_en': hora.toUtc().toIso8601String()},
    where: 'id = ? AND visto_en IS NULL',
    whereArgs: [id],
  );

  /// Anota lo que respondió el servidor a un lote: el resultado N es del evento N. Devuelve cuántos
  /// eventos salieron de la cola.
  ///
  /// En una sola transacción, para que la app pueda morir en cualquier punto sin quedar a medias:
  /// - `aplicado`, `conflicto` y `rechazado` son definitivos: el evento deja de estar pendiente y
  ///   guarda el motivo y el detalle. Venga o no marcado como duplicado, es lo mismo.
  /// - `reintentar` (o un resultado que esta versión no conoce) lo deja pendiente, tal cual.
  /// - El estado del servicio que manda el servidor corrige el de la lista local, solo si a ese
  ///   servicio no le quedan eventos pendientes. Si ya no está en la ronda del conductor, se quita
  ///   de la lista. Al corregir se olvida el ETag de la lista: la próxima consulta la trae completa
  ///   (si no, un servicio que vuelve al estado anterior en el servidor daría un 304 con la lista
  ///   local ya cambiada).
  Future<int> registrarResultados(
    List<EventoLocal> lote,
    List<ResultadoEvento> resultados, {
    required DateTime hora,
  }) {
    if (lote.length != resultados.length) {
      throw ArgumentError('Se esperaba un resultado por evento.');
    }
    if (lote.isEmpty) return Future.value(0);
    final conductorId = lote.first.conductorId;
    return base.db.transaction((txn) async {
      var resueltos = 0;
      final remotos = <int, EstadoRemoto>{};
      for (final (posicion, evento) in lote.indexed) {
        final resultado = resultados[posicion];
        final remoto = resultado.servicio;
        if (remoto != null && remoto.id == evento.servicioId) remotos[remoto.id] = remoto;
        final estadoEnvio = switch (resultado.resultado) {
          ResultadoEvento.aplicado => EstadoEnvio.aplicado,
          ResultadoEvento.conflicto => EstadoEnvio.conflicto,
          ResultadoEvento.rechazado => EstadoEnvio.rechazado,
          _ => null,
        };
        if (estadoEnvio == null) continue;
        resueltos += await txn.update(
          'eventos_pendientes',
          {
            'estado_envio': estadoEnvio,
            'resultado_motivo': resultado.motivo,
            'resultado_detalle': resultado.detalle,
            'resuelto_en': hora.toUtc().toIso8601String(),
          },
          where: "id = ? AND estado_envio = 'pendiente'",
          whereArgs: [evento.id],
        );
      }

      // La lista guardada es del último conductor que ingresó. Si la respuesta es de eventos de
      // otro (llegó después de que cambiara la sesión), no se toca esa lista.
      final dueno = (await base.leerJson(Clave.conductor, en: txn))?['id'];
      if (dueno != conductorId) return resueltos;
      var corregidos = 0;
      for (final remoto in remotos.values) {
        final quedan = await pendientes(conductorId, servicioId: remoto.id, limite: 1, en: txn);
        if (quedan.isNotEmpty) continue;
        final estado = remoto.estado;
        if (estado == null || !remoto.enSuRonda) {
          corregidos += await txn.delete('servicios', where: 'id = ?', whereArgs: [remoto.id]);
        } else {
          corregidos += await txn.update(
            'servicios',
            {
              'estado': estado,
              'estado_previo': remoto.estadoPrevio,
              'a_bordo': remoto.aBordo ? 1 : 0,
            },
            where: 'id = ?',
            whereArgs: [remoto.id],
          );
        }
      }
      if (corregidos > 0) await base.borrar(Clave.etag, en: txn);
      return resueltos;
    });
  }
}

String? _limpio(String? texto) {
  final limpio = texto?.trim();
  return limpio == null || limpio.isEmpty ? null : limpio;
}
