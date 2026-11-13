// Arranque de la app del conductor: abre la base local, arma las piezas y lee la sesión guardada.

import 'package:material_ui/material_ui.dart';
import 'package:sqflite/sqflite.dart';

import 'api.dart';
import 'app.dart';
import 'asignaciones/almacen_asignaciones.dart';
import 'asignaciones/lista_asignaciones.dart';
import 'base_local.dart';
import 'dispositivo.dart';
import 'ingreso/almacen_token.dart';
import 'ingreso/sesion.dart';

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
  final lista = ListaAsignaciones(almacen: AlmacenAsignaciones(base), api: api, sesion: sesion);
  runApp(ArriboApp(sesion: sesion, lista: lista));
  await sesion.iniciar();
}
