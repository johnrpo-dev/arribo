# App del conductor

App Flutter de Arribo para los conductores de grúa: solo Android, distribuida por APK directo
(sin tiendas). Desde la 1a-11: ingreso con celular y PIN, lista de asignaciones en orden de ronda
que se ve sin señal, y llamar o abrir la dirección en Google Maps o Waze con un toque. Desde la
1a-12: botones de estado en el detalle (En camino, Recogido, Entregado y Novedad) y cola de eventos
que funciona sin señal. Las fotos y el bloqueo por capacidad llegan en la 1a-13.

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
- `lib/asignaciones/`: modelo del servicio, su almacén en la base, la lista, sus pantallas, los
  enlaces, los estados (`estados.dart`) y la confirmación de cada toque (`confirmacion.dart`).
- `lib/cola/`: la cola de eventos (`cola_eventos.dart`, sin red), quien la envía
  (`sincronizador.dart`), el evento (`evento.dart`) y las tareas por turnos (`fila.dart`).
- `lib/formato.dart`, `lib/tema.dart`, `lib/comunes.dart`, `lib/dispositivo.dart`: textos y fechas,
  tema, piezas compartidas, nombre del celular.

**Estado:** `ChangeNotifier` propios (`Sesion`, `ListaAsignaciones`, `Sincronizador`) que las
pantallas escuchan con `ListenableBuilder`. Sin paquetes de estado: son tres piezas y se pasan por
constructor. La lista escucha al sincronizador y avisa a las pantallas cuando la cola cambia.

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
| `estado_local` | Datos sueltos por clave: `dispositivo_id`, `conductor`, `etag`, `ultima_actualizacion`, `configuracion` y `ultima_secuencia` |
| `servicios` | La lista de `GET /asignaciones/` con todos sus campos; `posicion` es el puesto en la lista del servidor (orden de ronda). Sin columnas de cobro |
| `eventos_pendientes` | Cola de eventos (1a-12): pendientes y ya respondidos, con su resultado |
| `fotos_pendientes` | Fotos por subir de la 1a-13 (todavía sin uso) |

Versión 2 (1a-12): agrega a `eventos_pendientes` las columnas `vehiculo` (placa o VIN al tocar, para
nombrarlo en un aviso aunque el servicio ya no esté en la lista), `conductor_nombre` (de quién son
los cambios que siguen sin enviar) y `visto_en` (cuándo el conductor dio por visto un aviso).

La lista, su configuración, su ETag y la hora se guardan en una sola transacción: nunca queda un ETag
nuevo con datos viejos (un 304 escondería los cambios).

En `eventos_pendientes`: `id` es el UUID v4 del evento generado al tocar;
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

`BaseLocal.pendientesPorEnviar()` cuenta eventos y fotos pendientes (de todos, o de un conductor):
mientras el conductor de la sesión tenga alguno, la app no le cierra la sesión (el servidor toma como
conductor del evento al dueño del token).

### Estados y cola de eventos (1a-12)

`lib/asignaciones/estados.dart` repite la regla de `backend/nucleo/estados.py` (el paso que sigue,
desde dónde se reporta una novedad) solo para ofrecer el botón correcto y mostrar el estado con los
toques pendientes. Quien decide es el servidor: si no coinciden, el evento llega como conflicto.

Un toque del conductor:

1. Confirmación corta en una hoja inferior (`confirmacion.dart`). Recogido y Entregado pasan por
   `prepararRecogidoOEntregado`: ahí engancha la 1a-13 (capacidad, fotos y nombre).
2. `ColaEventos.encolar`, en una transacción: comprueba que sea el paso que sigue al estado que ve
   el conductor, toma la secuencia (`ultima_secuencia`, que solo crece) e inserta el evento con su
   UUID v4. Si la app muere aquí, el evento ya está guardado.
3. La lista vuelve a leer la base: el estado que se muestra es lo confirmado por el servidor más los
   eventos pendientes, en orden. No se escribe encima de lo confirmado.
4. `Sincronizador.enviar()`: un lote de máximo 100, desde el pendiente más antiguo, con el token de
   quien tocó. La respuesta se anota en una transacción: el evento sale de la cola (aplicado,
   conflicto o rechazado) y el servicio queda con el estado que devolvió el servidor, o sale de la
   lista si ya no está en la ronda. `reintentar` lo deja en la cola.

Disparadores del envío: abrir la app y volver a primer plano (la lista se actualiza y antes envía),
deslizar la lista, cada toque, y un reintento con espera creciente (5, 10, 20 y 30 s con la app a la
vista; hasta 5 minutos en segundo plano). Nunca hay dos envíos a la vez, y el envío y la consulta de
la lista van por turnos para que una lista vieja no se guarde después del resultado de un evento.

Reglas que no se rompen:

- El UUID y la secuencia de un evento no cambian nunca. Reenviar es mandar la misma fila; si la
  respuesta se perdió, vuelve como `duplicado` y se trata igual.
- Conflicto y rechazado no se reintentan: quedan a la vista hasta que el conductor toca "Entendido".
- Cada evento se envía solo con el token de quien lo tocó. Un 401 conserva la cola. Los eventos de
  otro conductor esperan a que él ingrese de nuevo; mientras, la app avisa de quién son.
- Con cambios propios sin enviar no se cierra sesión.

### Sesión y errores de la API

- El identificador del celular (`dispositivo_id`) es un UUID que se genera la primera vez y se guarda
  en la base; el nombre (`dispositivo_nombre`, por ejemplo "Motorola moto g32") lo da `MainActivity.kt`.
- Toda respuesta 401 a una petición con token borra el token y vuelve al ingreso mostrando el
  `detalle` del servidor. Nada local se borra: ni la lista ni lo pendiente por enviar.
- Si ingresa otro conductor en el mismo celular, se borra la lista del anterior (no lo pendiente,
  que tampoco se envía con el token del nuevo).
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
