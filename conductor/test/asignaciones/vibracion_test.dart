// La vibración corta de los momentos clave: siempre junto a un cambio que se ve (la confirmación
// que se abre, el paso guardado, el bloqueo explicado, la foto aceptada, el tema elegido) y nunca
// al cargar, al actualizar ni al sincronizar.

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/fotos/almacen_fotos.dart';
import 'package:arribo_conductor/fotos/camara.dart';
import 'package:arribo_conductor/fotos/foto.dart';
import 'package:arribo_conductor/fotos/subidor_fotos.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:material_ui/material_ui.dart';

import '../ayudas.dart';

/// El tipo de cada vibración como le llega a Android.
const ligera = 'HapticFeedbackType.lightImpact';
const media = 'HapticFeedbackType.mediumImpact';
const fuerte = 'HapticFeedbackType.heavyImpact';
const seleccion = 'HapticFeedbackType.selectionClick';

/// El cliente de la API sin subida real de fotos (dentro de testWidgets la lectura real de archivos
/// no avanza): en estas pruebas las fotos nunca llegan al servidor.
class _ApiSinSubidaDeFotos extends ClienteApi {
  _ApiSinSubidaDeFotos(http.Client cliente)
    : super(servidor: 'http://servidor.prueba', cliente: cliente);

  @override
  Future<ResultadoFoto> subirFoto(String token, FotoLocal foto) async => throw const ErrorDeRed();
}

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late Sesion sesion;
  late Sincronizador sincronizador;
  late SubidorDeFotos fotos;
  late ListaAsignaciones lista;
  late CamaraFalsa camara;
  const placas = {41: 'ABC123', 42: 'XYZ789'};
  // Viernes 20 de noviembre, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  Map<String, Object?> servicioDe(int id, String estado, {int capacidad = 1}) => {
    ...servicioJson(id: id, estado: estado, placa: placas[id], ordenRonda: id - 40),
    'a_bordo': estado == 'recogido',
    'grua': {'id': 2, 'placa': 'GRU001', 'capacidad': capacidad},
  };

  /// Lo que quedó guardado la última vez que hubo señal, con la grúa de [capacidad] puestos.
  Future<void> guardar(Map<int, String> estados, {int capacidad = 1}) async {
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        for (final MapEntry(key: id, value: estado) in estados.entries)
          Servicio.desdeJson(servicioDe(id, estado, capacidad: capacidad)),
      ],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora.subtract(const Duration(minutes: 30)),
    );
  }

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso((_) async => sinSenal());
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await guardar({41: 'asignado', 42: 'asignado'});
    final api = _ApiSinSubidaDeFotos(servidor.cliente);
    sesion = Sesion(api: api, base: prueba.base, almacenToken: AlmacenTokenEnMemoria('token-ana'));
    sincronizador = Sincronizador(
      cola: ColaEventos(prueba.base),
      api: api,
      sesion: sesion,
      reloj: () => ahora,
      esperas: const [],
    );
    fotos = SubidorDeFotos(
      almacen: AlmacenFotos(prueba.base),
      api: api,
      sesion: sesion,
      reloj: () => ahora,
      esperas: const [],
    );
    lista = ListaAsignaciones(
      almacen: AlmacenAsignaciones(prueba.base),
      api: api,
      sesion: sesion,
      sincronizador: sincronizador,
      fotos: fotos,
      reloj: () => ahora,
    );
    camara = CamaraFalsa(prueba.carpeta);
  });
  tearDown(() async {
    fotos.dispose();
    sincronizador.dispose();
    await prueba.cerrar();
  });

  /// Abre la app con la sesión iniciada, por defecto en una pantalla alta (todo se ve sin
  /// desplazarse), y devuelve las vibraciones desde antes de abrirla: abrir y cargar la lista no
  /// vibra.
  Future<List<String>> abrirApp(WidgetTester tester, {bool alta = true}) async {
    if (alta) {
      tester.view.physicalSize = const Size(1080, 7200);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
    }
    final vibraciones = registrarVibraciones(tester);
    await tester.pumpWidget(
      ArriboApp(
        sesion: sesion,
        lista: lista,
        reloj: () => ahora,
        abrirEnlace: (_) async => true,
        camara: camara,
      ),
    );
    await sesion.iniciar();
    await tester.pumpAndSettle();
    expect(vibraciones, isEmpty);
    return vibraciones;
  }

  Future<void> tocar(WidgetTester tester, Finder boton) async {
    await tester.tap(boton);
    await tester.pumpAndSettle();
  }

  Future<List<Map<String, Object?>>> cola(WidgetTester tester) =>
      prueba.base.db.query('eventos_pendientes', orderBy: 'secuencia');

  group('marcar un paso desde la lista y el detalle', () {
    testWidgets('un paso guardado vibra una vez, medio, después de la ligera de la confirmación', (
      tester,
    ) async {
      final vibraciones = await abrirApp(tester);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      expect(find.text('¿Marcar En camino?'), findsOneWidget);
      expect(vibraciones, [ligera]);
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(vibraciones, [ligera, media]);
      expect((await cola(tester)).single['destino'], 'en_camino');
    });

    testWidgets('cancelar la confirmación solo vibra al abrirla, nada se guarda', (tester) async {
      final vibraciones = await abrirApp(tester);

      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      await tocar(tester, find.text('Cancelar'));

      expect(vibraciones, [ligera]);
      expect(await cola(tester), isEmpty);
    });

    testWidgets('En camino bloqueado por un servicio sin finalizar vibra fuerte y no guarda nada', (
      tester,
    ) async {
      await guardar({41: 'en_camino', 42: 'asignado'});
      final vibraciones = await abrirApp(tester);
      await abrirDetalleDe(tester, 'XYZ789');

      await tocar(tester, find.text('Marcar En camino'));
      expect(find.text('Servicio sin finalizar'), findsOneWidget);
      expect(find.text('¿Marcar En camino?'), findsNothing);
      await tocar(tester, find.text('Entendido'));

      expect(vibraciones, [fuerte]);
      expect(await cola(tester), isEmpty);
    });

    testWidgets('Recogido bloqueado por la grúa llena vibra fuerte al mostrar por qué', (
      tester,
    ) async {
      await guardar({41: 'recogido', 42: 'en_camino'});
      final vibraciones = await abrirApp(tester);
      await abrirDetalleDe(tester, 'XYZ789');

      await tocar(tester, find.text('Marcar Recogido'));
      expect(find.text('La grúa va llena'), findsOneWidget);
      await tocar(tester, find.text('Entendido'));

      expect(vibraciones, [fuerte]);
      expect(await cola(tester), isEmpty);
    });

    testWidgets('una novedad vibra ligero al pedir el motivo y medio al quedar guardada', (
      tester,
    ) async {
      final vibraciones = await abrirApp(tester);
      await abrirDetalleDe(tester, 'ABC123');

      await tocar(tester, find.text('Reportar novedad'));
      expect(vibraciones, [ligera]);
      await tester.enterText(find.byKey(const Key('motivo')), 'Vía cerrada');
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(vibraciones, [ligera, media]);
      expect((await cola(tester)).single['destino'], 'novedad');
    });

    testWidgets('si el servicio cambió mientras confirmaba, vibra fuerte con el aviso', (
      tester,
    ) async {
      final vibraciones = await abrirApp(tester);
      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));

      // Con la confirmación abierta, llega del servidor que el servicio ya no está.
      servidor.responder = (_) async => listaCorrecta([servicioDe(42, 'asignado')], etag: '"e2"');
      await lista.actualizar();
      await tester.pumpAndSettle();
      expect(vibraciones, [ligera]);
      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(find.text('El servicio cambió mientras confirmaba. Revíselo de nuevo.'), findsOne);
      expect(vibraciones, [ligera, fuerte]);
      expect(await cola(tester), isEmpty);
    });
  });

  group('la pantalla de fotos y nombre', () {
    /// Desde la lista hasta la pantalla del Recogido del servicio en camino.
    Future<List<String>> abrirRecogido(WidgetTester tester) async {
      await guardar({41: 'en_camino', 42: 'asignado'});
      final vibraciones = await abrirApp(tester);
      await tocar(tester, find.byKey(const Key('tarjeta-marcar-recogido')));
      expect(find.byKey(const Key('tomar-foto')), findsOneWidget);
      return vibraciones;
    }

    Future<void> tomarFoto(WidgetTester tester) =>
        tocar(tester, find.byKey(const Key('tomar-foto')));

    testWidgets('abrirla no vibra; marcar con lo que falta vibra fuerte y no guarda nada', (
      tester,
    ) async {
      final vibraciones = await abrirRecogido(tester);
      expect(vibraciones, isEmpty);

      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(find.byKey(const Key('faltantes')), findsOneWidget);
      expect(vibraciones, [fuerte]);
      expect(await cola(tester), isEmpty);
    });

    testWidgets('cada foto aceptada vibra ligero', (tester) async {
      final vibraciones = await abrirRecogido(tester);

      await tomarFoto(tester);
      expect(find.text('Lleva 1 de 4 fotos.'), findsOneWidget);
      expect(vibraciones, [ligera]);
      await tomarFoto(tester);

      expect(vibraciones, [ligera, ligera]);
    });

    testWidgets('si el conductor cancela la cámara no vibra', (tester) async {
      final vibraciones = await abrirRecogido(tester);
      camara.cancela = true;

      await tomarFoto(tester);

      expect(find.text('Lleva 0 de 4 fotos.'), findsOneWidget);
      expect(vibraciones, isEmpty);
    });

    testWidgets('si la cámara no abre o la foto no sirve, vibra fuerte con el aviso', (
      tester,
    ) async {
      final vibraciones = await abrirRecogido(tester);

      camara.error = const ErrorDeCamara('No se pudo abrir la cámara. Intente de nuevo.');
      await tomarFoto(tester);
      expect(find.text('No se pudo abrir la cámara. Intente de nuevo.'), findsOneWidget);
      expect(vibraciones, [fuerte]);

      camara.contenido = [137, 80, 78, 71, 13, 10, 26, 10];
      await tomarFoto(tester);
      expect(find.text('La foto no quedó guardada como JPEG. Tómela de nuevo.'), findsOneWidget);
      expect(vibraciones, [fuerte, fuerte]);
    });

    testWidgets('marcar el paso completo vibra una vez, medio, al quedar guardado', (tester) async {
      final vibraciones = await abrirRecogido(tester);
      for (var i = 0; i < 4; i++) {
        await tomarFoto(tester);
      }
      await tester.enterText(find.byKey(const Key('nombre-quien')), 'Carlos Pérez');
      await tester.pumpAndSettle();
      vibraciones.clear();

      await tocar(tester, find.byKey(const Key('confirmar')));

      expect(find.byKey(const Key('tomar-foto')), findsNothing);
      expect(vibraciones, [media]);
      expect((await cola(tester)).single['destino'], 'recogido');
    });

    testWidgets('quitar una foto no vibra', (tester) async {
      final vibraciones = await abrirRecogido(tester);
      await tomarFoto(tester);
      vibraciones.clear();

      await tocar(tester, find.bySemanticsLabel('Foto 1. Toque para quitarla.'));
      await tocar(tester, find.text('Quitar foto'));

      expect(find.text('Lleva 0 de 4 fotos.'), findsOneWidget);
      expect(vibraciones, isEmpty);
    });
  });

  testWidgets('elegir un tema vibra una vez, de selección', (tester) async {
    final vibraciones = await abrirApp(tester);

    await tocar(tester, find.byTooltip('Más opciones'));
    await tocar(tester, find.text('Tema'));
    expect(vibraciones, isEmpty);
    await tocar(tester, find.byKey(const Key('tema-dark')));

    expect(find.byType(AlertDialog), findsNothing);
    expect(vibraciones, [seleccion]);
  });

  group('lo que pasa sin que el conductor marque nada no vibra', () {
    testWidgets('tocar Actualizar no vibra', (tester) async {
      final vibraciones = await abrirApp(tester);
      servidor.responder = (_) async =>
          listaCorrecta([servicioDe(41, 'asignado'), servicioDe(42, 'asignado')], etag: '"e2"');

      await tocar(tester, find.byTooltip('Actualizar'));

      expect(find.text('Actualizado hoy, 10:00 a. m.'), findsOneWidget);
      expect(vibraciones, isEmpty);
    });

    testWidgets('deslizar hacia abajo para actualizar no vibra', (tester) async {
      // En la pantalla de siempre: la lista se puede deslizar.
      final vibraciones = await abrirApp(tester, alta: false);

      await tester.fling(find.text('ABC123'), const Offset(0, 400), 1000);
      await tester.pumpAndSettle();

      expect(servidor.peticiones, hasLength(2));
      expect(vibraciones, isEmpty);
    });

    testWidgets('enviar el paso pendiente cuando vuelve la señal no vibra otra vez', (
      tester,
    ) async {
      final vibraciones = await abrirApp(tester);
      await tocar(tester, find.byKey(const Key('tarjeta-marcar-en_camino')));
      await tocar(tester, find.byKey(const Key('confirmar')));
      expect(vibraciones, [ligera, media]);

      final eventos = ServidorDeEventos({41: 'asignado', 42: 'asignado'});
      servidor.responder = (peticion) async => switch (peticion.url.path) {
        '/api/v1/eventos/' => eventos.recibir(peticion),
        _ => listaCorrecta([
          servicioDe(41, eventos.estados[41]!),
          servicioDe(42, eventos.estados[42]!),
        ], etag: '"e2"'),
      };
      await tocar(tester, find.byTooltip('Actualizar'));

      expect(eventos.aplicados, 1);
      expect(find.text('Pendiente por enviar'), findsNothing);
      expect(vibraciones, [ligera, media]);
    });
  });
}
