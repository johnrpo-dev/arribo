// La cámara del sistema: la foto se pide ya achicada y comprimida (el plugin lo hace en nativo y
// entrega solo la ruta), el original de la cámara no se queda ocupando espacio y la foto que quedó
// sin entregar cuando Android mató la app se recupera.

import 'dart:io';

import 'package:arribo_conductor/fotos/camara.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const canal = MethodChannel('plugins.flutter.io/image_picker');
  final llamadas = <MethodCall>[];
  late Directory cache;
  Object? Function(MethodCall llamada) responder = (_) => null;

  setUp(() {
    llamadas.clear();
    cache = Directory.systemTemp.createTempSync('arribo_camara_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      canal,
      (llamada) async {
        llamadas.add(llamada);
        return responder(llamada);
      },
    );
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      canal,
      null,
    );
    cache.deleteSync(recursive: true);
  });

  /// Lo que deja el plugin en la caché de la app: el original de la cámara y el comprimido.
  ({File original, File comprimida}) fotoEnCache() {
    final original = File('${cache.path}/image_picker123.jpg')
      ..writeAsBytesSync(List.filled(4096, 7));
    final comprimida = File('${cache.path}/scaled_image_picker123.jpg')
      ..writeAsBytesSync(jpegDePrueba);
    return (original: original, comprimida: comprimida);
  }

  test(
    'pide la foto a la cámara del sistema, achicada a 1600 px y en JPEG de calidad 80',
    () async {
      final foto = fotoEnCache();
      responder = (_) => foto.comprimida.path;

      final ruta = await CamaraDelSistema().tomarFoto();

      expect(ruta, foto.comprimida.path);
      final llamada = llamadas.single;
      expect(llamada.method, 'pickImage');
      final argumentos = llamada.arguments as Map<Object?, Object?>;
      // 0 es la cámara; 1 sería la galería.
      expect(argumentos['source'], 0);
      expect(argumentos['maxWidth'], 1600);
      expect(argumentos['maxHeight'], 1600);
      expect(argumentos['imageQuality'], 80);
      expect(ladoMaximoFoto, 1600);
      expect(calidadJpeg, 80);
    },
  );

  test('se queda solo con la foto comprimida: el original de la cámara se borra', () async {
    final foto = fotoEnCache();
    responder = (_) => foto.comprimida.path;

    await CamaraDelSistema().tomarFoto();

    expect(foto.comprimida.existsSync(), isTrue);
    expect(foto.original.existsSync(), isFalse);
  });

  test('si el conductor cancela la cámara, no hay foto', () async {
    responder = (_) => null;

    expect(await CamaraDelSistema().tomarFoto(), isNull);
  });

  test('si la cámara no se puede abrir, el error llega con un texto para el conductor', () async {
    responder = (_) => throw PlatformException(code: 'no_available_camera');

    await expectLater(
      CamaraDelSistema().tomarFoto(),
      throwsA(
        isA<ErrorDeCamara>().having(
          (e) => e.mensaje,
          'mensaje',
          'No se encontró una cámara en este celular.',
        ),
      ),
    );
  });

  test('recupera la foto que quedó sin entregar cuando Android mató la app', () async {
    final foto = fotoEnCache();
    responder = (llamada) =>
        llamada.method == 'retrieve' ? {'type': 'image', 'path': foto.comprimida.path} : null;

    final ruta = await CamaraDelSistema().recuperarFotoPerdida();

    expect(llamadas.single.method, 'retrieve');
    expect(ruta, foto.comprimida.path);
    expect(foto.original.existsSync(), isFalse);
  });

  test('si no quedó ninguna foto sin entregar, no recupera nada', () async {
    responder = (_) => null;

    expect(await CamaraDelSistema().recuperarFotoPerdida(), isNull);
  });
}
