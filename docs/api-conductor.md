# API de la app del conductor (contrato versión 1)

Contrato entre el servidor (`backend/api/`) y la app Flutter (`conductor/`). Lo usan la sincronización
(1a-10), las pantallas de la app (1a-11 a 1a-13) y el push (1a-14). Si el código y este documento no
coinciden, es un error: se corrige uno de los dos en la misma tarea.

Implementado en la 1a-09: ingreso, cierre de sesión, lista y detalle de asignaciones.
Implementado en la 1a-10: envío de eventos y subida de fotos. Pendiente: el push (1a-14).

## Reglas generales

- **Base:** `https://<dominio>/api/v1/`. En desarrollo, `http://127.0.0.1:8000/api/v1/`.
- **Formato:** JSON en UTF-8, en las peticiones (`Content-Type: application/json`) y en las respuestas.
  La única excepción es la subida de una foto, que se envía como `multipart/form-data` (la respuesta
  sigue siendo JSON). Las rutas terminan en `/`.
- **Versión del contrato:** toda respuesta con cuerpo trae `"version": 1`. Sube solo si un cambio
  rompe a una app ya instalada (quitar o renombrar un campo, cambiar su tipo o su significado).
  Agregar un campo no la cambia: **la app ignora los campos que no conoce**. Una versión nueva
  tendría su propio prefijo (`/api/v2/`).
- **Fechas:** ISO 8601 en UTC con `Z`, por ejemplo `"2026-11-20T19:30:00Z"`. Pueden traer fracciones
  de segundo. La app las muestra en hora de Colombia (America/Bogota, UTC−5, sin horario de verano).
- **Vacíos:** un texto opcional sin dato llega como `null`, nunca como `""`.
- **Valores de cobro:** nunca. Ninguna respuesta trae valor, tarifa, líneas de cobro, factura ni
  pagador (tampoco las de eventos y fotos, aunque un Entregado cree la línea de cobro en el
  servidor). Las pruebas recorren el JSON completo para comprobarlo.
- **Solo lo suyo:** un conductor solo ve sus servicios. Pedir uno ajeno da 404, igual que uno que no existe.

## Autenticación

Cada celular tiene su propio token. Se obtiene con `POST /ingresar/` y se manda en cada petición:

```
Authorization: Bearer <token>
```

- El token no vence. Deja de servir si la app cierra sesión (`POST /salir/`), si logística lo revoca
  en el admin (Api del conductor → Tokens de celular → acción "Revocar los tokens seleccionados"),
  o si el mismo conductor vuelve a ingresar en el mismo celular (`dispositivo_id`): queda vigente el nuevo.
- Mientras el conductor esté inactivo, o su usuario esté inactivo o fuera del grupo conductor,
  el token responde 401 `conductor_no_habilitado`. Si lo reactivan, el mismo token vuelve a servir.
- **Toda respuesta 401 significa "volver a la pantalla de ingreso"** (y mostrar `detalle`). Lleva
  la cabecera `WWW-Authenticate: Bearer realm="arribo"`.
- El servidor guarda solo el hash del token. Si la app lo pierde, el conductor ingresa de nuevo.
- La sesión del panel web no sirve en la API: sin `Authorization` la respuesta es 401.

Quién puede ingresar: un `Conductor` activo, con PIN fijado y con un usuario activo del grupo
`conductor`. Todo se configura en `/admin/` (no hay pantalla del panel para esto): el usuario en
Autenticación → Usuarios (sin contraseña: no entra al panel), y en Flota → Conductores se elige ese
usuario y se escribe el PIN en "Nuevo PIN de la app".

**PIN:** exactamente 6 dígitos (0–9). Se guarda solo con hash (el de Django). No se puede ver: si el
conductor lo olvida, se fija uno nuevo en el admin.

**Límite de intentos:** 5 PIN equivocados dentro de 15 minutos bloquean ese celular 15 minutos. Durante
el bloqueo no se revisa el PIN (ni el correcto entra) y la respuesta es 429. Pasa igual con un celular
que no es de ningún conductor, para no revelar cuáles existen. Un ingreso correcto pone la cuenta en
cero. Un PIN con otro formato (por ejemplo, 4 dígitos) responde 400 y no cuenta como fallo.

## Errores

Toda respuesta de error tiene esta forma. La app decide por `error` (no cambia entre versiones);
`detalle` es el texto en español para mostrarle al conductor.

```json
{"version": 1, "error": "credenciales_invalidas", "detalle": "Celular o PIN incorrectos."}
```

| HTTP | `error` | Cuándo | Qué hace la app |
|---|---|---|---|
| 400 | `datos_invalidos` | Falta un campo o tiene otro formato. Trae `campos` (ver abajo) | Corregir y reintentar |
| 400 | `json_invalido` | El cuerpo no es JSON | Error de la app: registrarlo |
| 401 | `credenciales_invalidas` | Celular o PIN incorrectos, o celular que no es de nadie | Mostrar `detalle` |
| 401 | `conductor_no_habilitado` | Conductor o usuario inactivo, sin usuario o fuera del grupo conductor | Pantalla de ingreso con `detalle` |
| 401 | `no_autenticado` | Petición sin `Authorization: Bearer` | Pantalla de ingreso |
| 401 | `sesion_invalida` | Token desconocido, mal escrito o revocado | Borrar el token y pantalla de ingreso |
| 404 | `no_encontrado` | El servicio no existe, es de otro conductor o ya terminó | Quitarlo de la lista local |
| 409 | `evidencia_distinta` | Solo en fotos: ya hay otra foto con ese UUID | Error de la app: registrarlo |
| 413 | `foto_demasiado_grande` | Solo en fotos: pesa más de 5 MB. Trae `maximo_bytes` | Comprimir más y subirla de nuevo |
| 405 | `metodo_no_permitido` | Método HTTP equivocado | Error de la app: registrarlo |
| 415 | `tipo_no_soportado` | El cuerpo viene con un `Content-Type` que esa ruta no acepta (JSON en todas; `multipart/form-data` solo en las fotos) | Error de la app: registrarlo |
| 429 | `demasiados_intentos` | Celular bloqueado por PIN equivocados. Trae `reintentar_en` | Mostrar `detalle`; no reintentar antes |
| 500 | (sin cuerpo JSON) | Error del servidor | Reintentar más tarde |

Una ruta que no existe (por ejemplo `/api/v1/nada/`) responde el 404 de Django, en HTML y sin esta forma.

El envío de eventos casi nunca responde con un error: un evento que no encaja o que no se puede leer
va como un resultado dentro de la respuesta 200 (ver "Enviar eventos").

Datos inválidos:

```json
{
  "version": 1,
  "error": "datos_invalidos",
  "detalle": "Revise los datos enviados.",
  "campos": {"pin": ["El PIN tiene exactamente 6 dígitos, del 0 al 9."],
             "dispositivo_id": ["Este campo es requerido."]}
}
```

Bloqueo (además, cabecera `Retry-After: 900`):

```json
{
  "version": 1,
  "error": "demasiados_intentos",
  "detalle": "Demasiados intentos fallidos. Intente de nuevo en 15 minutos.",
  "reintentar_en": 900
}
```

## Ingresar

`POST /api/v1/ingresar/` — sin `Authorization` (si la lleva, se ignora).

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `celular` | texto | sí | Cualquier formato: `"+57 300 123 4567"`, `"300-123-4567"` y `"3001234567"` son el mismo |
| `pin` | texto | sí | Exactamente 6 dígitos. Texto, no número (puede empezar por 0) |
| `dispositivo_id` | texto (≤ 100) | sí | Identificador que la app genera al instalarse (un UUID) y guarda; el mismo en cada ingreso |
| `dispositivo_nombre` | texto (≤ 100) | no | Para reconocerlo en el admin, por ejemplo `"Motorola moto g32"` |

```json
{"celular": "300 123 4567", "pin": "482913",
 "dispositivo_id": "7f0c2a64-3f7e-4b4e-9d55-0b7f1e2c9a10", "dispositivo_nombre": "Motorola moto g32"}
```

Respuesta 200:

```json
{
  "version": 1,
  "token": "q3V9lW0m4cJm3n7wqR0tq4x8m2k1yZ5hQ9f6s2d8a1E",
  "conductor": {"id": 3, "nombre": "Ana Gómez", "celular": "3001234567"}
}
```

El token solo aparece en esta respuesta: la app lo guarda en almacenamiento seguro del celular.
Errores: 400 `datos_invalidos`, 401 `credenciales_invalidas` o `conductor_no_habilitado`, 429 `demasiados_intentos`.

## Cerrar sesión

`POST /api/v1/salir/` — con `Authorization`, sin cuerpo. Respuesta **204** sin cuerpo: el token de este
celular queda revocado (los de otros celulares del mismo conductor siguen). Repetirlo da 401
`sesion_invalida`; la app puede tomarlo como sesión ya cerrada.

## Asignaciones

`GET /api/v1/asignaciones/` — con `Authorization`.

Los servicios no terminales del conductor (asignado, en camino, recogido y novedad), **en el orden de
su ronda**, con todo lo que la app necesita para trabajar sin señal. Un servicio entregado, cancelado,
devuelto a la cola o reasignado a otro conductor deja de aparecer: la app lo quita de su lista
(conservando lo que tenga pendiente por enviar).

Respuesta 200:

```json
{
  "version": 1,
  "configuracion": {"minimo_fotos": 4, "momento_placa_vin": "recoger"},
  "servicios": [
    {
      "id": 41,
      "solicitud_id": 17,
      "estado": "asignado",
      "estado_previo": null,
      "tipo": "traslado",
      "es_regreso": false,
      "orden_ronda": 1,
      "vehiculo": {"placa": "ABC123", "vin": "1HGCM82633A004352", "marca": "Mazda",
                   "linea": "CX-30", "color": "Rojo"},
      "origen": {
        "direccion": "Calle 10 # 43-20, El Poblado",
        "ubicacion": "https://maps.app.goo.gl/abc123",
        "contacto": {"nombre": "Portería Autos del Valle", "telefono": "6044445566"}
      },
      "destino": {
        "direccion": "Carrera 70 # 1-50, Belén",
        "ubicacion": null,
        "contacto": {"nombre": "Taller Belén", "telefono": "3102223344"}
      },
      "referencia_externa": "SIN-4471",
      "programada_para": "2026-11-20T19:30:00Z",
      "grua": {"id": 2, "placa": "GRU001", "capacidad": 1},
      "a_bordo": false
    }
  ]
}
```

`configuracion` (de la configuración de la empresa, igual para todos los servicios):

| Campo | Valores | Uso en la app |
|---|---|---|
| `minimo_fotos` | 0 a 20 | Fotos que exigen Recogido y Entregado (1a-13) |
| `momento_placa_vin` | `"asignar"` o `"recoger"` | Desde cuándo se exige placa o VIN. Al recoger se exige siempre; un desvare exige placa |

Cada servicio:

| Campo | Tipo | Notas |
|---|---|---|
| `id` | entero | Id del servicio; es el que va en los eventos |
| `solicitud_id` | entero | Varios servicios de la misma solicitud son vehículos del mismo pedido |
| `estado` | texto | `asignado`, `en_camino`, `recogido` o `novedad` |
| `estado_previo` | texto o null | Solo en `novedad`: el estado al que vuelve si logística la resuelve reanudando |
| `tipo` | texto | `traslado`, `evento` o `desvare` |
| `es_regreso` | booleano | Regreso de un evento. `origen` y `destino` ya vienen invertidos respecto de la solicitud |
| `orden_ronda` | entero o null | Puesto en la ronda (1 primero). Puede tener huecos; la lista ya viene ordenada |
| `vehiculo` | objeto | `placa`, `vin`, `marca`, `linea`, `color`; cada uno texto o null |
| `origen` | objeto | Dónde se recoge el vehículo: `direccion` (texto), `ubicacion` (enlace o coordenadas, sin geocodificar) y `contacto` (`nombre`, `telefono` solo dígitos, o null) |
| `destino` | objeto | Dónde se entrega; misma forma. En un desvare suele venir todo en null |
| `referencia_externa` | texto o null | Número de caso de la aseguradora o del concesionario |
| `programada_para` | fecha o null | null = inmediato. En un regreso es la fecha de regreso |
| `grua` | objeto | La grúa guardada en el servicio (`id`, `placa`, `capacidad` 1 o 2), aunque el conductor cambie de grúa después |
| `a_bordo` | booleano | El vehículo ocupa un puesto de la grúa: recogido, o novedad que venía de recogido. Con esto y `capacidad` la app bloquea un Recogido de más (1a-13) |

### Refrescos baratos con ETag

Toda respuesta 200 de asignaciones trae `ETag` (el hash del cuerpo) y `Cache-Control: private, no-cache`.
La app guarda el último `ETag` y lo manda en `If-None-Match`; si nada cambió (servicios, orden de la
ronda, datos de la solicitud o configuración), la respuesta es **304 sin cuerpo** y la app sigue con lo
que tiene. Se eligió esto, y no una fecha de actualización por servicio, porque cubre cualquier cambio
(también los que no dejan evento, como subir o bajar en la ronda) sin campos ni reglas nuevas en la base.

```
GET /api/v1/asignaciones/
Authorization: Bearer <token>
If-None-Match: "3f2a9c0e5b7d41a8c6e2f0b9d4a7c1e3"
```

## Detalle de una asignación

`GET /api/v1/asignaciones/<id>/` — con `Authorization`. Mismo servicio que en la lista, con su ETag:

```json
{"version": 1, "configuracion": {"minimo_fotos": 4, "momento_placa_vin": "recoger"},
 "servicio": {"id": 41, "...": "los mismos campos de la lista"}}
```

404 `no_encontrado` si el servicio no existe, es de otro conductor o ya no está en su ronda (terminado,
devuelto a la cola o reasignado). El 404 es idéntico en los tres casos.

## Enviar eventos

`POST /api/v1/eventos/` — con `Authorization`. Un lote con los toques pendientes del celular.

```json
{
  "eventos": [
    {
      "id": "0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e",
      "servicio_id": 41,
      "destino": "en_camino",
      "secuencia": 118,
      "hora_dispositivo": "2026-11-20T19:42:07Z",
      "motivo": null,
      "nombre_quien": null,
      "latitud": null,
      "longitud": null
    }
  ]
}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `id` | sí | UUID v4 generado en el celular al tocar el botón. Reenviar el mismo id nunca aplica dos veces |
| `servicio_id` | sí | Id del servicio de la lista |
| `destino` | sí | `en_camino`, `recogido`, `entregado` o `novedad`. Otro estado (`cancelado`, `asignado`, `pendiente_asignar`) se guarda como conflicto |
| `secuencia` | sí | Entero. Contador del celular que solo crece (no se reinicia al cerrar sesión ni al reinstalar si se puede evitar). Da el orden, no la hora |
| `hora_dispositivo` | no | Hora del celular al tocar, ISO 8601 con `Z` u offset (sin zona se toma como hora de Colombia). Se guarda junto con la hora de sincronización del servidor |
| `motivo` | en `novedad` | Texto. Una novedad sin motivo se guarda como conflicto |
| `nombre_quien` | no | Quien entrega o recibe el vehículo, en `recogido` y `entregado` (1a-13) |
| `latitud`, `longitud` | no | Números (fase 1b) |

- **El conductor del evento es el del token**, no un campo del cuerpo. Por eso cada evento se envía
  con el token de quien lo tocó: la app no cierra sesión con eventos pendientes por enviar.
- **Tope:** 100 eventos por lote. Con más, 400 `datos_invalidos` y no se aplica ninguno: la app envía
  los 100 más antiguos y sigue con el resto en otro lote.
- **Datos secundarios ilegibles no tumban el evento.** Si `hora_dispositivo`, `latitud`, `longitud`,
  `motivo` o `nombre_quien` vienen con un valor que no se puede leer, el evento se guarda con ese
  dato vacío. Solo `id`, `servicio_id`, `destino` y `secuencia` son indispensables.

### Orden

El servidor aplica el lote **por `secuencia`**, sin importar el orden en que vengan en la lista ni la
hora del celular (si la secuencia se repite, en el orden de la lista). Entre lotes, cada evento se
evalúa contra el estado que el servicio tenga cuando llega.

Para que el orden se cumpla también entre lotes, la app **envía un lote a la vez y siempre desde el
evento pendiente más antiguo**; si no recibe respuesta, reintenta el mismo lote (puede sumarle los
toques nuevos al final). Así un reintento que se cruza con la petición original es seguro: cada
evento lo aplica una de las dos y la otra lo ve duplicado.

Si aun así la secuencia 7 llega en un lote anterior al de la 6 (dos envíos distintos que se cruzan),
la 7 normalmente no encaja con el estado del momento y queda **guardada como conflicto con alerta a
logística** (`salto_de_estado`); la 6 se aplica cuando llega. Ninguna se pierde y la 7 no se vuelve
a evaluar: logística corrige el estado desde el panel.

### Respuesta

Siempre **200** si el lote se pudo leer, con un resultado por evento **en el mismo orden en que se
enviaron** (el resultado N es del evento N):

```json
{
  "version": 1,
  "resultados": [
    {
      "id": "0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e",
      "resultado": "aplicado",
      "duplicado": false,
      "motivo": null,
      "detalle": null,
      "capacidad_excedida": false,
      "servicio": {"id": 41, "estado": "en_camino", "estado_previo": null,
                   "a_bordo": false, "en_su_ronda": true}
    },
    {
      "id": "9a3c5d1e-0c2a-4f7e-8b4e-9d550b7f1e2c",
      "resultado": "conflicto",
      "duplicado": false,
      "motivo": "servicio_cancelado",
      "detalle": "El servicio ya estaba cancelado.",
      "capacidad_excedida": false,
      "servicio": {"id": 42, "estado": "cancelado", "estado_previo": null,
                   "a_bordo": false, "en_su_ronda": false}
    }
  ]
}
```

| `resultado` | Qué pasó en el servidor | Qué hace la app |
|---|---|---|
| `aplicado` | Se guardó y cambió el estado del servicio | Lo saca de la cola |
| `conflicto` | Se guardó en el historial pero **no** cambió el servicio; logística recibe una alerta | Lo saca de la cola (nunca lo reintenta) y muestra `detalle` |
| `rechazado` | No se pudo guardar y no se guardará nunca (ver motivos); logística recibe una alerta con lo que llegó | Lo saca de la cola y lo registra como error de la app |
| `reintentar` | No se guardó por una falla del servidor | Lo deja en la cola y lo reenvía en el siguiente lote, en su orden |

- **`duplicado`** es `true` cuando el servidor ya tenía ese evento (un reenvío). `resultado`,
  `motivo`, `detalle` y `capacidad_excedida` son **los de la primera vez**, tal como quedaron
  guardados: un conflicto reenviado sigue siendo conflicto aunque ahora encajaría; no se vuelve a
  evaluar. La app trata igual una respuesta con `duplicado` en `true` o en `false`.
- **`capacidad_excedida`** es `true` en un `recogido` que se aplicó aunque la grúa ya iba llena. Se
  aplica porque el vehículo ya está montado, queda marcado en el evento y abre una alerta a
  logística. La app bloquea antes ese Recogido (1a-13); esto solo pasa con datos desactualizados.
- **`servicio`** es el estado del servicio **al terminar el lote** (no después de cada evento), para
  que la app corrija el suyo: `estado`, `estado_previo` y `a_bordo` como en la lista de asignaciones,
  y `en_su_ronda` (si sigue apareciendo en `GET /asignaciones/`). Si el servicio terminó, viene con
  su estado (`entregado` o `cancelado`) y `en_su_ronda` en `false`. Si ya no es de este conductor
  (reasignado o devuelto a la cola), `estado` viene en `null` y `en_su_ronda` en `false`: la app lo
  quita de la lista. Es `null` cuando el servicio no existe o el evento no se pudo leer. La app usa
  este estado solo si no le quedan eventos pendientes de ese servicio.
- **`campos`** viene solo en `datos_invalidos`: los errores por campo, para depurar la app.
- `id` vuelve en minúsculas y con guiones, aunque se haya enviado de otra forma: la app empareja
  cada resultado con su evento por la posición. En un evento ilegible, `id` es el texto que llegó,
  o `null` si no venía como texto.

Motivos (`motivo`; `detalle` es su texto en español):

| `resultado` | `motivo` | Cuándo |
|---|---|---|
| `conflicto` | `servicio_cancelado` | El servicio ya estaba cancelado |
| `conflicto` | `servicio_entregado` | El servicio ya estaba entregado |
| `conflicto` | `servicio_no_asignado` | El servicio no es de este conductor: lo reasignaron, volvió a la cola o nunca fue suyo |
| `conflicto` | `salto_de_estado` | El destino no es el que sigue al estado del servicio (salto, retroceso o repetido con otro id) |
| `conflicto` | `novedad_abierta` | El servicio tiene una novedad que logística no ha resuelto |
| `conflicto` | `novedad_sin_motivo` | `novedad` sin `motivo` |
| `conflicto` | `destino_no_permitido` | Un estado que no se marca desde la app (por ejemplo `cancelado`) |
| `conflicto` | `identificacion_incompleta` | `recogido` de un vehículo sin placa ni VIN (o un desvare sin placa) |
| `rechazado` | `id_reutilizado` | El `id` ya está guardado con otro servicio, destino, secuencia o conductor. No se aplica, no reemplaza al guardado ni se guarda como conflicto nuevo |
| `rechazado` | `servicio_desconocido` | `servicio_id` no existe (un evento no se puede guardar sin servicio) |
| `rechazado` | `datos_invalidos` | Falta o no se puede leer `id`, `servicio_id`, `destino` o `secuencia`, o el elemento no es un objeto |
| `reintentar` | `error_del_servidor` | El servidor falló al guardar ese evento; no quedó nada guardado |
| `reintentar` | `espera_evento_anterior` | Un evento anterior del mismo servicio en este lote no se pudo guardar; este no se evaluó |

Un evento sobre un servicio ajeno **no** se rechaza: se guarda como conflicto (`servicio_no_asignado`)
con alerta, porque puede ser algo que el conductor hizo de verdad.

### Atomicidad

Cada evento va en su propia transacción con todos sus efectos: el cambio de estado, la línea de
cobro cuando el servicio queda Entregado, el enlace de las fotos que lo esperaban y la alerta de
conflicto o de capacidad. O queda todo, o no queda nada y la respuesta de ese evento es `reintentar`.
Un evento que falla no deshace los anteriores ni detiene los de **otros** servicios; los posteriores
del **mismo** servicio en ese lote responden `reintentar` sin evaluarse, porque dependen de él.

Errores de la petición completa: 400 `datos_invalidos` (falta la lista `eventos` o trae más de 100),
400 `json_invalido`, 401 (los de siempre) y 500. En cualquiera de ellos la app conserva la cola
entera y reintenta después.

## Subir una foto

`PUT /api/v1/evidencias/<uuid>/` — con `Authorization`, cuerpo `multipart/form-data` (es la única
ruta que no recibe JSON). El `<uuid>` lo genera el celular al tomar la foto.

| Campo | Notas |
|---|---|
| `archivo` | La foto, en JPEG, ya comprimida en el celular. Máximo 5 MB (5.242.880 bytes) |
| `servicio_id` | Servicio al que pertenece |
| `evento_id` | El `id` del evento de Recogido o Entregado al que acompaña (el mismo UUID que va en el lote de eventos) |
| `tipo` | `recogida` (acompaña a un `recogido`) o `entrega` (a un `entregado`). `soporte` no se sube desde la app en la fase 1a |

Respuesta **201** si la guardó; **200** si ya la tenía (no la reemplaza):

```json
{"version": 1, "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7", "resultado": "guardada", "enlazada": true}
```

`resultado` es `guardada` (201) o `repetida` (200). Con cualquiera de las dos la app la da por subida
y puede borrar su copia local. `enlazada` dice si ya quedó unida a su evento.

- **Reintento.** Si la subida se corta, la app sube **la foto completa otra vez** con el mismo UUID:
  es seguro repetirla cuantas veces haga falta. En la fase 1a no hay subida por partes ni se reanuda
  desde donde quedó (una foto comprimida pesa menos de 1 MB).
- **La misma foto no se duplica.** El servidor compara el contenido (SHA-256) y los datos: el mismo
  UUID con el mismo archivo, servicio, evento y tipo responde 200. El mismo UUID con otro contenido u
  otros datos responde **409 `evidencia_distinta`** y la guardada queda intacta.
- **La foto puede llegar antes que su evento.** Las fotos y los eventos van en colas distintas y el
  servidor no exige orden: la foto se guarda igual (`enlazada` en `false`) y queda unida al evento
  en cuanto este llega, se aplique o quede en conflicto. No hay que reenviarla. Una foto se une a un
  evento solo si es de su mismo servicio, lo tocó el mismo conductor que la subió y el tipo
  corresponde (`recogida` con `recogido`, `entrega` con `entregado`); si no, queda guardada sin unir.
- **Quién puede subirla.** El conductor que tiene el servicio o que lo tuvo (hay algún evento suyo en
  su historial). Sirve aunque el servicio ya esté entregado o cancelado, y también si se lo
  reasignaron mientras estaba sin señal: sus fotos son la evidencia de lo que hizo. Para un servicio
  que nunca fue suyo, o que no existe, responde 404 `no_encontrado` y no guarda nada.
- **Qué se valida.** Que el contenido empiece como un JPEG (no se confía en el nombre ni en el tipo
  que declara el celular) y el tamaño. El archivo se guarda en el disco del servidor con un nombre
  que pone el servidor; el nombre que manda el celular no se usa.

Errores:

| HTTP | `error` | Cuándo | Qué hace la app |
|---|---|---|---|
| 400 | `datos_invalidos` | Falta un campo, `tipo` no vale, el archivo viene vacío o no es un JPEG (`campos.archivo`) | Error de la app: registrarlo y no reintentar |
| 404 | `no_encontrado` | El servicio no existe o nunca fue de este conductor | No reintentar |
| 409 | `evidencia_distinta` | Ya hay otra foto con ese UUID | Error de la app: registrarlo y no reintentar |
| 413 | `foto_demasiado_grande` | Pesa más de 5 MB. Trae `maximo_bytes`. El servidor no la guarda. Con un cuerpo de más de 20 MB deja de leer y la respuesta puede llegar como conexión cortada | Comprimir más y subir con el mismo UUID |
| 415 | `tipo_no_soportado` | El cuerpo no es `multipart/form-data` | Error de la app: registrarlo |
| 401, 500 o sin respuesta | | Sesión o falla del servidor o de la red | Lo de siempre: reingresar, o reintentar más tarde |

Un `<uuid>` mal formado en la ruta responde el 404 de Django (en HTML), como cualquier ruta que no existe.

## Reservado para la 1a-14

Registro del token de Firebase del celular para el push (por ejemplo `POST /api/v1/push/`). Lo define esa tarea.
