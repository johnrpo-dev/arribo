// Piezas de la lista y del detalle de un servicio.

import 'package:material_ui/material_ui.dart';

import '../formato.dart';
import '../tema.dart';
import 'enlaces.dart';
import 'servicio.dart';

/// La placa, o el VIN, o un aviso si no hay ninguno.
String identificacionDe(Vehiculo vehiculo) => vehiculo.placa ?? vehiculo.vin ?? 'Sin placa ni VIN';

/// "Traslado", "Evento (regreso)", "Desvare".
String tipoDe(Servicio servicio) =>
    servicio.esRegreso ? '${nombreTipo(servicio.tipo)} (regreso)' : nombreTipo(servicio.tipo);

class EtiquetaEstado extends StatelessWidget {
  const EtiquetaEstado(this.estado, {super.key});

  final String estado;

  @override
  Widget build(BuildContext context) {
    final colores = coloresDeEstado(estado);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: colores.fondo,
        border: Border.all(color: colores.texto),
        borderRadius: const BorderRadius.all(Radius.circular(6)),
      ),
      child: Text(
        nombreEstado(estado),
        style: Theme.of(context).textTheme.labelMedium?.copyWith(color: colores.texto),
      ),
    );
  }
}

/// Un lugar del servicio (recoger o entregar): dirección, contacto y los botones de un toque.
class SeccionLugar extends StatelessWidget {
  const SeccionLugar({
    super.key,
    required this.titulo,
    required this.lugar,
    required this.abrirEnlace,
    this.textoSinDatos = 'Sin datos.',
    this.mostrarUbicacion = false,
  });

  final String titulo;
  final Lugar lugar;
  final AbrirEnlace abrirEnlace;
  final String textoSinDatos;

  /// En el detalle se muestra también el enlace o las coordenadas que escribió logística.
  final bool mostrarUbicacion;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final secundario = textos.bodyLarge?.copyWith(color: Colores.textoSecundario);
    final llamar = enlaceLlamar(lugar.contactoTelefono);
    final maps = enlaceGoogleMaps(lugar);
    final waze = enlaceWaze(lugar);
    final contacto = [
      lugar.contactoNombre,
      if (lugar.contactoTelefono != null) telefonoLegible(lugar.contactoTelefono!),
    ].whereType<String>().join(' · ');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(titulo, style: textos.labelMedium?.copyWith(color: Colores.textoSecundario)),
        const SizedBox(height: 4),
        if (lugar.vacio)
          Text(textoSinDatos, style: secundario)
        else ...[
          Text(lugar.direccion ?? 'Sin dirección', style: textos.titleMedium),
          if (mostrarUbicacion && lugar.ubicacion != null) ...[
            const SizedBox(height: 4),
            SelectableText(lugar.ubicacion!, style: secundario),
          ],
          if (contacto.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(contacto, style: textos.bodyLarge),
          ],
          if (llamar != null || maps != null || waze != null) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (llamar != null)
                  _BotonEnlace(
                    icono: Icons.call,
                    texto: 'Llamar',
                    descripcion: 'Llamar a ${lugar.contactoNombre ?? 'el contacto'}',
                    enlace: llamar,
                    abrirEnlace: abrirEnlace,
                    siFalla: 'No se pudo abrir el marcador del teléfono.',
                  ),
                if (maps != null)
                  _BotonEnlace(
                    icono: Icons.map_outlined,
                    texto: 'Maps',
                    descripcion: 'Abrir $titulo en Google Maps',
                    enlace: maps,
                    abrirEnlace: abrirEnlace,
                    siFalla: 'No se pudo abrir Google Maps ni el navegador.',
                  ),
                if (waze != null)
                  _BotonEnlace(
                    icono: Icons.navigation_outlined,
                    texto: 'Waze',
                    descripcion: 'Abrir $titulo en Waze',
                    enlace: waze,
                    abrirEnlace: abrirEnlace,
                    siFalla: 'No se pudo abrir Waze ni el navegador.',
                  ),
              ],
            ),
          ],
        ],
      ],
    );
  }
}

class _BotonEnlace extends StatelessWidget {
  const _BotonEnlace({
    required this.icono,
    required this.texto,
    required this.descripcion,
    required this.enlace,
    required this.abrirEnlace,
    required this.siFalla,
  });

  final IconData icono;
  final String texto;
  final String descripcion;
  final Uri enlace;
  final AbrirEnlace abrirEnlace;
  final String siFalla;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      icon: Icon(icono),
      label: Text(texto, semanticsLabel: descripcion),
      onPressed: () async {
        final mensajero = ScaffoldMessenger.maybeOf(context);
        final abierto = await abrirEnlace(enlace);
        if (!abierto) mensajero?.showSnackBar(SnackBar(content: Text(siFalla)));
      },
    );
  }
}

/// Una línea "Etiqueta: valor" del detalle.
class FilaDato extends StatelessWidget {
  const FilaDato(this.etiqueta, this.valor, {super.key});

  final String etiqueta;
  final String valor;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: '$etiqueta: ',
              style: textos.bodyLarge?.copyWith(color: Colores.textoSecundario),
            ),
            TextSpan(text: valor, style: textos.bodyLarge),
          ],
        ),
      ),
    );
  }
}
