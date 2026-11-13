# Progreso de la fase 1a

Se actualiza al final de cada tarea: qué se hizo, qué se decidió y cómo probarlo a mano.
Los escalamientos de nivel de agente se registran en la sección del final, con su motivo.

## Puntos de control

| Punto | Contenido | Tareas | Estado |
|---|---|---|---|
| PC1 | Modelo de datos y reglas probadas contra PostgreSQL | 1a-01 (Flutter), 1a-02, 1a-03, 1a-04, 1a-16a | Cerrado el 12 de noviembre de 2026 (748 pruebas; falta compilar el APK, pendiente del NDK) |
| PC2 | Configuración, registro de solicitud y asignación | 1a-05, 1a-06, 1a-07, 1a-08 | Pendiente |
| PC3 | API, app del conductor y push | 1a-09 a 1a-14 | Pendiente |
| PC4 | Documentos, cobro, alertas y paneles | 1a-15, 1a-16b, 1a-17, 1a-18, 1a-19 | Pendiente |
| PC5 | Datos ficticios, despliegue y ensayo | 1a-20, 1a-21, 1a-22 | Pendiente |

Condición del PC1: pruebas contra la base (no solo en `nucleo/`) para asignación conductor–grúa sin
traslapes, unicidad de placa y VIN, idempotencia de eventos de sincronización y que una línea de cobro
no pueda quedar en estado inválido.

La tarea 1a-16 se partió en dos: 1a-16a (modelo de línea de cobro con sus restricciones, en el PC1) y
1a-16b (pantallas, tarifa y permisos, en el PC4).

## Tareas

### Preparación (12 de noviembre de 2026)
- Hecho: esqueleto del backend, reglas en `nucleo/` con pruebas, PostgreSQL como único motor, remoto en GitHub.
- Decidido: minSdk 26 (Android 8.0, de 2017) para la app; cubre más de los 5–6 años pedidos.
- Decidido: el historial genérico de cambios por registro queda para la fase 1b. En la 1a el historial
  son los eventos de estado (solo agregar) y el historial de cambios de valor del cobro.
- Cómo probar: desde `backend/`, `uv run pytest -q` (55 pruebas).

### 1a-02 Flota y usuarios (12 de noviembre de 2026)
- Hecho: app `flota` con Grúa, Conductor y Asignación conductor–grúa; función `grua_vigente`;
  grupos administrador, logistica, facturacion y conductor (migración de datos); admin sin borrado.
- Decidido: los traslapes los impide PostgreSQL con restricciones de exclusión sobre `[inicio, fin)`
  (extensión `btree_gist`); periodos contiguos sí se permiten. `clean()` repite la regla solo para que
  el admin muestre el error en español. La placa normalizada y la capacidad 1 o 2 también son
  restricciones de la base. Los grupos aún no tienen permisos: los asigna cada tarea que los use.
- Preguntas abiertas: cuatro en `QUESTIONS.md` (grúa inactiva, motivo de temporal, guiones en la placa,
  formato del celular).
- Cómo probar: `uv run pytest -q` (94 pruebas); en `/admin/`, crear una grúa y un conductor, asignarlo,
  y ver el mensaje en español al intentar una segunda asignación que se cruce.

### 1a-03 Clientes (12 de noviembre de 2026)
- Hecho: `nucleo/identificacion.py` (`normalizar_placa`, `normalizar_telefono`) y `nucleo/tipos.py`
  (`TipoServicio`: traslado, evento, desvare). App `clientes` con Cliente, Teléfono de cliente,
  Contacto y Tarifa; funciones `buscar_cliente_por_telefono` y `tarifa_propuesta`; admin sin borrado
  con teléfonos y tarifas dentro del cliente, y búsqueda por teléfono digitado de cualquier forma.
  En `flota`, la placa ya no admite guiones ni símbolos y el celular del conductor se guarda solo con
  dígitos (la migración normaliza lo ya guardado). Campo `es_demo` (no editable) en Grúa, Conductor y
  Cliente para que la 1a-20 borre solo los datos ficticios.
- Decidido: placas y teléfonos se normalizan (resueltas en `QUESTIONS.md`). Teléfono: solo dígitos,
  sin el 57 cuando antecede a un número de 10, entre 7 y 15 dígitos. El teléfono de cliente es único en
  toda la tabla; el de contacto no. Como máximo una tarifa vigente por cliente y tipo de servicio
  (las anteriores se conservan como no vigentes), valor mayor que cero; todo garantizado por la base.
  Si la migración encuentra dos placas o celulares que quedan iguales al normalizar, se detiene con un
  mensaje en vez de fusionar o borrar.
- Preguntas abiertas nuevas: dos en `QUESTIONS.md` (convenio compartido entre clientes, NIT único).
- Cómo probar (5 minutos): `uv run pytest -q` (192 pruebas) y `uv run python manage.py migrate`; en
  `/admin/` → Clientes → Añadir cliente: crear un concesionario con el teléfono "+57 300 123 4567" y
  una tarifa de traslado vigente; al guardar, el teléfono queda como 3001234567. Crear otro cliente
  con "300-123-4567": el admin avisa a quién pertenece. En la lista de clientes, buscar "300 123 4567"
  y verlo aparecer. Agregar al primero una segunda tarifa de traslado vigente: el admin la rechaza en
  español. En Flota, crear una grúa con placa "abc-123" y verla guardada como ABC123.

### 1a-04 Solicitudes y servicios (12 de noviembre de 2026)
- Hecho: en el núcleo, `normalizar_vin`, `validar_vin` (17 caracteres sin I, O ni Q; sin dígito
  verificador) y `validar_identificacion` (placa o VIN; el desvare exige placa). App `solicitudes`
  con Vehículo, Solicitud, Servicio, Evento de estado y Evidencia, todas sus reglas como
  restricciones con nombre en PostgreSQL. `solicitudes/operaciones.py` es la única forma de cambiar
  estado, conductor o grúa de un servicio: `asignar`, `reasignar`, `cambiar_estado`,
  `resolver_novedad` (panel) y `aplicar_evento_del_conductor` / `aplicar_lote_del_conductor` (app).
  Todas llaman a `nucleo/estados.py`, `nucleo/capacidad.py` y `nucleo/sincronizacion.py`, corren en
  una transacción con la fila del servicio bloqueada y dejan exactamente un evento por cambio. Admin
  en español sin borrado; eventos y evidencias de solo lectura. `MEDIA_ROOT` en `backend/media/`.
- Decidido (idempotencia): el id que genera el celular es la llave primaria del evento. Primero se
  mira si ya está guardado (el reenvío común); luego, con la fila del servicio bloqueada, se vuelve a
  mirar (dos peticiones sobre el mismo servicio quedan en fila); y si aun así dos peticiones llegan a
  guardar el mismo id (por ejemplo sobre servicios distintos), la llave primaria deja entrar una
  sola: la otra se deshace entera, sin evento ni cambio de estado, y responde "duplicado". Probado
  forzando el choque y con dos hilos reales contra la base. Un conflicto reenviado también es
  duplicado: no se vuelve a evaluar.
- Decidido (capacidad): al pasar a Recogido se bloquea la fila de la grúa y se cuentan sus servicios
  a bordo con `nucleo.estados.a_bordo`, así dos recogidas simultáneas no se cuelan. Desde el panel se
  rechaza con `CapacidadExcedida`; desde la app se aplica y el evento queda con
  `capacidad_excedida` (decisión del orquestador: el vehículo ya está montado). La identificación
  sí se exige también desde la app: sin ella, el evento es conflicto.
- Decidido: guardar un servicio con otro estado, conductor o grúa sin pasar por las operaciones
  falla (`CambioDeEstadoNoPermitido`); editar referencia u orden de ronda sí se puede. Los eventos
  no se modifican ni se borran (instancia y consultas en lote). En el evento, textos sin límite de
  largo y ubicación sin restricción de rango, para que un dato raro del celular nunca impida
  guardarlo. `asignar` rechaza servicios de una solicitud en borrador o no concretada (regla de
  `CLAUDE.md`). Exigir placa o VIN también al asignar queda como punto de extensión
  (`identificacion_exigida_al_asignar`), apagado hasta la tarea de configuración. El Vehículo también
  lleva la marca `es_demo`, porque un vehículo puede quedar sin solicitudes que lo marquen.
- Decidido tras la revisión (orquestador): el conductor no cancela desde la app. El núcleo solo
  acepta desde la app los destinos En camino, Recogido, Entregado y Novedad
  (`DESTINOS_DESDE_LA_APP` en `nucleo/sincronizacion.py`); cualquier otro, como un Cancelado, se
  guarda como conflicto y el servicio no cambia. Anotado en `CLAUDE.md` y resuelto en `QUESTIONS.md`.
- Decidido tras la revisión (orquestador): la respuesta de regreso de un evento se exige solo en una
  solicitud abierta. Una llamada perdida se cierra como no concretada sin preguntar por el regreso
  (restricción `solicitud_evento_responde_regreso` corregida en la migración 0002).
- Preguntas abiertas nuevas: una en `QUESTIONS.md` (obligatorios del borrador y destino del desvare).
- Cómo probar (5 minutos): `uv run pytest -q` (602 pruebas) y `uv run python manage.py migrate`.
  En `/admin/` → Solicitudes → Vehículos: crear uno con placa "abc-123" y verlo como ABC123; crear
  otro con "ABC 123" y ver "Ya hay un vehículo con la placa ABC123."; poner un VIN con la letra O y
  ver el aviso. En Solicitudes, crear un evento "Abierta" sin responder si tiene regreso y ver el
  aviso; responder "Sí" con fecha, agregar un servicio con el vehículo y guardar: el estado dice
  "Abierta" y en el servicio no se pueden editar estado, conductor ni grúa. Con un conductor que
  tenga grúa vigente (Flota), en `uv run python manage.py shell`:
  `from solicitudes import operaciones as op; from solicitudes.models import Servicio;`
  `from flota.models import Conductor; s = Servicio.objects.last(); c = Conductor.objects.first()`,
  luego `op.asignar(s, c, actor=None)`, `op.cambiar_estado(s, "en_camino", actor=None)` y
  `op.cambiar_estado(s, "cancelado", actor=None)` (falla: exige motivo). Para la idempotencia:
  `import uuid; from django.utils import timezone; d = dict(id=uuid.uuid4(), servicio=s,`
  `conductor=c, destino="recogido", secuencia=1, hora_dispositivo=timezone.now())` y llamar dos
  veces `op.aplicar_evento_del_conductor(**d)`: la primera da aplicado, la segunda duplicado. En el
  admin, el servicio muestra sus eventos y no deja modificarlos ni borrarlos.

### 1a-16a Líneas de cobro (12 de noviembre de 2026)
- Hecho: app `cobros` con Línea de cobro (servicio × pagador, posición 1 o 2, estado, valor,
  número de factura) e Historial de cobro (solo agregar). `cobros/operaciones.py` es la única forma
  de crear una línea o cambiar su estado, valor o factura: `crear_linea_al_entregar`,
  `marcar_cobrable`, `fijar_valor`, `facturar`, `pagar` y `anular_factura`. Todas llaman a
  `nucleo/cobro.py`, corren en una transacción con la fila bloqueada y dejan exactamente un registro
  de historial (quién, cuándo, acción, valor anterior y nuevo, factura, motivo). Admin en español de
  solo lectura, con el historial dentro de la línea. Sin pantallas: son de la 1a-16b.
- Decidido (la base manda): ocho restricciones con nombre en PostgreSQL sobre la línea (y tres
  sobre el historial: acción válida, anulación con motivo, cambio de valor con valor nuevo). Estado entre los cinco
  válidos y posición 1 o 2; única por (servicio, posición) y por (servicio, pagador), así que un
  servicio tiene como máximo dos líneas y no repite pagador; y la coherencia por estado: sin valor
  ⇒ sin valor ni factura; por facturar ⇒ valor mayor que cero y sin factura; facturado y pagado ⇒
  valor mayor que cero y número de factura que no sea solo espacios; no cobrable ⇒ sin factura.
  Probado con `update()` directo para cada combinación inválida. `save()` no deja cambiar estado,
  valor ni factura por fuera de las operaciones (`CambioDeCobroNoPermitido`); crear una línea con
  `objects.create()` sí se puede (igual que un servicio), pero así no deja historial: el código del
  sistema usa siempre las operaciones.
- Decidido (cuándo nace): `solicitudes` envía la señal `servicio_entregado` desde el único punto
  donde guarda un cambio de estado (`_cambiar` en `solicitudes/operaciones.py`), dentro de la misma
  transacción, y `cobros` la escucha (conectada en `CobrosConfig.ready()`); `solicitudes` no importa
  `cobros` (lo vigila una prueba). La línea nace con el pagador de la solicitud, posición 1 y la
  tarifa vigente del pagador para el tipo de servicio: con tarifa, por facturar; sin tarifa, sin
  valor. Si la línea no se puede crear, todo se deshace: el servicio no queda Entregado y, desde la
  app, el evento no se guarda (el celular lo reenvía). Un evento duplicado o en conflicto no crea
  línea. Es idempotente: si el servicio ya tiene línea, no se crea otra ni se toca la existente.
- Decidido: un servicio cancelado no tiene línea; `marcar_cobrable` se la crea (misma línea inicial,
  acción "marcada cobrable" en el historial), solo sobre servicios cancelados y una sola vez. El
  valor se exige en `Decimal`: un `float` (o un entero o texto) se rechaza antes de llegar a la base.
  La división entre dos pagadores no se construyó (el modelo ya admite la posición 2).
- Cambios fuera de `cobros`: `solicitudes/senales.py` (la señal) y `_cambiar` la envía; las
  utilidades de prueba pasaron de `tests/solicitudes/conftest.py` a `tests/conftest.py` para que
  las usen también las pruebas de cobros. El núcleo no cambió.
- Preguntas abiertas nuevas: cuatro en `QUESTIONS.md` (valor de un cancelado cobrable, cancelado
  antes de asignar, quién deja una línea no cobrable, cambio de pagador después de entregar).
- Cómo probar (5 minutos): `uv run pytest -q` (748 pruebas) y `uv run python manage.py migrate`.
  En `/admin/` → Solicitudes, en una solicitud abierta de traslado agregar un servicio con un
  vehículo que tenga placa. En `uv run python manage.py shell`:
  `from decimal import Decimal; from solicitudes import operaciones as op; from cobros import operaciones as cobro`
  `from solicitudes.models import Servicio; from flota.models import Conductor`
  `s = Servicio.objects.last(); c = Conductor.objects.first()` (con grúa vigente), luego
  `op.asignar(s, c, actor=None)` y `op.cambiar_estado(s, x, actor=None)` con x = `"en_camino"`,
  `"recogido"` y `"entregado"`. En `/admin/` → Cobros → Líneas de cobro aparece la línea "Sin
  valor" (o "Por facturar" con el valor de la tarifa, si el cliente tiene una vigente de traslado),
  sin campos editables y sin botón de borrar. En el shell: `l = s.lineas_cobro.get()`,
  `cobro.fijar_valor(l, Decimal("250000"), actor=None)`, `cobro.facturar(l, "FE-1", actor=None)` y
  `cobro.fijar_valor(l, Decimal("1"), actor=None)` (falla: "No se cambia el valor de una línea en
  facturado"). Por último `from cobros.models import LineaCobro;`
  `LineaCobro.objects.filter(pk=l.pk).update(numero_factura="")` falla con
  `linea_cobro_facturada_coherente`. En el admin, la línea muestra su historial: creada, cambio de
  valor y facturada.

### Base del panel (12 de noviembre de 2026)
- Hecho: app `panel` con ingreso en `/ingresar/` y salida en `/salir/` (vistas de Django; la salida
  solo por POST), inicio en `/` que saluda por nombre y lista las secciones del rol, y la página de
  componentes `/estilos/` (solo administrador). `panel/roles.py` trae el decorador
  `requiere_rol(...)`; `panel/secciones.py` es la única lista de secciones de la navegación (nombre,
  ruta, roles y vista). Plantilla `plantillas/base.html` con bloques `titulo`, `contenido` (y
  `cuerpo` para páginas sin barra lateral), parcial de mensajes, página 403 en español y hoja de
  estilos escrita a mano `panel/static/panel/arribo.css`. HTMX 2.0.11 guardado en los estáticos
  (sin CDN), con el token CSRF en `hx-headers` del `<body>`. `/salud/` no cambió.
- Decidido: el superusuario entra a todo. Un usuario del grupo `conductor` no entra al panel aunque
  tenga otro rol (403). Sin sesión, cualquier página del panel lleva al ingreso y vuelve a la página
  pedida; con sesión y sin el rol, 403 con opción de volver al inicio o salir. Las secciones sin
  pantalla (hoy todas) muestran "Aún no disponible"; cada tarea futura conecta su vista en
  `panel/secciones.py` cambiando `vista=None` por la ruta de su vista. La etiqueta de estado usa como
  modificador el valor del estado (`estado estado--en_camino`), para escribir
  `estado--{{ servicio.estado }}` en las plantillas. El fondo de "Entregado" quedó en `#eef8f2`
  (más claro que el resto) para que el verde pase AA. HTMX 2.0.11 y no 4.0.1: htmx.org y npm aún
  marcan la línea 2 como la estable por defecto; la 4 se publica aparte.
- Cómo probar (5 minutos): `uv run pytest -q` (809 pruebas) y, desde `backend/`,
  `uv run python manage.py createsuperuser`, luego `uv run python manage.py runserver`. Abrir
  `http://127.0.0.1:8000/`: lleva al ingreso. Entrar con una clave equivocada y ver "Usuario o
  contraseña incorrectos"; entrar bien y ver "Hola" con las siete secciones, todas "Aún no
  disponible". Abrir `/estilos/` y revisar tabla, etiquetas, formulario con error, botones y
  mensajes; angostar la ventana por debajo de 800 px y ver la barra superior con la navegación
  desplazable. En `/admin/`, crear un usuario en el grupo `facturacion`, entrar con él en otra
  ventana privada: solo ve Cobros, y `/tablero/` da "Sin acceso a esta página". Pulsar Salir.

### 1a-05 Configuración (12 de noviembre de 2026)
- Hecho: app `configuracion` con un solo registro (`Configuracion`) que se obtiene con
  `configuracion_vigente()` (lo crea con los valores por defecto de `docs/arquitectura.md` si no
  existe). Campos: momento de placa o VIN, mínimo de fotos (0 a 20), roles que ven valores,
  retención de fotos (6, 12, 24 meses o indefinida), seis umbrales de alertas, horario nocturno
  (inicio y fin) y formato de exportación de factura. `configuracion/operaciones.py` trae
  `guardar_configuracion` (deja un registro de historial por campo cambiado: quién, cuándo, campo,
  valor anterior y nuevo; el historial es de solo agregar) y `puede_ver_valores(usuario)`.
  Pantalla en `/configuracion/` (solo administrador), conectada en `panel/secciones.py`, con
  mensaje "Configuración guardada." y errores junto a cada campo.
- Decidido: el registro único lo garantiza la base (campo `unico` siempre verdadero y único). Toda
  regla de la configuración tiene restricción en PostgreSQL: mínimo de fotos de 0 a 20, umbrales
  mayores que cero, inicio y fin del horario nocturno distintos (el horario puede cruzar la
  medianoche), opciones válidas, y el administrador siempre ve valores (se muestra marcado y
  deshabilitado; no se puede desmarcar). El conductor no es opción: nunca ve valores, aunque tenga
  otro rol; el superusuario cuenta como administrador. Los costos de retención están en una tabla
  de `configuracion/models.py` (son del proveedor de almacenamiento, no del cliente). La
  exportación es un campo de opciones con una sola opción ("Excel/CSV genérico"): el formato depende
  del cliente, así que vive en la configuración, y los adaptadores futuros serán opciones nuevas.
  El horario nocturno se guarda pero aún no tiene efecto (lo dice la pantalla). CSS nuevo: solo el
  componente `grupo-opciones`/`opcion` para radios y casillas, que no existía. Parcial nuevo
  `parciales/campo.html` (etiqueta, control, ayuda y errores) para reutilizar en otros formularios.
- Fuera de esta tarea: modalidad de cobro y firma ya están en `clientes.Cliente`; precio en
  `clientes.Tarifa`; tipos de documento llegan con 1a-15. El historial no se muestra aún en pantalla.
- Cómo probar (5 minutos): `uv run pytest -q` (855 pruebas), `uv run python manage.py migrate` y
  `uv run python manage.py runserver`. Entrar como administrador y abrir Configuración: ver los
  valores por defecto (al recoger, 4 fotos, administrador marcado y gris, facturación marcada,
  12 meses con su costo, umbrales 10/2/15/4/5/30, 19:00 a 06:00). Cambiar el mínimo de fotos a 25 y
  guardar: error junto al campo. Ponerlo en 6 y guardar: "Configuración guardada." y al recargar
  sigue en 6. Poner inicio y fin del horario iguales: error junto a Fin. En
  `uv run python manage.py shell`: `from configuracion.models import HistorialConfiguracion;`
  `HistorialConfiguracion.objects.values_list("campo", "valor_anterior", "valor_nuevo", "usuario__username")`
  muestra `("minimo_fotos", "4", "6", ...)`. Con un usuario de logística, `/configuracion/` da
  "Sin acceso a esta página". Angostar la ventana a 375 px: sin desplazamiento horizontal.

## Escalamientos

Ninguno todavía.
