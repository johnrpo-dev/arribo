// Placa y VIN del vehículo: normalización y la regla de identificación al recoger.
//
// Copia de backend/nucleo/identificacion.py. El servidor decide: un Recogido de un vehículo sin
// placa ni VIN (o un desvare sin placa) queda como conflicto `identificacion_incompleta`. La app
// lo bloquea antes y le dice al conductor qué falta. Las dos copias cumplen los mismos casos de
// docs/casos-reglas.json (test/casos_compartidos_test.dart).

const int largoVin = 17;

final _noAlfanumerico = RegExp(r'[^A-Z0-9]');
final _separadoresVin = RegExp(r'[\s-]');

/// Letras y dígitos sin I, O ni Q (se confunden con 1 y 0). No se valida el dígito verificador.
final _vinValido = RegExp('^[A-HJ-NPR-Z0-9]{$largoVin}\$');

/// Momentos en que se puede exigir la placa o el VIN, en el orden en que ocurren.
abstract final class MomentoIdentificacion {
  static const alAsignar = 'asignar';
  static const alRecoger = 'recoger';

  static const orden = [alAsignar, alRecoger];
}

/// Mayúsculas y solo letras y dígitos: "abc-123" y "ABC 123" dan "ABC123".
String normalizarPlaca(String? texto) =>
    (texto ?? '').toUpperCase().replaceAll(_noAlfanumerico, '');

/// Mayúsculas, sin espacios ni guiones. Otros símbolos se dejan: [vinValido] los rechaza.
String normalizarVin(String? texto) => (texto ?? '').toUpperCase().replaceAll(_separadoresVin, '');

/// Un VIN ya normalizado: exactamente 17 letras o dígitos, sin I, O ni Q.
bool vinValido(String vin) => _vinValido.hasMatch(vin);

/// Lo que le falta al vehículo para recogerlo (`validar_identificacion`), o null si está completo:
/// placa o VIN, al menos uno; un desvare exige la placa. Solo revisa que estén.
String? identificacionFaltante({
  required String? placa,
  required String? vin,
  required String tipo,
}) {
  final tienePlaca = normalizarPlaca(placa).isNotEmpty;
  if (tipo == 'desvare' && !tienePlaca) return 'Un desvare exige la placa del vehículo.';
  if (!tienePlaca && normalizarVin(vin).isEmpty) {
    return 'El vehículo necesita placa o VIN (al menos uno).';
  }
  return null;
}

/// ¿Se exige la placa o el VIN en [momentoActual]? Desde el momento configurado en adelante: al
/// recoger se exige siempre. Una configuración que esta versión no conoce exige (lo más estricto).
bool identificacionExigida(String momentoConfigurado, String momentoActual) =>
    MomentoIdentificacion.orden.indexOf(momentoActual) >=
    MomentoIdentificacion.orden.indexOf(momentoConfigurado);
