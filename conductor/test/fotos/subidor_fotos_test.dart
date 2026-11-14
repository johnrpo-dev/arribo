// La cola de fotos: no pierde ninguna, no las duplica, sube una a la vez después de su evento,
// deja a la vista las que el servidor rechaza (sin reintentarlas para siempre), borra el archivo
// solo tras confirmar la subida y sobrevive a reinicios.

import 'dart:io';

import 'package:arribo_conductor/api.dart';
import 'package:arribo_conductor/asignaciones/almacen_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/lista_asignaciones.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:arribo_conductor/base_local.dart';
import 'package:arribo_conductor/cola/cola_eventos.dart';
import 'package:arribo_conductor/cola/sincronizador.dart';
import 'package:arribo_conductor/fotos/almacen_fotos.dart';
import 'package:arribo_conductor/fotos/foto.dart';
import 'package:arribo_conductor/fotos/subidor_fotos.dart';
import 'package:arribo_conductor/ingreso/sesion.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../ayudas.dart';

void main() {
  late BaseDePrueba prueba;
  late ServidorFalso servidor;
  late ServidorDeEventos eventos;
  late ServidorDeFotos fotos;
  late AlmacenTokenEnMemoria token;
  late Sesion sesion;
  late AlmacenFotos almacen;
  late ColaEventos cola;
  late SubidorDeFotos subidor;
  late CamaraFalsa camara;
  final desechables = <ChangeNotifier>[];
  var conSenal = true;
  final ahora = DateTime.utc(2026, 11, 20, 19, 42, 7);

  Future<http.Response> responder(PeticionRecibida peticion) async {
    if (!conSenal) sinSenal();
    final ruta = peticion.url.path;
    if (ruta.startsWith('/api/v1/evidencias/')) return fotos.recibir(peticion);
    return switch (ruta) {
      '/api/v1/eventos/' => eventos.recibir(peticion),
      '/api/v1/ingresar/' => ingresoCorrecto(token: 'token-ana-2'),
      '/api/v1/salir/' => http.Response('', 204),
      '/api/v1/asignaciones/' => listaCorrecta([
        for (final MapEntry(key: id, value: estado) in eventos.estados.entries)
          if (const {'asignado', 'en_camino', 'recogido', 'novedad'}.contains(estado))
            servicioJson(id: id, estado: estado, placa: 'ABC$id'),
      ], etag: '"${eventos.estados}"'),
      _ => http.Response('', 404),
    };
  }

  /// Sin reintento automático salvo que la prueba lo pida: cada subida la dispara la prueba.
  SubidorDeFotos nuevoSubidor(BaseLocal base, {List<Duration> esperas = const []}) {
    final nuevo = SubidorDeFotos(
      almacen: AlmacenFotos(base),
      api: servidor.api(),
      sesion: sesion,
      reloj: () => ahora,
      esperas: esperas,
    );
    desechables.add(nuevo);
    return nuevo;
  }

  /// Un Recogido o un Entregado ya marcado, con [cuantas] fotos en la cola. Con [respondido], el
  /// servidor ya respondió al evento (las fotos se pueden subir).
  Future<List<FotoLocal>> pasoMarcado({
    int servicioId = 41,
    String destino = 'recogido',
    int cuantas = 4,
    bool respondido = true,
    Conductor? conductor,
  }) async {
    final quien = conductor ?? sesion.conductor!;
    final paso = await almacen.abrirPaso(
      conductorId: quien.id,
      servicioId: servicioId,
      destino: destino,
      hora: ahora,
    );
    final tomadas = [
      for (var i = 0; i < cuantas; i++)
        await almacen.agregarFoto(paso, camara.dejarFoto(), hora: ahora.add(Duration(seconds: i))),
    ];
    final evento = await cola.encolar(
      conductor: quien,
      servicioId: servicioId,
      destino: destino,
      hora: ahora,
      nombreQuien: 'Carlos Pérez',
      id: paso.eventoId,
      alGuardar: (txn, evento) => almacen.confirmar(txn, evento, minimoFotos: cuantas),
    );
    if (respondido) {
      await cola.registrarResultados(
        [evento],
        [ResultadoEvento(id: evento.id, resultado: ResultadoEvento.aplicado)],
        hora: ahora,
      );
    }
    return tomadas;
  }

  Future<Map<String, String>> estadosDeEnvio() async => {
    for (final fila in await prueba.base.db.query('fotos_pendientes'))
      fila['id']! as String: fila['estado_envio']! as String,
  };

  bool existe(FotoLocal foto) => File(foto.ruta).existsSync();

  /// El sistema mata la app: se pierde lo que estaba en memoria y se abre de nuevo.
  Future<void> matarYReabrir() async {
    final base = await prueba.reabrir();
    sesion = Sesion(api: servidor.api(), base: base, almacenToken: token);
    await sesion.iniciar();
    almacen = AlmacenFotos(base);
    cola = ColaEventos(base);
    subidor = nuevoSubidor(base);
    await subidor.cargar();
  }

  setUp(() async {
    conSenal = true;
    prueba = await BaseDePrueba.crear();
    eventos = ServidorDeEventos({41: 'en_camino', 42: 'recogido'});
    fotos = ServidorDeFotos();
    servidor = ServidorFalso(responder);
    token = AlmacenTokenEnMemoria('token-ana');
    await prueba.base.escribirJson(Clave.conductor, conductorJson());
    await AlmacenAsignaciones(prueba.base).reemplazar(
      servicios: [
        Servicio.desdeJson(servicioJson(id: 41, estado: 'en_camino', placa: 'ABC41')),
        Servicio.desdeJson(servicioJson(id: 42, estado: 'recogido', placa: 'ABC42')),
      ],
      configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
      etag: '"e1"',
      hora: ahora,
    );
    sesion = Sesion(api: servidor.api(), base: prueba.base, almacenToken: token);
    await sesion.iniciar();
    almacen = AlmacenFotos(prueba.base);
    cola = ColaEventos(prueba.base);
    camara = CamaraFalsa(prueba.carpeta);
    subidor = nuevoSubidor(prueba.base);
  });
  tearDown(() async {
    // Lo que quedó en marcha termina antes de cerrar la base.
    await pumpEventQueue();
    for (final desechable in desechables) {
      desechable.dispose();
    }
    desechables.clear();
    await prueba.cerrar();
  });

  group('subir', () {
    test('sube cada foto una vez, en orden, con los datos de su evento', () async {
      final tomadas = await pasoMarcado();

      await subidor.subir();

      expect(fotos.recibidas, tomadas.map((f) => f.id));
      expect(fotos.guardadas.keys, tomadas.map((f) => f.id));
      final recibida = fotos.guardadas[tomadas.first.id]!;
      expect(recibida.servicioId, '41');
      expect(recibida.eventoId, tomadas.first.eventoId);
      expect(recibida.tipo, 'recogida');
      expect((await estadosDeEnvio()).values.toSet(), {'subida'});
      expect(subidor.pendientes, 0);
      expect(subidor.subidas, 4);
      expect(subidor.problema, isNull);
    });

    test('el archivo se borra solo después de que el servidor confirma esa foto', () async {
      final tomadas = await pasoMarcado();
      final existianAlLlegar = <String, bool>{};
      final anterioresBorradas = <bool>[];
      fotos.responderCon = (recibida) {
        final posicion = tomadas.indexWhere((f) => f.id == recibida.id);
        existianAlLlegar[recibida.id] = existe(tomadas[posicion]);
        // Las que ya confirmó el servidor están borradas; las que faltan, no.
        anterioresBorradas.add(tomadas.take(posicion).every((f) => !existe(f)));
        return null;
      };

      await subidor.subir();

      expect(existianAlLlegar.values, everyElement(isTrue));
      expect(anterioresBorradas, everyElement(isTrue));
      expect(tomadas.any(existe), isFalse);
    });

    test('no sube nada mientras el evento de la foto no tenga respuesta del servidor', () async {
      final tomadas = await pasoMarcado(respondido: false);

      await subidor.subir();

      expect(fotos.recibidas, isEmpty);
      expect((await estadosDeEnvio()).values.toSet(), {'pendiente'});
      expect(tomadas.every(existe), isTrue);
      await subidor.releer();
      expect(subidor.pendientes, 4);
    });

    test('nunca hay dos subidas a la vez: pedirlo dos veces sube cada foto una sola vez', () async {
      final tomadas = await pasoMarcado();

      await Future.wait([subidor.subir(), subidor.subir(), subidor.subir()]);

      expect(fotos.recibidas, tomadas.map((f) => f.id));
    });

    test(
      'una foto a la vez: la siguiente no sale hasta que el servidor responde la anterior',
      () async {
        await pasoMarcado();
        var enCurso = 0;
        var maximoALaVez = 0;
        servidor.responder = (peticion) async {
          enCurso++;
          if (enCurso > maximoALaVez) maximoALaVez = enCurso;
          await Future<void>.delayed(const Duration(milliseconds: 5));
          enCurso--;
          return responder(peticion);
        };

        await subidor.subir();

        expect(fotos.recibidas, hasLength(4));
        expect(maximoALaVez, 1);
      },
    );

    test('despertar no hace nada si no hay fotos listas, y sube si las hay', () async {
      await subidor.releer();
      subidor.despertar();
      await pumpEventQueue();
      expect(servidor.peticiones, isEmpty);

      await pasoMarcado();
      await subidor.releer();
      subidor.despertar();
      await esperarHasta(() => subidor.pendientes == 0);

      expect(fotos.guardadas, hasLength(4));
    });
  });

  group('no pierde fotos', () {
    test('sin señal quedan todas pendientes con su archivo, y suben al volver la señal', () async {
      final tomadas = await pasoMarcado();
      conSenal = false;

      await subidor.subir();

      expect(subidor.problema, isA<ErrorDeRed>());
      expect(subidor.pendientes, 4);
      expect((await estadosDeEnvio()).values.toSet(), {'pendiente'});
      expect(tomadas.every(existe), isTrue);

      conSenal = true;
      await subidor.subir();

      expect(fotos.guardadas.keys, tomadas.map((f) => f.id));
      expect(subidor.pendientes, 0);
      expect(subidor.problema, isNull);
    });

    test(
      'si la señal se corta a mitad, las que faltan siguen después sin repetir las subidas',
      () async {
        final tomadas = await pasoMarcado();
        var recibidas = 0;
        fotos.responderCon = (_) {
          recibidas++;
          if (recibidas == 3) sinSenal();
          return null;
        };

        await subidor.subir();
        expect(subidor.pendientes, 2);
        expect(tomadas.sublist(2).every(existe), isTrue);

        fotos.responderCon = null;
        await subidor.subir();

        expect(fotos.guardadas.keys, tomadas.map((f) => f.id));
        // La tercera se intentó dos veces; las dos primeras, una sola.
        expect(fotos.recibidas.where((id) => id == tomadas[0].id), hasLength(1));
        expect(fotos.recibidas.where((id) => id == tomadas[2].id), hasLength(2));
      },
    );

    test('un 500 deja la foto en la cola y se reintenta', () async {
      final tomadas = await pasoMarcado(cuantas: 1);
      fotos.responderCon = (_) => http.Response('Error', 500);

      await subidor.subir();

      expect(subidor.problema, isA<ErrorDelServidor>());
      expect((await estadosDeEnvio())[tomadas.single.id], 'pendiente');
      expect(existe(tomadas.single), isTrue);

      fotos.responderCon = null;
      await subidor.subir();
      expect((await estadosDeEnvio())[tomadas.single.id], 'subida');
    });

    test('las fotos pendientes sobreviven a un reinicio y suben después', () async {
      final tomadas = await pasoMarcado();
      conSenal = false;
      await subidor.subir();

      await matarYReabrir();
      expect(subidor.pendientes, 4);
      expect(tomadas.every(existe), isTrue);

      conSenal = true;
      await subidor.subir();

      expect(fotos.guardadas.keys, tomadas.map((f) => f.id));
      expect(tomadas.any(existe), isFalse);
    });

    test(
      'si la app muere entre confirmar la subida y borrar el archivo, se borra al abrir',
      () async {
        final tomadas = await pasoMarcado(cuantas: 1);
        await almacen.marcarSubida(tomadas.single.id, hora: ahora);
        expect(existe(tomadas.single), isTrue);

        await matarYReabrir();

        expect(existe(tomadas.single), isFalse);
        expect(subidor.pendientes, 0);
      },
    );
  });

  group('no duplica', () {
    test('si la respuesta se pierde, vuelve a subir la misma foto con el mismo UUID y el servidor '
        'guarda una sola', () async {
      final tomadas = await pasoMarcado(cuantas: 1);
      fotos.perderRespuesta = true;

      await subidor.subir();
      // El servidor ya la tiene, pero el celular no lo sabe: sigue pendiente y con su archivo.
      expect(fotos.guardadas, hasLength(1));
      expect((await estadosDeEnvio())[tomadas.single.id], 'pendiente');
      expect(existe(tomadas.single), isTrue);

      await subidor.subir();

      expect(fotos.recibidas, [tomadas.single.id, tomadas.single.id]);
      expect(fotos.guardadas, hasLength(1));
      expect((await estadosDeEnvio())[tomadas.single.id], 'subida');
      expect(existe(tomadas.single), isFalse);
    });

    test('una foto ya subida no se vuelve a subir', () async {
      await pasoMarcado();
      await subidor.subir();

      await subidor.subir();
      await matarYReabrir();
      await subidor.subir();

      expect(fotos.recibidas, hasLength(4));
    });
  });

  group('una foto que el servidor rechaza', () {
    test('413: queda visible como problema, conserva su archivo y no se reintenta; las demás '
        'suben', () async {
      final tomadas = await pasoMarcado();
      final grande = tomadas[1];
      fotos.responderCon = (recibida) => recibida.id == grande.id ? fotoDemasiadoGrande() : null;

      await subidor.subir();

      final estados = await estadosDeEnvio();
      expect(estados[grande.id], 'error');
      expect(({...estados}..remove(grande.id)).values, everyElement('subida'));
      expect(existe(grande), isTrue);
      expect(subidor.conProblema.single.id, grande.id);
      expect(subidor.conProblema.single.error, 'La foto pesa más de 5 MB.');
      expect(subidor.conProblema.single.vehiculo, 'ABC41');
      expect(subidor.pendientes, 0);

      // Ni pidiéndolo de nuevo, ni al reabrir la app: no se reintenta para siempre.
      await subidor.subir();
      await matarYReabrir();
      await subidor.subir();

      expect(fotos.recibidas.where((id) => id == grande.id), hasLength(1));
      expect(subidor.conProblema.single.id, grande.id);
      expect(subidor.esperaDelReintento, isNull);
    });

    test(
      '413 de un servidor intermedio (sin la forma del contrato): igual queda como problema',
      () async {
        final tomadas = await pasoMarcado(cuantas: 1);
        fotos.responderCon = (_) => http.Response('<html>Request Entity Too Large</html>', 413);

        await subidor.subir();
        await subidor.subir();

        expect((await estadosDeEnvio())[tomadas.single.id], 'error');
        expect(fotos.recibidas, hasLength(1));
        expect(existe(tomadas.single), isTrue);
      },
    );

    test('409: ya hay otra foto con ese UUID; queda como problema y no se reintenta', () async {
      final tomadas = await pasoMarcado(cuantas: 2);
      fotos.guardadas[tomadas.first.id] = FotoRecibida(
        id: tomadas.first.id,
        servicioId: '41',
        eventoId: tomadas.first.eventoId,
        tipo: 'recogida',
        bytes: const [255, 216, 255, 0],
      );

      await subidor.subir();
      await subidor.subir();

      final estados = await estadosDeEnvio();
      expect(estados[tomadas.first.id], 'error');
      expect(estados[tomadas.last.id], 'subida');
      expect(fotos.recibidas.where((id) => id == tomadas.first.id), hasLength(1));
      expect(existe(tomadas.first), isTrue);
      expect(subidor.conProblema.single.error, 'Ya hay otra foto con ese identificador.');
    });

    test('404 del contrato (el servicio nunca fue suyo): no se reintenta', () async {
      final tomadas = await pasoMarcado(cuantas: 1);
      fotos.responderCon = (_) =>
          errorDelContrato(404, 'no_encontrado', 'No se encontró el servicio.');

      await subidor.subir();
      await subidor.subir();

      expect((await estadosDeEnvio())[tomadas.single.id], 'error');
      expect(fotos.recibidas, hasLength(1));
    });

    test(
      'si el archivo ya no está en el celular, queda como problema sin llamar al servidor',
      () async {
        final tomadas = await pasoMarcado(cuantas: 2);
        File(tomadas.first.ruta).deleteSync();

        await subidor.subir();

        final estados = await estadosDeEnvio();
        expect(estados[tomadas.first.id], 'error');
        expect(estados[tomadas.last.id], 'subida');
        expect(fotos.recibidas, [tomadas.last.id]);
      },
    );

    test(
      'el aviso desaparece cuando el conductor lo da por visto; la foto sigue guardada',
      () async {
        final tomadas = await pasoMarcado(cuantas: 1);
        fotos.responderCon = (_) => fotoDemasiadoGrande();
        await subidor.subir();

        await subidor.marcarVista(tomadas.single.id);

        expect(subidor.conProblema, isEmpty);
        expect((await estadosDeEnvio())[tomadas.single.id], 'error');
        expect(existe(tomadas.single), isTrue);
      },
    );
  });

  group('reintento con espera creciente', () {
    test('después de un fallo reintenta solo, cada vez con más espera, hasta que sube', () async {
      const esperas = [Duration(milliseconds: 10), Duration(milliseconds: 30)];
      subidor = nuevoSubidor(prueba.base, esperas: esperas);
      await pasoMarcado(cuantas: 1);
      conSenal = false;

      await subidor.subir();
      expect(subidor.esperaDelReintento, esperas[0]);
      await esperarHasta(() => subidor.esperaDelReintento == esperas[1]);
      // La espera llega a su tope y ahí se queda.
      final intentos = servidor.peticiones.length;
      await esperarHasta(() => servidor.peticiones.length > intentos);
      await esperarHasta(() => !subidor.subiendo && subidor.esperaDelReintento != null);
      expect(subidor.esperaDelReintento, esperas[1]);

      conSenal = true;
      await esperarHasta(() => subidor.pendientes == 0);

      expect(fotos.guardadas, hasLength(1));
      expect(subidor.esperaDelReintento, isNull);
    });

    test('cuando una subida sale bien, la espera vuelve a empezar desde la más corta', () async {
      const esperas = [Duration(milliseconds: 10), Duration(seconds: 30)];
      subidor = nuevoSubidor(prueba.base, esperas: esperas);
      await pasoMarcado(cuantas: 2);
      var intentos = 0;
      fotos.responderCon = (_) {
        intentos++;
        // Falla, sube la primera, y vuelve a fallar con la segunda.
        if (intentos != 2) sinSenal();
        return null;
      };

      await subidor.subir();
      await esperarHasta(() => fotos.guardadas.length == 1 && !subidor.subiendo);

      expect(subidor.esperaDelReintento, esperas[0]);
    });
  });

  group('sesión', () {
    test('un 401 cierra la sesión y conserva las fotos; al volver a ingresar suben con el token '
        'nuevo', () async {
      final tomadas = await pasoMarcado();
      fotos.responderCon = (_) =>
          errorDelContrato(401, 'sesion_invalida', 'Su sesión ya no es válida.');

      await subidor.subir();

      expect(sesion.estado, EstadoSesion.sinSesion);
      expect(sesion.aviso, 'Su sesión ya no es válida.');
      expect((await estadosDeEnvio()).values.toSet(), {'pendiente'});
      expect(tomadas.every(existe), isTrue);
      expect(fotos.recibidas, hasLength(1));

      fotos.responderCon = null;
      await sesion.ingresar(celular: '300 123 4567', pin: '482913');
      await subidor.subir();

      expect(fotos.guardadas, hasLength(4));
      final subidas = servidor.peticiones.where((p) => p.metodo == 'PUT').toList();
      expect(subidas.last.cabeceras['Authorization'], 'Bearer token-ana-2');
    });

    test('las fotos de otro conductor no se suben con esta sesión', () async {
      const beto = Conductor(id: 8, nombre: 'Beto Ruiz', celular: '3009876543');
      final deBeto = await pasoMarcado(servicioId: 42, destino: 'entregado', conductor: beto);
      final deAna = await pasoMarcado(servicioId: 41);

      await subidor.subir();

      expect(fotos.guardadas.keys, deAna.map((f) => f.id));
      expect(deBeto.every(existe), isTrue);
      expect(subidor.ajenas, 4);
      expect(subidor.pendientes, 0);
    });

    test('sin sesión no sube nada', () async {
      await pasoMarcado();
      await sesion.cerrarPorServidor(
        const SesionCerrada(codigo: 'sesion_invalida', detalle: 'Cerrada.'),
        tokenUsado: 'token-ana',
      );

      await subidor.subir();

      expect(fotos.recibidas, isEmpty);
    });

    test('con fotos pendientes no se puede cerrar sesión; después de subirlas, sí', () async {
      await pasoMarcado();
      conSenal = false;
      await subidor.subir();

      expect(await sesion.salir(), ResultadoSalida.hayPendientes);
      expect(sesion.estado, EstadoSesion.activa);

      conSenal = true;
      await subidor.subir();

      expect(await sesion.salir(), ResultadoSalida.cerrada);
    });

    test('una foto rechazada no impide cerrar sesión: ya no se va a enviar', () async {
      await pasoMarcado(cuantas: 1);
      fotos.responderCon = (_) => fotoDemasiadoGrande();
      await subidor.subir();

      expect(await sesion.salir(), ResultadoSalida.cerrada);
    });
  });

  group('con la lista y la cola de eventos', () {
    late Sincronizador sincronizador;
    late ListaAsignaciones lista;

    setUp(() async {
      sincronizador = Sincronizador(
        cola: cola,
        api: servidor.api(),
        sesion: sesion,
        reloj: () => ahora,
        esperas: const [],
      );
      lista = ListaAsignaciones(
        almacen: AlmacenAsignaciones(prueba.base),
        api: servidor.api(),
        sesion: sesion,
        sincronizador: sincronizador,
        fotos: subidor,
        reloj: () => ahora,
      );
      desechables.addAll([lista, sincronizador]);
      await lista.cargarLocal();
    });

    Future<PasoEnCurso> prepararPaso(int servicioId, String destino, {int cuantas = 4}) async {
      final paso = await almacen.abrirPaso(
        conductorId: 3,
        servicioId: servicioId,
        destino: destino,
        hora: ahora,
      );
      for (var i = 0; i < cuantas; i++) {
        await almacen.agregarFoto(paso, camara.dejarFoto(), hora: ahora.add(Duration(seconds: i)));
      }
      return paso;
    }

    /// La ronda con un solo servicio, sin ningún vehículo montado en la grúa.
    Future<void> soloElServicio41() async {
      eventos = ServidorDeEventos({41: 'en_camino'});
      await AlmacenAsignaciones(prueba.base).reemplazar(
        servicios: [Servicio.desdeJson(servicioJson(id: 41, estado: 'en_camino', placa: 'ABC41'))],
        configuracion: const ConfiguracionApp(minimoFotos: 4, momentoPlacaVin: 'recoger'),
        etag: '"e2"',
        hora: ahora,
      );
      await lista.cargarLocal();
    }

    test(
      'al marcar el paso con señal, el evento se envía y sus fotos suben solas después',
      () async {
        await soloElServicio41();
        final paso = await prepararPaso(41, 'recogido');

        final evento = await lista.confirmarPaso(paso, nombreQuien: 'Carlos Pérez');
        await esperarHasta(() => fotos.guardadas.length == 4 && !subidor.subiendo);

        expect(eventos.estados[41], 'recogido');
        expect(eventos.guardados[evento.id], isNotNull);
        // El evento llegó antes que la primera foto.
        final rutas = [for (final p in servidor.peticiones) p.url.path];
        expect(
          rutas.indexOf('/api/v1/eventos/'),
          lessThan(rutas.indexWhere((r) => r.startsWith('/api/v1/evidencias/'))),
        );
        expect(fotos.guardadas.values.every((f) => f.eventoId == evento.id), isTrue);
        expect(lista.fotos.pendientes, 0);
      },
    );

    test(
      'sin señal: el estado cambia, las fotos quedan pendientes por subir y suben al volver',
      () async {
        await soloElServicio41();
        conSenal = false;
        final paso = await prepararPaso(41, 'recogido');

        await lista.confirmarPaso(paso, nombreQuien: 'Carlos Pérez');
        await sincronizador.enviar();

        expect(lista.servicio(41)!.estado, 'recogido');
        expect(lista.pendientesDe(41), 1);
        expect(lista.fotos.pendientes, 4);
        expect(lista.fotos.pendientesDe(41), 4);
        expect(fotos.recibidas, isEmpty);

        conSenal = true;
        await lista.actualizar();
        await esperarHasta(() => fotos.guardadas.length == 4 && !subidor.subiendo);

        expect(lista.fotos.pendientes, 0);
        expect(lista.pendientesDe(41), 0);
      },
    );

    test('con fotos sin subir de un servicio ya entregado, siguen subiendo aunque salga de la '
        'lista', () async {
      final paso = await prepararPaso(42, 'entregado');
      fotos.responderCon = (_) => sinSenal();

      await lista.confirmarPaso(paso, nombreQuien: 'Marta Díaz');
      await esperarHasta(() => eventos.estados[42] == 'entregado' && !subidor.subiendo);
      await lista.actualizar();
      await pumpEventQueue();
      expect(lista.servicio(42), isNull);
      expect(lista.fotos.pendientes, 4);

      fotos.responderCon = null;
      await lista.actualizar();
      await esperarHasta(() => fotos.guardadas.length == 4 && !subidor.subiendo);

      expect(fotos.guardadas.values.every((f) => f.tipo == 'entrega'), isTrue);
    });

    test('marcar Recogido con la grúa llena no guarda nada y dice qué falta entregar', () async {
      // El 42 ya va montado en la grúa de un puesto.
      final paso = await prepararPaso(41, 'recogido');

      await expectLater(
        lista.confirmarPaso(paso, nombreQuien: 'Carlos Pérez'),
        throwsA(isA<ToqueNoValido>().having((e) => e.mensaje, 'mensaje', contains('ABC42'))),
      );

      expect(await prueba.base.db.query('eventos_pendientes'), isEmpty);
      expect(lista.bloqueoDeRecogida(lista.servicio(41)!)!.faltanPorEntregar.single.id, 42);
    });

    test('después de entregar el que iba montado, sí deja recoger el siguiente', () async {
      conSenal = false;
      final entrega = await prepararPaso(42, 'entregado');
      await lista.confirmarPaso(entrega, nombreQuien: 'Marta Díaz');

      // Sin señal: la capacidad se calcula con lo que el conductor ya marcó, aunque no haya salido.
      expect(lista.bloqueoDeRecogida(lista.servicio(41)!), isNull);
      final recogida = await prepararPaso(41, 'recogido');
      await lista.confirmarPaso(recogida, nombreQuien: 'Carlos Pérez');

      expect(lista.servicio(41)!.estado, 'recogido');
    });
  });
}
