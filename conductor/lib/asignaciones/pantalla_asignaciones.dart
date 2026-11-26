// La lista de servicios del conductor, en el orden de su ronda. Se muestra siempre desde la base
// local y se refresca al abrir, al volver a primer plano y al deslizar hacia abajo.

import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../comunes.dart';
import '../formato.dart';
import '../ingreso/sesion.dart';
import '../preferencia_tema.dart';
import '../tema.dart';
import 'componentes.dart';
import 'enlaces.dart';
import 'lista_asignaciones.dart';
import 'servicio.dart';

/// Ruta del detalle; el argumento es el id del servicio. Es restaurable: si el sistema mata la app
/// con el detalle abierto, vuelve a él (los datos salen de la base local).
const String rutaServicio = '/servicio';

class PantallaAsignaciones extends StatefulWidget {
  const PantallaAsignaciones({
    super.key,
    required this.lista,
    required this.sesion,
    required this.abrirEnlace,
    this.reloj = DateTime.now,
    this.tema,
  });

  final ListaAsignaciones lista;
  final Sesion sesion;
  final AbrirEnlace abrirEnlace;
  final DateTime Function() reloj;

  /// El tema elegido; con él, el menú ofrece cambiarlo.
  final PreferenciaTema? tema;

  @override
  State<PantallaAsignaciones> createState() => _PantallaAsignacionesState();
}

class _PantallaAsignacionesState extends State<PantallaAsignaciones> {
  late final AppLifecycleListener _ciclo;

  @override
  void initState() {
    super.initState();
    // Al volver a primer plano se envía lo pendiente y se refresca la lista (en ese orden).
    _ciclo = AppLifecycleListener(
      onResume: () {
        widget.lista.sincronizador.enPrimerPlano = true;
        widget.lista.fotos.enPrimerPlano = true;
        widget.lista.actualizar();
      },
      onPause: () {
        widget.lista.sincronizador.enPrimerPlano = false;
        widget.lista.fotos.enPrimerPlano = false;
      },
    );
    _iniciar();
  }

  /// Al abrir la app (o al ingresar): la lista guardada, y después enviar lo pendiente y refrescar.
  Future<void> _iniciar() async {
    await widget.lista.cargarLocal();
    await widget.lista.actualizar();
  }

  /// Con cambios o fotos sin enviar no se cierra sesión: se explica por qué y se intenta enviarlos.
  Future<void> _explicarPendientes(int pendientes, int fotos) {
    widget.lista.actualizar();
    final cambios = pendientes == 1 ? '1 cambio' : '$pendientes cambios';
    final cuantasFotos = fotos == 1 ? '1 foto' : '$fotos fotos';
    final cuantos = fotos == 0
        ? (pendientes == 1
              ? 'Hay 1 cambio pendiente por enviar.'
              : 'Hay $pendientes cambios pendientes por enviar.')
        : pendientes == 0
        ? (fotos == 1
              ? 'Hay 1 foto pendiente por subir.'
              : 'Hay $fotos fotos pendientes por subir.')
        : 'Hay $cambios y $cuantasFotos pendientes por enviar.';
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Todavía no puede cerrar sesión'),
        content: Text(
          '$cuantos Se envían con su sesión: si la cierra antes, no llegarían a su nombre. '
          'Busque señal y espere a que se envíen.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Entendido')),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _ciclo.dispose();
    super.dispose();
  }

  Future<void> _salir() async {
    final pendientes = widget.lista.sincronizador.pendientes;
    final fotos = widget.lista.fotos.pendientes;
    if (pendientes + fotos > 0) return _explicarPendientes(pendientes, fotos);
    final confirmado = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('¿Cerrar sesión?'),
        content: const Text('Para volver a entrar necesitará su celular y su PIN.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Cerrar sesión'),
          ),
        ],
      ),
    );
    if (confirmado != true || !mounted) return;
    final mensajero = ScaffoldMessenger.of(context);
    final resultado = await widget.sesion.salir();
    if (resultado == ResultadoSalida.hayPendientes) {
      // La sesión volvió a revisar la base y encontró algo sin enviar (por ejemplo, un toque hecho
      // mientras el diálogo estaba abierto).
      mensajero.showSnackBar(
        const SnackBar(
          content: Text(
            'No se puede cerrar sesión: hay cambios o fotos sin enviar, y se envían con su '
            'sesión. Espere a tener señal.',
          ),
        ),
      );
    }
  }

  /// Automático, claro u oscuro: al tocar la opción se cierra el diálogo y el tema se aplica y se
  /// guarda.
  Future<void> _elegirTema(PreferenciaTema tema) {
    // Un segundo toque mientras el diálogo se cierra no debe cerrar también la lista.
    var cerrado = false;
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Tema'),
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        // Con letra grande y el celular acostado, las opciones se desplazan en vez de no caber.
        content: SingleChildScrollView(
          child: RadioGroup<ThemeMode>(
            groupValue: tema.value,
            onChanged: (modo) {
              if (modo == null || cerrado) return;
              cerrado = true;
              Navigator.of(context).pop();
              unawaited(tema.elegir(modo));
            },
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final opcion in opcionesDeTema)
                  RadioListTile<ThemeMode>(
                    key: Key('tema-${opcion.modo.name}'),
                    value: opcion.modo,
                    minTileHeight: 56,
                    title: Text(opcion.nombre),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final nombre = widget.sesion.conductor?.nombre;
    final tema = widget.tema;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mis servicios'),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            icon: const Icon(Icons.refresh),
            onPressed: widget.lista.actualizar,
          ),
          PopupMenuButton<String>(
            tooltip: 'Más opciones',
            onSelected: (opcion) {
              if (opcion == 'salir') _salir();
              if (opcion == 'tema' && tema != null) _elegirTema(tema);
            },
            itemBuilder: (context) => [
              if (nombre != null) PopupMenuItem(enabled: false, child: Text(nombre)),
              if (tema != null) const PopupMenuItem(value: 'tema', child: Text('Tema')),
              const PopupMenuItem(value: 'salir', child: Text('Cerrar sesión')),
            ],
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: widget.lista,
        builder: (context, _) {
          final lista = widget.lista;
          if (!lista.cargada) return const Center(child: CircularProgressIndicator());
          final ahora = widget.reloj();
          return RefreshIndicator(
            onRefresh: lista.actualizar,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
              children: [
                _EstadoDeLaLista(lista: lista, ahora: ahora),
                const SizedBox(height: 12),
                if (lista.servicios.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 32),
                    child: Text(
                      lista.ultimaActualizacion == null
                          ? 'Cuando haya señal aparecerán aquí sus servicios.'
                          : 'No tiene servicios asignados.',
                      style: Theme.of(context).textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                  ),
                for (final servicio in lista.servicios) ...[
                  TarjetaServicio(
                    servicio: servicio,
                    pendiente: lista.pendientesDe(servicio.id) > 0,
                    fotosPendientes: lista.fotos.pendientesDe(servicio.id),
                    ahora: ahora,
                    abrirEnlace: widget.abrirEnlace,
                    alTocar: () =>
                        Navigator.of(context)
                            .restorablePushNamed(rutaServicio, arguments: servicio.id),
                  ),
                  const SizedBox(height: 12),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Una línea discreta con la hora de la última actualización y el aviso si no hay conexión; y,
/// cuando los hay, cuántos cambios y cuántas fotos están pendientes por enviar, los cambios que el
/// servidor no aplicó y las fotos que rechazó.
class _EstadoDeLaLista extends StatelessWidget {
  const _EstadoDeLaLista({required this.lista, required this.ahora});

  final ListaAsignaciones lista;
  final DateTime ahora;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final actualizada = textoUltimaActualizacion(lista.ultimaActualizacion, ahora: ahora);
    final problema = lista.problema;
    final cola = lista.sincronizador;
    final fotos = lista.fotos;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (cola.pendientes > 0) ...[
          Recuadro(
            textoPendientes(cola.pendientes, problema: cola.problema),
            key: const Key('pendientes'),
            tipo: TipoRecuadro.aviso,
            icono: Icons.cloud_upload_outlined,
          ),
          const SizedBox(height: 8),
        ],
        for (final ajenos in cola.pendientesAjenos) ...[
          Recuadro(
            textoPendientesAjenos(ajenos),
            tipo: TipoRecuadro.aviso,
            icono: Icons.report_problem_outlined,
          ),
          const SizedBox(height: 8),
        ],
        if (fotos.pendientes > 0) ...[
          Recuadro(
            textoFotosPendientes(fotos.pendientes, problema: fotos.problema),
            key: const Key('fotos-pendientes'),
            tipo: TipoRecuadro.aviso,
            icono: Icons.photo_camera_outlined,
          ),
          const SizedBox(height: 8),
        ],
        if (fotos.ajenas > 0) ...[
          Recuadro(
            textoFotosAjenas(fotos.ajenas),
            tipo: TipoRecuadro.aviso,
            icono: Icons.report_problem_outlined,
          ),
          const SizedBox(height: 8),
        ],
        for (final evento in cola.avisos) ...[
          AvisoDeEvento(evento: evento, alEntender: () => cola.marcarVisto(evento.id)),
          const SizedBox(height: 8),
        ],
        for (final foto in fotos.conProblema) ...[
          AvisoDeFoto(
            key: Key('foto-con-problema-${foto.id}'),
            foto: foto,
            alEntender: () => fotos.marcarVista(foto.id),
          ),
          const SizedBox(height: 8),
        ],
        if (lista.sinConexion)
          Recuadro(
            'Sin conexión. Se muestra lo guardado en el celular. $actualizada',
            tipo: TipoRecuadro.aviso,
          )
        else if (problema != null)
          Recuadro('${problema.mensaje} $actualizada', tipo: TipoRecuadro.error)
        else
          Row(
            children: [
              if (lista.actualizando)
                const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                Icon(Icons.check_circle_outline, size: 18, color: context.colores.textoSecundario),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  lista.actualizando ? 'Actualizando…' : actualizada,
                  style: textos.bodySmall?.copyWith(color: context.colores.textoSecundario),
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class TarjetaServicio extends StatelessWidget {
  const TarjetaServicio({
    super.key,
    required this.servicio,
    required this.ahora,
    required this.abrirEnlace,
    required this.alTocar,
    this.pendiente = false,
    this.fotosPendientes = 0,
  });

  final Servicio servicio;

  /// El servicio tiene toques que aún no han llegado al servidor.
  final bool pendiente;

  /// Fotos de este servicio que aún no están en el servidor.
  final int fotosPendientes;
  final DateTime ahora;
  final AbrirEnlace abrirEnlace;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final vehiculo = servicio.vehiculo;
    final descripcion = vehiculo.descripcion;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: alTocar,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 10,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (servicio.ordenRonda != null)
                    Text(
                      '${servicio.ordenRonda}.',
                      style: textos.titleLarge,
                      semanticsLabel: 'Puesto ${servicio.ordenRonda} en la ronda',
                    ),
                  EtiquetaEstado(servicio.estado),
                  if (pendiente) const EtiquetaPendiente(),
                  if (fotosPendientes > 0) EtiquetaFotosPendientes(fotosPendientes),
                  if (servicio.esperaIda) const EtiquetaEsperaIda(),
                  Text(tipoDe(servicio), style: textos.bodyLarge),
                ],
              ),
              const SizedBox(height: 12),
              Text(identificacionDe(vehiculo), style: textos.headlineSmall),
              if (vehiculo.placa != null && vehiculo.vin != null)
                Text(
                  'VIN ${vehiculo.vin}',
                  style: textos.bodyLarge?.copyWith(color: context.colores.textoSecundario),
                ),
              if (descripcion != null) Text(descripcion, style: textos.bodyLarge),
              const SizedBox(height: 8),
              Text(
                'Hora: ${textoProgramada(servicio.programadaPara, ahora: ahora)}',
                style: textos.bodyLarge,
              ),
              const Divider(height: 32),
              SeccionLugar(titulo: 'Recoger en', lugar: servicio.origen, abrirEnlace: abrirEnlace),
              const Divider(height: 32),
              SeccionLugar(
                titulo: 'Entregar en',
                lugar: servicio.destino,
                abrirEnlace: abrirEnlace,
                textoSinDatos: 'Sin destino registrado.',
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(onPressed: alTocar, child: const Text('Ver detalle')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
