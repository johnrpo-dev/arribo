// La pantalla de un Recogido o de un Entregado: las fotos de evidencia y el nombre de quien entrega
// o recibe el vehículo. Solo con el mínimo de fotos y el nombre se guarda el evento. En un Recogido
// de un vehículo sin placa ni VIN (o un desvare sin placa), con la configuración "placa/VIN al
// recoger", el conductor además los digita (1a-13b) y viajan en el evento.
//
// Todo lo que el conductor hace aquí queda en la base local a medida que avanza (el paso, cada
// foto, el nombre, la placa y el VIN como van escritos), y la ruta es restaurable: si Android mata
// la app al abrir la cámara, al volver la pantalla se arma otra vez desde la base y recibe la foto
// que quedó sin entregar. Las fotos se muestran como miniaturas decodificadas en pequeño
// (`cacheWidth`), nunca la imagen completa.

import 'dart:async';
import 'dart:io';

import 'package:material_ui/material_ui.dart';

import '../cola/cola_eventos.dart';
import '../comunes.dart';
import '../formato.dart';
import '../fotos/camara.dart';
import '../fotos/foto.dart';
import '../tema.dart';
import 'componentes.dart';
import 'estados.dart';
import 'lista_asignaciones.dart';
import 'requisitos.dart';
import 'servicio.dart';

/// Cuánto se espera a que el celular diga si quedó una foto sin entregar.
const Duration esperaDeFotoPerdida = Duration(seconds: 5);

/// Ruta de la pantalla; el argumento es `{'id': <servicio>, 'destino': 'recogido' | 'entregado'}`.
const String rutaPaso = '/paso';

/// Los argumentos de [rutaPaso] (un mapa, para que la ruta se pueda restaurar).
Map<String, Object> argumentosDePaso({required int servicioId, required String destino}) => {
  'id': servicioId,
  'destino': destino,
};

class PantallaPaso extends StatefulWidget {
  const PantallaPaso({
    super.key,
    required this.servicioId,
    required this.destino,
    required this.lista,
    required this.camara,
    this.reloj = DateTime.now,
  });

  final int servicioId;

  /// `recogido` o `entregado`.
  final String destino;
  final ListaAsignaciones lista;
  final Camara camara;
  final DateTime Function() reloj;

  @override
  State<PantallaPaso> createState() => _PantallaPasoState();
}

class _PantallaPasoState extends State<PantallaPaso> {
  final _nombre = TextEditingController();
  final _placa = TextEditingController();
  final _vin = TextEditingController();

  /// El paso como está en la base; null mientras se lee (o sin conductor).
  PasoEnCurso? _paso;
  bool _cargando = true;

  /// Con la cámara abierta o guardando: no se aceptan más toques.
  bool _ocupado = false;

  /// Lo que faltaba la última vez que intentó marcar.
  List<String> _faltantes = const [];

  /// Un problema con la cámara o con la foto que se acaba de tomar.
  String? _aviso;

  /// La última escritura del nombre, la placa o el VIN en la base: se espera antes de abrir la
  /// cámara o de marcar.
  Future<void> _guardado = Future.value();

  VoidCallback? _esperaDeLaLista;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    final espera = _esperaDeLaLista;
    if (espera != null) widget.lista.removeListener(espera);
    _nombre.dispose();
    _placa.dispose();
    _vin.dispose();
    super.dispose();
  }

  /// La lista sale de la base local; al restaurar la app puede no estar leída todavía.
  Future<void> _listaCargada() {
    if (widget.lista.cargada) return Future.value();
    final lista = Completer<void>();
    void oir() {
      if (!widget.lista.cargada) return;
      widget.lista.removeListener(oir);
      _esperaDeLaLista = null;
      lista.complete();
    }

    _esperaDeLaLista = oir;
    widget.lista.addListener(oir);
    return lista.future;
  }

  Future<void> _cargar() async {
    await _listaCargada();
    if (!mounted) return;
    final conductor = widget.lista.sesion.conductor;
    final servicio = widget.lista.servicio(widget.servicioId);
    final almacen = widget.lista.fotos.almacen;
    PasoEnCurso? paso;
    if (conductor != null && servicio != null && puedeMarcar(servicio.estado, widget.destino)) {
      // Lo guardado (fotos y nombre) se ve de inmediato.
      paso = await almacen.abrirPaso(
        conductorId: conductor.id,
        servicioId: widget.servicioId,
        destino: widget.destino,
        hora: widget.reloj(),
      );
    }
    if (!mounted) return;
    setState(() {
      _paso = paso;
      _nombre.text = paso?.nombreQuien ?? '';
      _placa.text = paso?.placaDigitada ?? '';
      _vin.text = paso?.vinDigitado ?? '';
      _cargando = false;
      // Hasta saber si quedó una foto sin entregar no se abre la cámara ni se marca el paso.
      _ocupado = paso != null;
    });
    if (paso == null) return;
    try {
      await _recibirFotoPerdida();
    } finally {
      await _releer();
      if (mounted) setState(() => _ocupado = false);
    }
  }

  /// Si Android mató la app con la cámara abierta, la foto llega ahora y se agrega al paso desde el
  /// que se abrió la cámara. Si el celular no responde a tiempo, no se toca nada: la foto se
  /// recibirá la próxima vez que se abra esta pantalla.
  Future<void> _recibirFotoPerdida() async {
    const sinRespuesta = Object();
    final Object? ruta = await widget.camara
        .recuperarFotoPerdida()
        .then<Object?>((ruta) => ruta)
        .timeout(esperaDeFotoPerdida, onTimeout: () => sinRespuesta);
    if (identical(ruta, sinRespuesta)) return;
    await widget.lista.fotos.almacen.entregarFotoPerdida(ruta as String?, hora: widget.reloj());
  }

  Future<void> _releer() async {
    final paso = _paso;
    if (paso == null) return;
    final leido = await widget.lista.fotos.almacen.leerPaso(
      conductorId: paso.conductorId,
      servicioId: paso.servicioId,
      destino: paso.destino,
    );
    if (mounted && leido != null) setState(() => _paso = leido);
  }

  void _alEscribirNombre(String texto) {
    final paso = _paso;
    if (paso == null) return;
    _guardado = widget.lista.fotos.almacen.guardarNombre(paso, texto);
    if (_faltantes.isNotEmpty) setState(() => _faltantes = const []);
  }

  void _alEscribirPlaca(String texto) {
    final paso = _paso;
    if (paso == null) return;
    _guardado = widget.lista.fotos.almacen.guardarIdentificacion(paso, placa: texto);
    if (_faltantes.isNotEmpty) setState(() => _faltantes = const []);
  }

  void _alEscribirVin(String texto) {
    final paso = _paso;
    if (paso == null) return;
    _guardado = widget.lista.fotos.almacen.guardarIdentificacion(paso, vin: texto);
    if (_faltantes.isNotEmpty) setState(() => _faltantes = const []);
  }

  /// Los datos que la pantalla pide digitar en este paso, o null si ninguno.
  ({bool placa, bool vin})? _porDigitar(Servicio? servicio) =>
      servicio == null || widget.destino != Estado.recogido
      ? null
      : widget.lista.identificacionPorDigitar(servicio);

  Future<void> _tomarFoto() async {
    final paso = _paso;
    if (_ocupado || paso == null) return;
    final almacen = widget.lista.fotos.almacen;
    setState(() {
      _ocupado = true;
      _aviso = null;
      _faltantes = const [];
    });
    try {
      // Antes de abrir la cámara todo queda en la base: desde aquí Android puede matar la app.
      await _guardado;
      await almacen.camaraAbierta(paso, hora: widget.reloj());
      final String? ruta;
      try {
        ruta = await widget.camara.tomarFoto();
      } catch (_) {
        await almacen.camaraCerrada(paso);
        rethrow;
      }
      if (ruta == null) {
        await almacen.camaraCerrada(paso);
      } else {
        await almacen.agregarFoto(paso, ruta, hora: widget.reloj());
      }
    } on ErrorDeCamara catch (error) {
      _aviso = error.mensaje;
    } on FotoNoValida catch (error) {
      _aviso = error.mensaje;
    } finally {
      await _releer();
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _quitarFoto(FotoLocal foto, int numero) async {
    if (_ocupado) return;
    final quitar = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('¿Quitar la foto $numero?'),
        content: const Text('La foto se borra del celular. Puede tomar otra.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Quitar foto'),
          ),
        ],
      ),
    );
    if (quitar != true) return;
    await widget.lista.fotos.almacen.quitarFoto(foto);
    await _releer();
  }

  Future<void> _marcar(int minimoFotos) async {
    final paso = _paso;
    if (_ocupado || paso == null) return;
    final nombre = _nombre.text.trim();
    final servicio = widget.lista.servicio(widget.servicioId);
    final porDigitar = _porDigitar(servicio);
    final placa = porDigitar?.placa ?? false ? _placa.text : '';
    final vin = porDigitar?.vin ?? false ? _vin.text : '';
    final faltantes = [
      if (servicio != null && porDigitar != null)
        ...faltantesDeIdentificacion(servicio, placaDigitada: placa, vinDigitado: vin),
      ...faltantesDelPaso(
        destino: paso.destino,
        fotos: paso.fotos.length,
        minimoFotos: minimoFotos,
        nombreQuien: nombre,
      ),
    ];
    if (faltantes.isNotEmpty) {
      setState(() => _faltantes = faltantes);
      return;
    }
    setState(() => _ocupado = true);
    try {
      await _guardado;
      // Primero queda guardado en la cola, con sus fotos; después se cierra la pantalla.
      await widget.lista.confirmarPaso(
        paso,
        nombreQuien: nombre,
        placaDigitada: placa,
        vinDigitado: vin,
      );
      if (mounted) Navigator.of(context).pop();
    } on ToqueNoValido catch (error) {
      if (mounted) setState(() => _faltantes = [error.mensaje]);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final paso = nombreEstado(widget.destino);
    return ListenableBuilder(
      listenable: widget.lista,
      builder: (context, _) {
        final servicio = widget.lista.cargada ? widget.lista.servicio(widget.servicioId) : null;
        final enCurso = _paso;
        final minimoFotos = widget.lista.configuracion?.minimoFotos ?? 0;
        final listo = !_cargando && servicio != null && enCurso != null;
        return Scaffold(
          appBar: AppBar(title: Text('Marcar $paso')),
          body: _cargando
              ? const Center(child: CircularProgressIndicator())
              : !listo
              ? _SinPaso(paso: paso, enLaLista: servicio != null)
              : _Contenido(
                  servicio: servicio,
                  paso: enCurso,
                  minimoFotos: minimoFotos,
                  porDigitar: _porDigitar(servicio),
                  placa: _placa,
                  vin: _vin,
                  nombre: _nombre,
                  ocupado: _ocupado,
                  aviso: _aviso,
                  faltantes: _faltantes,
                  alEscribirPlaca: _alEscribirPlaca,
                  alEscribirVin: _alEscribirVin,
                  alEscribirNombre: _alEscribirNombre,
                  alTomarFoto: _tomarFoto,
                  alQuitarFoto: _quitarFoto,
                ),
          bottomNavigationBar: !listo
              ? null
              : Material(
                  color: context.colores.superficie,
                  shape: Border(top: BorderSide(color: context.colores.borde)),
                  child: SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                      child: FilledButton(
                        key: const Key('confirmar'),
                        onPressed: _ocupado ? null : () => _marcar(minimoFotos),
                        child: Text('Marcar $paso', textAlign: TextAlign.center),
                      ),
                    ),
                  ),
                ),
        );
      },
    );
  }
}

/// El paso no se puede preparar: el servicio salió de la lista, o ese paso ya no es el que sigue
/// (por ejemplo, ya se marcó).
class _SinPaso extends StatelessWidget {
  const _SinPaso({required this.paso, required this.enLaLista});

  final String paso;
  final bool enLaLista;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(
          enLaLista
              ? '$paso ya no es el paso que sigue en este servicio. Vuelva al servicio.'
              : 'Este servicio ya no está en su lista.',
          style: Theme.of(context).textTheme.bodyLarge,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class _Contenido extends StatelessWidget {
  const _Contenido({
    required this.servicio,
    required this.paso,
    required this.minimoFotos,
    required this.porDigitar,
    required this.placa,
    required this.vin,
    required this.nombre,
    required this.ocupado,
    required this.aviso,
    required this.faltantes,
    required this.alEscribirPlaca,
    required this.alEscribirVin,
    required this.alEscribirNombre,
    required this.alTomarFoto,
    required this.alQuitarFoto,
  });

  final Servicio servicio;
  final PasoEnCurso paso;
  final int minimoFotos;

  /// Los datos de identificación que el conductor debe digitar; null si ninguno.
  final ({bool placa, bool vin})? porDigitar;
  final TextEditingController placa;
  final TextEditingController vin;
  final TextEditingController nombre;
  final bool ocupado;
  final String? aviso;
  final List<String> faltantes;
  final ValueChanged<String> alEscribirPlaca;
  final ValueChanged<String> alEscribirVin;
  final ValueChanged<String> alEscribirNombre;
  final VoidCallback alTomarFoto;
  final void Function(FotoLocal foto, int numero) alQuitarFoto;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final vehiculo = [
      identificacionDe(servicio.vehiculo),
      ?servicio.vehiculo.descripcion,
    ].join(' · ');
    final fotos = paso.fotos;
    final porDigitar = this.porDigitar;
    // Pocos elementos: todos se construyen (no una lista perezosa), y el botón de la cámara va
    // antes de las miniaturas para que no cambie de sitio con cada foto.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(vehiculo, style: textos.headlineSmall),
          const SizedBox(height: 20),
          if (porDigitar != null) ...[
            Text('Identificación del vehículo', style: textos.titleMedium),
            const SizedBox(height: 4),
            Text(
              porDigitar.vin
                  ? 'Este servicio no tiene placa ni VIN. Escriba al menos uno, como se ve en '
                        'el vehículo.'
                  : 'Un desvare exige la placa y este servicio no la tiene. Escríbala como se '
                        've en el vehículo.',
              key: const Key('pide-identificacion'),
              style: textos.bodyLarge,
            ),
            if (porDigitar.placa) ...[
              const SizedBox(height: 12),
              _CampoIdentificacion(
                key: const Key('placa-digitada'),
                controlador: placa,
                etiqueta: 'Placa',
                alEscribir: alEscribirPlaca,
              ),
            ],
            if (porDigitar.vin) ...[
              const SizedBox(height: 12),
              _CampoIdentificacion(
                key: const Key('vin-digitado'),
                controlador: vin,
                etiqueta: 'VIN',
                alEscribir: alEscribirVin,
              ),
            ],
            const SizedBox(height: 24),
          ],
          Text('Fotos', style: textos.titleMedium),
          const SizedBox(height: 4),
          Text(
            textoDeFotos(fotos.length, minimoFotos),
            key: const Key('cuenta-fotos'),
            style: textos.bodyLarge,
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            key: const Key('tomar-foto'),
            onPressed: ocupado ? null : alTomarFoto,
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text('Tomar foto'),
          ),
          if (aviso != null) ...[
            const SizedBox(height: 12),
            Recuadro(aviso!, tipo: TipoRecuadro.error),
          ],
          if (fotos.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final (posicion, foto) in fotos.indexed)
                  MiniaturaFoto(
                    key: ValueKey(foto.id),
                    foto: foto,
                    numero: posicion + 1,
                    alTocar: ocupado ? null : () => alQuitarFoto(foto, posicion + 1),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Toque una foto para quitarla.',
              style: textos.bodySmall?.copyWith(color: context.colores.textoSecundario),
            ),
          ],
          const SizedBox(height: 24),
          TextField(
            key: const Key('nombre-quien'),
            controller: nombre,
            style: textos.bodyLarge,
            textCapitalization: TextCapitalization.words,
            textInputAction: TextInputAction.done,
            decoration: InputDecoration(labelText: etiquetaDeQuien(paso.destino)),
            onChanged: alEscribirNombre,
          ),
          if (faltantes.isNotEmpty) ...[
            const SizedBox(height: 16),
            Recuadro(faltantes.join(' '), key: const Key('faltantes'), tipo: TipoRecuadro.error),
          ],
        ],
      ),
    );
  }
}

/// Una placa o un VIN como se leen en el vehículo: en mayúsculas y sin autocorrección.
class _CampoIdentificacion extends StatelessWidget {
  const _CampoIdentificacion({
    super.key,
    required this.controlador,
    required this.etiqueta,
    required this.alEscribir,
  });

  final TextEditingController controlador;
  final String etiqueta;
  final ValueChanged<String> alEscribir;

  @override
  Widget build(BuildContext context) => TextField(
    controller: controlador,
    style: Theme.of(context).textTheme.bodyLarge,
    textCapitalization: TextCapitalization.characters,
    autocorrect: false,
    enableSuggestions: false,
    textInputAction: TextInputAction.next,
    decoration: InputDecoration(labelText: etiqueta),
    onChanged: alEscribir,
  );
}

/// "Lleva 2 de 4 fotos." o, sin mínimo, "Lleva 2 fotos. No son obligatorias."
String textoDeFotos(int fotos, int minimoFotos) {
  final cuantas = fotos == 1 ? '1 foto' : '$fotos fotos';
  if (minimoFotos <= 0) return 'Lleva $cuantas. No son obligatorias.';
  return fotos >= minimoFotos
      ? 'Lleva $cuantas. El mínimo es $minimoFotos.'
      : 'Lleva $fotos de $minimoFotos fotos.';
}

/// Una foto en pequeño. La imagen se decodifica ya reducida al tamaño en que se muestra
/// (`cacheWidth`): la foto completa nunca se carga en memoria.
class MiniaturaFoto extends StatelessWidget {
  const MiniaturaFoto({super.key, required this.foto, required this.numero, this.alTocar});

  /// Lado de la miniatura, en puntos de pantalla.
  static const double lado = 96;

  final FotoLocal foto;
  final int numero;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final pixeles = (lado * MediaQuery.devicePixelRatioOf(context)).round();
    return Semantics(
      button: alTocar != null,
      label: 'Foto $numero. Toque para quitarla.',
      child: InkWell(
        onTap: alTocar,
        child: ClipRRect(
          borderRadius: const BorderRadius.all(Radius.circular(8)),
          child: Image.file(
            File(foto.ruta),
            width: lado,
            height: lado,
            fit: BoxFit.cover,
            cacheWidth: pixeles,
            excludeFromSemantics: true,
            errorBuilder: (context, error, stackTrace) => Container(
              width: lado,
              height: lado,
              color: context.colores.fondo,
              alignment: Alignment.center,
              child: Icon(Icons.broken_image_outlined, color: context.colores.textoSecundario),
            ),
          ),
        ),
      ),
    );
  }
}
