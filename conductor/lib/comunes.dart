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
    final colores = context.colores;
    final (color, fondo, iconoPorDefecto) = switch (tipo) {
      TipoRecuadro.error => (colores.peligro, colores.peligroFondo, Icons.error_outline),
      TipoRecuadro.aviso => (colores.aviso, colores.avisoFondo, Icons.cloud_off_outlined),
      TipoRecuadro.info => (colores.acento, colores.acentoFondo, Icons.info_outline),
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
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: colores.texto),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mientras una pantalla lee lo guardado en el celular: la rueda y debajo qué está haciendo.
/// TalkBack lo lee como un solo elemento, con el texto.
class Cargando extends StatelessWidget {
  const Cargando(this.texto, {super.key});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Semantics(
        container: true,
        label: texto,
        excludeSemantics: true,
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              const SizedBox(height: 16),
              Text(
                texto,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge
                    ?.copyWith(color: context.colores.textoSecundario),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// El alto de [child] cambia sin saltos (crece, se encoge, aparece, desaparece), en
/// [duracionDeTransicion]. Sin animaciones en el celular, el cambio es inmediato: [AnimatedSize] no
/// admite una duración cero.
class TamanoAnimado extends StatelessWidget {
  const TamanoAnimado({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final duracion = duracionDeTransicion(context);
    if (duracion == Duration.zero) return child;
    return AnimatedSize(duration: duracion, alignment: Alignment.topCenter, child: child);
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
