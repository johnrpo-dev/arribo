// Textos para el conductor: fechas en hora de Colombia y nombres de estados y tipos.
//
// La API manda las fechas en UTC. La app las muestra en hora de Colombia (America/Bogota, UTC−5,
// sin horario de verano), sin depender de la zona horaria configurada en el celular.

const Duration _desfaseColombia = Duration(hours: -5);

/// La hora de pared en Colombia. El resultado se marca como UTC solo para leer sus campos.
DateTime enHoraDeColombia(DateTime fecha) => fecha.toUtc().add(_desfaseColombia);

const _dias = ['lun.', 'mar.', 'mié.', 'jue.', 'vie.', 'sáb.', 'dom.'];
const _meses = [
  'ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.', //
  'jul.', 'ago.', 'sep.', 'oct.', 'nov.', 'dic.',
];

/// "2:30 p. m."
String horaCorta(DateTime fecha) {
  final c = enHoraDeColombia(fecha);
  final hora = c.hour % 12 == 0 ? 12 : c.hour % 12;
  final minutos = c.minute.toString().padLeft(2, '0');
  return '$hora:$minutos ${c.hour < 12 ? 'a. m.' : 'p. m.'}';
}

/// "hoy", "mañana" o "ayer" según el día en Colombia; null para otro día.
String? diaRelativo(DateTime fecha, {required DateTime ahora}) {
  final dia = _soloDia(enHoraDeColombia(fecha));
  final hoy = _soloDia(enHoraDeColombia(ahora));
  return switch (dia.difference(hoy).inDays) {
    0 => 'hoy',
    1 => 'mañana',
    -1 => 'ayer',
    _ => null,
  };
}

/// "vie. 20 nov." (con el año si no es el de [ahora]).
String fechaCorta(DateTime fecha, {required DateTime ahora}) {
  final c = enHoraDeColombia(fecha);
  final texto = '${_dias[c.weekday - 1]} ${c.day} ${_meses[c.month - 1]}';
  return c.year == enHoraDeColombia(ahora).year ? texto : '$texto ${c.year}';
}

/// "Hoy, 2:30 p. m.", "Mañana, 8:00 a. m." o "vie. 20 nov., 2:30 p. m.".
String fechaYHora(DateTime fecha, {required DateTime ahora}) {
  final relativo = diaRelativo(fecha, ahora: ahora);
  final dia = relativo == null
      ? fechaCorta(fecha, ahora: ahora)
      : '${relativo[0].toUpperCase()}${relativo.substring(1)}';
  return '$dia, ${horaCorta(fecha)}';
}

/// Cuándo hay que hacer el servicio. null en la API significa inmediato.
String textoProgramada(DateTime? programada, {required DateTime ahora}) =>
    programada == null ? 'Inmediato' : fechaYHora(programada, ahora: ahora);

/// "Actualizado hoy, 2:30 p. m." / "Actualizado el vie. 20 nov., 2:30 p. m.".
String textoUltimaActualizacion(DateTime? hora, {required DateTime ahora}) {
  if (hora == null) return 'La lista aún no se ha descargado.';
  final relativo = diaRelativo(hora, ahora: ahora);
  final dia = relativo ?? 'el ${fechaCorta(hora, ahora: ahora)}';
  return 'Actualizado $dia, ${horaCorta(hora)}';
}

DateTime _soloDia(DateTime f) => DateTime.utc(f.year, f.month, f.day);

/// "310 222 3344" para leerlo de un vistazo. Si no tiene 7 o 10 dígitos, tal cual.
String telefonoLegible(String telefono) => switch (telefono.length) {
  10 => '${telefono.substring(0, 3)} ${telefono.substring(3, 6)} ${telefono.substring(6)}',
  7 => '${telefono.substring(0, 3)} ${telefono.substring(3)}',
  _ => telefono,
};

String nombreEstado(String estado) => switch (estado) {
  'pendiente_asignar' => 'Pendiente de asignar',
  'asignado' => 'Asignado',
  'en_camino' => 'En camino',
  'recogido' => 'Recogido',
  'entregado' => 'Entregado',
  'cancelado' => 'Cancelado',
  'novedad' => 'Novedad',
  _ => estado,
};

String nombreTipo(String tipo) => switch (tipo) {
  'traslado' => 'Traslado',
  'evento' => 'Evento',
  'desvare' => 'Desvare',
  _ => tipo,
};
