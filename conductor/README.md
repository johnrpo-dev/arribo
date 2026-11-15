# App del conductor

App Flutter de Arribo para los conductores de grúa: solo Android, distribuida por APK directo
(sin tiendas). Desde la 1a-11: ingreso con celular y PIN, lista de asignaciones en orden de ronda
que se ve sin señal, y llamar o abrir la dirección en Google Maps o Waze con un toque. Desde la
1a-12: botones de estado en el detalle (En camino, Recogido, Entregado y Novedad) y cola de eventos
que funciona sin señal. Desde la 1a-13: Recogido y Entregado exigen fotos y el nombre de quien
entrega o recibe, las fotos suben en su propia cola, y un Recogido se bloquea si la grúa va llena.

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
- `lib/asignaciones/`: modelo del servicio, su almacén en la base, la lista, sus pantallas (lista,
  detalle y la de Recogido o Entregado, `pantalla_paso.dart`), los enlaces, la confirmación de cada
  toque (`confirmacion.dart`) y las reglas: estados (`estados.dart`), capacidad (`capacidad.dart`),
  identificación del vehículo (`identificacion.dart`) y lo que exige un paso (`requisitos.dart`).
- `lib/cola/`: la cola de eventos (`cola_eventos.dart`, sin red), quien la envía
  (`sincronizador.dart`), el evento (`evento.dart`) y las tareas por turnos (`fila.dart`).
- `lib/fotos/`: la foto y sus límites (`foto.dart`), la cámara del sistema (`camara.dart`), el paso
  en curso y la cola de fotos en la base (`almacen_fotos.dart`, sin red) y quien las sube
  (`subidor_fotos.dart`).
- `lib/formato.dart`, `lib/tema.dart`, `lib/comunes.dart`, `lib/dispositivo.dart`: textos y fechas,
  tema, piezas compartidas, nombre del celular.

**Estado:** `ChangeNotifier` propios (`Sesion`, `ListaAsignaciones`, `Sincronizador`,
`SubidorDeFotos`) que las pantallas escuchan con `ListenableBuilder`. Sin paquetes de estado: son
cuatro piezas y se pasan por constructor. La lista escucha al sincronizador y al subidor de fotos y
avisa a las pantallas cuando alguna de las dos colas cambia.

**Nada importante vive solo en memoria.** La lista se muestra siempre desde la base local; el
servidor solo la refresca (al abrir, al volver a primer plano y al deslizar hacia abajo). El token va
en el almacenamiento seguro del sistema (Keystore), nunca en la base. El detalle de un servicio y
la pantalla de Recogido o Entregado son rutas restaurables: si el sistema mata la app con una de
ellas abierta (pasa al abrir la cámara en un celular con poca memoria), vuelve a ella.

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
| `fotos_pendientes` | Fotos de evidencia (1a-13): las del paso en curso y la cola de subida |

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

En `fotos_pendientes`: `ruta` del JPEG en el disco del celular (nunca los bytes en la base), `id`
(UUID de `PUT /evidencias/<id>/`), `evento_id`, `tipo` (`recogida` o `entrega`) y `estado_envio`
(`pendiente`, `subida`, `error`, con el motivo en `error`).

Versión 3 (1a-13): la tabla `pasos_en_curso` (el Recogido o Entregado que el conductor está
preparando: conductor, servicio, destino, el UUID que llevará el evento, el nombre como va escrito
y desde cuándo está abierta la cámara) y cuatro columnas en `fotos_pendientes`: `borrador` (1
mientras el paso no se ha marcado: la foto todavía no se sube), `vehiculo` (placa o VIN, para
nombrarlo en un aviso), `archivo_borrado_en` (cuándo se borró el JPEG del celular, siempre después
de confirmada la subida) y `visto_en` (cuándo el conductor dio por visto el aviso de una foto
rechazada).

Versión 4 (1a-13b): `placa_digitada` y `vin_digitado` en `pasos_en_curso` (como van escritos en la
pantalla del Recogido; vacíos si no se pidieron) y `placa` y `vin` en `eventos_pendientes`
(normalizados, solo en un Recogido; null si no se digitaron).

`BaseLocal.pendientesPorEnviar()` cuenta eventos y fotos pendientes (de todos, o de un conductor):
mientras el conductor de la sesión tenga alguno, la app no le cierra la sesión (el servidor toma como
conductor del evento al dueño del token). Las fotos en borrador y las rechazadas no cuentan.

### Estados y cola de eventos (1a-12)

`lib/asignaciones/estados.dart` repite la regla de `backend/nucleo/estados.py` (el paso que sigue,
desde dónde se reporta una novedad) solo para ofrecer el botón correcto y mostrar el estado con los
toques pendientes. Quien decide es el servidor: si no coinciden, el evento llega como conflicto.

Un toque del conductor:

1. Confirmación corta en una hoja inferior (`confirmacion.dart`). Recogido y Entregado no se
   confirman ahí: abren su pantalla de fotos y nombre (ver "Fotos y capacidad").
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

### Fotos y capacidad (1a-13)

**Reglas copiadas del servidor.** La app repite en Dart los estados, la capacidad
(`capacidad.dart`, de `nucleo/capacidad.py`), la identificación del vehículo
(`identificacion.dart`, de `nucleo/identificacion.py`) y los límites de las fotos (`foto.dart`, de
`nucleo/evidencia.py`). Para que las copias no se desfasen, las dos cumplen los mismos casos de
`docs/casos-reglas.json`: los recorren `backend/tests/nucleo/test_casos_compartidos.py` y
`test/casos_compartidos_test.dart`. Si una regla cambia en `nucleo/`, su prueba falla hasta que el
archivo cambie; con el archivo cambiado, falla la de la app hasta que cambie su copia.

**Antes de abrir la pantalla** (`abrirRecogidoOEntregado`), un Recogido se bloquea, diciendo por
qué, si la grúa ya lleva tantos vehículos montados como puestos (lista los que falta marcar como
Entregado) o, con la configuración "placa/VIN al asignar", si al vehículo le falta la placa o el VIN
(un desvare exige placa): que llame a logística. "Montado" se calcula con lo que ve el conductor: lo
confirmado más sus toques sin enviar, así que funciona sin señal.

**Placa o VIN digitados (1a-13b).** Con "placa/VIN al recoger" (la de fábrica), un vehículo sin
placa ni VIN (o un desvare sin placa) no bloquea: la pantalla del Recogido pide digitarlos
(`identificacionPorDigitar` en `requisitos.dart`; un desvare pide solo la placa). Se guardan como van
escritos en el paso en curso y, al marcar, se revisan con la copia de la regla
(`faltantesDeIdentificacion`: falta, VIN de 17 sin I, O ni Q, placa de 1 a 10) y viajan
normalizados en el evento (`placa`, `vin`; contrato 1.1). La lista y el detalle muestran el vehículo
con lo digitado mientras el evento está pendiente; cuando el servidor lo aplica, queda en la lista
guardada donde le faltaba, hasta que la lista se vuelva a pedir. Lo que el servidor haga con ello
(guardarlo o abrir una alerta a logística) está en `docs/api-conductor.md`.

**La pantalla** (`pantalla_paso.dart`) pide las fotos y el nombre de quien entrega (Recogido) o
recibe (Entregado). Todo queda en la base a medida que avanza: el paso se crea al abrirla, con el
UUID que llevará el evento; cada foto es una fila en borrador atada a ese UUID; el nombre se guarda
en cada cambio. Al tocar "Marcar…", en una sola transacción (`ColaEventos.encolar` con
`AlmacenFotos.confirmar`): se comprueban el mínimo de fotos de la configuración y el nombre, se
guarda el evento, sus fotos dejan de ser borrador y el paso se borra. Si falta algo, no se guarda
nada y la pantalla dice qué falta.

**La cámara** (`camara.dart`) es la del sistema, con `image_picker`: corre en otro proceso, así que
la app no retiene en memoria ni la vista previa ni la foto, y no pide el permiso de cámara. El
plugin achica la foto a 1600 píxeles de lado y la comprime a JPEG de calidad 80 en código nativo,
en un hilo aparte y decodificando ya reducida; a Dart solo llega la ruta del archivo (unos cientos
de KB; el servidor acepta hasta 5 MB). `AlmacenFotos.agregarFoto` comprueba que sea un JPEG bajo el
tope, le da su UUID y la mueve de la caché a `fotos/`, junto a la base local (almacenamiento
privado que Android no vacía). Dart nunca lee los bytes de una foto, salvo los tres primeros. Las
miniaturas usan `cacheWidth`: se decodifican al tamaño en que se muestran.

**Si Android mata la app con la cámara abierta:** antes de abrirla se anota en el paso
(`camara_abierta_en`). Al volver, la pantalla se restaura (o el conductor la abre de nuevo), lee el
paso de la base y le pide al plugin la foto que quedó sin entregar (`retrieveLostData`); esa foto
se agrega al paso que tenía la cámara abierta.

**La cola de fotos** (`subidor_fotos.dart`): una foto a la vez, de la más antigua a la más nueva,
solo las que no son borrador y cuyo evento ya tuvo respuesta definitiva (así el servidor ya conoce
el toque cuando llega la foto), y solo con el token de quien la tomó. El `PUT` es idempotente por
UUID: si se corta o la respuesta se pierde, se sube completa otra vez y el servidor responde 200
sin duplicarla. El archivo se lee del disco por partes mientras se envía. Con 201 o 200 la foto
queda `subida` y solo entonces se borra su archivo (si la app muere en medio, se borra al abrir).
Sin red o con un 500 se reintenta con la misma espera creciente de los eventos. Un rechazo
definitivo (413, 409, 400, 404 o 415) no se reintenta: la foto queda en `error`, con su archivo, y
a la vista en la lista hasta que el conductor toca "Entendido". La lista despierta al subidor
cuando sabe que hay conexión: al abrir la app, cuando un lote de eventos llega al servidor y cuando
el servidor responde la lista.

Indicadores: arriba de la lista, "Hay N fotos pendientes por subir"; en la tarjeta y en el detalle
del servicio, "N fotos por subir". Con fotos propias pendientes no se cierra sesión.

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
| `image_picker` | La cámara del sistema para las fotos de evidencia (1a-13): toma la foto en otro proceso, la achica y la comprime en nativo y recupera la foto si Android mató la app |
| `sqflite_common_ffi` (solo pruebas) | La misma base SQLite en el computador, sin celular |

`sqflite_common_ffi` trae `sqlite3`, cuyo hook de compilación empacaba `libsqlite3.so` en el APK
aunque sea solo de pruebas. En `pubspec.yaml` (`hooks: user_defines: sqlite3: source: android:
system`) se le indica que en Android no la empaque: la app usa la SQLite de Android por `sqflite`.
Para revisarlo, el APK no debe traer `lib/*/libsqlite3.so`.
