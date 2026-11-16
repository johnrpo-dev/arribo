// El regreso de un evento espera a que su ida esté entregada.
//
// Copia de `regreso_bloqueado` (backend/nucleo/trayecto.py): no se recoge en el destino un vehículo
// que todavía no ha llegado allá. Bloquea En camino, Recogido y Entregado; la Novedad no (es un
// aviso). El servidor decide: si esta copia se equivoca, el toque llega como conflicto
// `ida_sin_entregar` y logística lo revisa. La vigila test/casos_compartidos_test.dart con los casos
// de docs/casos-reglas.json (`regreso`).

import 'estados.dart';

/// Pasos del regreso que esperan a que la ida esté entregada.
const Set<String> pasosQueEsperanLaIda = {Estado.enCamino, Estado.recogido, Estado.entregado};

/// ¿El regreso todavía no puede avanzar a [destino]?
bool regresoBloqueado({
  required bool esRegreso,
  required bool idaEntregada,
  required String destino,
}) => esRegreso && !idaEntregada && pasosQueEsperanLaIda.contains(destino);

/// Lo que ve el conductor en un regreso que espera.
const String textoEsperaIda = 'Disponible cuando se entregue la ida.';
