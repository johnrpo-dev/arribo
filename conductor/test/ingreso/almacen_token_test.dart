// El token en el almacenamiento seguro del sistema (con el doble de pruebas del paquete).

import 'package:arribo_conductor/ingreso/almacen_token.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('guarda, lee y borra el token', () async {
    final almacen = AlmacenTokenSeguro();

    expect(await almacen.leer(), isNull);
    await almacen.guardar('q3V9lW0m');
    expect(await almacen.leer(), 'q3V9lW0m');
    expect(await AlmacenTokenSeguro().leer(), 'q3V9lW0m');
    await almacen.borrar();
    expect(await almacen.leer(), isNull);
  });
}
