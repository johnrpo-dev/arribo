// El servicio que el conductor está atendiendo ahora: el que la lista pone arriba, con su botón
// del paso que sigue.

import 'estados.dart';
import 'servicio.dart';

/// En el orden de la lista: el primero en camino o recogido (ya empezó); si no hay, el primero
/// asignado que no espera a su ida. Nunca uno en novedad, cancelado, entregado o pendiente de
/// asignar. null si no hay ninguno.
Servicio? servicioActivo(List<Servicio> servicios) {
  for (final servicio in servicios) {
    if (servicio.estado == Estado.enCamino || servicio.estado == Estado.recogido) return servicio;
  }
  for (final servicio in servicios) {
    if (servicio.estado == Estado.asignado && !servicio.esperaIda) return servicio;
  }
  return null;
}
