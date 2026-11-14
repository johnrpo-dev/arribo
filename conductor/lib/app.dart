// La app: tema, idioma y qué pantalla se ve según la sesión.

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
  });

  final Sesion sesion;
  final ListaAsignaciones lista;
  final AbrirEnlace abrirEnlace;

  /// Con qué se toman las fotos de evidencia; por defecto, la cámara del sistema.
  final Camara? camara;
  final String servidor;
  final DateTime Function() reloj;

  @override
  State<ArriboApp> createState() => _ArriboAppState();
}

class _ArriboAppState extends State<ArriboApp> {
  final _navegador = GlobalKey<NavigatorState>();
  late EstadoSesion _estadoAnterior = widget.sesion.estado;
  late final Camara _camara = widget.camara ?? CamaraDelSistema();

  @override
  void initState() {
    super.initState();
    widget.sesion.addListener(_alCambiarLaSesion);
  }

  @override
  void dispose() {
    widget.sesion.removeListener(_alCambiarLaSesion);
    super.dispose();
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
    return MaterialApp(
      title: 'Arribo conductor',
      navigatorKey: _navegador,
      restorationScopeId: 'arribo',
      debugShowCheckedModeBanner: false,
      theme: temaArribo(),
      themeMode: ThemeMode.light,
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
