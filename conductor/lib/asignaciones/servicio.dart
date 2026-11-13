// Un servicio de la ronda del conductor: lo que manda GET /api/v1/asignaciones/ y lo que guarda la
// base local para mostrarlo sin señal.
//
// Nunca tiene valores de cobro (valor, tarifa, factura, pagador): la API no los manda y este
// modelo no tiene dónde guardarlos. Lo vigila test/asignaciones/servicio_test.dart.
//
// La app ignora los campos que no conoce (contrato, versión 1). Si falta un campo indispensable o
// llega con otro tipo, se lanza FormatException y la respuesta entera se descarta: nunca se
// escribe en la base una lista a medias.

class Vehiculo {
  const Vehiculo({this.placa, this.vin, this.marca, this.linea, this.color});

  final String? placa;
  final String? vin;
  final String? marca;
  final String? linea;
  final String? color;

  /// Marca, línea y color en una línea ("Mazda CX-30 Rojo"), o null si no hay ninguno.
  String? get descripcion {
    final partes = [marca, linea, color].whereType<String>().toList();
    return partes.isEmpty ? null : partes.join(' ');
  }
}

class Lugar {
  const Lugar({this.direccion, this.ubicacion, this.contactoNombre, this.contactoTelefono});

  final String? direccion;

  /// Enlace o coordenadas, tal como los escribió logística (sin geocodificar).
  final String? ubicacion;
  final String? contactoNombre;

  /// Solo dígitos.
  final String? contactoTelefono;

  bool get vacio =>
      direccion == null && ubicacion == null && contactoNombre == null && contactoTelefono == null;
}

class Grua {
  const Grua({required this.id, required this.placa, required this.capacidad});

  final int id;
  final String placa;
  final int capacidad;
}

/// La configuración de la empresa que acompaña a la lista.
class ConfiguracionApp {
  const ConfiguracionApp({required this.minimoFotos, required this.momentoPlacaVin});

  /// Fotos que exigen Recogido y Entregado (1a-13).
  final int minimoFotos;

  /// `asignar` o `recoger`.
  final String momentoPlacaVin;

  factory ConfiguracionApp.desdeJson(Map<String, Object?> json) => ConfiguracionApp(
    minimoFotos: _entero(json, 'minimo_fotos'),
    momentoPlacaVin: _texto(json, 'momento_placa_vin'),
  );

  Map<String, Object?> aJson() => {
    'minimo_fotos': minimoFotos,
    'momento_placa_vin': momentoPlacaVin,
  };
}

class Servicio {
  const Servicio({
    required this.id,
    required this.solicitudId,
    required this.estado,
    required this.tipo,
    this.estadoPrevio,
    this.esRegreso = false,
    this.ordenRonda,
    this.vehiculo = const Vehiculo(),
    this.origen = const Lugar(),
    this.destino = const Lugar(),
    this.referenciaExterna,
    this.programadaPara,
    this.grua,
    this.aBordo = false,
  });

  final int id;
  final int solicitudId;

  /// `asignado`, `en_camino`, `recogido` o `novedad`.
  final String estado;

  /// Solo en `novedad`: el estado al que vuelve si logística la resuelve reanudando.
  final String? estadoPrevio;

  /// `traslado`, `evento` o `desvare`.
  final String tipo;

  /// Regreso de un evento: origen y destino ya vienen invertidos.
  final bool esRegreso;

  final int? ordenRonda;
  final Vehiculo vehiculo;

  /// Dónde se recoge el vehículo.
  final Lugar origen;

  /// Dónde se entrega. En un desvare suele venir vacío.
  final Lugar destino;

  final String? referenciaExterna;

  /// En UTC. null = inmediato.
  final DateTime? programadaPara;

  /// La grúa guardada en el servicio.
  final Grua? grua;

  /// El vehículo ocupa un puesto de la grúa (recogido, o novedad que venía de recogido).
  final bool aBordo;

  factory Servicio.desdeJson(Map<String, Object?> json) {
    final vehiculo = _mapaOpcional(json, 'vehiculo') ?? const {};
    final grua = _mapaOpcional(json, 'grua');
    return Servicio(
      id: _entero(json, 'id'),
      solicitudId: _entero(json, 'solicitud_id'),
      estado: _texto(json, 'estado'),
      estadoPrevio: _textoOpcional(json, 'estado_previo'),
      tipo: _texto(json, 'tipo'),
      esRegreso: _booleanoOpcional(json, 'es_regreso') ?? false,
      ordenRonda: _enteroOpcional(json, 'orden_ronda'),
      vehiculo: Vehiculo(
        placa: _textoOpcional(vehiculo, 'placa'),
        vin: _textoOpcional(vehiculo, 'vin'),
        marca: _textoOpcional(vehiculo, 'marca'),
        linea: _textoOpcional(vehiculo, 'linea'),
        color: _textoOpcional(vehiculo, 'color'),
      ),
      origen: _lugarDesdeJson(_mapaOpcional(json, 'origen')),
      destino: _lugarDesdeJson(_mapaOpcional(json, 'destino')),
      referenciaExterna: _textoOpcional(json, 'referencia_externa'),
      programadaPara: _fechaOpcional(json, 'programada_para'),
      grua: grua == null
          ? null
          : Grua(
              id: _entero(grua, 'id'),
              placa: _texto(grua, 'placa'),
              capacidad: _entero(grua, 'capacidad'),
            ),
      aBordo: _booleanoOpcional(json, 'a_bordo') ?? false,
    );
  }

  /// La fila de la tabla `servicios`. `posicion` es el puesto en la lista del servidor.
  Map<String, Object?> aFila(int posicion) => {
    'id': id,
    'posicion': posicion,
    'solicitud_id': solicitudId,
    'estado': estado,
    'estado_previo': estadoPrevio,
    'tipo': tipo,
    'es_regreso': esRegreso ? 1 : 0,
    'orden_ronda': ordenRonda,
    'vehiculo_placa': vehiculo.placa,
    'vehiculo_vin': vehiculo.vin,
    'vehiculo_marca': vehiculo.marca,
    'vehiculo_linea': vehiculo.linea,
    'vehiculo_color': vehiculo.color,
    'origen_direccion': origen.direccion,
    'origen_ubicacion': origen.ubicacion,
    'origen_contacto_nombre': origen.contactoNombre,
    'origen_contacto_telefono': origen.contactoTelefono,
    'destino_direccion': destino.direccion,
    'destino_ubicacion': destino.ubicacion,
    'destino_contacto_nombre': destino.contactoNombre,
    'destino_contacto_telefono': destino.contactoTelefono,
    'referencia_externa': referenciaExterna,
    'programada_para': programadaPara?.toUtc().toIso8601String(),
    'grua_id': grua?.id,
    'grua_placa': grua?.placa,
    'grua_capacidad': grua?.capacidad,
    'a_bordo': aBordo ? 1 : 0,
  };

  factory Servicio.desdeFila(Map<String, Object?> fila) {
    final gruaId = fila['grua_id'] as int?;
    final programada = fila['programada_para'] as String?;
    return Servicio(
      id: fila['id']! as int,
      solicitudId: fila['solicitud_id']! as int,
      estado: fila['estado']! as String,
      estadoPrevio: fila['estado_previo'] as String?,
      tipo: fila['tipo']! as String,
      esRegreso: fila['es_regreso'] == 1,
      ordenRonda: fila['orden_ronda'] as int?,
      vehiculo: Vehiculo(
        placa: fila['vehiculo_placa'] as String?,
        vin: fila['vehiculo_vin'] as String?,
        marca: fila['vehiculo_marca'] as String?,
        linea: fila['vehiculo_linea'] as String?,
        color: fila['vehiculo_color'] as String?,
      ),
      origen: Lugar(
        direccion: fila['origen_direccion'] as String?,
        ubicacion: fila['origen_ubicacion'] as String?,
        contactoNombre: fila['origen_contacto_nombre'] as String?,
        contactoTelefono: fila['origen_contacto_telefono'] as String?,
      ),
      destino: Lugar(
        direccion: fila['destino_direccion'] as String?,
        ubicacion: fila['destino_ubicacion'] as String?,
        contactoNombre: fila['destino_contacto_nombre'] as String?,
        contactoTelefono: fila['destino_contacto_telefono'] as String?,
      ),
      referenciaExterna: fila['referencia_externa'] as String?,
      programadaPara: programada == null ? null : DateTime.parse(programada).toUtc(),
      grua: gruaId == null
          ? null
          : Grua(
              id: gruaId,
              placa: fila['grua_placa']! as String,
              capacidad: fila['grua_capacidad']! as int,
            ),
      aBordo: fila['a_bordo'] == 1,
    );
  }
}

Lugar _lugarDesdeJson(Map<String, Object?>? json) {
  if (json == null) return const Lugar();
  final contacto = _mapaOpcional(json, 'contacto') ?? const {};
  return Lugar(
    direccion: _textoOpcional(json, 'direccion'),
    ubicacion: _textoOpcional(json, 'ubicacion'),
    contactoNombre: _textoOpcional(contacto, 'nombre'),
    contactoTelefono: _textoOpcional(contacto, 'telefono'),
  );
}

// ---------- lectura estricta del JSON ----------

Never _mal(String campo, Object? valor) =>
    throw FormatException('El campo "$campo" llegó con un valor inesperado: $valor');

String _texto(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  return valor is String ? valor : _mal(campo, valor);
}

String? _textoOpcional(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  if (valor == null) return null;
  if (valor is! String) _mal(campo, valor);
  // El contrato manda null para un texto sin dato; un texto en blanco se trata igual.
  return valor.trim().isEmpty ? null : valor;
}

int _entero(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  return valor is int ? valor : _mal(campo, valor);
}

int? _enteroOpcional(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  if (valor == null) return null;
  return valor is int ? valor : _mal(campo, valor);
}

bool? _booleanoOpcional(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  if (valor == null) return null;
  return valor is bool ? valor : _mal(campo, valor);
}

DateTime? _fechaOpcional(Map<String, Object?> json, String campo) {
  final texto = _textoOpcional(json, campo);
  if (texto == null) return null;
  final fecha = DateTime.tryParse(texto);
  return fecha == null ? _mal(campo, texto) : fecha.toUtc();
}

Map<String, Object?>? _mapaOpcional(Map<String, Object?> json, String campo) {
  final valor = json[campo];
  if (valor == null) return null;
  return valor is Map<String, Object?> ? valor : _mal(campo, valor);
}
