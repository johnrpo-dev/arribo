// Lo que pasa entre tocar un botón de estado y guardar el evento: una confirmación corta, al
// alcance del pulgar, para que un toque accidental no cambie el estado. Dos toques en total.

import 'package:material_ui/material_ui.dart';

import '../formato.dart';
import 'componentes.dart';
import 'estados.dart';
import 'lista_asignaciones.dart';
import 'servicio.dart';

/// Lo que acompaña a un Recogido o a un Entregado.
class DatosDelPaso {
  const DatosDelPaso({this.nombreQuien, this.idEvento});

  /// Quien entrega (en un Recogido) o recibe (en un Entregado) el vehículo.
  final String? nombreQuien;

  /// El UUID del evento, si ya se fijó antes de guardarlo (las fotos se atan a él).
  final String? idEvento;
}

/// PUNTO DE ENGANCHE DE LA 1a-13. Todo Recogido y todo Entregado pasan por aquí antes de guardarse
/// en la cola. Devuelve lo que acompaña al evento, o null si no se debe marcar (el conductor
/// canceló, o falta un requisito).
///
/// Hoy (1a-12) solo pide la confirmación. La 1a-13 pone aquí, antes de confirmar: el bloqueo por
/// capacidad en un Recogido (con [lista] se ve qué vehículos van montados y cuál falta entregar),
/// el mínimo de fotos de `lista.configuracion` y el nombre de quien entrega o recibe; y devuelve el
/// `nombreQuien` y el `idEvento` con que guardó las fotos. Quien llama no cambia.
Future<DatosDelPaso?> prepararRecogidoOEntregado(
  BuildContext context, {
  required Servicio servicio,
  required String destino,
  required ListaAsignaciones lista,
}) async {
  assert(destino == Estado.recogido || destino == Estado.entregado);
  final confirmado = await confirmarPaso(context, servicio: servicio, destino: destino);
  return confirmado ? const DatosDelPaso() : null;
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
