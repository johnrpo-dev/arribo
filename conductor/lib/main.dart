// Arranque de la app del conductor: abre la base local, arma las piezas y lee la sesión guardada.

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
  // Un solo sincronizador: es el único que envía la cola de eventos.
  final sincronizador = Sincronizador(cola: ColaEventos(base), api: api, sesion: sesion);
  final lista = ListaAsignaciones(
    almacen: AlmacenAsignaciones(base),
    api: api,
    sesion: sesion,
    sincronizador: sincronizador,
  );
  runApp(ArriboApp(sesion: sesion, lista: lista));
  await sesion.iniciar();
}
