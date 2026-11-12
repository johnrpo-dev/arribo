# App del conductor

App Flutter de Arribo para los conductores de grúa: solo Android, distribuida por APK directo
(sin tiendas). Por ahora es un proyecto mínimo con una sola pantalla que dice "Arribo conductor";
la base local, la cola de salida, la cámara y el push llegan en tareas posteriores de
`docs/fase-1a-tareas.md`.

- Paquete: `co.arribo.arribo_conductor`
- `minSdk = 26` (Android 8.0 o superior), fijado en `android/app/build.gradle.kts`.

## Requisitos

- Flutter estable (probado con Flutter 3.50.0 / Dart 3.14.0) y el SDK de Android con sus licencias
  aceptadas (`flutter doctor --android-licenses`).
- Para correr en un celular: Android 8.0 o superior con la depuración USB activada.

## Comandos

Desde `conductor/`:

```
flutter test                 # pruebas de la app
flutter devices              # ver si el celular conectado por USB aparece
flutter run                  # instalar y correr en el Android físico conectado por USB
flutter build apk --debug    # APK de depuración en build/app/outputs/flutter-apk/app-debug.apk
```

Las dependencias se agregan con `flutter pub add` en la tarea que las use, para que queden en su
versión vigente.
