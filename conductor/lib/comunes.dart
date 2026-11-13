// Piezas de interfaz que usan varias pantallas.

import 'package:material_ui/material_ui.dart';

import 'tema.dart';

enum TipoRecuadro { error, aviso, info }

/// Un mensaje en un recuadro con borde, legible al sol. Se anuncia a TalkBack al aparecer.
class Recuadro extends StatelessWidget {
  const Recuadro(this.texto, {super.key, this.tipo = TipoRecuadro.info, this.icono});

  final String texto;
  final TipoRecuadro tipo;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final (color, fondo, iconoPorDefecto) = switch (tipo) {
      TipoRecuadro.error => (Colores.peligro, Colores.peligroFondo, Icons.error_outline),
      TipoRecuadro.aviso => (Colores.aviso, Colores.avisoFondo, Icons.cloud_off_outlined),
      TipoRecuadro.info => (Colores.acento, Colores.acentoFondo, Icons.info_outline),
    };
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: fondo,
          border: Border.all(color: color),
          borderRadius: const BorderRadius.all(Radius.circular(8)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icono ?? iconoPorDefecto, color: color),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                texto,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colores.texto),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mientras la app lee lo guardado al abrir.
class PantallaCargando extends StatelessWidget {
  const PantallaCargando({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
