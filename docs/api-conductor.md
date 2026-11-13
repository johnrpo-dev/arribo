# API de la app del conductor (contrato versión 1)

Contrato entre el servidor (`backend/api/`) y la app Flutter (`conductor/`). Lo usan la sincronización
(1a-10), las pantallas de la app (1a-11 a 1a-13) y el push (1a-14). Si el código y este documento no
coinciden, es un error: se corrige uno de los dos en la misma tarea.

Implementado en la 1a-09: ingreso, cierre de sesión, lista y detalle de asignaciones.
Borrador, sin implementar: envío de eventos y subida de fotos (sección "Borradores").

## Reglas generales

- **Base:** `https://<dominio>/api/v1/`. En desarrollo, `http://127.0.0.1:8000/api/v1/`.
- **Formato:** JSON en UTF-8, en las peticiones (`Content-Type: application/json`) y en las respuestas.
  Las rutas terminan en `/`.
- **Versión del contrato:** toda respuesta con cuerpo trae `"version": 1`. Sube solo si un cambio
  rompe a una app ya instalada (quitar o renombrar un campo, cambiar su tipo o su significado).
  Agregar un campo no la cambia: **la app ignora los campos que no conoce**. Una versión nueva
  tendría su propio prefijo (`/api/v2/`).
- **Fechas:** ISO 8601 en UTC con `Z`, por ejemplo `"2026-11-20T19:30:00Z"`. Pueden traer fracciones
  de segundo. La app las muestra en hora de Colombia (America/Bogota, UTC−5, sin horario de verano).
- **Vacíos:** un texto opcional sin dato llega como `null`, nunca como `""`.
- **Valores de cobro:** nunca. Ninguna respuesta trae valor, tarifa, líneas de cobro, factura ni
  pagador. Las pruebas recorren el JSON completo para comprobarlo.
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
| 405 | `metodo_no_permitido` | Método HTTP equivocado | Error de la app: registrarlo |
| 415 | `tipo_no_soportado` | El cuerpo viene con otro `Content-Type` (por ejemplo, de formulario) | Error de la app: registrarlo |
| 429 | `demasiados_intentos` | Celular bloqueado por PIN equivocados. Trae `reintentar_en` | Mostrar `detalle`; no reintentar antes |
| 500 | (sin cuerpo JSON) | Error del servidor | Reintentar más tarde |

Una ruta que no existe (por ejemplo `/api/v1/nada/`) responde el 404 de Django, en HTML y sin esta forma.

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

## Borradores (1a-10, sin implementar)

Propuesta para la tarea 1a-10, que puede ajustarla antes de implementarla. Se apoya en lo que ya
existe: `solicitudes/operaciones.py` (`aplicar_lote_del_conductor`) y los modelos `EventoEstado` y
`Evidencia`, cuyos ids genera el celular.

### Enviar eventos

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

| Campo | Notas |
|---|---|
| `id` | UUID v4 generado en el celular al tocar el botón. Reenviar el mismo id nunca aplica dos veces |
| `servicio_id` | Id del servicio de la lista |
| `destino` | `en_camino`, `recogido`, `entregado` o `novedad`. Cualquier otro se guarda como conflicto |
| `secuencia` | Contador del celular que solo crece (no se reinicia al cerrar sesión). Da el orden, no la hora |
| `hora_dispositivo` | Hora del celular al tocar, ISO 8601 (con `Z` u offset). Se guarda junto con la hora de sincronización |
| `motivo` | Obligatorio en `novedad` (sin él, conflicto) |
| `nombre_quien` | Quien entrega o recibe el vehículo, en `recogido` y `entregado` (1a-13) |
| `latitud`, `longitud` | Opcionales (fase 1b) |

El conductor del evento es el del token, no un campo del cuerpo. El servidor ordena el lote por
`secuencia` y aplica cada evento en su propia transacción. Respuesta 200, un resultado por evento:

```json
{
  "version": 1,
  "resultados": [
    {"id": "0b7f1e2c-9a10-4b4e-9d55-7f0c2a643f7e", "resultado": "aplicado"},
    {"id": "5d1e...", "resultado": "duplicado"},
    {"id": "9a3c...", "resultado": "conflicto"}
  ]
}
```

- `aplicado`: el servidor cambió el estado. `duplicado`: ya lo tenía (reenvío). `conflicto`: no encaja
  (servicio cancelado o reasignado, salto de estado, novedad sin motivo, destino no permitido); se
  guarda igual y abre una alerta a logística. **En los tres casos la app lo da por enviado** y lo
  saca de la cola; nunca lo reintenta por un conflicto.
- Por decidir en la 1a-10: tope de eventos por lote, qué hacer con un `servicio_id` que no existe
  (el evento no se puede guardar sin servicio) y si la respuesta avisa `capacidad_excedida` (hoy un
  Recogido de más desde la app se aplica y queda marcado en el evento).

### Subir una foto

`PUT /api/v1/evidencias/<uuid>/` — con `Authorization`, `multipart/form-data`. El uuid lo genera el
celular al tomar la foto, así que repetir la subida (por ejemplo, tras cortarse la señal) es seguro.

| Campo | Notas |
|---|---|
| `archivo` | La foto comprimida en el celular (JPEG) |
| `servicio_id` | Servicio al que pertenece |
| `evento_id` | Id del evento de Recogido o Entregado al que acompaña |
| `tipo` | `recogida`, `entrega` o `soporte` |

Respuestas propuestas: 201 si la guardó; 200 si ya la tenía (no la reemplaza); 409 `evento_pendiente`
si el evento aún no llegó al servidor (la app sube primero los eventos y reintenta la foto después);
413 si pasa del tamaño máximo (por decidir en la 1a-10).

### Reservado para la 1a-14

Registro del token de Firebase del celular para el push (por ejemplo `POST /api/v1/push/`). Lo define esa tarea.
