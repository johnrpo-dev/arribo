import 'package:flutter_test/flutter_test.dart';

import 'package:arribo_conductor/main.dart';

void main() {
  testWidgets('la pantalla inicial muestra "Arribo conductor"', (tester) async {
    await tester.pumpWidget(const ArriboConductorApp());

    expect(find.text('Arribo conductor'), findsOneWidget);
  });
}
