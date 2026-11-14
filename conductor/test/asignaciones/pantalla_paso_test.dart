// La pantalla de Recogido y Entregado: mínimo de fotos y nombre exigidos, placa o VIN digitados al
// recoger un vehículo que llegó sin ellos (1a-13b), bloqueo por capacidad mostrando qué falta
// entregar, el estado de la pantalla que sobrevive a que Android mate la app, miniaturas
// decodificadas en pequeño y los indicadores de fotos pendientes.

import 'dart:io';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/app.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/pantalla_paso.dart';
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

/// El cliente de la API con una subida de fotos que no lee el disco (dentro de testWidgets la
/// lectura real de archivos no avanza). La subida de verdad se prueba en api_fotos_test.dart y
/// subidor_fotos_test.dart.
class ApiDePrueba extends ClienteApi {
  ApiDePrueba(http.Client cliente, this.conSenal)
    : super(servidor: 'http://servidor.prueba', cliente: cliente);

  final bool Function() conSenal;

  /// El UUID de cada foto que llegó al servidor.
  final List<String> fotosSubidas = [];

  /// Lo que responde el servidor a una foto en vez de guardarla.
  ErrorApi? rechazo;

  @override
  Future<ResultadoFoto> subirFoto(String token, FotoLocal foto) async {
    if (!conSenal()) throw const ErrorDeRed();
    final error = rechazo;
    if (error != null) throw error;
    fotosSubidas.add(foto.id);
    return const ResultadoFoto(resultado: 'guardada', enlazada: true);
  }
}

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late ServidorDeEventos eventos;
  late AlmacenTokenEnMemoria token;
  late ApiDePrueba api;
  late Sesion sesion;
  late Sincronizador sincronizador;
  late SubidorDeFotos fotos;
  late ListaAsignaciones lista;
  late CamaraFalsa camara;
  var conSenal = false;
  var minimoFotos = 4;
  var capacidad = 1;
  var tipo = 'traslado';
  var sinIdentificar = <int>{};

  /// Cuándo exige la empresa la placa o el VIN (`momento_placa_vin`).
  var momento = 'recoger';

  const placas = {41: 'ABC123', 42: 'XYZ789'};

  /// El estado que tenía antes un servicio guardado en novedad.
  var previos = <int, String>{};
  // Viernes 20 de noviembre, 10:00 a. m. en Colombia.
  final ahora = DateTime.utc(2026, 11, 20, 15);

  Map<String, Object?> servicioDe(int id, String estado) => {
    ...servicioJson(id: id, estado: estado, placa: placas[id] ?? 'JKL456', tipo: tipo),
    'estado_previo': estado == 'novedad' ? eventos.previos[id] : null,
    'a_bordo': estado == 'recogido' || (estado == 'novedad' && eventos.previos[id] == 'recogido'),
    'grua': {'id': 2, 'placa': 'GRU001', 'capacidad': capacidad},
    if (sinIdentificar.contains(id))
      'vehiculo': {'placa': null, 'vin': null, 'marca': 'Mazda', 'linea': 'CX-30', 'color': 'Rojo'},
  };

  Future<http.Response> responder(PeticionRecibida peticion) async {
    if (!conSenal) sinSenal();
    return switch (peticion.url.path) {
      '/api/v1/eventos/' => eventos.recibir(peticion),
      '/api/v1/asignaciones/' => respuestaJson(
        200,
        {
          ...listaJson([
            for (final MapEntry(key: id, value: estado) in eventos.estados.entries)
              if (const {'asignado', 'en_camino', 'recogido', 'novedad'}.contains(estado))
                servicioDe(id, estado),
          ]),
          'configuracion': {'minimo_fotos': minimoFotos, 'momento_placa_vin': momento},
        },
        cabeceras: {'etag': '"${eventos.estados}"'},
      ),
      '/api/v1/salir/' => http.Response('', 204),
      _ => http.Response('', 404),
    };
  }

  /// Lo que quedó guardado la última vez que hubo señal, igual a lo que tiene el servidor.
  Future<void> guardar(Map<int, String> estados) async {
    eventos = ServidorDeEventos(estados)..previos.addAll(previos);
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        for (final MapEntry(key: id, value: estado) in estados.entries)
          Servicio.desdeJson(servicioDe(id, estado)),
      ],
      configuracion: ConfiguracionApp(minimoFotos: minimoFotos, momentoPlacaVin: momento),
      etag: '"e1"',
      hora: ahora.subtract(const Duration(minutes: 30)),
    );
  }

  void armar() {
    api = ApiDePrueba(servidor.cliente, () => conSenal);
    sesion = Sesion(api: api, base: prueba.base, almacenToken: token);
    // Sin reintentos con espera: en estas pruebas los envíos los disparan el toque y la lista.
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
  }

  void desarmar() {
    fotos.dispose();
    sincronizador.dispose();
  }

  setUp(() async {
    conSenal = false;
    minimoFotos = 4;
    capacidad = 1;
    tipo = 'traslado';
    sinIdentificar = {};
    momento = 'recoger';
    previos = {};
    prueba = await BaseDePrueba.crear();
    servidor = ServidorFalso(responder);
    token = AlmacenTokenEnMemoria('token-ana');
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await guardar({41: 'en_camino', 42: 'en_camino'});
    armar();
  });
  tearDown(() async {
    desarmar();
    await prueba.cerrar();
  });

  /// Una pantalla alta para ver la lista y el detalle completos sin desplazarse.
  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1080, 7200);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
  }

  Future<void> abrirApp(WidgetTester tester) async {
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
  }

  Future<void> tocar(WidgetTester tester, Finder boton) async {
    await tester.tap(boton);
    await tester.pumpAndSettle();
  }

  Future<void> abrirDetalle(WidgetTester tester, {String vehiculo = 'ABC123'}) async {
    pantallaAlta(tester);
    await abrirApp(tester);
    await tocar(tester, find.text(vehiculo));
  }

  /// Desde la lista hasta la pantalla de fotos y nombre del paso que sigue.
  Future<void> abrirPaso(
    WidgetTester tester, {
    String vehiculo = 'ABC123',
    String paso = 'Recogido',
  }) async {
    await abrirDetalle(tester, vehiculo: vehiculo);
    await tocar(tester, find.text('Marcar $paso'));
  }

  Future<void> tomarFotos(WidgetTester tester, int cuantas) async {
    for (var i = 0; i < cuantas; i++) {
      await tester.ensureVisible(find.byKey(const Key('tomar-foto')));
      await tocar(tester, find.byKey(const Key('tomar-foto')));
    }
  }

  Future<void> escribirNombre(WidgetTester tester, String nombre) async {
    await tester.ensureVisible(find.byKey(const Key('nombre-quien')));
    await tester.enterText(find.byKey(const Key('nombre-quien')), nombre);
    await tester.pumpAndSettle();
  }

  Future<void> marcar(WidgetTester tester) => tocar(tester, find.byKey(const Key('confirmar')));

  /// Escribe en un campo de la pantalla del paso ('placa-digitada', 'vin-digitado').
  Future<void> escribir(WidgetTester tester, String campo, String texto) async {
    await tester.ensureVisible(find.byKey(Key(campo)));
    await tester.enterText(find.byKey(Key(campo)), texto);
    await tester.pumpAndSettle();
  }

  String textoDe(WidgetTester tester, String campo) => tester
      .widget<TextField>(
        find.descendant(of: find.byKey(Key(campo)), matching: find.byType(TextField)),
      )
      .controller!
      .text;

  /// La flecha de volver de la barra superior.
  Future<void> volver(WidgetTester tester) => tocar(tester, find.byType(BackButton));

  /// Las filas de una tabla de la base local. (Sin `runAsync`: con tiempo real las miniaturas
  /// empezarían a leer sus archivos y en Windows quedarían tomados al borrar la carpeta.)
  Future<List<Map<String, Object?>>> tabla(WidgetTester tester, String nombre) =>
      prueba.base.db.query(nombre, orderBy: 'rowid');

  bool enLaPantallaDelPaso() => find.byKey(const Key('tomar-foto')).evaluate().isNotEmpty;

  /// Android mata la app (por ejemplo, con la cámara abierta): se pierde todo lo que estaba en
  /// memoria y la app arranca desde cero sobre lo que quedó en la base. (Que la base y los
  /// archivos sobreviven a cerrarla y abrirla se prueba en test/fotos/.)
  Future<void> matarYReabrir(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    desarmar();
    armar();
  }

  group('mínimo de fotos y nombre', () {
    testWidgets('con 3 fotos de 4 no deja marcar Recogido y dice cuántas faltan', (tester) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 3);
      await escribirNombre(tester, 'Carlos Pérez');
      expect(find.text('Lleva 3 de 4 fotos.'), findsOneWidget);

      await marcar(tester);

      expect(find.text('Falta 1 foto: lleva 3 de 4.'), findsOneWidget);
      expect(enLaPantallaDelPaso(), isTrue);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
    });

    testWidgets('sin el nombre de quien entrega no deja marcar Recogido', (tester) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 4);
      expect(find.text('Nombre de quien entrega el vehículo'), findsOneWidget);

      await marcar(tester);

      expect(
        find.text('Escriba el nombre de quien entrega el vehículo para marcar Recogido.'),
        findsOneWidget,
      );
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);

      // Al escribirlo, el aviso se quita y ya deja marcar.
      await escribirNombre(tester, 'Carlos Pérez');
      expect(find.byKey(const Key('faltantes')), findsNothing);
      await marcar(tester);
      expect((await tabla(tester, 'eventos_pendientes')).single['destino'], 'recogido');
    });

    testWidgets('Entregado exige las fotos y el nombre de quien recibe', (tester) async {
      await guardar({41: 'recogido'});
      await abrirPaso(tester, paso: 'Entregado');
      expect(find.text('Nombre de quien recibe el vehículo'), findsOneWidget);

      await marcar(tester);

      expect(
        find.text(
          'Faltan 4 fotos: lleva 0 de 4. '
          'Escriba el nombre de quien recibe el vehículo para marcar Entregado.',
        ),
        findsOneWidget,
      );
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
    });

    testWidgets('con 4 fotos y el nombre marca Recogido: el evento lleva el nombre y sus fotos', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 4);
      await escribirNombre(tester, '  Carlos Pérez ');
      expect(find.text('Lleva 4 fotos. El mínimo es 4.'), findsOneWidget);

      await marcar(tester);

      // Vuelve al detalle, con el estado nuevo y lo pendiente a la vista.
      expect(enLaPantallaDelPaso(), isFalse);
      expect(find.text('Recogido'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsOneWidget);
      expect(find.text('4 fotos por subir'), findsOneWidget);
      final evento = (await tabla(tester, 'eventos_pendientes')).single;
      expect(evento['destino'], 'recogido');
      expect(evento['nombre_quien'], 'Carlos Pérez');
      final guardadas = await tabla(tester, 'fotos_pendientes');
      expect(guardadas, hasLength(4));
      expect(guardadas.every((f) => f['evento_id'] == evento['id']), isTrue);
      expect(guardadas.every((f) => f['tipo'] == 'recogida' && f['borrador'] == 0), isTrue);
      expect(guardadas.every((f) => File(f['ruta']! as String).existsSync()), isTrue);
      expect(await tabla(tester, 'pasos_en_curso'), isEmpty);
    });

    testWidgets('el mínimo de fotos es el de la configuración de la empresa', (tester) async {
      minimoFotos = 2;
      await guardar({41: 'en_camino'});
      await abrirPaso(tester);
      await tomarFotos(tester, 1);
      await escribirNombre(tester, 'Carlos Pérez');

      await marcar(tester);
      expect(find.text('Falta 1 foto: lleva 1 de 2.'), findsOneWidget);

      await tomarFotos(tester, 1);
      await marcar(tester);
      expect((await tabla(tester, 'eventos_pendientes')).single['destino'], 'recogido');
    });

    testWidgets('con mínimo 0 las fotos no son obligatorias, pero el nombre sí', (tester) async {
      minimoFotos = 0;
      await guardar({41: 'en_camino'});
      await abrirPaso(tester);
      expect(find.text('Lleva 0 fotos. No son obligatorias.'), findsOneWidget);

      await marcar(tester);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);

      await escribirNombre(tester, 'Carlos Pérez');
      await marcar(tester);
      expect((await tabla(tester, 'eventos_pendientes')).single['destino'], 'recogido');
    });
  });

  group('la cámara', () {
    testWidgets('si el conductor cancela la cámara no se agrega ninguna foto', (tester) async {
      await abrirPaso(tester);
      camara.cancela = true;

      await tomarFotos(tester, 1);

      expect(find.text('Lleva 0 de 4 fotos.'), findsOneWidget);
      expect(await tabla(tester, 'fotos_pendientes'), isEmpty);
      // Y se puede intentar otra vez.
      await tomarFotos(tester, 1);
      expect(find.text('Lleva 1 de 4 fotos.'), findsOneWidget);
    });

    testWidgets('si la cámara no abre, lo dice y la pantalla sigue sirviendo', (tester) async {
      await abrirPaso(tester);
      camara.error = const ErrorDeCamara('No se pudo abrir la cámara. Intente de nuevo.');

      await tomarFotos(tester, 1);

      expect(find.text('No se pudo abrir la cámara. Intente de nuevo.'), findsOneWidget);
      await tomarFotos(tester, 1);
      expect(find.text('Lleva 1 de 4 fotos.'), findsOneWidget);
      expect(find.text('No se pudo abrir la cámara. Intente de nuevo.'), findsNothing);
    });

    testWidgets('una foto que no quedó como JPEG no se agrega y pide tomarla de nuevo', (
      tester,
    ) async {
      await abrirPaso(tester);
      camara.contenido = [137, 80, 78, 71, 13, 10, 26, 10];

      await tomarFotos(tester, 1);

      expect(find.text('La foto no quedó guardada como JPEG. Tómela de nuevo.'), findsOneWidget);
      expect(find.text('Lleva 0 de 4 fotos.'), findsOneWidget);
    });

    testWidgets('se puede quitar una foto del paso antes de marcarlo', (tester) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 2);
      final antes = await tabla(tester, 'fotos_pendientes');

      await tocar(tester, find.byType(MiniaturaFoto).first);
      expect(find.text('¿Quitar la foto 1?'), findsOneWidget);
      await tocar(tester, find.text('Quitar foto'));

      expect(find.text('Lleva 1 de 4 fotos.'), findsOneWidget);
      expect(find.byType(MiniaturaFoto), findsOneWidget);
      final despues = await tabla(tester, 'fotos_pendientes');
      expect(despues.single['id'], antes.last['id']);
      expect(File(antes.first['ruta']! as String).existsSync(), isFalse);
    });

    testWidgets('las miniaturas se decodifican en pequeño, nunca la imagen completa', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 3);

      final imagenes = tester.widgetList<Image>(find.byType(Image)).toList();
      expect(imagenes, hasLength(3));
      for (final imagen in imagenes) {
        final proveedor = imagen.image;
        expect(proveedor, isA<ResizeImage>());
        // 96 puntos de pantalla a 3 píxeles por punto.
        expect((proveedor as ResizeImage).width, 288);
        expect(proveedor.imageProvider, isA<FileImage>());
        expect(imagen.width, MiniaturaFoto.lado);
      }
    });
  });

  group('placa o VIN al recoger', () {
    /// Las fotos y el nombre completos: solo falta (o no) la identificación.
    Future<void> completarFotosYNombre(WidgetTester tester) async {
      await tomarFotos(tester, 4);
      await escribirNombre(tester, 'Carlos Pérez');
    }

    // Antes de la 1a-13b este caso bloqueaba el Recogido ("llame a logística") y, sin señal, el
    // conductor no podía recoger el vehículo.
    testWidgets('un vehículo sin placa ni VIN abre el Recogido y pide digitar placa o VIN', (
      tester,
    ) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');

      expect(enLaPantallaDelPaso(), isTrue);
      expect(find.byKey(const Key('placa-digitada')), findsOneWidget);
      expect(find.byKey(const Key('vin-digitado')), findsOneWidget);
      expect(
        find.text(
          'Este servicio no tiene placa ni VIN. Escriba al menos uno, como se ve en el vehículo.',
        ),
        findsOneWidget,
      );

      await completarFotosYNombre(tester);
      await marcar(tester);

      expect(find.text('El vehículo necesita placa o VIN (al menos uno).'), findsOneWidget);
      expect(enLaPantallaDelPaso(), isTrue);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
    });

    testWidgets('sin señal marca Recogido con la placa digitada: va en el evento y ya se ve', (
      tester,
    ) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');
      await completarFotosYNombre(tester);
      await escribir(tester, 'placa-digitada', 'xyz-987');

      await marcar(tester);

      // Vuelve al detalle, que ya muestra la placa digitada; la lista también.
      expect(enLaPantallaDelPaso(), isFalse);
      expect(find.text('XYZ987'), findsOneWidget);
      expect(find.text('Pendiente por enviar'), findsOneWidget);
      final evento = (await tabla(tester, 'eventos_pendientes')).single;
      expect((evento['destino'], evento['placa'], evento['vin']), ('recogido', 'XYZ987', null));
      expect(await tabla(tester, 'pasos_en_curso'), isEmpty);
      await volver(tester);
      expect(find.text('XYZ987'), findsOneWidget);
      expect(find.text('Sin placa ni VIN'), findsNothing);

      // Con señal, el evento sale con la placa y el vehículo la conserva.
      conSenal = true;
      await sincronizador.enviar();
      await tester.pumpAndSettle();
      final enviado = eventos.lotes.single.single;
      expect((enviado['id'], enviado['placa'], enviado['vin']), (evento['id'], 'XYZ987', null));
      expect(eventos.estados[41], 'recogido');
      expect(find.text('XYZ987'), findsOneWidget);
    });

    testWidgets('un traslado se puede recoger con solo el VIN digitado', (tester) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');
      await completarFotosYNombre(tester);
      await escribir(tester, 'vin-digitado', '1hgcm-82633 a004352');

      await marcar(tester);

      final evento = (await tabla(tester, 'eventos_pendientes')).single;
      expect((evento['placa'], evento['vin']), (null, '1HGCM82633A004352'));
      expect(find.text('1HGCM82633A004352'), findsOneWidget);
    });

    testWidgets('un desvare sin placa pide solo la placa, y sin ella no deja marcar', (
      tester,
    ) async {
      sinIdentificar = {41};
      tipo = 'desvare';
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');

      expect(find.byKey(const Key('placa-digitada')), findsOneWidget);
      expect(find.byKey(const Key('vin-digitado')), findsNothing);
      expect(
        find.text(
          'Un desvare exige la placa y este servicio no la tiene. Escríbala como se ve en el '
          'vehículo.',
        ),
        findsOneWidget,
      );
      await completarFotosYNombre(tester);
      await marcar(tester);
      expect(find.text('Un desvare exige la placa del vehículo.'), findsOneWidget);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);

      await escribir(tester, 'placa-digitada', 'ABC 123');
      expect(find.byKey(const Key('faltantes')), findsNothing);
      await marcar(tester);
      expect((await tabla(tester, 'eventos_pendientes')).single['placa'], 'ABC123');
    });

    testWidgets('un VIN mal digitado no deja marcar y dice cómo debe ser', (tester) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');
      await completarFotosYNombre(tester);
      await escribir(tester, 'vin-digitado', '1HGCM82633A0O4352');

      await marcar(tester);

      expect(find.text('El VIN debe tener 17 letras o dígitos, sin I, O ni Q.'), findsOneWidget);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);

      await escribir(tester, 'vin-digitado', '1HGCM82633A004352');
      await marcar(tester);
      expect((await tabla(tester, 'eventos_pendientes')).single['vin'], '1HGCM82633A004352');
    });

    testWidgets('lo digitado sigue en la pantalla si Android mata la app', (tester) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');
      await escribir(tester, 'placa-digitada', 'xyz-9');
      await escribir(tester, 'vin-digitado', '1HGCM');
      final paso = (await tabla(tester, 'pasos_en_curso')).single;
      expect((paso['placa_digitada'], paso['vin_digitado']), ('xyz-9', '1HGCM'));

      await matarYReabrir(tester);
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN');

      expect(textoDe(tester, 'placa-digitada'), 'xyz-9');
      expect(textoDe(tester, 'vin-digitado'), '1HGCM');
      // Y sigue hasta marcar con lo que había escrito.
      await escribir(tester, 'placa-digitada', 'xyz-987');
      await escribir(tester, 'vin-digitado', '');
      await completarFotosYNombre(tester);
      await marcar(tester);
      final evento = (await tabla(tester, 'eventos_pendientes')).single;
      expect((evento['id'], evento['placa'], evento['vin']), (paso['evento_id'], 'XYZ987', null));
    });

    testWidgets(
      'con la configuración "al asignar" no se pide: se bloquea y dice que llame a logística',
      (tester) async {
        sinIdentificar = {41};
        momento = 'asignar';
        await guardar({41: 'en_camino'});
        await abrirDetalle(tester, vehiculo: 'Sin placa ni VIN');

        await tocar(tester, find.text('Marcar Recogido'));

        expect(find.text('Falta identificar el vehículo'), findsOneWidget);
        expect(
          find.textContaining('El vehículo necesita placa o VIN (al menos uno). Llame a logística'),
          findsOneWidget,
        );
        expect(enLaPantallaDelPaso(), isFalse);
        await tocar(tester, find.text('Entendido'));
        expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
        expect(await tabla(tester, 'pasos_en_curso'), isEmpty);
      },
    );

    testWidgets('un vehículo con placa no pide digitar nada', (tester) async {
      await abrirPaso(tester);

      expect(enLaPantallaDelPaso(), isTrue);
      expect(find.byKey(const Key('placa-digitada')), findsNothing);
      expect(find.byKey(const Key('vin-digitado')), findsNothing);
      expect(find.byKey(const Key('pide-identificacion')), findsNothing);
    });

    testWidgets('el Entregado no pide la placa ni el VIN', (tester) async {
      sinIdentificar = {41};
      await guardar({41: 'recogido'});
      await abrirPaso(tester, vehiculo: 'Sin placa ni VIN', paso: 'Entregado');

      expect(enLaPantallaDelPaso(), isTrue);
      expect(find.byKey(const Key('placa-digitada')), findsNothing);
      expect(find.byKey(const Key('vin-digitado')), findsNothing);
    });

    testWidgets('cuando logística registra la placa y la lista se actualiza, ya no la pide', (
      tester,
    ) async {
      sinIdentificar = {41};
      await guardar({41: 'en_camino'});
      pantallaAlta(tester);
      await abrirApp(tester);
      sinIdentificar = {};
      conSenal = true;

      await lista.actualizar();
      await tester.pumpAndSettle();
      await tocar(tester, find.text('ABC123'));
      await tocar(tester, find.text('Marcar Recogido'));

      expect(enLaPantallaDelPaso(), isTrue);
      expect(find.byKey(const Key('placa-digitada')), findsNothing);
    });
  });

  group('capacidad de la grúa', () {
    testWidgets(
      'con un vehículo montado, Recogido en otro se bloquea y muestra cuál falta entregar',
      (tester) async {
        await guardar({41: 'recogido', 42: 'en_camino'});
        await abrirDetalle(tester, vehiculo: 'XYZ789');

        await tocar(tester, find.text('Marcar Recogido'));

        expect(find.text('La grúa va llena'), findsOneWidget);
        expect(find.text('Falta marcar como Entregado:'), findsOneWidget);
        expect(
          tester.widget<Text>(find.byKey(const Key('falta-entregar-41'))).data,
          startsWith('ABC123'),
        );
        expect(find.byKey(const Key('falta-entregar-42')), findsNothing);
        expect(enLaPantallaDelPaso(), isFalse);
        await tocar(tester, find.text('Entendido'));
        expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
      },
    );

    testWidgets('funciona igual sin señal, con el Recogido anterior todavía sin enviar', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 4);
      await escribirNombre(tester, 'Carlos Pérez');
      await marcar(tester);
      await volver(tester);

      await tocar(tester, find.text('XYZ789'));
      await tocar(tester, find.text('Marcar Recogido'));

      expect(find.text('La grúa va llena'), findsOneWidget);
      expect(find.byKey(const Key('falta-entregar-41')), findsOneWidget);
      expect((await tabla(tester, 'eventos_pendientes')).map((e) => e['servicio_id']), [41]);
    });

    testWidgets('una novedad de un vehículo ya recogido sigue ocupando el puesto', (tester) async {
      previos = {41: 'recogido'};
      await guardar({41: 'novedad', 42: 'en_camino'});
      await abrirDetalle(tester, vehiculo: 'XYZ789');

      await tocar(tester, find.text('Marcar Recogido'));

      expect(find.byKey(const Key('falta-entregar-41')), findsOneWidget);
    });

    testWidgets('después de marcar Entregado el que iba montado, deja recoger el siguiente', (
      tester,
    ) async {
      await guardar({41: 'recogido', 42: 'en_camino'});
      await abrirPaso(tester, paso: 'Entregado');
      await tomarFotos(tester, 4);
      await escribirNombre(tester, 'Marta Díaz');
      await marcar(tester);
      await volver(tester);

      await tocar(tester, find.text('XYZ789'));
      await tocar(tester, find.text('Marcar Recogido'));

      expect(find.text('La grúa va llena'), findsNothing);
      expect(enLaPantallaDelPaso(), isTrue);
    });

    testWidgets('con capacidad 2 permite dos montados y bloquea el tercero', (tester) async {
      capacidad = 2;
      await guardar({41: 'recogido', 42: 'en_camino', 43: 'en_camino'});
      pantallaAlta(tester);
      await abrirApp(tester);

      // El segundo: hay un puesto libre.
      await tocar(tester, find.text('XYZ789'));
      await tocar(tester, find.text('Marcar Recogido'));
      expect(enLaPantallaDelPaso(), isTrue);
      await tomarFotos(tester, 4);
      await escribirNombre(tester, 'Carlos Pérez');
      await marcar(tester);
      expect(find.textContaining('Montado en la grúa: Sí'), findsOneWidget);
      await volver(tester);

      // El tercero: los dos puestos van ocupados.
      await tester.scrollUntilVisible(find.text('JKL456'), 400);
      await tester.ensureVisible(find.text('JKL456'));
      await tester.pumpAndSettle();
      await tocar(tester, find.text('JKL456'));
      await tocar(tester, find.text('Marcar Recogido'));
      expect(find.text('La grúa va llena'), findsOneWidget);
      expect(find.byKey(const Key('falta-entregar-41')), findsOneWidget);
      expect(find.byKey(const Key('falta-entregar-42')), findsOneWidget);
      expect(
        tester.widget<Text>(find.byKey(const Key('bloqueo'))).data,
        'La grúa tiene 2 puestos y ya lleva montados los vehículos ABC123, XYZ789. '
        'Marque uno como Entregado antes de recoger otro.',
      );
    });
  });

  group('sobrevive a que Android mate la app', () {
    testWidgets('las fotos tomadas y el nombre escrito siguen en la pantalla al reabrir', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 2);
      await escribirNombre(tester, 'Carlos Pé');
      final antes = await tabla(tester, 'fotos_pendientes');

      await matarYReabrir(tester);
      await abrirPaso(tester);

      expect(find.text('Lleva 2 de 4 fotos.'), findsOneWidget);
      expect(find.byType(MiniaturaFoto), findsNWidgets(2));
      expect(
        tester.widget<TextField>(find.byKey(const Key('nombre-quien'))).controller!.text,
        'Carlos Pé',
      );
      // Y sigue hasta marcar con las mismas fotos y el mismo evento.
      await tomarFotos(tester, 2);
      await escribirNombre(tester, 'Carlos Pérez');
      await marcar(tester);
      final guardadas = await tabla(tester, 'fotos_pendientes');
      expect(guardadas.map((f) => f['id']).take(2), antes.map((f) => f['id']));
      final evento = (await tabla(tester, 'eventos_pendientes')).single;
      expect(evento['id'], antes.first['evento_id']);
      expect(evento['nombre_quien'], 'Carlos Pérez');
    });

    testWidgets('la foto que se tomó con la app muerta aparece al volver a la pantalla', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 1);
      await escribirNombre(tester, 'Carlos');
      // Android mata la app con la cámara abierta: la llamada a la cámara nunca responde.
      camara.nuncaResponde = true;
      await tomarFotos(tester, 1);
      expect(camara.abiertas, 2);

      await matarYReabrir(tester);
      // El conductor tomó la foto y volvió: el celular la tiene guardada para la app.
      camara.perdida = camara.dejarFoto();
      await abrirPaso(tester);

      expect(find.text('Lleva 2 de 4 fotos.'), findsOneWidget);
      expect(
        tester.widget<TextField>(find.byKey(const Key('nombre-quien'))).controller!.text,
        'Carlos',
      );
      final guardadas = await tabla(tester, 'fotos_pendientes');
      expect(guardadas, hasLength(2));
      expect(guardadas.every((f) => File(f['ruta']! as String).existsSync()), isTrue);
      expect((await tabla(tester, 'pasos_en_curso')).single['camara_abierta_en'], isNull);
    });

    testWidgets('al restaurar la app, vuelve a la pantalla de fotos con lo que llevaba', (
      tester,
    ) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 3);
      await escribirNombre(tester, 'Carlos Pérez');

      // Android destruye la actividad y la restaura con su estado guardado.
      await tester.restartAndRestore();
      await tester.pumpAndSettle();

      expect(enLaPantallaDelPaso(), isTrue);
      expect(find.text('Lleva 3 de 4 fotos.'), findsOneWidget);
      expect(
        tester.widget<TextField>(find.byKey(const Key('nombre-quien'))).controller!.text,
        'Carlos Pérez',
      );
    });

    testWidgets('salir de la pantalla sin marcar conserva el paso para después', (tester) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 2);
      await escribirNombre(tester, 'Carlos');

      await volver(tester);
      expect(find.text('En camino'), findsOneWidget);
      await tocar(tester, find.text('Marcar Recogido'));

      expect(find.text('Lleva 2 de 4 fotos.'), findsOneWidget);
      expect(await tabla(tester, 'eventos_pendientes'), isEmpty);
    });
  });

  group('fotos pendientes por subir', () {
    Future<void> marcarRecogidoConFotos(WidgetTester tester) async {
      await abrirPaso(tester);
      await tomarFotos(tester, 4);
      await escribirNombre(tester, 'Carlos Pérez');
      await marcar(tester);
      await volver(tester);
    }

    testWidgets('sin señal, la lista dice cuántas fotos faltan por subir y marca el servicio', (
      tester,
    ) async {
      await marcarRecogidoConFotos(tester);

      expect(
        find.text('Hay 4 fotos pendientes por subir. Se suben solas cuando haya señal.'),
        findsOneWidget,
      );
      expect(find.text('4 fotos por subir'), findsOneWidget);
      expect(find.text('Recogido'), findsOneWidget);
      expect(api.fotosSubidas, isEmpty);
    });

    testWidgets('al volver la señal suben solas, después del evento, y el indicador desaparece', (
      tester,
    ) async {
      await marcarRecogidoConFotos(tester);
      final guardadas = await tabla(tester, 'fotos_pendientes');
      conSenal = true;

      await lista.actualizar();
      await tester.pumpAndSettle();

      expect(eventos.estados[41], 'recogido');
      expect(api.fotosSubidas, guardadas.map((f) => f['id']));
      expect(find.byKey(const Key('fotos-pendientes')), findsNothing);
      expect(find.text('4 fotos por subir'), findsNothing);
      // Los archivos se borraron solo después de confirmada la subida.
      expect(guardadas.any((f) => File(f['ruta']! as String).existsSync()), isFalse);
    });

    testWidgets('con señal, marcar el paso envía el evento y sube las fotos sin más toques', (
      tester,
    ) async {
      conSenal = true;
      await marcarRecogidoConFotos(tester);

      expect(eventos.estados[41], 'recogido');
      expect(api.fotosSubidas, hasLength(4));
      expect(find.byKey(const Key('fotos-pendientes')), findsNothing);
      expect(find.byKey(const Key('pendientes')), findsNothing);
    });

    testWidgets('las fotos pendientes siguen ahí después de cerrar y abrir la app', (tester) async {
      await marcarRecogidoConFotos(tester);

      await matarYReabrir(tester);
      await abrirApp(tester);

      expect(find.byKey(const Key('fotos-pendientes')), findsOneWidget);
      expect(find.text('4 fotos por subir'), findsOneWidget);
      final guardadas = await tabla(tester, 'fotos_pendientes');
      expect(guardadas.every((f) => File(f['ruta']! as String).existsSync()), isTrue);
    });

    testWidgets(
      'una foto que el servidor rechaza queda a la vista como problema hasta "Entendido"',
      (tester) async {
        await marcarRecogidoConFotos(tester);
        conSenal = true;
        api.rechazo = const ErrorDeContrato(
          estadoHttp: 413,
          codigo: 'foto_demasiado_grande',
          detalle: 'La foto pesa más de 5 MB.',
        );

        await lista.actualizar();
        await tester.pumpAndSettle();

        expect(
          find.text(
            'ABC123: una foto de la recogida no se pudo subir. La foto pesa más de 5 MB. '
            'La foto sigue guardada en este celular. Avise a logística.',
          ),
          findsNWidgets(4),
        );
        // Ya no están pendientes: no se van a reintentar.
        expect(find.byKey(const Key('fotos-pendientes')), findsNothing);
        final guardadas = await tabla(tester, 'fotos_pendientes');
        expect(guardadas.every((f) => f['estado_envio'] == 'error'), isTrue);
        expect(guardadas.every((f) => File(f['ruta']! as String).existsSync()), isTrue);

        await tocar(tester, find.text('Entendido').first);
        expect(find.textContaining('no se pudo subir'), findsNWidgets(3));
      },
    );

    testWidgets('con fotos pendientes no deja cerrar sesión y explica por qué', (tester) async {
      await marcarRecogidoConFotos(tester);
      // El evento ya llegó; las fotos todavía no.
      conSenal = true;
      api.rechazo = const ErrorDeRed();
      await lista.actualizar();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pendientes')), findsNothing);
      expect(find.byKey(const Key('fotos-pendientes')), findsOneWidget);

      await tocar(tester, find.byTooltip('Más opciones'));
      await tocar(tester, find.text('Cerrar sesión'));

      expect(find.text('Todavía no puede cerrar sesión'), findsOneWidget);
      expect(find.textContaining('Hay 4 fotos pendientes por subir.'), findsNWidgets(2));
      await tocar(tester, find.text('Entendido'));
      expect(sesion.estado, EstadoSesion.activa);
      expect(token.token, 'token-ana');
    });
  });

  testWidgets('con el texto del sistema al 200 % la pantalla de fotos y el bloqueo no se rompen', (
    tester,
  ) async {
    await guardar({41: 'recogido', 42: 'en_camino'});
    celularConTextoGrande(tester);
    await abrirApp(tester);

    await tester.scrollUntilVisible(find.text('XYZ789'), 400);
    await tester.pumpAndSettle();
    await tocar(tester, find.text('XYZ789'));
    await tocar(tester, find.text('Marcar Recogido'));
    expect(find.text('La grúa va llena'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('Entendido'));
    await tocar(tester, find.text('Entendido'));
    await volver(tester);

    await tester.scrollUntilVisible(find.text('ABC123'), -400);
    await tester.pumpAndSettle();
    await tocar(tester, find.text('ABC123'));
    await tocar(tester, find.text('Marcar Entregado'));
    expect(tester.takeException(), isNull);
    await tomarFotos(tester, 4);
    expect(tester.takeException(), isNull);
    await escribirNombre(tester, 'Marta Díaz');
    await marcar(tester);
    expect(tester.takeException(), isNull);
    expect(await tabla(tester, 'eventos_pendientes'), hasLength(1));
  });
}
