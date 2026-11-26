// Lo que exige la app antes de guardar un En camino, un Recogido o un Entregado.
//
// - En camino: que el conductor no tenga ya tantos servicios iniciados sin finalizar como puestos
//   tiene la grúa (copia del servidor, capacidad.dart). Se le dice cuáles debe terminar primero.
// - Recogido: el vehículo identificado (placa o VIN; un desvare, placa) y un puesto libre en la
//   grúa. Las dos reglas son copia del servidor (identificacion.dart y capacidad.dart). Con la
//   configuración "placa/VIN al recoger", si al vehículo le falta, el conductor la digita en la
//   pantalla del Recogido y viaja en el evento (1a-13b); con "al asignar" no se pide: logística
//   ya debió registrarla y, si falta, el Recogido se bloquea.
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
  if (!seDigitaAlRecoger(configuracion)) {
    final falta = identificacionFaltante(
      placa: servicio.vehiculo.placa,
      vin: servicio.vehiculo.vin,
      tipo: servicio.tipo,
      numeroBodega: servicio.vehiculo.numeroBodega,
    );
    if (falta != null) {
      return BloqueoDeRecogida(
        titulo: 'Falta identificar el vehículo',
        mensaje:
            '$falta Llame a logística para que registren ese dato en el servicio y después '
            'actualice la lista.',
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

/// Por qué no se puede marcar En camino todavía: el conductor ya tiene tantos servicios iniciados
/// sin finalizar como puestos tiene la grúa. [mensaje] es el texto para el conductor y
/// [sinFinalizar], los servicios que debe terminar antes de tomar el siguiente.
class BloqueoDeInicio {
  const BloqueoDeInicio({required this.titulo, required this.mensaje, required this.sinFinalizar});

  final String titulo;
  final String mensaje;
  final List<Servicio> sinFinalizar;
}

/// El bloqueo de un En camino de [servicio], o null si puede marcarlo. [ronda] son los servicios
/// del conductor con el estado que él ve (el confirmado más sus toques sin enviar).
BloqueoDeInicio? bloqueoDeInicio(Servicio servicio, Iterable<Servicio> ronda) {
  final excedido = capacidadParaIniciar(servicio, ronda);
  if (excedido == null) return null;
  final cuantos = excedido.sinFinalizar.length;
  final capacidad = excedido.capacidad;
  if (capacidad == 1 && cuantos == 1) {
    return BloqueoDeInicio(
      titulo: 'Servicio sin finalizar',
      mensaje:
          'Tiene un servicio iniciado y no se ha finalizado. Debe terminarlo para tomar el '
          'siguiente.',
      sinFinalizar: excedido.sinFinalizar,
    );
  }
  final puestos = capacidad == 1 ? '1 puesto' : '$capacidad puestos';
  final sobran = cuantos - capacidad + 1;
  final termine = sobran == 1 ? 'Termine uno' : 'Termine $sobran';
  return BloqueoDeInicio(
    titulo: 'Servicios sin finalizar',
    mensaje:
        'La grúa tiene $puestos y ya tiene $cuantos servicios iniciados sin finalizar. '
        '$termine para tomar el siguiente.',
    sinFinalizar: excedido.sinFinalizar,
  );
}

/// ¿El conductor puede digitar la placa o el VIN que le falten al vehículo al recogerlo? Sí,
/// salvo con la configuración "al asignar": ahí logística la registra antes de asignar. Sin
/// configuración guardada vale la de fábrica ("al recoger").
bool seDigitaAlRecoger(ConfiguracionApp? configuracion) =>
    (configuracion?.momentoPlacaVin ?? MomentoIdentificacion.alRecoger) !=
    MomentoIdentificacion.alAsignar;

/// Qué datos le pide digitar la pantalla del Recogido, o null si no le pide ninguno (el vehículo
/// ya está identificado, también si solo tiene número de bodega, o la configuración es "al
/// asignar"). Un desvare pide solo la placa, que
/// es la que exige; un traslado o un evento sin placa ni VIN piden los dos (basta uno).
({bool placa, bool vin})? identificacionPorDigitar(
  Servicio servicio, {
  required ConfiguracionApp? configuracion,
}) {
  if (!seDigitaAlRecoger(configuracion)) return null;
  final vehiculo = servicio.vehiculo;
  final falta = identificacionFaltante(
    placa: vehiculo.placa,
    vin: vehiculo.vin,
    tipo: servicio.tipo,
    numeroBodega: vehiculo.numeroBodega,
  );
  if (falta == null) return null;
  return (placa: true, vin: servicio.tipo != 'desvare');
}

/// Lo que le falta a la placa o al VIN digitados en la pantalla del Recogido, en frases para el
/// conductor. Vacía si con lo digitado el vehículo queda identificado y cada dato digitado tiene
/// el formato correcto.
List<String> faltantesDeIdentificacion(
  Servicio servicio, {
  required String placaDigitada,
  required String vinDigitado,
}) {
  final placa = normalizarPlaca(placaDigitada);
  final vin = normalizarVin(vinDigitado);
  final falta = identificacionFaltanteAlRecoger(
    placaGuardada: servicio.vehiculo.placa,
    vinGuardado: servicio.vehiculo.vin,
    placaDigitada: placa,
    vinDigitado: vin,
    tipo: servicio.tipo,
    numeroBodega: servicio.vehiculo.numeroBodega,
  );
  return [
    ?falta,
    if (placa.isNotEmpty && !placaValida(placa))
      'La placa debe tener de 1 a $largoMaximoPlaca letras o dígitos.',
    if (vin.isNotEmpty && !vinValido(vin))
      'El VIN debe tener $largoVin letras o dígitos, sin I, O ni Q.',
  ];
}

String _nombreDe(Servicio servicio) =>
    servicio.vehiculo.placa ??
    servicio.vehiculo.vin ??
    (servicio.vehiculo.numeroBodega == null ? null : 'bodega ${servicio.vehiculo.numeroBodega}') ??
    'servicio N.º ${servicio.id}';

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
