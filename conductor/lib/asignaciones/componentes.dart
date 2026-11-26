// Piezas de la lista y del detalle de un servicio.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../cola/evento.dart';
import '../comunes.dart';
import '../formato.dart';
import '../fotos/foto.dart';
import '../tema.dart';
import 'enlaces.dart';
import 'estados.dart';
import 'servicio.dart';

/// La placa, o el VIN, o un aviso si no hay ninguno.
String identificacionDe(Vehiculo vehiculo) =>
    vehiculo.placa ??
    vehiculo.vin ??
    (vehiculo.numeroBodega == null ? null : 'Bodega ${vehiculo.numeroBodega}') ??
    'Sin placa, VIN ni número de bodega';

/// "Traslado", "Evento (regreso)", "Desvare".
String tipoDe(Servicio servicio) =>
    servicio.esRegreso ? '${nombreTipo(servicio.tipo)} (regreso)' : nombreTipo(servicio.tipo);

/// El icono que acompaña el nombre de cada estado: la etiqueta no depende solo del color.
IconData iconoDeEstado(String estado) => switch (estado) {
  'pendiente_asignar' => Icons.schedule,
  'asignado' => Icons.assignment_ind_outlined,
  'en_camino' => Icons.local_shipping_outlined,
  'recogido' => Icons.directions_car_filled_outlined,
  'entregado' => Icons.check_circle_outline,
  'novedad' => Icons.report_problem_outlined,
  'cancelado' => Icons.cancel_outlined,
  _ => Icons.help_outline,
};

/// La forma común de las etiquetas: pastilla con borde, icono y texto del mismo color.
class _Pastilla extends StatelessWidget {
  const _Pastilla({
    super.key,
    required this.icono,
    required this.texto,
    required this.color,
    required this.fondo,
  });

  final IconData icono;
  final String texto;
  final Color color;
  final Color fondo;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: ShapeDecoration(
        color: fondo,
        shape: StadiumBorder(side: BorderSide(color: color, width: 1.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ExcludeSemantics(child: Icon(icono, size: 18, color: color)),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              texto,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}

class EtiquetaEstado extends StatelessWidget {
  const EtiquetaEstado(this.estado, {super.key});

  final String estado;

  @override
  Widget build(BuildContext context) {
    final colores = coloresDeEstado(estado);
    final nombre = nombreEstado(estado);
    // TalkBack la lee una sola vez, como "Estado: En camino".
    return Semantics(
      label: 'Estado: $nombre',
      excludeSemantics: true,
      child: _Pastilla(
        icono: iconoDeEstado(estado),
        texto: nombre,
        color: colores.texto,
        fondo: colores.fondo,
      ),
    );
  }
}

/// Marca de un servicio con toques que aún no han llegado al servidor.
class EtiquetaPendiente extends StatelessWidget {
  const EtiquetaPendiente({super.key});

  @override
  Widget build(BuildContext context) {
    return const _Pastilla(
      icono: Icons.cloud_upload_outlined,
      texto: 'Pendiente por enviar',
      color: Colores.aviso,
      fondo: Colores.avisoFondo,
    );
  }
}

/// Marca de un regreso que espera a que su ida esté entregada (ver `trayecto.dart`).
class EtiquetaEsperaIda extends StatelessWidget {
  const EtiquetaEsperaIda({super.key});

  @override
  Widget build(BuildContext context) {
    return const _Pastilla(
      key: Key('espera-ida'),
      icono: Icons.lock_outline,
      texto: 'Espera la ida',
      color: Colores.regreso,
      fondo: Colores.regresoFondo,
    );
  }
}

/// Marca de un servicio con fotos de evidencia que aún no están en el servidor.
class EtiquetaFotosPendientes extends StatelessWidget {
  const EtiquetaFotosPendientes(this.cantidad, {super.key});

  final int cantidad;

  @override
  Widget build(BuildContext context) {
    return _Pastilla(
      icono: Icons.photo_camera_outlined,
      texto: cantidad == 1 ? '1 foto por subir' : '$cantidad fotos por subir',
      color: Colores.aviso,
      fondo: Colores.avisoFondo,
    );
  }
}

/// Los tres pasos que marca el conductor, en orden.
const pasosDeAvance = [Estado.enCamino, Estado.recogido, Estado.entregado];

/// Cuántos de los tres pasos están cumplidos. En una novedad, los que había antes de ella (0 si
/// no se sabe).
int pasosCumplidos(String estado, {String? estadoPrevio}) {
  final base = estado == Estado.novedad ? estadoPrevio : estado;
  return pasosDeAvance.indexOf(base ?? '') + 1;
}

/// El avance del servicio en tres tramos: En camino, Recogido, Entregado. En una novedad se
/// pinta en rojo hasta donde iba; un servicio cancelado no la muestra.
class BarraDeAvance extends StatelessWidget {
  const BarraDeAvance(this.estado, {super.key, this.estadoPrevio});

  final String estado;

  /// Solo en una novedad: el estado que tenía antes.
  final String? estadoPrevio;

  @override
  Widget build(BuildContext context) {
    if (estado == Estado.cancelado) return const SizedBox.shrink();
    final conNovedad = estado == Estado.novedad;
    final cumplidos = pasosCumplidos(estado, estadoPrevio: estadoPrevio);
    final lleno = conNovedad ? Colores.peligro : Colores.acento;
    final estilo = Theme.of(context).textTheme.bodySmall;
    final escala = MediaQuery.textScalerOf(context);
    final etiqueta = StringBuffer('Avance: paso $cumplidos de ${pasosDeAvance.length}');
    if (cumplidos > 0) etiqueta.write(', ${nombreEstado(pasosDeAvance[cumplidos - 1])}');
    if (conNovedad) etiqueta.write(', con novedad');

    return Semantics(
      label: etiqueta.toString(),
      excludeSemantics: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < pasosDeAvance.length; i++) ...[
            if (i > 0) const SizedBox(width: 6),
            Expanded(
              child: Column(
                children: [
                  Container(
                    key: Key('avance-$i'),
                    height: 8,
                    decoration: BoxDecoration(
                      color: i < cumplidos ? lleno : Colores.borde,
                      borderRadius: const BorderRadius.all(Radius.circular(4)),
                    ),
                  ),
                  const SizedBox(height: 6),
                  // RichText y no Text: el nombre del paso no se confunde con la etiqueta del
                  // estado cuando se busca el texto en pantalla, y TalkBack lee la barra entera.
                  RichText(
                    textAlign: TextAlign.center,
                    textScaler: escala,
                    text: TextSpan(
                      text: nombreEstado(pasosDeAvance[i]),
                      style: i == cumplidos - 1
                          ? estilo?.copyWith(color: Colores.texto, fontWeight: FontWeight.w700)
                          : estilo?.copyWith(color: Colores.textoSecundario),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// "Hay 4 fotos pendientes por subir. Se suben solas cuando haya señal."
String textoFotosPendientes(int cantidad, {ErrorApi? problema}) {
  final cuantas = cantidad == 1
      ? 'Hay 1 foto pendiente por subir.'
      : 'Hay $cantidad fotos pendientes por subir.';
  if (problema != null && problema is! ErrorDeRed) {
    return '$cuantas El servidor no las recibió; la app lo intenta de nuevo sola.';
  }
  return cantidad == 1
      ? '$cuantas Se sube sola cuando haya señal.'
      : '$cuantas Se suben solas cuando haya señal.';
}

/// Las fotos de otro conductor que siguen en este celular: no se suben con la sesión actual.
String textoFotosAjenas(int cantidad) {
  final cuantas = cantidad == 1 ? '1 foto' : '$cantidad fotos';
  return 'En este celular hay $cuantas sin subir de otro conductor. No se suben con su sesión: '
      'saldrán cuando él vuelva a ingresar aquí. Avise a logística.';
}

/// Lo que se le dice al conductor de una foto que el servidor rechazó.
String textoDeFotoConProblema(FotoLocal foto) {
  final vehiculo = foto.vehiculo ?? 'Servicio N.º ${foto.servicioId}';
  final de = foto.tipo == TipoFoto.recogida ? 'la recogida' : 'la entrega';
  final motivo = foto.error;
  return '$vehiculo: una foto de $de no se pudo subir.${motivo == null ? '' : ' $motivo'} '
      'La foto sigue guardada en este celular. Avise a logística.';
}

/// El aviso de una foto que el servidor rechazó. Queda a la vista hasta que el conductor toca
/// "Entendido"; la foto sigue guardada en el celular.
class AvisoDeFoto extends StatelessWidget {
  const AvisoDeFoto({super.key, required this.foto, required this.alEntender});

  final FotoLocal foto;
  final VoidCallback alEntender;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Recuadro(textoDeFotoConProblema(foto), tipo: TipoRecuadro.error),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: alEntender, child: const Text('Entendido')),
        ),
      ],
    );
  }
}

/// "Hay 2 cambios pendientes por enviar. Se envían solos cuando haya señal."
String textoPendientes(int cantidad, {ErrorApi? problema}) {
  final cuantos = cantidad == 1
      ? 'Hay 1 cambio pendiente por enviar.'
      : 'Hay $cantidad cambios pendientes por enviar.';
  if (problema != null && problema is! ErrorDeRed) {
    return '$cuantos El servidor no los recibió; la app lo intenta de nuevo sola.';
  }
  return cantidad == 1
      ? '$cuantos Se envía solo cuando haya señal.'
      : '$cuantos Se envían solos cuando haya señal.';
}

/// Los cambios de otro conductor que siguen en este celular: no se envían con la sesión actual.
String textoPendientesAjenos(PendientesDeConductor ajenos) {
  final quien = ajenos.nombre ?? 'otro conductor';
  final cuantos = ajenos.cantidad == 1 ? '1 cambio' : '${ajenos.cantidad} cambios';
  return 'En este celular hay $cuantos sin enviar de $quien. No se envían con su sesión: '
      'saldrán cuando $quien vuelva a ingresar aquí. Avise a logística.';
}

/// Lo que se le dice al conductor de un toque que el servidor no aplicó.
String textoDeAviso(EventoLocal evento) {
  final vehiculo = evento.vehiculo ?? 'Servicio N.º ${evento.servicioId}';
  final paso = nombreEstado(evento.destino);
  final que = evento.estadoEnvio == EstadoEnvio.rechazado
      ? 'El servidor no pudo guardar su marca de «$paso».'
      : 'Su marca de «$paso» quedó guardada, pero el servicio no cambió.';
  final detalle = evento.resultadoDetalle;
  return '$vehiculo: $que${detalle == null ? '' : ' $detalle'} '
      'Logística ya recibió el aviso y lo revisará.';
}

/// El aviso de un toque que el servidor no aplicó (conflicto o rechazado). Queda a la vista hasta
/// que el conductor toca "Entendido"; el evento sigue guardado.
class AvisoDeEvento extends StatelessWidget {
  const AvisoDeEvento({super.key, required this.evento, required this.alEntender});

  final EventoLocal evento;
  final VoidCallback alEntender;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Recuadro(textoDeAviso(evento), tipo: TipoRecuadro.error),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: alEntender, child: const Text('Entendido')),
        ),
      ],
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
