// Lo que exige la app antes de guardar un Recogido o un Entregado.
//
// - Recogido: el vehículo identificado (placa o VIN; un desvare, placa) y un puesto libre en la
//   grúa. Las dos reglas son copia del servidor (identificacion.dart y capacidad.dart).
// - Recogido y Entregado: el mínimo de fotos de la configuración de la empresa y el nombre de
//   quien entrega o recibe el vehículo. Esta regla es de la app: el servidor guarda el evento con
//   las fotos y el nombre que lleguen.

import '../formato.dart';
import 'capacidad.dart';
import 'estados.dart';
import 'identificacion.dart';
import 'servicio.dart';

/// Por qué no se puede marcar Recogido todavía. [mensaje] es el texto para el conductor.
class BloqueoDeRecogida {
  const BloqueoDeRecogida({
    required this.titulo,
    required this.mensaje,
    this.faltanPorEntregar = const [],
  });

  final String titulo;
  final String mensaje;

  /// En un bloqueo por capacidad: los vehículos que le falta marcar como Entregado.
  final List<Servicio> faltanPorEntregar;
}

/// El bloqueo de un Recogido de [servicio], o null si puede marcarlo. [ronda] son los servicios del
/// conductor con el estado que él ve (el confirmado más sus toques sin enviar).
BloqueoDeRecogida? bloqueoDeRecogida(
  Servicio servicio,
  Iterable<Servicio> ronda, {
  required ConfiguracionApp? configuracion,
}) {
  final momento = configuracion?.momentoPlacaVin ?? MomentoIdentificacion.alRecoger;
  if (identificacionExigida(momento, MomentoIdentificacion.alRecoger)) {
    final falta = identificacionFaltante(
      placa: servicio.vehiculo.placa,
      vin: servicio.vehiculo.vin,
      tipo: servicio.tipo,
    );
    if (falta != null) {
      return BloqueoDeRecogida(
        titulo: 'Falta identificar el vehículo',
        mensaje:
            '$falta Llame a logística para que registren ese dato en el servicio y después '
            'actualice la lista. La app todavía no permite digitarlo.',
      );
    }
  }
  final excedida = capacidadParaRecoger(servicio, ronda);
  if (excedida != null) {
    final faltan = excedida.pendientesDeEntregar;
    final puestos = excedida.capacidad == 1 ? '1 puesto' : '${excedida.capacidad} puestos';
    final cuales = faltan.map(_nombreDe).join(', ');
    return BloqueoDeRecogida(
      titulo: 'La grúa va llena',
      mensaje: faltan.length == 1
          ? 'La grúa tiene $puestos y ya lleva montado el vehículo $cuales. '
                'Márquelo como Entregado antes de recoger otro.'
          : 'La grúa tiene $puestos y ya lleva montados los vehículos $cuales. '
                'Marque uno como Entregado antes de recoger otro.',
      faltanPorEntregar: faltan,
    );
  }
  return null;
}

String _nombreDe(Servicio servicio) =>
    servicio.vehiculo.placa ?? servicio.vehiculo.vin ?? 'servicio N.º ${servicio.id}';

/// "Nombre de quien entrega el vehículo" (Recogido) o "…de quien recibe…" (Entregado).
String etiquetaDeQuien(String destino) => destino == Estado.recogido
    ? 'Nombre de quien entrega el vehículo'
    : 'Nombre de quien recibe el vehículo';

/// Lo que le falta a un Recogido o a un Entregado para poder marcarse, en frases para el conductor.
/// Vacía si no le falta nada.
List<String> faltantesDelPaso({
  required String destino,
  required int fotos,
  required int minimoFotos,
  required String? nombreQuien,
}) {
  assert(destino == Estado.recogido || destino == Estado.entregado);
  final faltan = minimoFotos - fotos;
  return [
    if (faltan == 1)
      'Falta 1 foto: lleva $fotos de $minimoFotos.'
    else if (faltan > 1)
      'Faltan $faltan fotos: lleva $fotos de $minimoFotos.',
    if ((nombreQuien ?? '').trim().isEmpty)
      'Escriba el ${etiquetaDeQuien(destino).toLowerCase()} para marcar ${nombreEstado(destino)}.',
  ];
}
