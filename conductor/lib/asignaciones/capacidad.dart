// Capacidad de la grúa: nunca más vehículos montados que puestos, y nunca más servicios iniciados
// sin finalizar que puestos (al marcar En camino).
//
// Copia de backend/nucleo/capacidad.py. El servidor revalida cada Recogido y cada En camino; la app
// bloquea antes para que el conductor sepa qué le falta terminar. Las dos copias cumplen los mismos
// casos de docs/casos-reglas.json (test/casos_compartidos_test.dart).

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

/// El conductor ya tiene tantos servicios iniciados sin finalizar como puestos tiene la grúa.
/// [sinFinalizar] es lo que se le muestra: los servicios que debe terminar antes de tomar otro.
class InicioExcedido<T> {
  const InicioExcedido(this.capacidad, this.sinFinalizar);

  final int capacidad;
  final List<T> sinFinalizar;
}

/// Se llama antes de marcar En camino (`verificar_inicio`). [enCurso] son los OTROS servicios del
/// conductor iniciados y sin finalizar; [capacidad], la de la grúa del servicio que se inicia.
/// Devuelve null si puede iniciarlo.
InicioExcedido<T>? verificarInicio<T>(int capacidad, List<T> enCurso) {
  if (capacidad < 1) {
    throw ArgumentError.value(capacidad, 'capacidad', 'La capacidad de una grúa es al menos 1');
  }
  return enCurso.length >= capacidad ? InicioExcedido(capacidad, List.unmodifiable(enCurso)) : null;
}

/// Los otros servicios de [ronda] iniciados y sin finalizar. Cuentan todos los del conductor, en
/// cualquier grúa (la ronda es suya), con el estado que él ve.
List<Servicio> iniciadosSinFinalizar(Servicio servicio, Iterable<Servicio> ronda) => [
  for (final otro in ronda)
    if (otro.id != servicio.id && EstadoDeServicio(otro.estado, otro.estadoPrevio).enCurso) otro,
];

/// El bloqueo de un En camino de [servicio], o null si puede marcarlo. La capacidad es la de la
/// grúa del servicio; sin grúa conocida no se bloquea: el servidor revalida.
InicioExcedido<Servicio>? capacidadParaIniciar(Servicio servicio, Iterable<Servicio> ronda) {
  final grua = servicio.grua;
  if (grua == null || grua.capacidad < 1) return null;
  return verificarInicio(grua.capacidad, iniciadosSinFinalizar(servicio, ronda));
}
