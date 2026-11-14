// Capacidad de la grúa: nunca más vehículos montados que puestos.
//
// Copia de backend/nucleo/capacidad.py. El servidor revalida cada Recogido; la app bloquea antes
// para que el conductor sepa qué vehículo le falta marcar como Entregado. Las dos copias cumplen
// los mismos casos de docs/casos-reglas.json (test/casos_compartidos_test.dart).

import 'estados.dart';
import 'servicio.dart';

/// La grúa ya lleva tantos vehículos como puestos. [pendientesDeEntregar] es lo que se le muestra
/// al conductor: qué le falta marcar como Entregado.
class CapacidadExcedida<T> {
  const CapacidadExcedida(this.capacidad, this.pendientesDeEntregar);

  final int capacidad;
  final List<T> pendientesDeEntregar;
}

/// Se llama antes de marcar Recogido (`verificar_recogida`). [aBordo] son los otros vehículos que
/// ocupan un puesto de la grúa. Devuelve null si se puede recoger.
CapacidadExcedida<T>? verificarRecogida<T>(int capacidad, List<T> aBordo) {
  if (capacidad < 1) {
    throw ArgumentError.value(capacidad, 'capacidad', 'La capacidad de una grúa es al menos 1');
  }
  return aBordo.length >= capacidad
      ? CapacidadExcedida(capacidad, List.unmodifiable(aBordo))
      : null;
}

/// Los otros servicios de [ronda] que van montados en la grúa de [servicio]: recogidos, o en
/// novedad que venía de recogido. La ronda trae el estado que ve el conductor (el confirmado más
/// sus toques sin enviar).
List<Servicio> montadosEnLaGrua(Servicio servicio, Iterable<Servicio> ronda) => [
  for (final otro in ronda)
    if (otro.id != servicio.id &&
        otro.grua?.id == servicio.grua?.id &&
        EstadoDeServicio(otro.estado, otro.estadoPrevio).aBordo)
      otro,
];

/// El bloqueo por capacidad de un Recogido de [servicio], o null si puede recogerlo. Sin grúa
/// conocida no se bloquea: el servidor revalida.
CapacidadExcedida<Servicio>? capacidadParaRecoger(Servicio servicio, Iterable<Servicio> ronda) {
  final grua = servicio.grua;
  if (grua == null || grua.capacidad < 1) return null;
  return verificarRecogida(grua.capacidad, montadosEnLaGrua(servicio, ronda));
}
