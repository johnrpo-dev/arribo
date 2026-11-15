// Arranque de la app del conductor: abre la base local, arma las piezas y lee la sesión guardada.

import 'package:firebase_core/firebase_core.dart';
import 'package:material_ui/material_ui.dart';
import 'package:sqflite/sqflite.dart';

import 'api.dart';
import 'app.dart';
import 'asignaciones/almacen_asignaciones.dart';
import 'asignaciones/lista_asignaciones.dart';
import 'base_local.dart';
import 'cola/cola_eventos.dart';
import 'cola/sincronizador.dart';
import 'dispositivo.dart';
import 'fotos/almacen_fotos.dart';
import 'fotos/subidor_fotos.dart';
import 'ingreso/almacen_token.dart';
import 'ingreso/sesion.dart';
import 'push.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final base = await BaseLocal.abrir(
    databaseFactory,
    '${await getDatabasesPath()}/$nombreArchivoBase',
  );
  final api = ClienteApi();
  final sesion = Sesion(
    api: api,
    base: base,
    almacenToken: AlmacenTokenSeguro(),
    nombreDispositivo: nombreDelDispositivo,
  );
  // Un solo sincronizador: es el único que envía la cola de eventos.
  final sincronizador = Sincronizador(cola: ColaEventos(base), api: api, sesion: sesion);
  // Y un solo subidor de fotos: una foto a la vez. Los JPEG van en una carpeta junto a la base.
  final fotos = SubidorDeFotos(almacen: AlmacenFotos(base), api: api, sesion: sesion);
  final lista = ListaAsignaciones(
    almacen: AlmacenAsignaciones(base),
    api: api,
    sesion: sesion,
    sincronizador: sincronizador,
    fotos: fotos,
  );
  // Avisos push (1a-14). Si Firebase no arranca, la app funciona igual, sin avisos: la lista se
  // refresca al abrirla, al volver a ella y al deslizar.
  final mensajeria = await _iniciarFirebase();
  if (mensajeria != null) {
    RegistroPush(mensajeria: mensajeria, api: api, sesion: sesion, lista: lista).iniciar();
  }
  runApp(ArriboApp(sesion: sesion, lista: lista, avisosTocados: mensajeria?.avisosTocados));
  await sesion.iniciar();
}

Future<MensajeriaPush?> _iniciarFirebase() async {
  try {
    // Sin opciones: en Android las lee de la configuración que arma el plugin google-services a
    // partir de android/app/google-services.json.
    await Firebase.initializeApp();
    return MensajeriaFirebase();
  } catch (error) {
    debugPrint('Firebase no arrancó; la app sigue sin avisos push ($error).');
    return null;
  }
}
