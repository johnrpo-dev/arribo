// Vibración corta en los momentos clave. Siempre va junto a un cambio que se ve (un paso guardado,
// una hoja que se abre, un bloqueo explicado, una opción elegida): nunca sola. Nunca al actualizar
// ni al sincronizar, que pasan sin que el conductor haya tocado nada. En Android respeta el ajuste
// del sistema "vibración al tocar": no hay preferencia propia en la app. El tipo de vibración de
// cada momento se decide solo aquí.

import 'dart:async';

import 'package:flutter/services.dart';

/// Un paso quedó guardado en la cola.
void vibrarPasoGuardado() => unawaited(_vibrar(HapticFeedback.mediumImpact));

/// Se abre una confirmación, o una foto quedó aceptada.
void vibrarAtencion() => unawaited(_vibrar(HapticFeedback.lightImpact));

/// Algo se rechazó o se bloqueó, y se le muestra al conductor por qué.
void vibrarBloqueo() => unawaited(_vibrar(HapticFeedback.heavyImpact));

/// Se eligió una opción.
void vibrarSeleccion() => unawaited(_vibrar(HapticFeedback.selectionClick));

/// Sin esperar y sin fallar: si el canal con Android falla, la pantalla sigue igual.
Future<void> _vibrar(Future<void> Function() vibracion) async {
  try {
    await vibracion();
  } catch (_) {
    // Una vibración que no llega no le cambia nada al conductor.
  }
}
