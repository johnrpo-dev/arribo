# App del conductor

App Flutter de Arribo para los conductores de grúa: solo Android, distribuida por APK directo
(sin tiendas). Desde la 1a-11: ingreso con celular y PIN, lista de asignaciones en orden de ronda
que se ve sin señal, detalle de solo lectura, y llamar o abrir la dirección en Google Maps o Waze
con un toque. Los botones de estado y la cola sin señal llegan en la 1a-12; las fotos, en la 1a-13.

- Paquete: `co.arribo.arribo_conductor`
- `minSdk = 26` (Android 8.0 o superior), fijado en `android/app/build.gradle.kts`.
- Contrato con el servidor: `docs/api-conductor.md` (versión 1).

## Requisitos

- Flutter estable (probado con Flutter 3.50.0 / Dart 3.14.0) y el SDK de Android con sus licencias
  aceptadas (`flutter doctor --android-licenses`).
- Para correr en un celular: Android 8.0 o superior con la depuración USB activada.

## Comandos

Desde `conductor/`:

```
flutter test                 # pruebas de la app (no necesitan celular)
flutter analyze              # revisión estática
flutter devices              # ver si el celular conectado por USB aparece
flutter run                  # instalar y correr en el Android físico conectado por USB
flutter build apk --debug    # APK de depuración en build/app/outputs/flutter-apk/app-debug.apk
```

### Servidor al que apunta la app

La dirección del servidor se elige al compilar o correr, sin tocar el código:

```
flutter run --dart-define=ARRIBO_API=http://127.0.0.1:8000        # valor por defecto
flutter build apk --release --dart-define=ARRIBO_API=https://<dominio>   # 1a-21
```

La pantalla de ingreso muestra abajo, en letra pequeña, a qué servidor apunta.

En desarrollo, el celular llega al backend del PC por el cable USB. `adb` no está en el PATH; está en
el SDK de Android:

```
& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse tcp:8000 tcp:8000
```

Esto hace que `127.0.0.1:8000` en el celular sea el `runserver` del PC. Hay que repetirlo cada vez
que se desconecta el cable. Para quitarlo: `... adb.exe reverse --remove-all`.

HTTP en claro solo se permite en el APK de depuración y solo hacia `127.0.0.1` y `localhost`
(`android/app/src/debug/res/xml/network_security_config.xml`). El APK de release solo habla HTTPS.

**Probar sin señal:** el túnel de `adb reverse` va por el cable y sigue funcionando en modo avión.
Para simular de verdad que no hay señal, además del modo avión hay que quitar el túnel
(`adb.exe reverse --remove-all`) o desconectar el cable.

## Cómo está armada

Carpetas por funcionalidad:

- `lib/main.dart`: arranque (abre la base, arma las piezas, lee la sesión guardada).
- `lib/app.dart`: tema, idioma (español de Colombia) y qué pantalla se ve según la sesión.
- `lib/api.dart`: cliente de la API (tiempos máximos cortos, errores del contrato, ETag, 401).
- `lib/base_local.dart`: base SQLite y sus migraciones.
- `lib/ingreso/`: sesión (token y conductor), almacén seguro del token y pantalla de ingreso.
- `lib/asignaciones/`: modelo del servicio, su almacén en la base, la lista, sus pantallas y los enlaces.
- `lib/formato.dart`, `lib/tema.dart`, `lib/comunes.dart`, `lib/dispositivo.dart`: textos y fechas,
  tema, piezas compartidas, nombre del celular.

**Estado:** `ChangeNotifier` propios (`Sesion`, `ListaAsignaciones`) que las pantallas escuchan con
`ListenableBuilder`. Sin paquetes de estado: son dos piezas y se pasan por constructor.

**Nada importante vive solo en memoria.** La lista se muestra siempre desde la base local; el
servidor solo la refresca (al abrir, al volver a primer plano y al deslizar hacia abajo). El token va
en el almacenamiento seguro del sistema (Keystore), nunca en la base. El detalle de un servicio es una
ruta restaurable: si el sistema mata la app con el detalle abierto, vuelve a él.

### Base local (`lib/base_local.dart`)

SQLite con `sqflite`. La versión de la base es la cantidad de migraciones de la lista
`migraciones`; una migración publicada no se cambia nunca, un cambio es una migración nueva al final.
Cada migración corre dentro de la transacción de apertura: si falla, la versión no avanza. Abrir una
base más nueva que la app (instalar un APK viejo encima) falla en vez de usar un esquema desconocido.

Versión 1:

| Tabla | Para qué |
|---|---|
| `estado_local` | Datos sueltos por clave: `dispositivo_id`, `conductor`, `etag`, `ultima_actualizacion`, `configuracion` (y `ultima_secuencia` desde la 1a-12) |
| `servicios` | La lista de `GET /asignaciones/` con todos sus campos; `posicion` es el puesto en la lista del servidor (orden de ronda). Sin columnas de cobro |
| `eventos_pendientes` | Cola de eventos de la 1a-12 (todavía sin uso) |
| `fotos_pendientes` | Fotos por subir de la 1a-13 (todavía sin uso) |

La lista, su configuración, su ETag y la hora se guardan en una sola transacción: nunca queda un ETag
nuevo con datos viejos (un 304 escondería los cambios).

Previsto para la 1a-12 (`eventos_pendientes`): `id` es el UUID v4 del evento generado al tocar;
`conductor_id` es quien lo tocó (el evento se envía solo con su token); `destino` solo admite
`en_camino`, `recogido`, `entregado` y `novedad`; `secuencia` es única y sale de `ultima_secuencia`
en `estado_local`, que se incrementa en la misma transacción que inserta el evento y nunca baja (no
se reinicia al cerrar sesión); `hora_dispositivo` en ISO 8601 UTC con Z; `estado_envio` es
`pendiente`, `aplicado`, `conflicto` o `rechazado`, con el motivo y el detalle del servidor. El
índice `(estado_envio, secuencia)` sirve para tomar "los 100 pendientes más antiguos".

Previsto para la 1a-13 (`fotos_pendientes`): `ruta` del JPEG en el disco del celular (nunca los
bytes en la base), `id` (UUID de `PUT /evidencias/<id>/`), `evento_id`, `tipo` (`recogida` o
`entrega`) y `estado_envio` (`pendiente`, `subida`, `error`).

Si esas tareas necesitan otro esquema, lo cambian con una migración nueva: las dos tablas llegan
vacías a todo celular instalado, así que se pueden rehacer sin perder nada.

`BaseLocal.pendientesPorEnviar()` ya cuenta eventos y fotos pendientes: con alguno, la app no cierra
sesión (el servidor toma como conductor del evento al dueño del token).

### Sesión y errores de la API

- El identificador del celular (`dispositivo_id`) es un UUID que se genera la primera vez y se guarda
  en la base; el nombre (`dispositivo_nombre`, por ejemplo "Motorola moto g32") lo da `MainActivity.kt`.
- Toda respuesta 401 a una petición con token borra el token y vuelve al ingreso mostrando el
  `detalle` del servidor. Nada local se borra: ni la lista ni lo pendiente por enviar.
- Si ingresa otro conductor en el mismo celular, se borra la lista del anterior (no lo pendiente).
- Cerrar sesión sin señal borra el token del celular igual; en el servidor queda revocado cuando se
  vuelva a ingresar en ese celular (o desde el admin).
- Sin red, tiempo agotado o un 500: la lista sigue mostrando lo guardado, con un aviso discreto.

## Dependencias

Se agregan con `flutter pub add` en la tarea que las use, para que queden en su versión vigente.

| Paquete | Para qué |
|---|---|
| `material_ui` | Los componentes Material. Desde Flutter 3.47 viven en este paquete y `package:flutter/material.dart` está marcado obsoleto |
| `http` | Peticiones a la API; trae `MockClient` para las pruebas con servidor falso |
| `sqflite` | Base local SQLite en el celular |
| `flutter_secure_storage` | El token en el Keystore de Android |
| `url_launcher` | Abrir el marcador del teléfono, Google Maps y Waze |
| `uuid` | El identificador del celular (y los ids de eventos y fotos desde la 1a-12) |
| `sqflite_common_ffi` (solo pruebas) | La misma base SQLite en el computador, sin celular |

`sqflite_common_ffi` trae `sqlite3`, cuyo hook de compilación empacaba `libsqlite3.so` en el APK
aunque sea solo de pruebas. En `pubspec.yaml` (`hooks: user_defines: sqlite3: source: android:
system`) se le indica que en Android no la empaque: la app usa la SQLite de Android por `sqflite`.
Para revisarlo, el APK no debe traer `lib/*/libsqlite3.so`.
