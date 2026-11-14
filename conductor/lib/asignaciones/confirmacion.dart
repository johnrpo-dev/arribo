// Lo que pasa entre tocar un botón de estado y guardar el evento. En camino pide una confirmación
// corta, al alcance del pulgar, para que un toque accidental no cambie el estado (dos toques en
// total). Novedad pide el motivo. Recogido y Entregado abren su pantalla de fotos y nombre
// (pantalla_paso.dart); un Recogido que no se puede marcar todavía se bloquea aquí, diciendo por qué.

import 'package:material_ui/material_ui.dart';

import '../formato.dart';
import 'componentes.dart';
import 'estados.dart';
import 'lista_asignaciones.dart';
import 'pantalla_paso.dart';
import 'requisitos.dart';
import 'servicio.dart';

/// Todo Recogido y todo Entregado pasan por aquí. Un Recogido se bloquea si al vehículo le falta
/// la placa o el VIN, o si la grúa va llena (se le muestra al conductor qué vehículo le falta
/// marcar como Entregado). Si no hay bloqueo, abre la pantalla de fotos y nombre, que es la que
/// guarda el evento. La ruta es restaurable: sobrevive a que Android mate la app con la cámara
/// abierta.
Future<void> abrirRecogidoOEntregado(
  BuildContext context, {
  required Servicio servicio,
  required String destino,
  required ListaAsignaciones lista,
}) async {
  assert(destino == Estado.recogido || destino == Estado.entregado);
  if (destino == Estado.recogido) {
    final bloqueo = lista.bloqueoDeRecogida(servicio);
    if (bloqueo != null) return mostrarBloqueo(context, bloqueo);
  }
  Navigator.of(context).restorablePushNamed(
    rutaPaso,
    arguments: argumentosDePaso(servicioId: servicio.id, destino: destino),
  );
}

/// Por qué no se puede marcar Recogido, en una hoja inferior. En un bloqueo por capacidad lista
/// los vehículos que falta marcar como Entregado.
Future<void> mostrarBloqueo(BuildContext context, BloqueoDeRecogida bloqueo) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (context) {
      final textos = Theme.of(context).textTheme;
      return _Hoja(
        children: [
          Text(bloqueo.titulo, style: textos.titleLarge),
          const SizedBox(height: 8),
          Text(bloqueo.mensaje, key: const Key('bloqueo'), style: textos.bodyLarge),
          if (bloqueo.faltanPorEntregar.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('Falta marcar como Entregado:', style: textos.titleMedium),
            const SizedBox(height: 4),
            for (final servicio in bloqueo.faltanPorEntregar)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text(
                  _vehiculoDe(servicio),
                  key: Key('falta-entregar-${servicio.id}'),
                  style: textos.bodyLarge,
                ),
              ),
          ],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Entendido', textAlign: TextAlign.center),
          ),
        ],
      );
    },
  );
}

String _vehiculoDe(Servicio servicio) =>
    [identificacionDe(servicio.vehiculo), ?servicio.vehiculo.descripcion].join(' · ');

/// "¿Marcar En camino?" con el vehículo a la vista. true solo si el conductor confirma.
Future<bool> confirmarPaso(
  BuildContext context, {
  required Servicio servicio,
  required String destino,
}) async {
  final paso = nombreEstado(destino);
  final confirmado = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (context) {
      final textos = Theme.of(context).textTheme;
      return _Hoja(
        children: [
          Text('¿Marcar $paso?', style: textos.titleLarge),
          const SizedBox(height: 8),
          Text(_vehiculoDe(servicio), style: textos.bodyLarge),
          const SizedBox(height: 20),
          FilledButton(
            key: const Key('confirmar'),
            onPressed: () => Navigator.of(context).pop(true),
            child: Text('Sí, marcar $paso', textAlign: TextAlign.center),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancelar'),
          ),
        ],
      );
    },
  );
  return confirmado ?? false;
}

/// Pide el motivo de la novedad (obligatorio). Devuelve el texto, o null si el conductor cancela.
Future<String?> pedirMotivoDeNovedad(BuildContext context, {required Servicio servicio}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    builder: (context) => _HojaNovedad(vehiculo: _vehiculoDe(servicio)),
  );
}

/// El contenido de una hoja inferior: se desplaza si no cabe (texto grande) y sube con el teclado.
class _Hoja extends StatelessWidget {
  const _Hoja({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(20, 24, 20, 16 + MediaQuery.viewInsetsOf(context).bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: children,
        ),
      ),
    );
  }
}

class _HojaNovedad extends StatefulWidget {
  const _HojaNovedad({required this.vehiculo});

  final String vehiculo;

  @override
  State<_HojaNovedad> createState() => _HojaNovedadState();
}

class _HojaNovedadState extends State<_HojaNovedad> {
  final _motivo = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _motivo.dispose();
    super.dispose();
  }

  void _reportar() {
    final motivo = _motivo.text.trim();
    if (motivo.isEmpty) {
      setState(() => _error = 'Escriba qué pasó para reportar la novedad.');
      return;
    }
    Navigator.of(context).pop(motivo);
  }

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    return _Hoja(
      children: [
        Text('Reportar novedad', style: textos.titleLarge),
        const SizedBox(height: 8),
        Text(widget.vehiculo, style: textos.bodyLarge),
        const SizedBox(height: 8),
        Text(
          'El servicio queda detenido hasta que logística resuelva la novedad.',
          style: textos.bodyMedium,
        ),
        const SizedBox(height: 16),
        TextField(
          key: const Key('motivo'),
          controller: _motivo,
          autofocus: true,
          minLines: 2,
          maxLines: 4,
          style: textos.bodyLarge,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(labelText: '¿Qué pasó?', errorText: _error),
          onChanged: (_) {
            if (_error != null) setState(() => _error = null);
          },
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('confirmar'),
          onPressed: _reportar,
          child: const Text('Reportar novedad', textAlign: TextAlign.center),
        ),
        const SizedBox(height: 8),
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancelar')),
      ],
    );
  }
}
