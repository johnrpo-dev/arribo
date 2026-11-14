// Las fotos en el celular: el paso de Recogido o Entregado que se guarda a medida que avanza
// (sobrevive a que Android mate la app al abrir la cámara), las fotos en disco con su UUID, y su
// paso a la cola de subida en la misma transacción que guarda el evento.

import 'dart:io';
import 'dart:typed_data';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/evento.dart';
import 'package:arribo_conductor/fotos/almacen_fotos.dart';
import 'package:arribo_conductor/fotos/foto.dart';
import 'package:flutter_test/flutter_test.dart';

import '../ayudas.dart';

const ana = Conductor(id: 3, nombre: 'Ana Gómez', celular: '3001234567');
const beto = Conductor(id: 8, nombre: 'Beto Ruiz', celular: '3009876543');
final hora = DateTime.utc(2026, 11, 20, 15);
final uuidV4 = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$');

void main() {
  late BaseDePrueba prueba;
  late AlmacenFotos almacen;
  late ColaEventos cola;
  late CamaraFalsa camara;

  setUp(() async {
    prueba = await BaseDePrueba.crear();
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        Servicio.desdeJson(servicioJson(id: 41, estado: 'en_camino')),
        Servicio.desdeJson(servicioJson(id: 42, estado: 'recogido', placa: 'XYZ789')),
      ],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: hora,
    );
    almacen = AlmacenFotos(prueba.base);
    cola = ColaEventos(prueba.base);
    camara = CamaraFalsa(prueba.carpeta);
  });
  tearDown(() => prueba.cerrar());

  Future<PasoEnCurso> abrir({
    Conductor conductor = ana,
    int servicioId = 41,
    String destino = 'recogido',
  }) => almacen.abrirPaso(
    conductorId: conductor.id,
    servicioId: servicioId,
    destino: destino,
    hora: hora,
  );

  Future<PasoEnCurso> releer(PasoEnCurso paso) async => (await almacen.leerPaso(
    conductorId: paso.conductorId,
    servicioId: paso.servicioId,
    destino: paso.destino,
  ))!;

  /// Toma [cuantas] fotos para el paso, cada una un segundo después de la anterior.
  Future<List<FotoLocal>> tomar(PasoEnCurso paso, int cuantas) async => [
    for (var i = 0; i < cuantas; i++)
      await almacen.agregarFoto(paso, camara.dejarFoto(), hora: hora.add(Duration(seconds: i))),
  ];

  /// Marca el paso: el evento entra a la cola y, en la misma transacción, sus fotos.
  Future<EventoLocal> marcar(
    PasoEnCurso paso, {
    Conductor conductor = ana,
    String? nombre = 'Carlos Pérez',
    int minimoFotos = 4,
  }) => cola.encolar(
    conductor: conductor,
    servicioId: paso.servicioId,
    destino: paso.destino,
    hora: hora,
    nombreQuien: nombre,
    id: paso.eventoId,
    alGuardar: (txn, evento) => almacen.confirmar(txn, evento, minimoFotos: minimoFotos),
  );

  /// El servidor respondió al evento: deja de estar pendiente.
  Future<void> responder(EventoLocal evento, {String resultado = ResultadoEvento.aplicado}) =>
      cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: resultado)],
        hora: hora,
      );

  Future<List<Map<String, Object?>>> filas(String tabla) => prueba.base.db.query(tabla);

  group('el paso en curso', () {
    test(
      'abrir el paso fija el UUID que llevará el evento; volver a abrirlo da el mismo',
      () async {
        final paso = await abrir();
        final otraVez = await abrir();

        expect(paso.eventoId, matches(uuidV4));
        expect(otraVez.eventoId, paso.eventoId);
        expect(paso.fotos, isEmpty);
        expect(paso.nombreQuien, '');
        expect(await filas('pasos_en_curso'), hasLength(1));
      },
    );

    test('Recogido y Entregado del mismo servicio son pasos distintos', () async {
      final recogido = await abrir(servicioId: 42, destino: 'recogido');
      final entregado = await abrir(servicioId: 42, destino: 'entregado');

      expect(entregado.eventoId, isNot(recogido.eventoId));
    });

    test('solo Recogido y Entregado llevan fotos', () {
      expect(() => abrir(destino: 'en_camino'), throwsArgumentError);
    });

    test(
      'cada foto queda en la carpeta privada de fotos con su propio UUID y sale de la caché',
      () async {
        final paso = await abrir();
        final temporal = camara.dejarFoto();

        final foto = await almacen.agregarFoto(paso, temporal, hora: hora);
        final otra = await almacen.agregarFoto(paso, camara.dejarFoto(), hora: hora);

        expect(foto.id, matches(uuidV4));
        expect(otra.id, isNot(foto.id));
        expect(foto.ruta, '${almacen.carpeta}/${foto.id}.jpg');
        // La carpeta está junto a la base local: almacenamiento privado de la app, no la caché.
        expect(almacen.carpeta, '${File(prueba.ruta).parent.path}/fotos');
        expect(File(foto.ruta).existsSync(), isTrue);
        expect(File(temporal).existsSync(), isFalse);
        expect(File(foto.ruta).readAsBytesSync().take(3), marcaJpeg);
        expect(foto.eventoId, paso.eventoId);
        expect(foto.tipo, 'recogida');
        expect(foto.borrador, isTrue);
        expect(foto.vehiculo, 'ABC123');
      },
    );

    test('las fotos de un Entregado son de tipo entrega', () async {
      final paso = await abrir(servicioId: 42, destino: 'entregado');

      final foto = await almacen.agregarFoto(paso, camara.dejarFoto(), hora: hora);

      expect(foto.tipo, 'entrega');
      expect(foto.vehiculo, 'XYZ789');
    });

    test('un archivo que no es JPEG no se agrega y se borra', () async {
      final paso = await abrir();
      camara.contenido = [137, 80, 78, 71, 13, 10, 26, 10];
      final temporal = camara.dejarFoto();

      await expectLater(
        almacen.agregarFoto(paso, temporal, hora: hora),
        throwsA(isA<FotoNoValida>()),
      );

      expect(File(temporal).existsSync(), isFalse);
      expect((await releer(paso)).fotos, isEmpty);
      expect(await filas('fotos_pendientes'), isEmpty);
    });

    test('una foto de más de 5 MB no se agrega: el servidor no la recibiría', () async {
      final paso = await abrir();
      camara.contenido = Uint8List(tamanoMaximoFoto + 1)..setAll(0, marcaJpeg);
      final temporal = camara.dejarFoto();

      await expectLater(
        almacen.agregarFoto(paso, temporal, hora: hora),
        throwsA(
          isA<FotoNoValida>().having((e) => e.mensaje, 'mensaje', contains('pesa demasiado')),
        ),
      );

      expect(File(temporal).existsSync(), isFalse);
      expect(await filas('fotos_pendientes'), isEmpty);
    });

    test('si la cámara no dejó el archivo, no se agrega nada', () async {
      final paso = await abrir();

      await expectLater(
        almacen.agregarFoto(paso, '${prueba.carpeta.path}/no_existe.jpg', hora: hora),
        throwsA(isA<FotoNoValida>()),
      );
      expect(await filas('fotos_pendientes'), isEmpty);
    });

    test('quitar una foto del paso borra su fila y su archivo', () async {
      final paso = await abrir();
      final [primera, segunda] = await tomar(paso, 2);

      await almacen.quitarFoto(primera);

      expect((await releer(paso)).fotos.map((f) => f.id), [segunda.id]);
      expect(File(primera.ruta).existsSync(), isFalse);
      expect(File(segunda.ruta).existsSync(), isTrue);
    });
  });

  group('sobrevive a que Android mate la app', () {
    test('las fotos tomadas y el nombre escrito siguen ahí al reabrir', () async {
      final paso = await abrir();
      final fotos = await tomar(paso, 2);
      await almacen.guardarNombre(paso, 'Carlos Pé');

      // El sistema mata la app (por ejemplo, al abrir la cámara) y el conductor vuelve.
      almacen = AlmacenFotos(await prueba.reabrir());
      final recuperado = await abrir();

      expect(recuperado.eventoId, paso.eventoId);
      expect(recuperado.nombreQuien, 'Carlos Pé');
      expect(recuperado.fotos.map((f) => f.id), fotos.map((f) => f.id));
      expect(recuperado.fotos.every((f) => File(f.ruta).existsSync()), isTrue);
    });

    test('la foto tomada con la app muerta se entrega al paso que abrió la cámara', () async {
      final paso = await abrir();
      await tomar(paso, 1);
      await almacen.camaraAbierta(paso, hora: hora);

      // Android mata la app con la cámara abierta; el conductor toma la foto y vuelve.
      almacen = AlmacenFotos(await prueba.reabrir());
      final perdida = camara.dejarFoto();
      final foto = await almacen.entregarFotoPerdida(
        perdida,
        hora: hora.add(const Duration(minutes: 1)),
      );

      final recuperado = await abrir();
      expect(foto, isNotNull);
      expect(recuperado.fotos, hasLength(2));
      expect(recuperado.fotos.last.id, foto!.id);
      expect(File(foto.ruta).existsSync(), isTrue);
      expect(File(perdida).existsSync(), isFalse);
    });

    test('la foto perdida se entrega una sola vez: después nadie espera otra', () async {
      final paso = await abrir();
      await almacen.camaraAbierta(paso, hora: hora);
      await almacen.entregarFotoPerdida(camara.dejarFoto(), hora: hora);

      final sobrante = camara.dejarFoto();
      final foto = await almacen.entregarFotoPerdida(sobrante, hora: hora);

      expect(foto, isNull);
      expect((await releer(paso)).fotos, hasLength(1));
      expect(File(sobrante).existsSync(), isFalse);
    });

    test('si el conductor canceló la cámara, no llega foto y el paso queda como estaba', () async {
      final paso = await abrir();
      await tomar(paso, 1);
      await almacen.camaraAbierta(paso, hora: hora);

      expect(await almacen.entregarFotoPerdida(null, hora: hora), isNull);

      expect((await releer(paso)).fotos, hasLength(1));
      expect((await filas('pasos_en_curso')).single['camara_abierta_en'], isNull);
    });

    test('con dos pasos abiertos, la foto perdida va al que tenía la cámara abierta', () async {
      final recogido = await abrir(servicioId: 41);
      final entregado = await abrir(servicioId: 42, destino: 'entregado');
      await almacen.camaraAbierta(entregado, hora: hora);

      await almacen.entregarFotoPerdida(camara.dejarFoto(), hora: hora);

      expect((await releer(recogido)).fotos, isEmpty);
      expect((await releer(entregado)).fotos.single.tipo, 'entrega');
    });
  });

  group('marcar el paso', () {
    test(
      'guarda el evento con el UUID del paso y sus fotos entran a la cola, todo junto',
      () async {
        final paso = await abrir();
        final fotos = await tomar(paso, 4);

        final evento = await marcar(paso);

        expect(evento.id, paso.eventoId);
        expect(evento.destino, 'recogido');
        expect(evento.nombreQuien, 'Carlos Pérez');
        final guardadas = await filas('fotos_pendientes');
        expect(guardadas, hasLength(4));
        expect(guardadas.every((f) => f['borrador'] == 0), isTrue);
        expect(guardadas.every((f) => f['evento_id'] == evento.id), isTrue);
        expect(guardadas.every((f) => f['estado_envio'] == 'pendiente'), isTrue);
        expect(guardadas.map((f) => f['id']).toSet(), fotos.map((f) => f.id).toSet());
        // El paso ya no está en curso.
        expect(await filas('pasos_en_curso'), isEmpty);
      },
    );

    test('con menos fotos que el mínimo no se guarda nada y dice cuántas faltan', () async {
      final paso = await abrir();
      await tomar(paso, 3);

      await expectLater(
        marcar(paso),
        throwsA(
          isA<ToqueNoValido>().having((e) => e.mensaje, 'mensaje', 'Falta 1 foto: lleva 3 de 4.'),
        ),
      );

      // Ni el evento, ni la secuencia, ni las fotos en la cola: el paso sigue como estaba.
      expect(await filas('eventos_pendientes'), isEmpty);
      expect(await prueba.base.leer(Clave.ultimaSecuencia), isNull);
      expect((await releer(paso)).fotos, hasLength(3));
      expect((await filas('fotos_pendientes')).every((f) => f['borrador'] == 1), isTrue);
    });

    test('sin el nombre de quien entrega no se guarda nada', () async {
      final paso = await abrir();
      await tomar(paso, 4);

      await expectLater(marcar(paso, nombre: '  '), throwsA(isA<ToqueNoValido>()));
      await expectLater(marcar(paso, nombre: null), throwsA(isA<ToqueNoValido>()));

      expect(await filas('eventos_pendientes'), isEmpty);
      expect(await filas('pasos_en_curso'), hasLength(1));
    });

    test('el mínimo de fotos es el de la configuración que se le pasa', () async {
      final paso = await abrir();
      await tomar(paso, 1);

      final evento = await marcar(paso, minimoFotos: 1);

      expect(evento.destino, 'recogido');
      expect(await filas('pasos_en_curso'), isEmpty);
    });

    test('un evento con un id que no es de un paso abierto no se guarda', () async {
      final paso = await abrir();
      await tomar(paso, 4);

      await expectLater(
        cola.encolar(
          conductor: ana,
          servicioId: 41,
          destino: 'recogido',
          hora: hora,
          nombreQuien: 'Carlos Pérez',
          alGuardar: (txn, evento) => almacen.confirmar(txn, evento, minimoFotos: 4),
        ),
        throwsA(isA<ToqueNoValido>()),
      );
      expect(await filas('eventos_pendientes'), isEmpty);
    });

    test('una foto que ya entró a la cola no se puede quitar', () async {
      final paso = await abrir();
      final fotos = await tomar(paso, 4);
      await marcar(paso);

      await almacen.quitarFoto(fotos.first);

      expect(await filas('fotos_pendientes'), hasLength(4));
      expect(File(fotos.first.ruta).existsSync(), isTrue);
    });

    test('las fotos de un paso sin marcar no cuentan como pendientes por enviar', () async {
      final paso = await abrir();
      await tomar(paso, 4);
      expect(await prueba.base.pendientesPorEnviar(conductorId: ana.id), 0);

      await marcar(paso);

      // El evento y sus cuatro fotos.
      expect(await prueba.base.pendientesPorEnviar(conductorId: ana.id), 5);
    });
  });

  group('la cola de subida', () {
    test('una foto no se sube antes de que su evento tenga respuesta del servidor', () async {
      final paso = await abrir();
      final fotos = await tomar(paso, 4);
      final evento = await marcar(paso);

      expect(await almacen.siguientePorSubir(ana.id), isNull);
      expect((await almacen.resumen(ana.id)).pendientes, 4);
      expect((await almacen.resumen(ana.id)).listas, 0);

      await responder(evento);

      expect((await almacen.siguientePorSubir(ana.id))?.id, fotos.first.id);
      expect((await almacen.resumen(ana.id)).listas, 4);
    });

    test('también se suben las fotos de un evento que quedó en conflicto', () async {
      final paso = await abrir();
      await tomar(paso, 4);
      final evento = await marcar(paso);

      await responder(evento, resultado: ResultadoEvento.conflicto);

      expect(await almacen.siguientePorSubir(ana.id), isNotNull);
    });

    test('las fotos salen de la más antigua a la más nueva', () async {
      final paso = await abrir();
      final fotos = await tomar(paso, 4);
      await responder(await marcar(paso));

      final orden = <String>[];
      for (var foto = await almacen.siguientePorSubir(ana.id); foto != null;) {
        orden.add(foto.id);
        await almacen.marcarSubida(foto.id, hora: hora);
        foto = await almacen.siguientePorSubir(ana.id);
      }

      expect(orden, fotos.map((f) => f.id));
    });

    test('el archivo se borra solo después de confirmada la subida', () async {
      final paso = await abrir();
      final [primera, segunda, ...] = await tomar(paso, 4);
      await responder(await marcar(paso));

      // Nada confirmado: no se borra nada.
      expect(await almacen.borrarArchivosSubidos(hora: hora), 0);
      expect(File(primera.ruta).existsSync(), isTrue);

      await almacen.marcarSubida(primera.id, hora: hora);
      expect(await almacen.borrarArchivosSubidos(hora: hora), 1);

      expect(File(primera.ruta).existsSync(), isFalse);
      expect(File(segunda.ruta).existsSync(), isTrue);
      // La fila queda con su resultado: nada se borra de la base.
      final fila = (await filas('fotos_pendientes')).firstWhere((f) => f['id'] == primera.id);
      expect(fila['estado_envio'], 'subida');
      expect(fila['subida_en'], isNotNull);
      expect(fila['archivo_borrado_en'], isNotNull);
      // Y no se vuelve a intentar borrarla.
      expect(await almacen.borrarArchivosSubidos(hora: hora), 0);
    });

    test(
      'una foto rechazada conserva su archivo, deja de estar pendiente y queda como problema',
      () async {
        final paso = await abrir();
        final [primera, ...] = await tomar(paso, 4);
        await responder(await marcar(paso));

        await almacen.marcarError(primera.id, 'La foto pesa más de 5 MB.');
        await almacen.borrarArchivosSubidos(hora: hora);

        final resumen = await almacen.resumen(ana.id);
        expect(resumen.pendientes, 3);
        expect(resumen.conProblema.single.id, primera.id);
        expect(resumen.conProblema.single.error, 'La foto pesa más de 5 MB.');
        expect(File(primera.ruta).existsSync(), isTrue);
        expect((await almacen.siguientePorSubir(ana.id))?.id, isNot(primera.id));

        await almacen.marcarVista(primera.id, hora: hora);
        expect((await almacen.resumen(ana.id)).conProblema, isEmpty);
        expect(await filas('fotos_pendientes'), hasLength(4));
      },
    );

    test('las fotos pendientes sobreviven a un reinicio', () async {
      final paso = await abrir();
      final fotos = await tomar(paso, 4);
      await responder(await marcar(paso));

      almacen = AlmacenFotos(await prueba.reabrir());

      expect((await almacen.resumen(ana.id)).pendientes, 4);
      expect((await almacen.siguientePorSubir(ana.id))?.id, fotos.first.id);
      expect(fotos.every((f) => File(f.ruta).existsSync()), isTrue);
    });

    test('el resumen cuenta por servicio y separa las fotos de otro conductor', () async {
      final deAna = await abrir(servicioId: 41);
      await tomar(deAna, 4);
      await marcar(deAna);
      final deBeto = await abrir(conductor: beto, servicioId: 42, destino: 'entregado');
      await tomar(deBeto, 2);
      await marcar(deBeto, conductor: beto, minimoFotos: 2);

      final resumenDeAna = await almacen.resumen(ana.id);
      expect(resumenDeAna.pendientes, 4);
      expect(resumenDeAna.porServicio, {41: 4});
      expect(resumenDeAna.ajenas, 2);
      final resumenDeBeto = await almacen.resumen(beto.id);
      expect(resumenDeBeto.porServicio, {42: 2});
      expect(resumenDeBeto.ajenas, 4);
      // Cada uno sube solo las suyas.
      await prueba.base.db.update('eventos_pendientes', {'estado_envio': 'aplicado'});
      expect((await almacen.siguientePorSubir(ana.id))?.conductorId, ana.id);
      expect((await almacen.siguientePorSubir(beto.id))?.conductorId, beto.id);
    });
  });
}
