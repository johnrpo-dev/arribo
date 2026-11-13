// Enlaces de un toque: marcador del teléfono, Google Maps y Waze.

import 'package:arribo_conductor/asignaciones/enlaces.dart';
import 'package:arribo_conductor/asignaciones/servicio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('llamar', () {
    test('abre el marcador con el número del contacto', () {
      expect(enlaceLlamar('3102223344').toString(), 'tel:3102223344');
    });

    test('sin teléfono no hay botón de llamar', () {
      expect(enlaceLlamar(null), isNull);
      expect(enlaceLlamar(''), isNull);
    });
  });

  group('Google Maps', () {
    test('busca la dirección, con el # codificado para que no corte el enlace', () {
      final enlace = enlaceGoogleMaps(const Lugar(direccion: 'Calle 10 # 43-20, El Poblado'))!;

      expect(enlace.scheme, 'https');
      expect(enlace.host, 'www.google.com');
      expect(enlace.queryParameters['query'], 'Calle 10 # 43-20, El Poblado');
      expect(enlace.toString(), isNot(contains(' # ')));
      expect(enlace.fragment, isEmpty);
    });

    test('usa el enlace que escribió logística antes que la dirección', () {
      final enlace = enlaceGoogleMaps(
        const Lugar(direccion: 'Calle 10 # 43-20', ubicacion: 'https://maps.app.goo.gl/abc123'),
      );

      expect(enlace.toString(), 'https://maps.app.goo.gl/abc123');
    });

    test('con coordenadas busca las coordenadas', () {
      final enlace = enlaceGoogleMaps(const Lugar(ubicacion: '6.2101, -75.5712'))!;

      expect(enlace.queryParameters['query'], '6.2101,-75.5712');
    });

    test('nunca abre un enlace que no sea web', () {
      final enlace = enlaceGoogleMaps(
        const Lugar(direccion: 'Calle 10', ubicacion: 'intent://algo#Intent;end'),
      );

      expect(enlace!.host, 'www.google.com');
      expect(enlace.queryParameters['query'], 'Calle 10');
    });

    test('sin dirección ni ubicación no hay botón', () {
      expect(enlaceGoogleMaps(const Lugar(contactoNombre: 'Taller')), isNull);
    });
  });

  group('Waze', () {
    test('busca la dirección y navega', () {
      final enlace = enlaceWaze(const Lugar(direccion: 'Carrera 70 # 1-50, Belén'))!;

      expect(enlace.host, 'waze.com');
      expect(enlace.path, '/ul');
      expect(enlace.queryParameters, {'q': 'Carrera 70 # 1-50, Belén', 'navigate': 'yes'});
    });

    test('prefiere las coordenadas de un enlace de Google', () {
      final enlace = enlaceWaze(
        const Lugar(
          direccion: 'Carrera 70',
          ubicacion: 'https://www.google.com/maps/place/Taller/@6.2101,-75.5712,17z',
        ),
      )!;

      expect(enlace.queryParameters['ll'], '6.2101,-75.5712');
    });

    test('un enlace corto de Google no le sirve a Waze: usa la dirección', () {
      final enlace = enlaceWaze(
        const Lugar(direccion: 'Calle 10', ubicacion: 'https://maps.app.goo.gl/abc123'),
      )!;

      expect(enlace.queryParameters['q'], 'Calle 10');
    });
  });

  group('coordenadas', () {
    test('lee las formas comunes', () {
      expect(coordenadasDe('6.2101,-75.5712'), (latitud: 6.2101, longitud: -75.5712));
      expect(coordenadasDe('geo:6.2101,-75.5712'), (latitud: 6.2101, longitud: -75.5712));
      expect(coordenadasDe('https://www.google.com/maps?q=6.2101,-75.5712'), (
        latitud: 6.2101,
        longitud: -75.5712,
      ));
      expect(coordenadasDe('https://maps.google.com/?q=6.2101%2C-75.5712'), (
        latitud: 6.2101,
        longitud: -75.5712,
      ));
    });

    test('no confunde una dirección ni acepta coordenadas imposibles', () {
      expect(coordenadasDe('Calle 10 # 43-20, El Poblado'), isNull);
      expect(coordenadasDe('10, 20 metros adelante'), isNull);
      expect(coordenadasDe('95.0,-75.5'), isNull);
      expect(coordenadasDe(null), isNull);
    });
  });
}
