// Los estados de un servicio como los ve la app del conductor.
//
// La regla vive en el servidor (backend/nucleo/estados.py) y es él quien decide. La app la repite
// solo para dos cosas: ofrecer el botón del paso que sigue y mostrar de inmediato el estado con los
// toques que aún no se han enviado. Si esta copia y el servidor no coinciden, el evento llega como
// conflicto y logística lo revisa: nada se pierde. Lo vigila test/asignaciones/estados_test.dart.

abstract final class Estado {
  static const asignado = 'asignado';
  static const enCamino = 'en_camino';
  static const recogido = 'recogido';
  static const entregado = 'entregado';
  static const novedad = 'novedad';
  static const cancelado = 'cancelado';
}

/// Los cuatro botones del conductor (`DESTINOS_DESDE_LA_APP` en el servidor). Cancelar es de logística.
const Set<String> destinosDesdeLaApp = {
  Estado.enCamino,
  Estado.recogido,
  Estado.entregado,
  Estado.novedad,
};

/// Sin saltos ni retrocesos (`AVANCE`). Asignar lo hace logística, no la app.
const Map<String, String> _avance = {
  Estado.asignado: Estado.enCamino,
  Estado.enCamino: Estado.recogido,
  Estado.recogido: Estado.entregado,
};

/// `NOVEDAD_DESDE`.
const Set<String> _novedadDesde = {Estado.asignado, Estado.enCamino, Estado.recogido};

/// El paso que sigue a [estado], o null si no hay (entregado, cancelado, o una novedad abierta: de
/// una novedad solo se sale cuando logística la resuelve).
String? siguientePaso(String estado) => _avance[estado];

bool admiteNovedad(String estado) => _novedadDesde.contains(estado);

/// ¿Se puede marcar [destino] desde la app con el servicio en [estado]?
bool puedeMarcar(String estado, String destino) =>
    destino == Estado.novedad ? admiteNovedad(estado) : _avance[estado] == destino;

/// El estado de un servicio: lo que confirmó el servidor, o eso más los toques sin enviar.
class EstadoDeServicio {
  const EstadoDeServicio(this.estado, [this.estadoPrevio]);

  final String estado;

  /// Solo en una novedad: el estado que tenía antes.
  final String? estadoPrevio;

  /// El vehículo ocupa un puesto de la grúa: recogido, o novedad que venía de recogido.
  bool get aBordo =>
      estado == Estado.recogido || (estado == Estado.novedad && estadoPrevio == Estado.recogido);

  /// Como queda al marcar [destino]; el mismo si ese paso no sigue al estado actual.
  EstadoDeServicio marcar(String destino) {
    if (!puedeMarcar(estado, destino)) return this;
    return destino == Estado.novedad
        ? EstadoDeServicio(Estado.novedad, estado)
        : EstadoDeServicio(destino);
  }

  /// El estado que ve el conductor: el confirmado más sus toques pendientes, en el orden en que
  /// los hizo. Un toque que no encaja (por ejemplo, el servidor ya lo aplicó y la respuesta se
  /// perdió, o logística cambió el servicio) no mueve el estado: el servidor dirá qué pasó con él.
  EstadoDeServicio conPendientes(Iterable<String> destinos) =>
      destinos.fold(this, (estado, destino) => estado.marcar(destino));
}
