// Placa y VIN del vehículo: normalización y la regla de identificación al recoger.
//
// El vehículo se identifica con placa, VIN o número de bodega (al menos uno). El número de bodega
// lo escribe la oficina; el conductor solo digita placa o VIN.
//
// Copia de backend/nucleo/identificacion.py. El servidor decide: un Recogido de un vehículo sin
// placa, VIN ni número de bodega (o un desvare sin placa), sin que el evento los traiga digitados, queda como
// conflicto `identificacion_incompleta`. La app pide digitarlos antes (1a-13b) y le dice al
// conductor qué falta. Las dos copias cumplen los mismos casos de docs/casos-reglas.json
// (test/casos_compartidos_test.dart).

const int largoVin = 17;

/// Lo que cabe en la placa del vehículo en el servidor.
const int largoMaximoPlaca = 10;

final _noAlfanumerico = RegExp(r'[^A-Z0-9]');
final _separadoresVin = RegExp(r'[\s-]');

/// Letras y dígitos sin I, O ni Q (se confunden con 1 y 0). No se valida el dígito verificador.
final _vinValido = RegExp('^[A-HJ-NPR-Z0-9]{$largoVin}\$');

final _placaValida = RegExp('^[A-Z0-9]{1,$largoMaximoPlaca}\$');

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

final _espacios = RegExp(r'\s');

/// Mayúsculas y sin espacios (`normalizar_numero_bodega`): " b 1024 " da "B1024".
String normalizarNumeroBodega(String? texto) =>
    (texto ?? '').toUpperCase().replaceAll(_espacios, '');

/// Una placa ya normalizada: de 1 a 10 letras o dígitos (`validar_placa`).
bool placaValida(String placa) => _placaValida.hasMatch(placa);

/// Lo que le falta al vehículo para recogerlo (`validar_identificacion`), o null si está completo:
/// placa, VIN o número de bodega, al menos uno; un desvare exige la placa. Solo revisa que estén.
String? identificacionFaltante({
  required String? placa,
  required String? vin,
  required String tipo,
  required String? numeroBodega,
}) {
  final tienePlaca = normalizarPlaca(placa).isNotEmpty;
  if (tipo == 'desvare' && !tienePlaca) return 'Un desvare exige la placa del vehículo.';
  if (!tienePlaca && normalizarVin(vin).isEmpty && normalizarNumeroBodega(numeroBodega).isEmpty) {
    return 'El vehículo necesita placa, VIN o número de bodega (al menos uno).';
  }
  return null;
}

/// ¿Se exige la placa o el VIN en [momentoActual]? Desde el momento configurado en adelante: al
/// recoger se exige siempre. Una configuración que esta versión no conoce exige (lo más estricto).
bool identificacionExigida(String momentoConfigurado, String momentoActual) =>
    MomentoIdentificacion.orden.indexOf(momentoActual) >=
    MomentoIdentificacion.orden.indexOf(momentoConfigurado);

// ---------- placa o VIN digitados al recoger (1a-13b) ----------

/// [identificacionFaltante] de un Recogido con lo que el vehículo tiene y, donde le falte, lo que
/// el conductor digitó al recogerlo (`validar_identificacion_al_recoger`). Lo digitado cuenta
/// aunque esté mal formado: solo revisa que esté. El formato lo revisan [placaValida] y
/// [vinValido].
String? identificacionFaltanteAlRecoger({
  required String? placaGuardada,
  required String? vinGuardado,
  required String? placaDigitada,
  required String? vinDigitado,
  required String tipo,
  required String? numeroBodega,
}) => identificacionFaltante(
  placa: _primero(normalizarPlaca(placaGuardada), normalizarPlaca(placaDigitada)),
  vin: _primero(normalizarVin(vinGuardado), normalizarVin(vinDigitado)),
  tipo: tipo,
  numeroBodega: numeroBodega,
);

String _primero(String guardado, String digitado) => guardado.isNotEmpty ? guardado : digitado;

/// Los datos de la identificación del vehículo (`CampoIdentificacion`).
abstract final class CampoIdentificacion {
  static const placa = 'placa';
  static const vin = 'vin';
}

/// Por qué un dato digitado al recoger no quedó en el vehículo (`Revision`).
abstract final class Revision {
  /// El vehículo ya tenía otro: no se sobreescribe.
  static const distinto = 'distinto';

  /// No cumple el formato.
  static const invalido = 'invalido';

  /// Otro vehículo ya lo tiene. Solo lo sabe el servidor.
  static const deOtroVehiculo = 'de_otro_vehiculo';
}

class DatoPorRevisar {
  const DatoPorRevisar(this.campo, this.digitado, this.revision, {this.existente = ''});

  final String campo;

  /// Normalizado.
  final String digitado;
  final String revision;

  /// El dato que ya tenía el vehículo (en [Revision.distinto]); vacío si no.
  final String existente;
}

/// Lo que la placa y el VIN digitados al recoger hacen con la identificación del vehículo.
class Complemento {
  const Complemento({
    required this.placa,
    required this.vin,
    required this.nuevos,
    required this.porRevisar,
  });

  /// La placa que queda en el vehículo (normalizada; vacía si no tiene).
  final String placa;
  final String vin;

  /// Los datos que se completan con lo digitado.
  final List<String> nuevos;
  final List<DatoPorRevisar> porRevisar;
}

/// La placa y el VIN digitados al recoger, comparados con los del vehículo
/// (`completar_identificacion`). Por cada dato digitado (normalizado; vacío = no digitado): si el
/// vehículo no lo tiene y es válido, se completa con él; si es igual, nada; si el vehículo ya tiene
/// otro, no se sobreescribe (queda por revisar); si no es válido, no se guarda (queda por revisar).
Complemento completarIdentificacion({
  required String? placaGuardada,
  required String? vinGuardado,
  required String? placaDigitada,
  required String? vinDigitado,
}) {
  final quedan = {
    CampoIdentificacion.placa: normalizarPlaca(placaGuardada),
    CampoIdentificacion.vin: normalizarVin(vinGuardado),
  };
  final nuevos = <String>[];
  final porRevisar = <DatoPorRevisar>[];
  for (final (campo, digitado, valido) in [
    (CampoIdentificacion.placa, normalizarPlaca(placaDigitada), placaValida),
    (CampoIdentificacion.vin, normalizarVin(vinDigitado), vinValido),
  ]) {
    final guardado = quedan[campo]!;
    if (digitado.isEmpty || digitado == guardado) continue;
    if (!valido(digitado)) {
      porRevisar.add(DatoPorRevisar(campo, digitado, Revision.invalido));
    } else if (guardado.isNotEmpty) {
      porRevisar.add(DatoPorRevisar(campo, digitado, Revision.distinto, existente: guardado));
    } else {
      quedan[campo] = digitado;
      nuevos.add(campo);
    }
  }
  return Complemento(
    placa: quedan[CampoIdentificacion.placa]!,
    vin: quedan[CampoIdentificacion.vin]!,
    nuevos: nuevos,
    porRevisar: porRevisar,
  );
}
