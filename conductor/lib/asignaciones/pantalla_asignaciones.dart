// La lista de servicios del conductor, en el orden de su ronda. Se muestra siempre desde la base
// local y se refresca al abrir, al volver a primer plano y al deslizar hacia abajo.

import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../comunes.dart';
import '../formato.dart';
import '../ingreso/sesion.dart';
import '../preferencia_tema.dart';
import '../tema.dart';
import '../vibracion.dart';
import 'componentes.dart';
import 'confirmacion.dart';
import 'enlaces.dart';
import 'estados.dart';
import 'lista_asignaciones.dart';
import 'servicio.dart';
import 'servicio_activo.dart';
import 'trayecto.dart';

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
              vibrarSeleccion();
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
          // El servicio que está atendiendo va arriba ("Ahora"), con el botón del paso que sigue;
          // los demás quedan debajo ("Después"), en el orden de la ronda.
          final activo = servicioActivo(lista.servicios);
          final despues = [
            for (final servicio in lista.servicios)
              if (servicio.id != activo?.id) servicio,
          ];
          Widget tarjeta(Servicio servicio, {bool activa = false}) => TarjetaServicio(
            key: ValueKey('tarjeta-${servicio.id}'),
            servicio: servicio,
            pendiente: lista.pendientesDe(servicio.id) > 0,
            fotosPendientes: lista.fotos.pendientesDe(servicio.id),
            ahora: ahora,
            abrirEnlace: widget.abrirEnlace,
            activa: activa,
            lista: activa ? lista : null,
            alTocar: () =>
                Navigator.of(context).restorablePushNamed(rutaServicio, arguments: servicio.id),
          );
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
                if (activo != null) ...[
                  const _TituloDeSeccion('Ahora'),
                  tarjeta(activo, activa: true),
                  const SizedBox(height: 12),
                  if (despues.isNotEmpty) const _TituloDeSeccion('Después'),
                ],
                for (final servicio in despues) ...[tarjeta(servicio), const SizedBox(height: 12)],
              ],
            ),
          );
        },
      ),
    );
  }
}

/// "Ahora" y "Después" sobre las tarjetas.
class _TituloDeSeccion extends StatelessWidget {
  const _TituloDeSeccion(this.texto);

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Semantics(
        header: true,
        child: Text(texto, style: Theme.of(context).textTheme.titleMedium),
      ),
    );
  }
}

/// Arriba de la lista. Lo informativo (sin conexión o un error, con la hora de la última
/// actualización; cambios y fotos pendientes por enviar) va junto en un solo recuadro, una fila
/// por cosa. Lo que pide algo al conductor (cambios o fotos de otro conductor, cambios que el
/// servidor no aplicó, fotos que rechazó) sigue aparte, cada uno en su recuadro. Si no hay nada
/// que contar, una línea discreta con la hora de la última actualización.
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
    final conProblemaDeConexion = lista.sinConexion || problema != null;
    final filas = [
      if (cola.pendientes > 0)
        _FilaDeEstado(
          textoPendientes(cola.pendientes, problema: cola.problema),
          key: const Key('pendientes'),
          icono: Icons.cloud_upload_outlined,
        ),
      if (fotos.pendientes > 0)
        _FilaDeEstado(
          textoFotosPendientes(fotos.pendientes, problema: fotos.problema),
          key: const Key('fotos-pendientes'),
          icono: Icons.photo_camera_outlined,
        ),
      if (lista.sinConexion)
        _FilaDeEstado(
          'Sin conexión. Se muestra lo guardado en el celular. $actualizada',
          icono: Icons.cloud_off_outlined,
        )
      else if (problema != null)
        _FilaDeEstado(
          '${problema.mensaje} $actualizada',
          icono: Icons.error_outline,
          tipo: TipoRecuadro.error,
        ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (filas.isNotEmpty) ...[_PanelDeEstado(filas), const SizedBox(height: 8)],
        for (final ajenos in cola.pendientesAjenos) ...[
          Recuadro(
            textoPendientesAjenos(ajenos),
            tipo: TipoRecuadro.aviso,
            icono: Icons.report_problem_outlined,
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
        if (!conProblemaDeConexion)
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

/// Una fila del recuadro de estado: icono y texto. Se anuncia a TalkBack al aparecer.
class _FilaDeEstado extends StatelessWidget {
  const _FilaDeEstado(this.texto, {super.key, required this.icono, this.tipo = TipoRecuadro.aviso});

  final String texto;
  final IconData icono;
  final TipoRecuadro tipo;

  @override
  Widget build(BuildContext context) {
    final colores = context.colores;
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icono, color: tipo == TipoRecuadro.error ? colores.peligro : colores.aviso),
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

/// Las filas de estado en un solo recuadro, separadas por líneas; rojo si alguna es un error.
class _PanelDeEstado extends StatelessWidget {
  const _PanelDeEstado(this.filas);

  final List<_FilaDeEstado> filas;

  @override
  Widget build(BuildContext context) {
    final colores = context.colores;
    final conError = filas.any((fila) => fila.tipo == TipoRecuadro.error);
    final color = conError ? colores.peligro : colores.aviso;
    return Container(
      key: const Key('estado-de-la-lista'),
      decoration: BoxDecoration(
        color: conError ? colores.peligroFondo : colores.avisoFondo,
        border: Border.all(color: color),
        borderRadius: const BorderRadius.all(Radius.circular(8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, fila) in filas.indexed) ...[
            if (i > 0) Divider(height: 1, thickness: 1, color: color),
            fila,
          ],
        ],
      ),
    );
  }
}

/// Un servicio de la lista. La del servicio activo ([activa]) va completa: franja del color del
/// estado, barra de avance, placa en grande, los lugares con sus botones de un toque y el botón del
/// paso que sigue. Las demás van compactas: estado, vehículo, hora y dónde recoger.
class TarjetaServicio extends StatelessWidget {
  const TarjetaServicio({
    super.key,
    required this.servicio,
    required this.ahora,
    required this.abrirEnlace,
    required this.alTocar,
    this.pendiente = false,
    this.fotosPendientes = 0,
    this.activa = false,
    this.lista,
  });

  final Servicio servicio;

  /// El servicio tiene toques que aún no han llegado al servidor.
  final bool pendiente;

  /// Fotos de este servicio que aún no están en el servidor.
  final int fotosPendientes;
  final DateTime ahora;
  final AbrirEnlace abrirEnlace;
  final VoidCallback alTocar;

  /// Es el servicio que el conductor está atendiendo ([servicioActivo]).
  final bool activa;

  /// Con ella la tarjeta activa ofrece el botón del paso que sigue.
  final ListaAsignaciones? lista;

  @override
  Widget build(BuildContext context) {
    final textos = Theme.of(context).textTheme;
    final colores = context.colores;
    final vehiculo = servicio.vehiculo;
    final descripcion = vehiculo.descripcion;
    final siguiente = siguientePaso(servicio.estado);
    final lista = this.lista;
    // Un regreso que espera a su ida no ofrece el paso: la etiqueta "Espera la ida" dice por qué.
    final conBoton =
        activa &&
        lista != null &&
        siguiente != null &&
        !(servicio.esperaIda &&
            regresoBloqueado(
              esRegreso: servicio.esRegreso,
              idaEntregada: false,
              destino: siguiente,
            ));

    final contenido = Column(
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
        if (activa) ...[
          const SizedBox(height: 16),
          BarraDeAvance(servicio.estado, estadoPrevio: servicio.estadoPrevio),
        ],
        const SizedBox(height: 12),
        Text(identificacionDe(vehiculo), style: activa ? estiloPlaca : textos.headlineSmall),
        if (activa) ...[
          if (vehiculo.placa != null && vehiculo.vin != null)
            Text(
              'VIN ${vehiculo.vin}',
              style: textos.bodyLarge?.copyWith(color: colores.textoSecundario),
            ),
          if (descripcion != null) Text(descripcion, style: textos.bodyLarge),
        ],
        const SizedBox(height: 8),
        Text(
          'Hora: ${textoProgramada(servicio.programadaPara, ahora: ahora)}',
          style: textos.bodyLarge,
        ),
        if (activa) ...[
          const Divider(height: 32),
          SeccionLugar(titulo: 'Recoger en', lugar: servicio.origen, abrirEnlace: abrirEnlace),
          const Divider(height: 32),
          SeccionLugar(
            titulo: 'Entregar en',
            lugar: servicio.destino,
            abrirEnlace: abrirEnlace,
            textoSinDatos: 'Sin destino registrado.',
          ),
          if (conBoton) ...[
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: _BotonDelPaso(
                key: ValueKey('paso-${servicio.id}-$siguiente'),
                servicio: servicio,
                destino: siguiente,
                lista: lista,
              ),
            ),
          ],
        ] else ...[
          const SizedBox(height: 4),
          Text(
            'Recoger en: ${servicio.origen.direccion ?? 'Sin dirección'}',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: textos.bodyLarge?.copyWith(color: colores.textoSecundario),
          ),
        ],
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(onPressed: alTocar, child: const Text('Ver detalle')),
        ),
      ],
    );

    if (activa) {
      // La activa no se abre al tocarla en cualquier parte (un roce con guantes al desplazar):
      // solo con "Ver detalle". Y TalkBack lee cada parte por separado.
      return Card(
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            Padding(padding: const EdgeInsets.fromLTRB(22, 16, 16, 16), child: contenido),
            // La franja del color del estado, dentro de la forma de la tarjeta.
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              width: 6,
              child: ColoredBox(
                key: const Key('franja-activa'),
                color: colores.deEstado(servicio.estado).texto,
              ),
            ),
          ],
        ),
      );
    }
    // Una compacta se abre al tocarla en cualquier parte (es lo único que hace) y TalkBack la lee
    // como un solo botón corto; "Ver detalle" se ve, pero no se anuncia aparte.
    return Semantics(
      key: Key('tarjeta-compacta-${servicio.id}'),
      container: true,
      button: true,
      label: '${identificacionDe(vehiculo)}, ${nombreEstado(servicio.estado)}. Ver detalle',
      onTap: alTocar,
      excludeSemantics: true,
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: alTocar,
          child: Padding(padding: const EdgeInsets.all(16), child: contenido),
        ),
      ),
    );
  }
}

/// "Marcar En camino" (o Recogido, o Entregado) en la tarjeta activa: el mismo recorrido que el
/// botón del detalle ([marcarPaso]), con la misma protección contra dos toques.
class _BotonDelPaso extends StatefulWidget {
  const _BotonDelPaso({
    super.key,
    required this.servicio,
    required this.destino,
    required this.lista,
  });

  final Servicio servicio;
  final String destino;
  final ListaAsignaciones lista;

  @override
  State<_BotonDelPaso> createState() => _BotonDelPasoState();
}

class _BotonDelPasoState extends State<_BotonDelPaso> with MarcadorDePaso {
  @override
  Widget build(BuildContext context) {
    return FilledButton(
      key: Key('tarjeta-marcar-${widget.destino}'),
      onPressed: ocupado
          ? null
          : () => marcarUnaVez(
              servicio: widget.servicio,
              destino: widget.destino,
              lista: widget.lista,
            ),
      child: Text('Marcar ${nombreEstado(widget.destino)}', textAlign: TextAlign.center),
    );
  }
}
