// La lista de servicios del conductor, en el orden de su ronda. Se muestra siempre desde la base
// local y se refresca al abrir, al volver a primer plano y al deslizar hacia abajo.

import 'package:material_ui/material_ui.dart';

import '../comunes.dart';
import '../formato.dart';
import '../ingreso/sesion.dart';
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
  });

  final ListaAsignaciones lista;
  final Sesion sesion;
  final AbrirEnlace abrirEnlace;
  final DateTime Function() reloj;

  @override
  State<PantallaAsignaciones> createState() => _PantallaAsignacionesState();
}

class _PantallaAsignacionesState extends State<PantallaAsignaciones> {
  late final AppLifecycleListener _ciclo;

  @override
  void initState() {
    super.initState();
    _ciclo = AppLifecycleListener(onResume: widget.lista.actualizar);
    _iniciar();
  }

  Future<void> _iniciar() async {
    await widget.lista.cargarLocal();
    await widget.lista.actualizar();
  }

  @override
  void dispose() {
    _ciclo.dispose();
    super.dispose();
  }

  Future<void> _salir() async {
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
      mensajero.showSnackBar(
        const SnackBar(
          content: Text('No se puede cerrar sesión: hay cambios sin enviar. Espere a tener señal.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final nombre = widget.sesion.conductor?.nombre;
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
            },
            itemBuilder: (context) => [
              if (nombre != null) PopupMenuItem(enabled: false, child: Text(nombre)),
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

/// Una línea discreta con la hora de la última actualización, y el aviso si no hay conexión.
class _EstadoDeLaLista extends StatelessWidget {
  const _EstadoDeLaLista({required this.lista, required this.ahora});

  final ListaAsignaciones lista;
  final DateTime ahora;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final actualizada = textoUltimaActualizacion(lista.ultimaActualizacion, ahora: ahora);
    final problema = lista.problema;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
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
                const Icon(Icons.check_circle_outline, size: 18, color: Colores.textoSecundario),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  lista.actualizando ? 'Actualizando…' : actualizada,
                  style: textos.bodySmall?.copyWith(color: Colores.textoSecundario),
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
  });

  final Servicio servicio;
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
                  Text(tipoDe(servicio), style: textos.bodyLarge),
                ],
              ),
              const SizedBox(height: 12),
              Text(identificacionDe(vehiculo), style: textos.headlineSmall),
              if (vehiculo.placa != null && vehiculo.vin != null)
                Text(
                  'VIN ${vehiculo.vin}',
                  style: textos.bodyLarge?.copyWith(color: Colores.textoSecundario),
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
