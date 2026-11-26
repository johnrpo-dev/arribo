// La app: tema, idioma y qué pantalla se ve según la sesión.

import 'dart:async';

import 'package:material_ui/material_ui.dart';

import 'api.dart';
import 'asignaciones/enlaces.dart';
import 'asignaciones/lista_asignaciones.dart';
import 'asignaciones/pantalla_asignaciones.dart';
import 'asignaciones/pantalla_paso.dart';
import 'asignaciones/pantalla_servicio.dart';
import 'comunes.dart';
import 'fotos/camara.dart';
import 'ingreso/pantalla_ingreso.dart';
import 'ingreso/sesion.dart';
import 'preferencia_tema.dart';
import 'push.dart';
import 'tema.dart';

class ArriboApp extends StatefulWidget {
  const ArriboApp({
    super.key,
    required this.sesion,
    required this.lista,
    this.abrirEnlace = abrirEnlaceExterno,
    this.camara,
    this.servidor = servidorConfigurado,
    this.reloj = DateTime.now,
    this.avisosTocados,
    this.tema,
  });

  final Sesion sesion;
  final ListaAsignaciones lista;
  final AbrirEnlace abrirEnlace;

  /// Con qué se toman las fotos de evidencia; por defecto, la cámara del sistema.
  final Camara? camara;
  final String servidor;
  final DateTime Function() reloj;

  /// Las notificaciones push que el conductor toca (1a-14): cada una lleva a la lista y la
  /// refresca. null sin Firebase (y en las pruebas que no lo usan).
  final Stream<MensajePush>? avisosTocados;

  /// El tema elegido (automático, claro u oscuro), ya leído de la base. Si no llega, se lee al
  /// abrir y mientras tanto sigue al teléfono.
  final PreferenciaTema? tema;

  @override
  State<ArriboApp> createState() => _ArriboAppState();
}

class _ArriboAppState extends State<ArriboApp> {
  final _navegador = GlobalKey<NavigatorState>();
  late EstadoSesion _estadoAnterior = widget.sesion.estado;
  late final Camara _camara = widget.camara ?? CamaraDelSistema();
  StreamSubscription<MensajePush>? _avisos;
  late final PreferenciaTema _tema;

  // Los dos temas se arman una vez: cambiar de modo solo elige cuál se usa.
  final _temaClaro = temaArribo();
  final _temaOscuro = temaArribo(Brightness.dark);

  @override
  void initState() {
    super.initState();
    final dado = widget.tema;
    if (dado != null) {
      _tema = dado;
    } else {
      _tema = PreferenciaTema(widget.sesion.base);
      unawaited(_tema.recargar());
    }
    widget.sesion.addListener(_alCambiarLaSesion);
    _avisos = widget.avisosTocados?.listen(_alTocarUnAviso);
  }

  @override
  void dispose() {
    widget.sesion.removeListener(_alCambiarLaSesion);
    unawaited(_avisos?.cancel());
    if (widget.tema == null) _tema.dispose();
    super.dispose();
  }

  /// El conductor tocó una notificación: se cierran las pantallas abiertas encima de la lista y
  /// se pide la lista al servidor. El servicio del aviso aparece en ella (o desaparece, si era
  /// "retirado"). Sin sesión no hace nada: queda el ingreso.
  void _alTocarUnAviso(MensajePush aviso) {
    if (widget.sesion.estado != EstadoSesion.activa) return;
    _navegador.currentState?.popUntil((ruta) => ruta.isFirst);
    unawaited(widget.lista.actualizar());
  }

  /// Al cerrarse la sesión (también por un 401) se cierran las pantallas abiertas encima de la
  /// lista, para que quede a la vista el ingreso.
  void _alCambiarLaSesion() {
    final estado = widget.sesion.estado;
    if (estado != _estadoAnterior && estado == EstadoSesion.sinSesion) {
      _navegador.currentState?.popUntil((ruta) => ruta.isFirst);
    }
    _estadoAnterior = estado;
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<ThemeMode>(
      valueListenable: _tema,
      builder: (context, modo, _) => _app(modo),
    );
  }

  Widget _app(ThemeMode modo) {
    return MaterialApp(
      title: 'Arribo conductor',
      navigatorKey: _navegador,
      restorationScopeId: 'arribo',
      debugShowCheckedModeBanner: false,
      theme: _temaClaro,
      darkTheme: _temaOscuro,
      themeMode: modo,
      locale: const Locale('es', 'CO'),
      supportedLocales: const [Locale('es', 'CO')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: ListenableBuilder(
        listenable: widget.sesion,
        builder: (context, _) => switch (widget.sesion.estado) {
          EstadoSesion.iniciando => const PantallaCargando(),
          EstadoSesion.sinSesion => PantallaIngreso(
            sesion: widget.sesion,
            sincronizador: widget.lista.sincronizador,
            servidor: widget.servidor,
            reloj: widget.reloj,
          ),
          EstadoSesion.activa => PantallaAsignaciones(
            lista: widget.lista,
            sesion: widget.sesion,
            abrirEnlace: widget.abrirEnlace,
            reloj: widget.reloj,
            tema: _tema,
          ),
        },
      ),
      onGenerateRoute: (ajustes) {
        final argumentos = ajustes.arguments;
        if (ajustes.name == rutaServicio && argumentos is int) {
          return MaterialPageRoute<void>(
            settings: ajustes,
            builder: (context) => PantallaServicio(
              id: argumentos,
              lista: widget.lista,
              abrirEnlace: widget.abrirEnlace,
              reloj: widget.reloj,
            ),
          );
        }
        if (ajustes.name == rutaPaso && argumentos is Map) {
          final id = argumentos['id'];
          final destino = argumentos['destino'];
          if (id is! int || destino is! String) return null;
          return MaterialPageRoute<void>(
            settings: ajustes,
            builder: (context) => PantallaPaso(
              servicioId: id,
              destino: destino,
              lista: widget.lista,
              camara: _camara,
              reloj: widget.reloj,
            ),
          );
        }
        return null;
      },
    );
  }
}
