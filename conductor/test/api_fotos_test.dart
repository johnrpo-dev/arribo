// Cliente de la API: subida de una foto (PUT /api/v1/evidencias/<uuid>/, docs/api-conductor.md).

import 'dart:io';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/fotos/foto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'ayudas.dart';

void main() {
  const id = '7c9e6679-7425-40de-944b-e07fc1f90ae7';
  const eventoId = '0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e';
  late Directory carpeta;
  late FotoLocal foto;

  setUp(() {
    carpeta = Directory.systemTemp.createTempSync('arribo_foto_');
    final archivo = File('${carpeta.path}/$id.jpg')..writeAsBytesSync(jpegDePrueba);
    foto = FotoLocal(
      id: id,
      conductorId: 3,
      servicioId: 41,
      eventoId: eventoId,
      tipo: TipoFoto.recogida,
      ruta: archivo.path,
      creadoEn: DateTime.utc(2026, 11, 20, 19, 42, 7),
    );
  });
  tearDown(() => carpeta.deleteSync(recursive: true));

  http.Response guardada({bool enlazada = false}) =>
      respuestaJson(201, {'version': 1, 'id': id, 'resultado': 'guardada', 'enlazada': enlazada});

  test(
    'sube la foto con PUT a su UUID, como multipart, con el token y los campos del contrato',
    () async {
      final servidor = ServidorFalso((_) async => guardada());

      await servidor.api().subirFoto('token-ana', foto);

      final peticion = servidor.peticiones.single;
      expect(peticion.metodo, 'PUT');
      expect(peticion.url.path, '/api/v1/evidencias/$id/');
      expect(peticion.cabeceras['Authorization'], 'Bearer token-ana');
      expect(peticion.cabeceras['content-type'], startsWith('multipart/form-data; boundary='));
      final recibida = fotoDe(peticion);
      expect(recibida.id, id);
      expect(recibida.servicioId, '41');
      expect(recibida.eventoId, eventoId);
      expect(recibida.tipo, 'recogida');
      // El archivo llega completo, byte por byte.
      expect(recibida.bytes, jpegDePrueba);
    },
  );

  test('ni el conductor ni ningún valor de cobro van en la subida', () async {
    final servidor = ServidorFalso((_) async => guardada());

    await servidor.api().subirFoto('token-ana', foto);

    final cuerpo = String.fromCharCodes(servidor.peticiones.single.bytes);
    final campos = RegExp(' name="([^"]+)"').allMatches(cuerpo).map((m) => m.group(1)).toSet();
    expect(campos, {'servicio_id', 'evento_id', 'tipo', 'archivo'});
  });

  test('201 guardada y 200 repetida son las dos una foto subida', () async {
    var respuesta = guardada(enlazada: true);
    final servidor = ServidorFalso((_) async => respuesta);

    final primera = await servidor.api().subirFoto('token-ana', foto);
    respuesta = respuestaJson(200, {
      'version': 1,
      'id': id,
      'resultado': 'repetida',
      'enlazada': true,
    });
    final segunda = await servidor.api().subirFoto('token-ana', foto);

    expect(primera.resultado, 'guardada');
    expect(primera.enlazada, isTrue);
    expect(segunda.resultado, 'repetida');
  });

  test('413: la foto pesa demasiado; se sabe por el código del contrato', () async {
    final servidor = ServidorFalso((_) async => fotoDemasiadoGrande());

    await expectLater(
      servidor.api().subirFoto('token-ana', foto),
      throwsA(
        isA<ErrorDeContrato>()
            .having((e) => e.estadoHttp, 'estadoHttp', 413)
            .having((e) => e.codigo, 'codigo', 'foto_demasiado_grande')
            .having((e) => e.detalle, 'detalle', 'La foto pesa más de 5 MB.'),
      ),
    );
  });

  test('409: ya hay otra foto con ese UUID', () async {
    final servidor = ServidorFalso(
      (_) async => errorDelContrato(409, 'evidencia_distinta', 'Ya hay otra foto con ese id.'),
    );

    await expectLater(
      servidor.api().subirFoto('token-ana', foto),
      throwsA(isA<ErrorDeContrato>().having((e) => e.estadoHttp, 'estadoHttp', 409)),
    );
  });

  test('401: la sesión se cerró', () async {
    final servidor = ServidorFalso(
      (_) async => errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida.'),
    );

    await expectLater(servidor.api().subirFoto('token-ana', foto), throwsA(isA<SesionCerrada>()));
  });

  test('sin señal y con un 500 son errores que se pueden reintentar', () async {
    final sinRed = ServidorFalso((_) async => sinSenal());
    final caido = ServidorFalso((_) async => http.Response('Error', 500));

    await expectLater(sinRed.api().subirFoto('token-ana', foto), throwsA(isA<ErrorDeRed>()));
    await expectLater(
      caido.api().subirFoto('token-ana', foto),
      throwsA(isA<ErrorDelServidor>().having((e) => e.estadoHttp, 'estadoHttp', 500)),
    );
  });

  test('si la subida tarda más que su tiempo máximo, es un error de red', () async {
    final servidor = ServidorFalso((_) async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      return guardada();
    });
    final api = ClienteApi(
      servidor: 'http://servidor.prueba',
      cliente: servidor.cliente,
      tiempoMaximoFoto: const Duration(milliseconds: 20),
    );

    await expectLater(api.subirFoto('token-ana', foto), throwsA(isA<ErrorDeRed>()));
  });

  test('si el archivo no está en el disco, falla sin llamar al servidor', () async {
    final servidor = ServidorFalso((_) async => guardada());
    File(foto.ruta).deleteSync();

    await expectLater(
      servidor.api().subirFoto('token-ana', foto),
      throwsA(isA<FileSystemException>()),
    );
    expect(servidor.peticiones, isEmpty);
  });
}
