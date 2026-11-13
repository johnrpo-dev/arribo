// Detalle de un servicio, de solo lectura. Los botones de estado llegan con la 1a-12.

import 'package:material_ui/material_ui.dart';

import '../formato.dart';
import '../tema.dart';
import 'componentes.dart';
import 'enlaces.dart';
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
    return Scaffold(
      appBar: AppBar(title: Text('Servicio N.º $id')),
      body: ListenableBuilder(
        listenable: lista,
        builder: (context, _) {
          if (!lista.cargada) return const Center(child: CircularProgressIndicator());
          final servicio = lista.servicio(id);
          if (servicio == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'Este servicio ya no está en su lista.',
                  style: Theme.of(context).textTheme.bodyLarge,
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return _Detalle(servicio: servicio, ahora: reloj(), abrirEnlace: abrirEnlace);
        },
      ),
    );
  }
}

class _Detalle extends StatelessWidget {
  const _Detalle({required this.servicio, required this.ahora, required this.abrirEnlace});

  final Servicio servicio;
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
            Text(tipoDe(servicio), style: textos.bodyLarge),
          ],
        ),
        if (servicio.estado == 'novedad' && estadoPrevio != null) ...[
          const SizedBox(height: 8),
          Text(
            'Estado antes de la novedad: ${nombreEstado(estadoPrevio)}',
            style: textos.bodyLarge?.copyWith(color: Colores.textoSecundario),
          ),
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
