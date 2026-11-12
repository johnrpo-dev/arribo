# App del conductor

Flutter, solo Android, instalada por APK directo.

Esta carpeta todavía no tiene el proyecto: Flutter no estaba instalado en el equipo cuando se armó el
esqueleto. Se crea en la tarea 1a-01 de `docs/fase-1a-tareas.md`.

## Crear el proyecto

1. Instalar Flutter (canal estable) y Android Studio siguiendo https://docs.flutter.dev/get-started/install/windows
2. Comprobar la instalación: `flutter doctor`
3. Desde la raíz del repositorio:

```
flutter create --org co.arribo --project-name arribo_conductor --platforms=android conductor
```

4. Verificar: `cd conductor`, `flutter test` y `flutter run` con el celular conectado.

Las dependencias (base local, cámara, push) se agregan con `flutter pub add` en la tarea que las use,
para que queden en su versión vigente.
