// Detalle de un servicio, con los botones de estado: el paso que sigue (En camino, Recogido o
// Entregado) y Novedad. Cada toque se guarda como evento en la cola local antes de cambiar la
// pantalla; el estado nuevo se ve de inmediato, marcado como pendiente por enviar.

import 'package:material_ui/material_ui.dart';

import '../cola/cola_eventos.dart';
import '../cola/evento.dart';
import '../comunes.dart';
import '../formato.dart';
import '../tema.dart';
import 'componentes.dart';
import 'confirmacion.dart';
import 'enlaces.dart';
import 'estados.dart';
import 'lista_asignaciones.dart';
import 'servicio.dart';

class PantallaServicio extends StatelessWidget {
  const PantallaServicio({
    super.key,
    required this.id,
    required this.lista,
    required this.abrirEnlace,
    this.reloj = DateTime.now,
  });

  final int id;
  final ListaAsignaciones lista;
  final AbrirEnlace abrirEnlace;
  final DateTime Function() reloj;

  @override
  Widget build(BuildContext context) {
    // La lista avisa también cuando cambia la cola de eventos.
    return ListenableBuilder(
      listenable: lista,
      builder: (context, _) {
        final servicio = lista.cargada ? lista.servicio(id) : null;
        final avisos = [
          for (final evento in lista.sincronizador.avisos)
            if (evento.servicioId == id) evento,
        ];
        void alEntender(EventoLocal evento) => lista.sincronizador.marcarVisto(evento.id);
        return Scaffold(
          appBar: AppBar(title: Text('Servicio N.º $id')),
          body: !lista.cargada
              ? const Center(child: CircularProgressIndicator())
              : servicio == null
              ? _FueraDeLaLista(avisos: avisos, alEntender: alEntender)
              : _Detalle(
                  servicio: servicio,
                  pendiente: lista.pendientesDe(id) > 0,
                  avisos: avisos,
                  alEntender: alEntender,
                  ahora: reloj(),
                  abrirEnlace: abrirEnlace,
                ),
          bottomNavigationBar: servicio == null
              ? null
              : _Acciones(servicio: servicio, lista: lista),
        );
      },
    );
  }
}

/// El servicio ya no está en la ronda del conductor (entregado, cancelado o reasignado).
class _FueraDeLaLista extends StatelessWidget {
  const _FueraDeLaLista({required this.avisos, required this.alEntender});

  final List<EventoLocal> avisos;
  final void Function(EventoLocal evento) alEntender;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        for (final evento in avisos) ...[
          AvisoDeEvento(evento: evento, alEntender: () => alEntender(evento)),
          const SizedBox(height: 12),
        ],
        Text(
          'Este servicio ya no está en su lista.',
          style: Theme.of(context).textTheme.bodyLarge,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

/// Los botones de estado, fijos abajo: el paso que sigue y, donde aplica, Novedad.
class _Acciones extends StatefulWidget {
  const _Acciones({required this.servicio, required this.lista});

  final Servicio servicio;
  final ListaAsignaciones lista;

  @override
  State<_Acciones> createState() => _AccionesState();
}

class _AccionesState extends State<_Acciones> {
  /// Entre el toque y el evento guardado no se aceptan más toques.
  bool _ocupado = false;

  Future<void> _marcar(String destino) async {
    if (_ocupado) return;
    final servicio = widget.servicio;
    final mensajero = ScaffoldMessenger.of(context);
    setState(() => _ocupado = true);
    try {
      String? motivo;
      var datos = const DatosDelPaso();
      if (destino == Estado.novedad) {
        motivo = await pedirMotivoDeNovedad(context, servicio: servicio);
        if (motivo == null) return;
      } else if (destino == Estado.recogido || destino == Estado.entregado) {
        final preparado = await prepararRecogidoOEntregado(
          context,
          servicio: servicio,
          destino: destino,
          lista: widget.lista,
        );
        if (preparado == null) return;
        datos = preparado;
      } else if (!await confirmarPaso(context, servicio: servicio, destino: destino)) {
        return;
      }
      // Primero queda guardado en la cola; la pantalla cambia cuando la lista vuelve a leer.
      await widget.lista.marcar(
        servicio.id,
        destino,
        motivo: motivo,
        nombreQuien: datos.nombreQuien,
        idEvento: datos.idEvento,
      );
    } on ToqueNoValido catch (error) {
      mensajero.showSnackBar(SnackBar(content: Text(error.mensaje)));
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final estado = widget.servicio.estado;
    final siguiente = siguientePaso(estado);
    final conNovedad = admiteNovedad(estado);
    if (siguiente == null && !conNovedad) return const SizedBox.shrink();
    return Material(
      color: Colores.superficie,
      shape: const Border(top: BorderSide(color: Colores.borde)),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (siguiente != null)
                FilledButton(
                  key: Key('marcar-$siguiente'),
                  onPressed: _ocupado ? null : () => _marcar(siguiente),
                  child: Text('Marcar ${nombreEstado(siguiente)}', textAlign: TextAlign.center),
                ),
              if (siguiente != null && conNovedad) const SizedBox(height: 8),
              if (conNovedad)
                OutlinedButton(
                  key: const Key('marcar-novedad'),
                  onPressed: _ocupado ? null : () => _marcar(Estado.novedad),
                  child: const Text('Reportar novedad', textAlign: TextAlign.center),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Detalle extends StatelessWidget {
  const _Detalle({
    required this.servicio,
    required this.pendiente,
    required this.avisos,
    required this.alEntender,
    required this.ahora,
    required this.abrirEnlace,
  });

  final Servicio servicio;

  /// El servicio tiene toques que aún no han llegado al servidor.
  final bool pendiente;

  /// Toques de este servicio que el servidor no aplicó y el conductor no ha dado por vistos.
  final List<EventoLocal> avisos;
  final void Function(EventoLocal evento) alEntender;
  final DateTime ahora;
  final AbrirEnlace abrirEnlace;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final vehiculo = servicio.vehiculo;
    final grua = servicio.grua;
    final estadoPrevio = servicio.estadoPrevio;

    Widget seccion(String titulo, List<Widget> contenido) => Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo, style: textos.titleMedium),
            const SizedBox(height: 8),
            ...contenido,
          ],
        ),
      ),
    );

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        Wrap(
          spacing: 10,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            EtiquetaEstado(servicio.estado),
            if (pendiente) const EtiquetaPendiente(),
            Text(tipoDe(servicio), style: textos.bodyLarge),
          ],
        ),
        if (servicio.estado == Estado.novedad && estadoPrevio != null) ...[
          const SizedBox(height: 8),
          Text(
            'Estado antes de la novedad: ${nombreEstado(estadoPrevio)}',
            style: textos.bodyLarge?.copyWith(color: Colores.textoSecundario),
          ),
        ],
        if (servicio.estado == Estado.novedad) ...[
          const SizedBox(height: 12),
          const Recuadro('Novedad abierta. El servicio sigue cuando logística la resuelva.'),
        ],
        if (servicio.estado == Estado.entregado) ...[
          const SizedBox(height: 12),
          const Recuadro('Servicio entregado. Sale de su lista cuando el cambio se envíe.'),
        ],
        for (final evento in avisos) ...[
          const SizedBox(height: 12),
          AvisoDeEvento(evento: evento, alEntender: () => alEntender(evento)),
        ],
        const SizedBox(height: 12),
        Text(identificacionDe(vehiculo), style: textos.headlineSmall),
        const SizedBox(height: 4),
        Text(
          'Hora: ${textoProgramada(servicio.programadaPara, ahora: ahora)}',
          style: textos.bodyLarge,
        ),
        const SizedBox(height: 16),
        seccion('Vehículo', [
          FilaDato('Placa', vehiculo.placa ?? 'Sin placa'),
          FilaDato('VIN', vehiculo.vin ?? 'Sin VIN'),
          if (vehiculo.marca != null) FilaDato('Marca', vehiculo.marca!),
          if (vehiculo.linea != null) FilaDato('Línea', vehiculo.linea!),
          if (vehiculo.color != null) FilaDato('Color', vehiculo.color!),
        ]),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: SeccionLugar(
              titulo: 'Recoger en',
              lugar: servicio.origen,
              abrirEnlace: abrirEnlace,
              mostrarUbicacion: true,
            ),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: SeccionLugar(
              titulo: 'Entregar en',
              lugar: servicio.destino,
              abrirEnlace: abrirEnlace,
              textoSinDatos: 'Sin destino registrado.',
              mostrarUbicacion: true,
            ),
          ),
        ),
        const SizedBox(height: 12),
        seccion('Otros datos', [
          if (servicio.ordenRonda != null) FilaDato('Puesto en la ronda', '${servicio.ordenRonda}'),
          FilaDato('Solicitud', 'N.º ${servicio.solicitudId}'),
          if (servicio.referenciaExterna != null)
            FilaDato('Referencia', servicio.referenciaExterna!),
          if (grua != null)
            FilaDato(
              'Grúa',
              '${grua.placa} (${grua.capacidad == 1 ? '1 puesto' : '${grua.capacidad} puestos'})',
            ),
          FilaDato('Montado en la grúa', servicio.aBordo ? 'Sí' : 'No'),
        ]),
      ],
    );
  }
}
