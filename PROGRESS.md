# Progreso de la fase 1a

Se actualiza al final de cada tarea: qué se hizo, qué se decidió y cómo probarlo a mano.
Los escalamientos de nivel de agente se registran en la sección del final, con su motivo.

## Puntos de control

| Punto | Contenido | Tareas | Estado |
|---|---|---|---|
| PC1 | Modelo de datos y reglas probadas contra PostgreSQL | 1a-01 (Flutter), 1a-02, 1a-03, 1a-04, 1a-16a | Cerrado el 12 de noviembre de 2026 (748 pruebas; falta compilar el APK, pendiente del NDK) |
| PC2 | Configuración, registro de solicitud y asignación | 1a-05, 1a-06, 1a-07, 1a-08 (más la base del panel) | Cerrado el 13 de noviembre de 2026 (1097 pruebas). APK de prueba compilado; falta probarlo en el Motorola |
| PC3 | API, app del conductor y push | 1a-09 a 1a-14 | Cerrado el 15 de noviembre de 2026 (1834 pruebas del servidor, 437 de la app). Falta la prueba en el Motorola: puntos 1 a 9c de docs/prueba-sin-senal.md y asignar desde el panel para que suene |
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

### 1a-06 Registro de solicitud I (12 de noviembre de 2026)
- Hecho: en el núcleo, `nucleo/registro.py` con `faltantes_para_abrir` (qué le falta a una
  solicitud para dejar de ser borrador) y sus pruebas. En `solicitudes`: `registro.py`
  (`registrar_solicitud`, una sola transacción que crea cliente nuevo, contactos, vehículo,
  solicitud y servicio), `formularios.py`, `views.py` y `urls.py`. Pantalla "Nueva solicitud" en
  `/solicitudes/nueva/` (logística y administrador), conectada en `panel/secciones.py`. Al escribir
  el teléfono, HTMX busca al cliente sin recargar (`/solicitudes/nueva/cliente/`): si existe, su
  nombre y sus últimas 5 solicitudes; si no, los campos nombre y tipo para crearlo al guardar.
  Detalle de solo lectura en `/solicitudes/<n>/` (datos, estado derivado, lo que falta y servicios).
- Decidido: "Guardar" deja la solicitud abierta, con su servicio pendiente de asignar, si tiene
  solicitante, tipo, origen, destino (no en desvare) y vehículo; si falta algo queda borrador y el
  aviso dice qué falta (también el detalle). "Guardar como borrador" siempre deja borrador. Sin
  teléfono (solicitante) ni tipo no se guarda nada: la base los exige. Un borrador con vehículo
  también guarda su servicio pendiente, para no perder lo digitado; no se puede asignar
  (`operaciones.asignar` lo impide). Un evento queda en borrador hasta la 1a-07, porque la base
  exige responder si tiene regreso y esa pregunta es de la 1a-07 (lo dice la pantalla). La placa o
  el VIN no se exigen para abrir; si se digitan, se normalizan y el VIN se valida. Un vehículo ya
  registrado con esa placa o VIN se reutiliza y se completa lo que le faltaba; si la placa y el VIN
  son de vehículos distintos, error junto al campo. El pagador es el solicitante salvo que se
  escriba el teléfono de otro cliente ya registrado. Un contacto con el mismo nombre y teléfono se
  reutiliza. "Programada para" vacío = inmediato; la hora se digita en hora de Colombia y se guarda
  en UTC. Sin CSS nuevo.
- Fuera de esta tarea: editar o completar un borrador (no hay pantalla todavía), varios vehículos,
  regreso del evento, momento configurable de placa o VIN, duplicados y no concretada (1a-07);
  la lista de solicitudes.
- Preguntas abiertas nuevas: dos en `QUESTIONS.md` (qué cuenta como vehículo; contacto ligado al
  cliente). La de obligatorios del borrador (1a-04) queda aplicada pero sigue abierta.
- Cómo probar (5 minutos): `uv run pytest -q` (928 pruebas) y `uv run python manage.py runserver`.
  Entrar con un usuario de logística o administrador y abrir Nueva solicitud: el cursor queda en el
  teléfono. Escribir "+57 310 555 0000": aparecen nombre y tipo del cliente nuevo. Llenarlos,
  elegir Traslado, origen, destino, placa "abc-123" y Guardar: abre el detalle con "Queda abierta",
  estado Abierta, pagador igual al solicitante y el servicio ABC123 "Pendiente de asignar". Volver a
  Nueva solicitud, escribir "310 555 0000": aparece el cliente con esa solicitud en su historial.
  Elegir Traslado, solo origen y Guardar: queda borrador y dice "falta el destino y al menos un
  vehículo". Repetir como Desvare sin destino con una placa: queda abierta. Con "Programada para"
  20/11 2:30 p. m., el detalle muestra 20/11/2026 14:30. Con un usuario de facturación,
  `/solicitudes/nueva/` da "Sin acceso a esta página". Angostar a 375 px: sin desplazamiento
  horizontal. Lo que se registre en esta prueba queda en la base local (nada se borra).

### 1a-07 Registro de solicitud II (13 de noviembre de 2026)
- Hecho: en el núcleo, `nucleo/registro.py` suma la referencia externa obligatoria si paga una
  aseguradora (faltante nuevo), `crea_regreso` y `verificar_cierre_no_concretada`;
  `nucleo/identificacion.py` suma `identificacion_exigida(momento_configurado, momento_actual)`.
  En `solicitudes`: `registro.py` registra varios vehículos (un servicio por vehículo), completa
  borradores (`completar_borrador`, solo borradores, con la fila bloqueada), crea los servicios de
  regreso al abrir un evento con regreso, advierte duplicados (`duplicados_activos`) y cierra como
  no concretada (`cerrar_no_concretada`). `operaciones.asignar` exige placa o VIN cuando la
  configuración dice "Al asignar" (desvare exige placa; el resto, placa o VIN). Pantallas: el mismo
  formulario sirve para nueva solicitud y para completar un borrador (`/solicitudes/<n>/completar/`,
  enlazado desde el detalle); las filas de vehículo se agregan con HTMX
  (`/solicitudes/nueva/vehiculo/`); el detalle muestra trayecto (ida o regreso del N.º) y
  referencia de cada servicio, la respuesta de regreso y, si nunca se asignó, el cierre como no
  concretada (`/solicitudes/<n>/no-concretada/`, solo POST).
- Decidido: los regresos se crean una vez, al quedar abierta: mismo vehículo y referencia,
  enlazados a su ida con `regreso_de`; como el servicio no tiene origen ni destino propios, el
  regreso va del destino al origen de la solicitud (el detalle lo dice). La pregunta "¿Tiene
  regreso?" solo se guarda en eventos; si la respuesta es sí, la fecha va junto (error junto al
  campo). Duplicado: mismo vehículo con un servicio no terminal en otra solicitud no cerrada como
  no concretada; el aviso enlaza a esa solicitud y no guarda hasta pulsar de nuevo Guardar (si
  cambian los duplicados, vuelve a advertir). El mismo vehículo en dos filas es error. Quitar un
  vehículo de un borrador cancela su servicio con motivo (nada se borra). No concretada: desde
  borrador o abierta, con motivo, solo si ningún servicio se asignó nunca; los servicios no se
  cancelan. Para que un cierre y una asignación simultáneos no dejen una solicitud no concretada
  con un servicio asignado, el cierre bloquea también las filas de los servicios y `asignar`
  vuelve a leer el estado de la solicitud después de bloquear el servicio (probado forzando el
  cruce con dos hilos; sin la relectura, la prueba falla). La nota del formulario dice cuándo se
  exigirá la placa o el VIN según la configuración. Sin CSS nuevo: las filas de vehículo usan
  `grupo-opciones` (leyenda "Vehículo N") y los componentes existentes; sin migraciones (la
  referencia externa ya estaba en el servicio).
- Decidido tras la revisión (orquestador): al completar un borrador el pagador se conserva
  aunque no tenga teléfono (el formulario dice "Paga hoy ..." y lleva su id oculto, validado
  contra la solicitud); solo cambia si se escribe el teléfono de otro pagador o se marca "Que
  pague quien llama". Nunca cambia por ausencia de un dato. Límite: un solicitante creado en el
  admin sin teléfono obliga a escribir uno al completar el borrador.
- Preguntas abiertas nuevas: cinco en `QUESTIONS.md` (referencia por vehículo, cuándo se cierra
  como no concretada, fecha de regreso, quitar vehículo de un borrador, qué es duplicado).
- Cómo probar (5 minutos): `uv run pytest -q` (1030 pruebas) y `uv run python manage.py runserver`.
  Entrar con logística o administrador y abrir Nueva solicitud. Escribir un teléfono (cliente
  nuevo: nombre y tipo), elegir "Evento o muestra de concesionario", origen y destino, placa
  "abc123" en Vehículo 1, pulsar "Agregar otro vehículo" y poner "xyz789" en Vehículo 2. Sin
  responder "¿Tiene regreso?", Guardar: queda borrador y dice que falta "la respuesta de si el
  evento tiene regreso". En el detalle pulsar "Completar borrador", marcar Sí sin fecha y Guardar:
  error junto a "Fecha y hora del regreso". Poner la fecha y Guardar: "Se crearon 2 servicios de
  regreso" y la tabla muestra 4 servicios, dos "Ida" y dos "Regreso del N.º …" con las mismas
  placas. Duplicado: en Nueva solicitud registrar otra con la placa "abc123": aparece "Posible
  duplicado" con enlace a la primera; pulsar Guardar de nuevo y se guarda. Aseguradora: con un
  pagador de tipo aseguradora y sin referencia, queda borrador ("falta la referencia externa").
  No concretada: en un borrador, al final del detalle elegir el motivo y "Cerrar como no
  concretada": estado "No concretada" con el motivo. En Configuración poner "Al asignar": la nota
  de Vehículos dice "se exigirán al asignar". Angostar a 375 px: sin desplazamiento horizontal.
  Lo que se registre queda en la base local.

### 1a-08 Asignación (13 de noviembre de 2026)
- Hecho: en el núcleo, `nucleo/disponibilidad.py` (`motivos_de_bloqueo`, `carga`: servicios no
  terminales y vehículos montados con `a_bordo`) y `nucleo/ronda.py` (`siguiente_orden`, `mover`,
  `numerar`). En `solicitudes`: `disponibilidad.py` con `motivos_de_bloqueo(conductor)` (el único
  lugar que decide si un conductor recibe servicios nuevos) y `disponibilidad_de_conductores()`;
  `operaciones.asignar` y `reasignar` bloquean la fila del conductor, rechazan a un conductor
  bloqueado (`ConductorBloqueado`; `SinGruaVigente` es un caso de ella) y ponen el servicio al
  final de su ronda; `reasignar` rechaza al mismo conductor (`MismoConductor`); nuevas
  `mover_en_ronda` y `ronda_de`. Al volver a la cola, el servicio deja la ronda. En el detalle de
  una solicitud abierta: "Asignar conductores" (un formulario por servicio pendiente, o de
  reasignar con motivo opcional si está asignado o en camino), la tabla "Conductores" (grúa,
  puestos, en ronda, montados, disponible o bloqueado con el motivo) y la "Ronda de ..." de cada
  conductor de la solicitud, con Subir y Bajar (incluye servicios de otras solicitudes, con
  enlace). Rutas `/solicitudes/<n>/servicios/<s>/asignar/` y `.../ronda/`, solo POST, logística y
  administrador. Con HTMX el contenido se reemplaza sin recargar la página; sin JavaScript, el
  mismo formulario recarga. Los errores de las operaciones (borrador, no concretada, placa o VIN
  exigidos al asignar, conductor bloqueado, servicio que cambió mientras tanto) salen como aviso.
- Decidido (bloqueos, lo más conservador): conductor inactivo, sin grúa vigente, o con grúa
  inactiva o fuera de servicio no recibe servicios nuevos, ni al asignar ni al reasignar; lo que ya
  tiene en curso sigue. La lista los muestra deshabilitados con su motivo y la operación los
  rechaza aunque lleguen. Documento vencido: punto de extensión en
  `solicitudes/disponibilidad.py` (`_datos_del_conductor`, campo `documentos_vencidos` del
  núcleo), se llena en la 1a-15. La carga no bloquea: más vehículos que puestos se atienden en
  rondas.
- Decidido (orden de ronda): campo existente `orden_ronda`. Único por conductor entre servicios
  no terminales (`servicio_orden_ronda_unico_por_conductor`, restricción en PostgreSQL); al
  asignar o reasignar, el servicio entra al final; Subir o Bajar numera de nuevo 1, 2, 3. Los
  huecos que dejan los terminados no se rellenan solos (el orden relativo se mantiene). Dos
  asignaciones simultáneas al mismo conductor toman puestos distintos (bloqueo del conductor,
  probado con dos hilos). La migración 0003 numeró los servicios activos ya guardados (no borra
  nada). Mover no deja evento: no es un cambio de estado. La tabla de servicios del detalle va
  por número, no por ronda.
- Verificado: la grúa queda guardada en el servicio y no cambia si el conductor pasa a otra grúa
  (contra la base); dos asignaciones del mismo servicio a la vez dejan una sola (contra la base,
  con hilos). Sin CSS nuevo: formularios con `grupo-opciones` y `parciales/campo.html`, tablas
  con `tabla-contenedor`. Revisado a 375 px sin desplazamiento horizontal de la página.
- Preguntas abiertas nuevas: tres en `QUESTIONS.md` (cómo se fija la ronda, motivo de reasignar,
  reasignar al mismo conductor); la de grúa inactiva (1a-02) queda aplicada de forma conservadora.
- Cómo probar (5 minutos): `uv run pytest -q` (1097 pruebas) y `uv run python manage.py migrate`.
  Antes, en `/admin/` → Flota (no hay pantalla de flota todavía): crear las grúas GRU001
  (capacidad 1) y GRU002 (capacidad 2), los conductores Ana y Beto, y dos asignaciones
  conductor–grúa (Ana en GRU001, Beto en GRU002) con inicio de ayer y sin fin. Crear también una
  conductora Carla sin asignación. Luego `uv run python manage.py runserver`, entrar con
  logística o administrador y registrar en Nueva solicitud un traslado con tres vehículos
  (placas ABC123, XYZ789, JKL456) hasta que quede abierta. En el detalle, "Conductores" muestra a
  Ana y Beto disponibles y a Carla bloqueada ("No tiene una grúa asignada"); en cada lista Carla
  aparece gris. Asignar el primero a Ana y los otros dos a Beto: la página no se recarga, sale
  "Servicio N.º … asignado a …", la tabla muestra "Ana (GRU001)" y "Beto (GRU002)", y aparecen
  "Ronda de Ana" (1 servicio) y "Ronda de Beto" (2). En la ronda de Beto pulsar Bajar en el
  primero: cambian de puesto. Reasignar el de Ana a Beto con un motivo: pasa al final de la ronda
  de Beto. En `/admin/`, poner fin (ahora) a la asignación de Beto en GRU002, crear la grúa
  GRU003 y asignársela a Beto desde ahora: el detalle sigue mostrando sus servicios con GRU002 y
  la tabla "Conductores" ya muestra GRU003. Con
  Configuración en "Al asignar" y un vehículo sin placa ni VIN, Asignar muestra "El vehículo
  necesita placa o VIN … La configuración exige placa o VIN al asignar." En un borrador no
  aparece "Asignar conductores". Angostar a 375 px: sin desplazamiento horizontal.

### 1a-09 API: ingreso y asignaciones (13 de noviembre de 2026)
- Hecho: el contrato de la API en `docs/api-conductor.md` (versión 1: autenticación, errores,
  ejemplos JSON, ETag y el borrador de eventos y fotos para la 1a-10). En el núcleo,
  `nucleo/ingreso.py` (PIN de 6 dígitos y límite de intentos) y `nucleo/trayecto.py` (el regreso va
  del destino al origen y en la fecha de regreso). En `flota.Conductor`, el hash del PIN
  (`pin_hash`, migración 0004) con `fijar_pin` y `verificar_pin`, y en el admin del conductor el
  campo "Nuevo PIN de la app" (no hay pantalla del panel para esto) y la columna "PIN fijado". App
  `api` bajo `/api/v1/`: `POST ingresar/`, `POST salir/`, `GET asignaciones/` y
  `GET asignaciones/<id>/`; modelos Token de celular e Intentos de ingreso, autenticación
  `Authorization: Bearer` propia y errores con la forma del contrato. En el admin, "Api del
  conductor": tokens (acción "Revocar los tokens seleccionados") e intentos (solo consulta).
- Decidido (PIN): exactamente 6 dígitos. El conductor lo digita una vez por celular, así que dos
  dígitos más casi no le cuestan, y con el límite adivinar el de un conductor toma unos tres años
  (siete meses probando los 10 a la vez); con 4 dígitos serían 10 días (2 días para alguno de los 10). Solo se guarda el hash de Django; la base
  rechaza un PIN en claro (`conductor_pin_solo_hash`). Si Django cambia el algoritmo, el hash se
  rehace en el siguiente ingreso.
- Decidido (intentos): 5 PIN equivocados dentro de 15 minutos bloquean el celular 15 minutos; durante
  el bloqueo ni el PIN correcto entra (429 con `reintentar_en`). Se guarda en la base, una fila por
  celular normalizado, bloqueada en cada intento: ocho intentos simultáneos revisan el PIN solo
  cinco veces (probado con hilos). Un celular que no es de nadie recibe la misma respuesta, cuenta
  igual y gasta el mismo hash. No es configuración del cliente: depende de la fuerza del PIN. Un PIN
  con otro formato responde 400 y no cuenta.
- Decidido (token): uno por celular (`dispositivo_id` que genera la app), aleatorio de 256 bits, del
  que se guarda solo el SHA-256 (la base lo exige con `token_solo_hash`). Como máximo uno vigente
  por conductor y celular (restricción parcial en la base); volver a ingresar en el mismo celular
  revoca el anterior. No vence. Se revoca, sin borrarse, al cerrar sesión o desde el admin. Cada
  petición revisa que el conductor y su usuario estén activos y en el grupo conductor (si no, 401
  `conductor_no_habilitado`; con el PIN correcto, el ingreso también responde eso). La API solo
  acepta este token: la sesión del panel no sirve ahí.
- Decidido (lista): los servicios no terminales del conductor en orden de ronda (la misma consulta
  de `solicitudes.operaciones`, nueva `consulta_ronda`), con estado previo, `a_bordo`, vehículo,
  origen y destino del servicio con sus contactos (en un regreso, ya invertidos), referencia, hora
  programada, grúa guardada con su capacidad, y de la configuración el mínimo de fotos y el momento
  de placa o VIN. Fechas en UTC con Z; textos vacíos como null. Para refrescos baratos, ETag sobre el
  cuerpo completo y 304 si no cambió: cubre cualquier cambio (también subir o bajar en la ronda, que
  no deja evento) sin campos nuevos en la base. Como mucho cuatro consultas por petición, tenga 2 u 8
  servicios. Un servicio ajeno, terminado o inexistente da el mismo 404. Ninguna respuesta lleva
  valor, tarifa, cobro, factura ni pagador (la prueba recorre todo el JSON y busca los números).
- Pruebas: en `tests/api/` con hash MD5 para no alargar la suite (el de producción tarda casi un
  segundo por ingreso); la prueba del hash del PIN corre con el de producción (PBKDF2).
- Preguntas abiertas nuevas: cinco en `QUESTIONS.md` (quién fija el PIN, vencimiento del token,
  cambiar el PIN cierra sesiones, conductor inactivo con servicios en curso, nombre del cliente).
- Cómo probar (5 minutos): `uv run pytest -q` (1238 pruebas) y
  `uv run python manage.py migrate`. En `/admin/` → Usuarios → Añadir usuario: "ana.app", con la
  autenticación por contraseña desactivada; guardar y, en Grupos, elegir `conductor`. En Flota →
  Conductores → Ana (la de la 1a-08): Usuario "ana.app", "Nuevo PIN de la app" 482913, Guardar; la
  lista muestra "PIN fijado". `uv run python manage.py runserver` y, en otra ventana de PowerShell
  (cambiar el celular por el de Ana):
  `$base = "http://127.0.0.1:8000/api/v1"`
  `$cuerpo = @{celular="300 000 0001"; pin="482913"; dispositivo_id="prueba-pc"; dispositivo_nombre="PowerShell"} | ConvertTo-Json`
  `$r = Invoke-RestMethod "$base/ingresar/" -Method Post -ContentType "application/json" -Body $cuerpo; $r.conductor`
  `$h = @{Authorization = "Bearer $($r.token)"}`
  `Invoke-RestMethod "$base/asignaciones/" -Headers $h | ConvertTo-Json -Depth 6`
  Se ven los servicios de Ana en el orden de su ronda, con contactos y grúa, y en ninguna parte
  "valor", "tarifa" ni "pagador" (PowerShell 5.1 puede mostrar mal las tildes: es la consola). Con
  un celular que no es de nadie y un PIN malo, seis veces:
  `$malo = @{celular="3109999999"; pin="000000"; dispositivo_id="prueba-pc"} | ConvertTo-Json`
  `1..6 | % { try { Invoke-RestMethod "$base/ingresar/" -Method Post -ContentType "application/json" -Body $malo } catch { $_.ErrorDetails.Message } }`
  Las cinco primeras dicen "Celular o PIN incorrectos." (lo mismo que con el celular de Ana y un PIN
  malo) y la sexta "Demasiados intentos fallidos. Intente de nuevo en 15 minutos.". Por último
  `Invoke-RestMethod "$base/salir/" -Method Post -Headers $h` y otra vez
  `try { Invoke-RestMethod "$base/asignaciones/" -Headers $h } catch { $_.ErrorDetails.Message }`:
  `sesion_invalida`. En `/admin/` → Api del conductor → Tokens de celular, el de "PowerShell" sale
  revocado, y en Intentos de ingreso, 3109999999 bloqueado. Lo que se cree en esta prueba queda en
  la base local.

### 1a-10 API: sincronización (13 de noviembre de 2026)
- Hecho: `POST /api/v1/eventos/` (lotes de toques del conductor) y `PUT /api/v1/evidencias/<uuid>/`
  (una foto de evidencia), y el contrato definitivo de las dos en `docs/api-conductor.md` (ya no hay
  borradores). En el núcleo, `nucleo/sincronizacion.py` dice ahora por qué un evento es conflicto
  (`Motivo`, con su texto en español) y cuándo un id repetido es un reenvío (`es_reenvio`), y
  `nucleo/evidencia.py` tiene las reglas de las fotos (JPEG, 5 MB, a qué evento acompaña, cuándo es
  la misma foto). App nueva `alertas`, solo lo mínimo: modelo Alerta (tipo, registro al que apunta,
  mensaje, abierta o resuelta, creada, resuelta por y cuándo), `abrir_alerta` y `resolver_alerta`, y
  el admin para verlas y marcarlas como resueltas. Sin pantallas ni comando: son de la 1a-18.
- Decidido (un solo camino): la API usa `solicitudes.operaciones.sincronizar_lote_del_conductor`,
  que pasa por el mismo `_aplicar_evento` de `aplicar_evento_del_conductor` y
  `aplicar_lote_del_conductor` (siguen iguales). Las alertas las abre `alertas` al oír dos señales
  nuevas de `solicitudes` (`evento_del_conductor_guardado` y `evento_del_conductor_rechazado`),
  igual que `cobros` con la línea: `solicitudes` no importa `alertas` (lo vigila una prueba), así la
  1a-18 puede importar `solicitudes` sin ciclo.
- Decidido (transacciones): cada evento va en su propia transacción con todos sus efectos: la fila
  del evento, el cambio de estado, la línea de cobro al quedar Entregado, el enlace de sus fotos y
  la alerta. O queda todo o nada. El lote no es una sola transacción: así no se sostienen bloqueos
  de varios servicios a la vez (evita abrazos mortales con el panel) y un evento que falla no
  deshace los anteriores. Si un evento falla por el servidor responde `reintentar` (no quedó nada:
  el celular lo reenvía), los de otros servicios siguen y los posteriores del mismo servicio en ese
  lote también responden `reintentar` sin evaluarse (dependen de él; evaluarlos daría un conflicto
  falso y definitivo).
- Decidido (idempotencia): la llave primaria del evento es el id del celular. Probado con dos
  peticiones HTTP simultáneas con el mismo lote y dos conexiones reales a PostgreSQL (el reintento
  por timeout mientras la primera sigue en curso): cada evento lo aplica una y la otra lo ve
  duplicado, nunca un conflicto. Un duplicado responde lo que quedó guardado la primera vez
  (resultado, motivo y marca de capacidad) con `duplicado: true`; un conflicto no se vuelve a evaluar
  aunque ahora encajaría. Por eso el evento guarda su motivo (`motivo_conflicto`, migración 0004 de
  solicitudes, con restricción en la base).
- Decidido (mismo id, otro contenido): si el id ya guardado llega con otro servicio, destino,
  secuencia o conductor, se responde `rechazado` (`id_reutilizado`): no se aplica, no pisa al
  guardado ni se guarda como conflicto nuevo, y abre una alerta sobre el evento original con lo que
  llegó. **Cambia dos pruebas de la 1a-04** que para ese caso (mismo id en dos servicios) esperaban
  "duplicado": ahora esperan "rechazado"; lo demás que comprobaban (entra uno solo, el otro se
  deshace entero) sigue igual.
- Decidido (orden): dentro del lote, por secuencia del dispositivo, nunca por la hora del celular ni
  por el orden de la lista. Entre lotes, cada evento se evalúa contra el estado que encuentra. El
  contrato le pide a la app un lote a la vez y siempre desde el pendiente más antiguo; si aun así la
  secuencia 7 llega antes que la 6, la 7 queda guardada como conflicto (`salto_de_estado`) con
  alerta y la 6 se aplica al llegar: nada se pierde y logística corrige desde el panel. No se
  retienen eventos esperando huecos (un evento perdido bloquearía todos los demás).
- Decidido (lo que se rechaza): solo lo que no se puede guardar: id reutilizado, servicio que no
  existe o un evento sin id, servicio, destino o secuencia legibles. Cada rechazo queda en el
  registro del servidor y abre una alerta "evento que no se pudo guardar" (sobre el conductor, o
  sobre el evento original). Un dato secundario ilegible (hora del celular, ubicación, textos) no
  tumba el evento: se guarda vacío. Un evento sobre un servicio ajeno no se rechaza: es conflicto
  guardado con alerta. Tope de 100 eventos por lote.
- Verificado (capacidad): un Recogido que excede la capacidad se aplica, queda marcado
  (`capacidad_excedida`, también en la respuesta) y abre la alerta "capacidad excedida", que dice
  qué vehículo ya iba montado. Entregar uno y recoger otro en el mismo lote no la excede.
- Decidido (fotos): la foto se escribe en disco por partes de 64 KB, sea grande o pequeña (la vista
  no usa el manejador de Django que deja en memoria lo que pesa menos de 2,5 MB), con su tamaño y su
  SHA-256 calculados al vuelo, y al guardar se mueve a `MEDIA_ROOT/evidencias/<servicio>/<uuid>.jpg`.
  El nombre lo pone el servidor; del que manda el celular no se usa ni la extensión. Solo JPEG (se
  mira el contenido) y máximo 5 MB (413; es un límite técnico, no configuración del cliente). La
  misma foto con el mismo UUID responde 200 y no duplica; el mismo UUID con otro contenido u otros
  datos, 409, sin tocar la guardada. Sin subida por partes: se reintenta la foto completa.
- Decidido (foto antes que el evento): se guarda igual, sin evento y con el id que el celular
  anunció (`evento_esperado`), y se enlaza sola cuando el evento llega, se aplique o quede en
  conflicto. La subida y la llegada del evento bloquean la misma fila del servicio, así que no se
  cruzan (probado con hilos). Una foto se enlaza solo a un evento de su mismo servicio, tocado por
  el mismo conductor y del tipo que corresponde (recogida con Recogido, entrega con Entregado); si
  no, queda guardada sin enlazar. La Evidencia guarda además quién la subió, el tamaño y la huella.
- Decidido (foto de servicio ajeno): la sube el conductor que tiene el servicio o que lo tuvo
  (hay un evento suyo en el historial), también si ya está entregado o si se lo reasignaron mientras
  estaba sin señal (es la evidencia de lo que hizo). Para un servicio que nunca fue suyo o que no
  existe: 404 y no se guarda nada.
- Preguntas abiertas nuevas: cuatro en `QUESTIONS.md` (foto de soporte, quién resuelve una alerta,
  cierre de sesión con eventos pendientes, fotos de un servicio que ya no es suyo).
- Para la 1a-21 (despliegue): nginx limita el cuerpo a 1 MB por defecto; hay que subirlo
  (`client_max_body_size 6m`) o las fotos de más de 1 MB no llegan a Django. Las fotos en
  `MEDIA_ROOT` no se sirven todavía por ninguna URL: mostrarlas en el panel es de otra tarea.
- Cómo probar (5 minutos): `uv run pytest -q` (1443 pruebas) y
  `uv run python manage.py migrate`. Con Ana lista para la app (pasos de la 1a-09) y un servicio
  asignado a ella desde el panel, `uv run python manage.py runserver` y en otra ventana de PowerShell:
  `$base = "http://127.0.0.1:8000/api/v1"`
  `$cuerpo = @{celular="300 000 0001"; pin="482913"; dispositivo_id="prueba-pc"} | ConvertTo-Json`
  `$r = Invoke-RestMethod "$base/ingresar/" -Method Post -ContentType "application/json" -Body $cuerpo`
  `$h = @{Authorization = "Bearer $($r.token)"}`
  `$s = (Invoke-RestMethod "$base/asignaciones/" -Headers $h).servicios[0].id`
  `function Evento($destino, $sec) { @{id=[guid]::NewGuid().ToString(); servicio_id=$s; destino=$destino; secuencia=$sec; hora_dispositivo=(Get-Date).ToUniversalTime().ToString("o")} }`
  `function Enviar($e) { $lote = @{eventos=@($e)} | ConvertTo-Json -Depth 5; (Invoke-RestMethod "$base/eventos/" -Method Post -Headers $h -ContentType "application/json" -Body $lote).resultados | Format-List id, resultado, duplicado, motivo, detalle }`
  `$a = Evento "en_camino" 1; Enviar $a` → `resultado: aplicado`, `duplicado: False`; el panel muestra
  el servicio En camino. `Enviar $a` otra vez → `aplicado` con `duplicado: True` y el historial del
  servicio en el admin sigue con un solo evento de En camino. `Enviar (Evento "entregado" 2)` →
  `conflicto`, `salto_de_estado`; el servicio sigue En camino y en `/admin/` → Alertas → Alertas
  aparece "Conflicto de sincronización" con el mensaje completo (se puede marcar como resuelta con
  la acción de la lista). Para la foto (cualquier JPEG del computador):
  `$b = Evento "recogido" 3; $foto = [guid]::NewGuid()`
  `curl.exe -s -X PUT "$base/evidencias/$foto/" -H "Authorization: Bearer $($r.token)" -F "servicio_id=$s" -F "evento_id=$($b.id)" -F "tipo=recogida" -F "archivo=@C:\ruta\foto.jpg"`
  → `"resultado":"guardada","enlazada":false` (el evento aún no llegó). `Enviar $b` → `aplicado`, y
  repetir el `curl.exe` → `"resultado":"repetida","enlazada":true`. El archivo queda en
  `backend\media\evidencias\<servicio>\<uuid>.jpg` y en `/admin/` → Solicitudes → Evidencias sale con
  su evento. Lo que se cree en esta prueba queda en la base local.

### 1a-11 App: ingreso y lista (13 de noviembre de 2026)
- Hecho: la app del conductor ya ingresa con celular y PIN, guarda el token en el Keystore, baja la
  lista de asignaciones en orden de ronda a una base SQLite local y la muestra aunque no haya señal,
  con la hora de la última actualización y un aviso discreto de "Sin conexión". Cada servicio muestra
  estado, tipo, vehículo (placa, VIN, marca, línea, color), hora (o "Inmediato"), dónde recoger y
  dónde entregar con su contacto, y botones de un toque: Llamar (abre el marcador con el número),
  Maps y Waze (enlaces universales: abren la app si está instalada y si no, el navegador). Tocar la
  tarjeta abre el detalle de solo lectura (referencia, solicitud, grúa, ubicación escrita por
  logística, si va montado). Refresca al abrir, al volver a primer plano, al deslizar hacia abajo y
  con el botón Actualizar. Menú con el nombre del conductor y "Cerrar sesión" (con confirmación).
  Arquitectura y esquema documentados en `conductor/README.md`. Sin cambios en el backend.
- Decidido (material_ui): Flutter 3.47 marcó obsoleto `package:flutter/material.dart` y `flutter
  create` ya había agregado `material_ui`; se migró ahora (el analizador lo marcaba) porque la app
  apenas empieza y ninguna dependencia usa widgets de Material, así que no hace falta el puente de
  compatibilidad.
- Decidido (estado): `ChangeNotifier` propios (`Sesion` y `ListaAsignaciones`) escuchados con
  `ListenableBuilder` y pasados por constructor. Sin provider ni otros paquetes: son dos piezas.
- Decidido (base local): `sqflite` con SQL escrito a mano y migraciones versionadas (una lista; la
  versión es su largo; cada una en la transacción de apertura). Descartado drift: genera código con
  build_runner y suma un paso de compilación para cuatro tablas. En pruebas, la misma SQLite por
  `sqflite_common_ffi` en archivos temporales. La versión 1 crea `estado_local`, `servicios` y,
  vacías, `eventos_pendientes` (1a-12) y `fotos_pendientes` (1a-13, solo la ruta del JPEG; nunca
  los bytes). La lista, su ETag y la hora se guardan en una sola transacción. Ninguna columna se
  llama como un valor de cobro (por eso la de `estado_local` es `dato` y no `valor`).
- Decidido (sesión): toda respuesta 401 a una petición con token borra el token y vuelve al ingreso
  con el `detalle` del servidor (también `conductor_no_habilitado`: al reactivarlo, el conductor
  vuelve a ingresar). Nada local se borra. Si ingresa otro conductor en el mismo celular se borra la
  lista del anterior, nunca lo pendiente. No se cierra sesión con eventos o fotos pendientes. Cerrar
  sesión sin señal borra el token del celular; en el servidor queda vigente hasta que se vuelva a
  ingresar en ese celular o se revoque en el admin. Una respuesta que llega después de cerrarse la
  sesión no se guarda.
- Decidido (red): tiempo máximo de 8 s para conectar y 15 s por petición. Servidor configurable con
  `--dart-define=ARRIBO_API=...` (por defecto `http://127.0.0.1:8000`); HTTP en claro solo en el APK
  de depuración y solo hacia 127.0.0.1 y localhost; release solo HTTPS. Permiso de internet en el
  manifiesto principal (antes estaba solo en debug). Sin respaldo de Android (`allowBackup=false` y
  reglas de extracción): el token cifrado no sirve en otro celular y la cola es de este.
- Decidido (ingreso): el PIN se valida en el celular (exactamente 6 dígitos, teclado numérico,
  solo dígitos) antes de enviarlo; los errores son el `detalle` del servidor sin agregar nada. En el
  bloqueo por intentos el botón queda apagado hasta la hora que informa el servidor ("Espere hasta
  las 3:45 p. m."). El celular del último conductor queda escrito. Fechas en hora de Colombia
  (UTC−5) sin depender de la zona del celular.
- Dependencias nuevas (con `flutter pub add`): `http` (API y servidor falso de pruebas), `sqflite`
  (base local), `flutter_secure_storage` (token en el Keystore), `url_launcher` (marcador, Maps,
  Waze), `uuid` (identificador del celular; ids de eventos y fotos en la 1a-12 y 1a-13) y, solo
  para pruebas, `sqflite_common_ffi`. Descartados: `connectivity_plus` (que haya red no dice que
  llegue al servidor; la lista sabe que no hay conexión porque la petición falla) y
  `device_info_plus` (el nombre del celular sale de 15 líneas en `MainActivity.kt`). El paquete
  `sqlite3` (llega por `sqflite_common_ffi`, solo de pruebas) metía `libsqlite3.so` en el APK para
  cada arquitectura; `pubspec.yaml` le indica que en Android no la empaque (la app usa la SQLite de
  Android por `sqflite`). Verificado: el APK ya no la trae.
- Verificado: `flutter analyze` sin problemas, `flutter test` 110 pruebas (cliente con servidor
  falso: ingreso correcto, PIN malo, bloqueo, datos inválidos, 401 → sesión cerrada, 304 no
  reescribe, sin señal y tiempo agotado; base local: migraciones, orden de ronda, transacción;
  la lista se ve desde la base cuando la red falla; el modelo y la base no tienen campos de cobro;
  pantalla de ingreso con validación de 6 dígitos; texto del sistema al 200 % sin romperse) y
  `flutter build apk --debug` compila. No se probó en el celular (no había uno conectado).
- Fuera de esta tarea: botones de estado y cola (1a-12), fotos y capacidad (1a-13), push (1a-14). El
  nombre bajo el ícono sigue siendo "arribo_conductor" (el de la plantilla).
- Preguntas abiertas nuevas: dos en `QUESTIONS.md` (ciudad de las direcciones; toques pendientes si
  ingresa otro conductor después de un 401).
- Cómo probar (10 minutos, con el Motorola por USB y la depuración USB activada):
  1. En el admin, tener a Ana lista para la app (pasos de la 1a-09: usuario del grupo `conductor`,
     PIN 482913, grúa vigente) y uno o dos servicios asignados a ella desde el panel (pasos de la
     1a-08), con un contacto con teléfono en el origen.
  2. Desde `backend/`: `uv run python manage.py runserver`.
  3. En otra ventana de PowerShell:
     `& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse tcp:8000 tcp:8000`
     y desde `conductor/`: `flutter run`.
  4. En el celular: el ingreso muestra abajo "Servidor: http://127.0.0.1:8000". Escribir un PIN de
     5 dígitos e Ingresar: "El PIN tiene 6 dígitos." sin llamar al servidor. Escribir el celular de
     Ana y un PIN equivocado: "Celular o PIN incorrectos.". Con el PIN correcto: "Mis servicios" con
     sus servicios en el orden de la ronda y "Actualizado hoy, …".
  5. Tocar Llamar: se abre el marcador con el número (no llama). Tocar Maps y Waze: se abre la app (o
     el navegador si no está instalada) con la dirección. Tocar la tarjeta: el detalle.
  6. En el panel, subir o bajar un servicio en la ronda de Ana; en el celular, deslizar la lista
     hacia abajo: cambia el orden.
  7. Sin señal: activar el modo avión **y** quitar el túnel USB (sigue andando en modo avión):
     `& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse --remove-all`. Cerrar la app
     del todo (deslizarla en recientes) y abrirla desde el ícono: la lista aparece igual, con
     teléfonos y direcciones, y el aviso "Sin conexión. Se muestra lo guardado en el celular.
     Actualizado hoy, …". Deslizar hacia abajo: sigue el aviso, nada se borra.
  8. Volver: quitar el modo avión, repetir el `adb reverse tcp:8000 tcp:8000` y deslizar: desaparece
     el aviso.
  9. En `/admin/` → Api del conductor → Tokens de celular, revocar el del Motorola; en el celular,
     deslizar la lista: vuelve al ingreso con el aviso del servidor y el celular de Ana ya escrito.
     Ingresar de nuevo: la lista sigue ahí.

### 1a-12 App: estados y cola sin señal (13 de noviembre de 2026)
- Hecho: el detalle del servicio tiene los botones de estado, fijos abajo: el paso que sigue
  ("Marcar En camino", "Marcar Recogido" o "Marcar Entregado") y "Reportar novedad" (con motivo
  obligatorio). Cada toque pide una confirmación corta en una hoja inferior (dos toques en total) y
  se guarda como evento en la cola local antes de cambiar la pantalla y antes de intentar la red.
  El estado nuevo se ve de inmediato en el detalle y en la lista con la marca "Pendiente por
  enviar"; arriba de la lista dice cuántos cambios faltan por enviar. La cola se envía sola al
  abrir la app, al volver a primer plano, al deslizar la lista, después de cada toque y con un
  reintento de espera creciente. Sin cambios en el backend ni en el contrato.
- Decidido (cola): `eventos_pendientes` en SQLite (`lib/cola/cola_eventos.dart`). En una sola
  transacción se comprueba que el toque sea el paso que sigue al estado que ve el conductor (lo
  confirmado más sus toques sin enviar), se toma la secuencia y se inserta el evento con su UUID
  v4. Por eso dos toques seguidos en el mismo botón no crean dos eventos. La secuencia sale del
  contador `ultima_secuencia` de `estado_local`: solo crece, sobrevive a cerrar la app, no se toca
  al cerrar sesión ni al cambiar de conductor y nunca queda por debajo de la mayor guardada. Un
  evento solo sale de la cola con respuesta definitiva (aplicado, conflicto o rechazado); nada se
  borra, la fila queda con su resultado. Migración 2 de la base local: tres columnas nuevas
  (placa o VIN del vehículo, nombre de quien tocó, y cuándo se dio por visto un aviso).
- Decidido (envío, `lib/cola/sincronizador.dart`): un solo envío a la vez (todos los disparadores
  piden lo mismo y, si ya hay uno, esperan ese); lotes de máximo 100 desde el pendiente más
  antiguo, en orden de secuencia; reenviar es mandar la misma fila (mismo UUID y secuencia), así
  que una respuesta perdida vuelve como `duplicado` y cuenta como enviada. Un evento en
  `reintentar` va primero en el lote siguiente y la app no insiste de inmediato: espera al
  siguiente disparador. Sin red, con un 500, un 400 del lote o una respuesta que no trae un
  resultado por evento (o con el id de otro), la cola queda entera. Reintento con espera de 5, 10,
  20 y 30 s (tope con la app a la vista; en segundo plano sigue creciendo hasta 5 minutos), que
  vuelve a 5 s cuando un envío sale bien. Sin dependencias nuevas: no se agregó
  `connectivity_plus` ni tareas en segundo plano de Android.
- Decidido (reconciliación): el estado que se muestra se calcula al leer (lo confirmado + la
  cola), no se escribe encima de lo confirmado. Al llegar la respuesta, en una sola transacción se
  marca el evento y se corrige el servicio de la lista con el estado que devolvió el servidor
  (solo si a ese servicio no le quedan pendientes); si ya no está en la ronda, sale de la lista.
  Conflicto y rechazado no se reintentan y quedan a la vista (en la lista y en el detalle) con el
  texto del servidor y "Logística ya recibió el aviso y lo revisará", hasta que el conductor toca
  "Entendido"; el aviso nombra el vehículo aunque el servicio ya no esté en la lista.
- Decidido (lista y eventos por turnos): el envío de eventos y la consulta de la lista no se
  cruzan, y al actualizar primero se envía y después se pide la lista. Así una lista pedida antes
  de aplicar un evento no se guarda después de su resultado. Al corregir un servicio con la
  respuesta de un evento se olvida el ETag de la lista (si el servidor volviera al estado
  anterior, por ejemplo al reanudar una novedad, daría 304 con la lista local ya cambiada). Si el
  envío falla por red, no se pide la lista (una espera en vez de dos).
- Decidido (sesión y varios conductores): con cambios propios sin enviar no se cierra sesión y un
  diálogo explica por qué. Un 401 cierra la sesión y conserva la cola; cuando el mismo conductor
  vuelve a ingresar, sale con su token nuevo. Los eventos de otro conductor nunca salen con el
  token del actual: se conservan, el ingreso y la lista avisan de quién son, y no le impiden al
  actual cerrar su sesión. Anotado en `QUESTIONS.md`.
- Para la 1a-13: Recogido y Entregado pasan por `prepararRecogidoOEntregado`
  (`lib/asignaciones/confirmacion.dart`), que hoy solo confirma; ahí van el bloqueo por capacidad,
  las fotos y el nombre de quien entrega o recibe. La cola ya acepta `nombre_quien` y un UUID
  fijado antes (para atar las fotos al evento), y la lista ya calcula "montado" con los pendientes.
- Verificado: `flutter analyze` sin problemas; `flutter test`, 247 pruebas (137 nuevas: la cola
  no pierde eventos si el envío falla, no los duplica, respuesta perdida → duplicado, secuencia
  tras reabrir la base, orden de envío, no adelanta un servicio detenido en `reintentar`, un solo
  envío a la vez, conflicto y rechazado visibles y sin reintento, 401 conserva la cola, otro
  conductor no envía los del primero, no se cierra sesión con pendientes, estado optimista y
  reconciliación, y la app "muerta" entre guardar, enviar, recibir y anotar); `flutter build apk
  --debug` compila. No se probó en el celular (no había uno conectado).
- Fuera de esta tarea: fotos, nombre de quien entrega o recibe y bloqueo por capacidad (1a-13);
  push (1a-14). Con la app en segundo plano (por ejemplo, navegando con Waze) el envío depende de
  que Android no la congele: se garantiza al volver a abrirla. Los eventos ya enviados quedan en
  la base del celular (no se depuran).
- Preguntas abiertas nuevas: tres en `QUESTIONS.md` (cambios de un conductor que no vuelve a
  ingresar en ese celular; deshacer un toque; qué hace el conductor ante un conflicto).
- Cómo probar (10 minutos, con el Motorola por USB; son los puntos 1 a 4 de
  `docs/prueba-sin-senal.md`):
  1. Ana lista para la app y con dos o tres servicios asignados (pasos de la 1a-11). Desde
     `backend/`: `uv run python manage.py runserver`. En otra ventana:
     `& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse tcp:8000 tcp:8000` y, desde
     `conductor/`, `flutter run`. Ingresar: aparece la lista.
  2. Quitar la señal: modo avión **y** `... adb.exe reverse --remove-all` (o desconectar el cable; el
     túnel USB sigue andando en modo avión). Cerrar la app del todo y abrirla: la lista aparece
     igual (punto 1).
  3. Tocar el primer servicio, "Marcar En camino" y "Sí, marcar En camino": cambia de inmediato a
     En camino con "Pendiente por enviar", y el botón pasa a "Marcar Recogido". Volver a la lista:
     la tarjeta tiene la marca y arriba dice "Hay 1 cambio pendiente por enviar". El panel sigue en
     Asignado. Cerrar la app del todo y abrirla: sigue igual. Menú → "Cerrar sesión": no deja y
     explica por qué (punto 2).
  4. Devolver la señal: quitar el modo avión y repetir `adb.exe reverse tcp:8000 tcp:8000` (o
     conectar el cable y repetirlo). Con la app a la vista, en menos de un minuto (o al deslizar
     la lista) desaparecen la marca y el aviso; el panel muestra En camino y en `/admin/` →
     Solicitudes → Eventos de estado el evento tiene la hora del celular y la de sincronización
     distintas (punto 3).
  5. Sin señal otra vez, "Marcar Recogido"; devolver y quitar la señal varias veces deslizando la
     lista. Al final, en Eventos de estado hay un solo Recogido y en Alertas no hay conflictos
     (punto 4).
  6. Opcional, conflicto: sin señal, marcar En camino en otro servicio; cancelarlo desde el panel;
     devolver la señal y deslizar la lista. El servicio sale de la lista y queda un aviso rojo con
     la placa y "El servicio ya estaba cancelado. Logística ya recibió el aviso y lo revisará";
     en `/admin/` → Alertas aparece el conflicto.
### 1a-15 Documentos (13 de noviembre de 2026)
- Hecho: en el núcleo, `nucleo/documentos.py`: estado de un documento en un día (vigente, por vencer
  según los días de anticipación de su tipo, vencido, aún no aplica, falta), qué estado bloquea
  (solo vencido), cuándo hay que avisar y qué archivos se aceptan. App nueva `documentos`:
  `TipoDocumento` (nombre único sin importar mayúsculas, aplica a grúa o a conductor, días de
  anticipación con 30 por defecto, activo) sembrado por migración con SOAT y Tecnomecánica (grúa) y
  Licencia de conducción (conductor); `Documento` (tipo, grúa o conductor, número opcional, vence o
  "aún no aplica" con la fecha desde la que aplica, archivo opcional, quién y cuándo).
  `documentos/consultas.py`: estado de cada tipo por grúa o conductor, documentos vencidos para
  asignar y `documentos_por_vencer(fecha)` para la alerta de la 1a-18 (no se construyó el comando
  ni el tablero). Pantalla Flota y documentos (`/flota/`, solo administrador, conectada en
  `panel/secciones.py`): grúas y conductores con la etiqueta de estado de cada documento, la página
  de cada documento (estado, registrar uno nuevo con foto o PDF opcional, historial con enlace al
  archivo) y los tipos de documento (crear, editar, desactivar). Admin de solo consulta.
- Decidido (bloqueo): `solicitudes/disponibilidad.py` llena `documentos_vencidos` con los
  documentos vencidos del conductor y de su grúa vigente. Asignar y reasignar lo rechazan con el
  motivo ("Documento vencido: SOAT de la grúa GRU001.") y la lista de conductores lo muestra
  bloqueado. Lo que está en curso no se interrumpe: los eventos de la app y los cambios de estado
  del panel no pasan por la disponibilidad (probado con documentos vencidos: En camino, Recogido y
  Entregado desde la app, por la API y desde el panel). Un documento que falta no bloquea (pregunta
  en `QUESTIONS.md`). Un tipo inactivo no se exige ni bloquea.
- Decidido (fechas): los días se cuentan en America/Bogota. Un documento que vence hoy sirve todo
  el día de hoy (hasta la medianoche de Medellín, aunque en UTC ya sea mañana): queda "por vencer"
  y vencido desde el día siguiente. "Por vencer" desde los días de anticipación del tipo,
  inclusive (con 30, el que vence en 30 días ya avisa; el de 31, no). "Aún no aplica" cuenta como
  vencido desde la fecha desde la que aplica si no se registró otro (pregunta en `QUESTIONS.md`).
- Decidido (base): el documento es de una grúa o de un conductor, exactamente uno, y del lado de su
  tipo. Lo garantiza PostgreSQL: el documento copia el lado del tipo (`aplica_a`) y una llave
  foránea compuesta (tipo, aplica_a) → (id, aplica_a) del tipo (escrita en SQL en la migración 0001,
  porque Django no las declara) impide que no coincidan; así, un tipo con documentos no puede
  cambiar de lado (la pantalla lo deshabilita). También son restricciones de la base: vence o aún
  no aplica (una de las dos), archivo con su tipo, nombre del tipo no vacío y único.
- Decidido (historial): nada se borra ni se edita. El vigente es el registrado más recientemente
  (no el que vence más tarde): así se corrige un error registrando otro. Guardar de nuevo un
  documento ya guardado da error.
- Decidido (archivo): JPEG, PNG o PDF de hasta 10 MB, reconocido por su contenido (pregunta en
  `QUESTIONS.md`). Se escribe en disco por partes desde el primer byte (la vista cambia los
  manejadores de subida, con la protección CSRF aplicada dentro de la vista) y se guarda en
  `MEDIA_ROOT/documentos/<grua|conductor>/<id>/<nombre aleatorio>.<ext>`; del nombre original no se
  usa nada. Si pasa del máximo se deja de escribir y no queda nada. Se ve en el panel por
  `/flota/documentos/<n>/archivo/`, solo administrador.
- Decidido (pantalla): etiquetas de estado existentes: vencido con la de Novedad (rojo), por vencer
  con la de Recogido (ámbar), vigente con la de Entregado (verde), aún no aplica con la de Asignado
  y falta con la de Pendiente. Sin CSS nuevo. Revisado a 375 px sin desplazamiento horizontal de la
  página (las tablas se desplazan dentro de su caja, como en el resto del panel).
- Preguntas abiertas nuevas: cuatro en `QUESTIONS.md` (documento que falta, fecha de "aún no
  aplica", avisos de inactivos, archivos aceptados).
- Cómo probar (5 minutos): `uv run pytest -q` (1529 pruebas) y
  `uv run python manage.py migrate`. Con Ana en la grúa GRU001 (pasos de la 1a-08) y un servicio
  pendiente en una solicitud abierta, `uv run python manage.py runserver` y entrar como
  administrador:
  1. Abrir Flota y documentos: las grúas con columnas SOAT y Tecnomecánica y los conductores con
     Licencia de conducción, todo en "Falta".
  2. Pulsar la etiqueta del SOAT de GRU001, dejar "Tiene fecha de vencimiento", poner como fecha
     **ayer**, adjuntar una foto JPEG y pulsar "Registrar SOAT": "SOAT registrado. Reemplaza al
     anterior.", estado "Vencido" en rojo y el aviso de que quien maneje la grúa no recibe
     servicios nuevos. En el historial, "Ver archivo" abre la foto.
  3. Abrir el detalle de la solicitud: en "Conductores", Ana sale "Bloqueado. Documento vencido:
     SOAT de la grúa GRU001." y en la lista de Asignar aparece gris.
  4. Volver al SOAT de GRU001 y registrar otro que venza en un año: queda "Vigente", el anterior
     pasa a "Reemplazado" en el historial y Ana vuelve a estar disponible.
  5. Adjuntar un archivo que no sea foto ni PDF (por ejemplo un .txt renombrado a .jpg): "El
     archivo debe ser una foto JPEG o PNG, o un PDF." y no se registra nada.
  6. En "Tipos de documento", crear "Póliza" para grúa con 45 días: aparece como columna nueva.
     Desactivarla: desaparece de la lista.
  7. Con un usuario de logística, `/flota/` da "Sin acceso a esta página". Angostar a 375 px: sin
     desplazamiento horizontal.

### 1a-13 App: fotos y capacidad (14 de noviembre de 2026)
- Hecho: en la app, "Marcar Recogido" y "Marcar Entregado" ya no se confirman con un toque: abren
  una pantalla donde el conductor toma las fotos con la cámara del celular y escribe el nombre de
  quien entrega (Recogido) o recibe (Entregado). Solo con el mínimo de fotos de Configuración y el
  nombre se guarda el evento; si falta algo, dice qué ("Falta 1 foto: lleva 3 de 4."). Las fotos
  suben solas, en su propia cola, después del evento; la lista dice cuántas faltan ("Hay 4 fotos
  pendientes por subir") y cada servicio lleva la marca "4 fotos por subir". Un Recogido se bloquea
  antes de abrir la pantalla si la grúa va llena (muestra qué vehículo falta marcar como Entregado)
  o si al vehículo le falta la placa o el VIN. Sin cambios en el comportamiento del backend ni en
  el contrato; en el backend solo se agregó una prueba.
- Decidido (cámara): la del sistema, con `image_picker`, y no una vista de cámara dentro de la app
  (`camera`). La cámara corre en otro proceso: la app no retiene en memoria la vista previa ni la
  foto, y no necesita el permiso de cámara. El costo es que Android puede matar la app mientras la
  cámara está abierta, y por eso todo lo de la pantalla vive en la base (ver abajo).
- Decidido (compresión): la hace el mismo plugin en código nativo, en un hilo aparte y
  decodificando ya reducida (`inSampleSize`): lado máximo de 1600 píxeles y JPEG de calidad 80,
  unos cientos de KB por foto (el servidor acepta 5 MB). A Dart solo llega la ruta del archivo;
  nunca se leen los bytes de una foto (solo los tres primeros, para comprobar que es un JPEG) y
  una que pese más de 5 MB no se acepta. El original de la cámara se borra de la caché. Cada foto
  recibe su UUID y se mueve a una carpeta `fotos/` junto a la base local (almacenamiento privado
  que Android no vacía, a diferencia de la caché). Sin dependencia nueva para la ruta
  (`path_provider`): sale de la ruta de la base. Las miniaturas usan `cacheWidth`.
- Decidido (la pantalla sobrevive a que Android mate la app): migración 3 de la base local. El
  paso se guarda al abrir la pantalla (`pasos_en_curso`, con el UUID que llevará el evento), cada
  foto al tomarla (fila en borrador atada a ese UUID) y el nombre en cada cambio. La pantalla es
  una ruta restaurable. Antes de abrir la cámara se anota en el paso; si la app muere, al volver se
  le pide al plugin la foto que quedó sin entregar y se agrega a ese paso. Salir de la pantalla sin
  marcar conserva lo que llevaba.
- Decidido (un solo paso para guardar): al marcar, en la misma transacción que inserta el evento,
  se comprueban el mínimo de fotos y el nombre, las fotos dejan de ser borrador y el paso se
  borra. O queda todo o no queda nada (ni se gasta la secuencia).
- Decidido (cola de fotos): una foto a la vez, en orden, solo con el token de quien la tomó y solo
  después de que su evento tuvo respuesta definitiva. El contrato admite la foto antes que el
  evento, pero así se evita un 404 falso (el servidor solo recibe fotos de quien tiene o tuvo el
  servicio, y "lo tuvo" se sabe por sus eventos). El `PUT` es idempotente por UUID: si se corta o
  la respuesta se pierde, se sube completa otra vez y el servidor responde 200 sin duplicarla. El
  archivo se lee del disco por partes al enviarlo, con un tiempo máximo de 2 minutos por foto.
  Reintento con la misma espera creciente de los eventos (5, 10, 20 y 30 s; hasta 5 minutos en
  segundo plano). El archivo se borra solo después de confirmada la subida; si la app muere entre
  las dos cosas, se borra al abrir. Sobrevive a reinicios. Con fotos propias pendientes no se
  cierra sesión; las de otro conductor esperan a que él vuelva a ingresar.
- Decidido (foto rechazada): un 413, 409, 400, 404 o 415 no se reintenta. La foto queda marcada
  con el texto del servidor, conserva su archivo y se ve en la lista como aviso rojo ("ABC123: una
  foto de la recogida no se pudo subir… Avise a logística") hasta que el conductor toca
  "Entendido". No impide cerrar sesión. Un 413 sin la forma del contrato (un nginx con el tope por
  defecto de 1 MB) se trata igual.
- Decidido (capacidad): la misma regla de `nucleo/capacidad.py`, con "montado" calculado sobre lo
  que ve el conductor (lo confirmado más sus toques sin enviar), así que funciona sin señal y se
  libera en cuanto marca Entregado. Se revisa al tocar "Marcar Recogido" y otra vez al guardar.
  Cuentan los servicios de la misma grúa que estén en su lista.
- Decidido (copias de reglas): `docs/casos-reglas.json` tiene los casos de estados (los 49 pares
  de estado y destino), a bordo, capacidad, placa, VIN, identificación y límites de las fotos. Lo
  recorren `backend/tests/nucleo/test_casos_compartidos.py` (118 pruebas) y
  `conductor/test/casos_compartidos_test.dart`. Comprobado cambiando a propósito la capacidad y la
  novedad en la copia de la app: la prueba falla.
- Defectos del contrato (anotados, sin tocar el backend): (1) el conductor no puede enviar la
  placa o el VIN de un vehículo que llegó sin ellos; el evento no tiene esos campos, así que la
  app bloquea el Recogido y le dice que llame a logística (el servidor igual lo dejaría en
  conflicto `identificacion_incompleta`). (2) El servidor no revisa ni el mínimo de fotos ni el
  nombre: esa regla solo la cumple la app. (3) Para un 413 el contrato dice "comprimir más y subir
  de nuevo"; la app no recomprime (ya comprime a menos de 1 MB), la deja como problema.
- Dependencia nueva (con `flutter pub add`): `image_picker` (cámara del sistema, compresión nativa
  y recuperación de la foto tras la muerte de la app). En el manifiesto de Android se declaró la
  consulta de la cámara (`IMAGE_CAPTURE`); no se agregó ningún permiso.
- Cambios en pruebas anteriores: la prueba de la 1a-12 "Recogido y Entregado se confirman…" ahora
  pasa por la pantalla de fotos y nombre (ya no existe la confirmación de un toque para esos dos
  pasos); la de tablas de la base incluye `pasos_en_curso`.
- Verificado: `flutter analyze` sin problemas; `flutter test`, 391 pruebas (mínimo de
  fotos y nombre exigidos; placa o VIN al recoger; bloqueo de capacidad con el vehículo que falta
  entregar; capacidad 2 permite dos montados; la pantalla sobrevive a reabrir y recibe la foto
  tomada con la app muerta; la cola de fotos no pierde, no duplica, deja el 413 visible sin
  reintentos infinitos y borra el archivo solo tras confirmar; casos compartidos);
  `flutter build apk --debug` compila; en `backend/`, `uv run pytest -q` (1647
  pruebas) y `uv run ruff check .` en verde. **No se probó en el celular** (no había uno
  conectado): la cámara real, la compresión y la muerte de la app al abrir la cámara solo están
  probadas con una cámara de mentira.
- Fuera de esta tarea: subir fotos con la app cerrada (fase 1b); que el conductor digite la placa
  o el VIN (el contrato no lo permite); reintentar a mano o exportar una foto rechazada; borrar las
  fotos de un paso que nunca se marcó; mostrar las fotos en el panel. `ListaAsignaciones.marcar` y
  `ColaEventos.encolar` siguen aceptando un Recogido sin fotos: la exigencia está en el camino que
  usan las pantallas (`confirmarPaso`).
- Preguntas abiertas nuevas: seis en `QUESTIONS.md`.
- Cómo probar (15 minutos, con el Motorola por USB; son los puntos 5 a 9 de
  `docs/prueba-sin-senal.md`):
  1. Ana lista para la app, con grúa de capacidad 1 y dos servicios asignados con placa (pasos de
     la 1a-11). Desde `backend/`: `uv run python manage.py runserver`. En otra ventana:
     `& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse tcp:8000 tcp:8000` y, desde
     `conductor/`, `flutter run`. Ingresar.
  2. Primer servicio: "Marcar En camino" y confirmar. "Marcar Recogido": se abre la pantalla de
     fotos. "Tomar foto" tres veces (se abre la cámara del Motorola; aceptar cada foto): aparecen
     tres miniaturas y "Lleva 3 de 4 fotos.". Escribir un nombre y "Marcar Recogido": no deja y
     dice "Falta 1 foto: lleva 3 de 4." (punto 5).
  3. Quitar la señal (modo avión **y** `... adb.exe reverse --remove-all`). Tomar la cuarta foto y
     "Marcar Recogido": vuelve al detalle con Recogido, "Pendiente por enviar" y "4 fotos por
     subir". En la lista: "Hay 4 fotos pendientes por subir. Se suben solas cuando haya señal."
     (punto 6).
  4. Forzar el cierre de la app (o reiniciar el celular) y abrirla: sigue igual, y "Cerrar sesión"
     no deja (punto 7).
  5. Segundo servicio, todavía sin señal: "Marcar En camino", confirmar, "Marcar Recogido": no abre
     la pantalla; dice "La grúa va llena" y la placa del primero bajo "Falta marcar como
     Entregado:" (punto 9).
  6. Devolver la señal (quitar el modo avión y repetir `adb.exe reverse tcp:8000 tcp:8000`) y
     deslizar la lista: el aviso de fotos baja hasta desaparecer. En el panel el servicio queda
     Recogido y en `/admin/` → Solicitudes → Evidencias están las 4 fotos con su evento; en
     Eventos de estado, el Recogido tiene el nombre de quien entregó (punto 8). Los archivos quedan
     en `backend\media\evidencias\<servicio>\`.
  7. La cámara mata la app: en Ajustes → Opciones de desarrollador, activar "No conservar
     actividades". En el primer servicio, "Marcar Entregado", tomar una foto, escribir medio nombre
     y tomar otra: al aceptar la foto, la app vuelve a la misma pantalla con las dos fotos y el
     nombre (punto 9b). Desactivar la opción.
  8. Opcional, tamaño real de una foto: después del paso 6, mirar cuánto pesa un archivo de
     `backend\media\evidencias\`: debe estar muy por debajo de 5 MB (se esperan unos cientos de KB).

### 1a-13b Placa o VIN digitados al recoger (14 de noviembre de 2026)
- Hecho (defecto de la 1a-13): con la configuración de fábrica ("placa/VIN al recoger"), un
  vehículo sin placa ni VIN bloqueaba "Marcar Recogido" y pedía llamar a logística; sin señal no
  se podía recoger. Ahora la pantalla del Recogido pide digitar la placa o el VIN (un desvare, la
  placa), lo digitado se guarda mientras escribe (sobrevive a que Android mate la app), viaja en el
  evento por la cola y la lista y el detalle muestran el vehículo con esa placa enseguida, también
  sin señal. Con "placa/VIN al asignar" no se pide: el Recogido se sigue bloqueando como antes.
- Contrato 1.1 (`docs/api-conductor.md`, primero): el evento Recogido acepta `placa` y `vin`
  opcionales, normalizados como `nucleo/identificacion.py`. En otro destino se ignoran. Un dato
  ilegible (un objeto o una lista) se guarda vacío sin tumbar el evento; un número se lee como
  texto. La respuesta no cambia. La versión del contrato en el cuerpo sigue siendo 1: es un cambio
  compatible (una app 1.0 no los manda y el servidor sigue igual).
- Decidido (regla, en `nucleo/identificacion.py` con sus casos compartidos):
  `validar_identificacion_al_recoger` cuenta lo digitado donde al vehículo le falte, aunque esté mal
  formado (el conductor lo leyó del vehículo que montó); `completar_identificacion` dice qué se
  guarda: lo que el vehículo no tenía y es válido; nunca sobreescribe uno distinto; lo distinto o
  inválido queda por revisar. Placa válida: de 1 a 10 letras o dígitos (`validar_placa`).
- Decidido (servidor, `solicitudes/operaciones.py`): el Recogido nunca se rechaza por lo digitado.
  Se aplica, lo digitado queda en el evento (`placa_digitada`, `vin_digitado`, migración 0005) y
  lo que no quedó en el vehículo abre la alerta nueva "Placa o VIN digitado por revisar" (una por
  evento, migración 0002 de `alertas`): dato distinto, inválido o que ya es de otro vehículo. La
  fila del vehículo se bloquea antes de comparar; cada dato se guarda en su propio punto de
  restauración, así que un choque con la unicidad de la base (otro Recogido simultáneo guardó la
  misma placa en otro vehículo) deshace solo ese dato y el evento sigue. Un Recogido sin
  identificación y sin nada digitado sigue siendo conflicto `identificacion_incompleta`, y un
  conflicto no toca el vehículo. El reenvío del mismo evento no repite nada.
- Decidido (app): `identificacionPorDigitar` decide qué campos se muestran (traslado o evento sin
  placa ni VIN: los dos, basta uno; desvare sin placa: solo la placa). Al marcar se revisa con la
  copia de la regla: falta, VIN de 17 sin I, O ni Q, placa de 1 a 10. Migración 4 de la base
  local (`pasos_en_curso.placa_digitada`/`vin_digitado`, `eventos_pendientes.placa`/`vin`). La
  lista superpone lo digitado de un Recogido pendiente sobre el vehículo, donde le falte; al
  aplicarse, se escribe en la lista guardada hasta que se vuelva a pedir.
- Lo que el servidor no revalida (mínimo de fotos, nombre de quien entrega o recibe) quedó igual.
- Pruebas que cambiaron porque codificaban el defecto: en `requisitos_test.dart` y
  `pantalla_paso_test.dart`, "sin placa ni VIN no se puede recoger, llame a logística" y "al
  recoger se exige siempre, también con al asignar" pasan a "pide digitarla" con "al recoger" y
  "se bloquea" con "al asignar"; "la identificación se revisa antes que la capacidad" ahora es con
  "al asignar". En `cola_eventos_test.dart` y `api_eventos_test.dart`, el JSON del evento incluye
  `placa` y `vin` (null), como dice el contrato 1.1.
- Verificado: en `backend/`, `uv run pytest -q` (1743 pruebas), `uv run ruff check .`,
  `manage.py makemigrations --check` sin cambios y `manage.py migrate` aplicado en la base local.
  Pruebas nuevas contra PostgreSQL: placa digitada guardada, distinta no se pisa y alerta, de otro
  vehículo da aplicado más alerta sin romper el lote, inválida da aplicado más alerta, duplicado
  sin efectos repetidos, sin valores de cobro, y dos Recogidos simultáneos con la misma placa (uno
  la guarda, el otro alerta). Comprobado quitando a propósito el punto de restauración: fallan la
  prueba de unicidad y la de concurrencia. En `conductor/`, `flutter analyze` sin problemas,
  `flutter test` (418 pruebas) y `flutter build apk --debug` compila. Comprobado quitando a
  propósito la superposición en la lista y el guardado al aplicarse: fallan sus pruebas. **No se
  probó en el celular.**
- Preguntas abiertas nuevas: cuatro en `QUESTIONS.md` ("al asignar" con un vehículo sin
  identificar, qué es una placa válida, qué hace logística con la alerta, dónde se piden en la
  pantalla). La de la 1a-13 sobre digitar la placa pasó a resueltas.
- Cómo probar (5 minutos, con el Motorola por USB; es el punto 9c de `docs/prueba-sin-senal.md`):
  1. Desde `backend/`: `uv run python manage.py migrate` y `uv run python manage.py runserver`.
     Confirmar en Configuración que el momento de placa/VIN es "al recoger". Registrar un
     traslado sin placa ni VIN y asignarlo a Ana. En otra ventana, `adb.exe reverse tcp:8000
     tcp:8000` y, desde `conductor/`, `flutter run`.
  2. En la app, "Marcar En camino" y confirmar. Activar el modo avión y quitar el reverse
     (`adb.exe reverse --remove-all`). "Marcar Recogido": aparecen "Identificación del vehículo",
     Placa y VIN. Tomar las fotos y escribir el nombre sin placa: "Marcar Recogido" dice "El
     vehículo necesita placa o VIN (al menos uno).".
  3. Escribir la placa "abc-123" y marcar: el detalle y la lista muestran ABC123 y "Pendiente por
     enviar".
  4. Devolver la señal (`adb.exe reverse tcp:8000 tcp:8000`, quitar el modo avión) y deslizar la
     lista: en `/admin/` → Solicitudes → Vehículos ese vehículo tiene la placa ABC123 y en Eventos
     de estado el Recogido muestra la placa digitada.
  5. Opcional: repetir con un segundo traslado y digitar la placa de un vehículo ya registrado: el
     Recogido se aplica, el vehículo sigue sin placa y en `/admin/` → Alertas aparece "Placa o VIN
     digitado por revisar" con lo que digitó.

### 1a-14 Push al conductor (15 de noviembre de 2026)
- Hecho: al asignar o reasignar desde el panel suena el celular del conductor con "Nuevo servicio
  asignado" (y el del anterior, con "Servicio reasignado"). Tocar la notificación abre la lista y la
  refresca; con la app abierta, el aviso refresca la lista. El detalle de la solicitud muestra por
  servicio "Visto por el conductor" con la hora, o "Sin ver".
- Contrato 1.2 (`docs/api-conductor.md`, primero): `PUT /api/v1/push/` con `{"token": ...}` (204)
  liga el token de push a la sesión del celular; `POST /salir/` lo borra; la lista y el detalle
  marcan "visto"; sección "Avisos push" con lo que lleva el aviso (solo `tipo` y `servicio_id`, más
  un texto fijo, sin cobro ni datos personales). Cambio compatible: el cuerpo sigue en `"version": 1`.
- Decidido (servidor):
  - Tabla de salida: `solicitudes` envía la señal `servicio_asignado` dentro de la transacción de
    asignar o reasignar. `api/receptores.py` crea una fila `NotificacionPush` por celular con push,
    en un punto de restauración propio: si algo falla se registra y la asignación sigue. Si la
    asignación se deshace, las filas también. El envío ocurre después de confirmar
    (`transaction.on_commit`); un fallo ahí nunca deshace nada.
  - Envío por la API HTTP v1 de FCM con `google-auth` (token de acceso de la cuenta de servicio) y
    `requests`, no `firebase-admin`: para enviar un mensaje basta un POST, y `firebase-admin` trae
    Firestore, Storage y gRPC, que no se usan.
  - Respuestas de FCM (`nucleo/push.py`): 2xx enviado; `UNREGISTERED` o `SENDER_ID_MISMATCH`, token
    desactivado (la sesión sigue); sin red, 401, 403, 408, 429 o 5xx, reintento; lo demás (incluido
    un 404 sin código, que puede ser el proyecto mal escrito), fallido. Hasta 5 intentos con esperas
    de 1, 5, 15 y 30 minutos (menos de una hora). Un aviso que ya no aplica (el servicio cambió de
    conductor o terminó) no se envía. Cada envío bloquea su fila (`skip_locked`): el envío tras
    confirmar y el comando nunca mandan el mismo aviso dos veces.
  - `manage.py enviar_notificaciones_pendientes` envía los pendientes que ya tocan y dice cuántos
    salieron. En producción va cada minuto (cron o temporizador, en la 1a-21).
  - Sin `ARRIBO_FIREBASE_CREDENCIALES` (o con un archivo ilegible) el servidor funciona igual: el
    aviso queda fallido con "El push no está configurado" y un aviso en el registro, que solo
    muestra la ruta y el tipo de error, nunca el contenido de la cuenta de servicio.
  - El token de push vive en `TokenDispositivo` (la sesión del celular): único entre sesiones (si
    otra sesión lo tenía, se le quita), y la base exige que una sesión revocada no lo tenga.
    Revocar (cerrar sesión, admin o nuevo ingreso en el celular) lo borra.
  - Visto por el conductor (`Servicio.visto_por_conductor_en`): lo marca la primera respuesta de la
    lista o del detalle que trae el servicio, también un 304, sin que la app mande nada (no se
    puede perder ni necesita cola sin señal). Vuelve a "sin ver" al reasignar o devolver a la cola;
    la base exige conductor cuando hay visto. No viaja a la app ni cambia el ETag.
  - Admin: en Tokens de dispositivo se ve si la sesión tiene push (no el token). "Notificaciones
    push" es de solo lectura, con estado, intentos y error de cada aviso.
- Decidido (app):
  - `firebase_core` y `firebase_messaging` con `flutter pub add`, y el plugin de Gradle
    `com.google.gms.google-services` 4.5.0 en `android/settings.gradle.kts` y
    `android/app/build.gradle.kts`, sin FlutterFire CLI. `google-services.json` sigue ignorado por
    git (comprobado con `git check-ignore`) y hace falta para compilar. Permiso
    `POST_NOTIFICATIONS` en el manifiesto; se pide al iniciar sesión.
  - `lib/push.dart` (`RegistroPush`): registra el token al ingresar, al abrir con sesión guardada y
    en `onTokenRefresh`; sin señal lo reintenta cuando el servidor vuelva a responder la lista; al
    cerrarse la sesión borra el token en Firebase. Si Firebase no arranca, la app sigue sin avisos.
- Prueba que cambió: `test_la_lista_hace_las_mismas_pocas_consultas_con_2_o_con_8_servicios`
  (`tests/api/test_asignaciones.py`) pasa de 4 a 5 consultas como máximo: la primera vez que la app
  baja servicios nuevos hay un solo UPDATE más, que los deja vistos. Sigue sin crecer con el número
  de servicios.
- En esta máquina, `backend/.env` ya tiene `ARRIBO_FIREBASE_CREDENCIALES` con la ruta a la cuenta de
  servicio en `OneDrive\Documents\arribo` (fuera del repositorio; no se copió ni se mostró su
  contenido). `backend/.env.example` trae la variable vacía con su explicación.
- Riesgo: firebase_messaging 17 marca obsoletos `getToken`, `onTokenRefresh` y `deleteToken` a favor
  del registro por identificador de instalación (`register`, `onRegistered`). Se siguen usando
  porque son lo que la API HTTP v1 recibe en `message.token`; cambiar exige cambiar también el envío
  del servidor. Revisarlo cuando Firebase anuncie el retiro del token.
- Verificado: en `backend/`, `uv run pytest -q` (1834 pruebas), `uv run ruff check .`,
  `manage.py makemigrations --check` sin cambios y `manage.py migrate` aplicado en la base local.
  Pruebas nuevas contra PostgreSQL: asignar encola en la misma transacción y envía al confirmar; una
  asignación deshecha no deja aviso; ni un fallo al encolar ni uno al enviar deshacen la asignación;
  reintento acotado con el reloj detenido y el comando; token `UNREGISTERED` desactivado sin tocar
  uno nuevo; reasignar avisa a los dos; un aviso vencido no sale; el mensaje HTTP v1 exacto y sin
  cobro ni datos personales; un 401 de FCM renueva el token de acceso; dos envíos simultáneos
  mandan uno; `PUT /push/` exige la sesión del celular y queda en su dispositivo; visto por lista,
  detalle y 304, reiniciado al reasignar o volver a la cola; columna del panel. Todas con un cliente
  HTTP y credenciales falsos: ninguna toca la red ni lee la cuenta de servicio real. Además se
  comprobó, sin mostrar nada, que el servidor carga la cuenta de servicio desde la ruta del `.env`.
  En `conductor/`, `flutter analyze` sin problemas, `flutter test` (437 pruebas) y
  `flutter build apk --debug` compila con el plugin de Firebase. **No se probó en el celular.**
- Preguntas abiertas nuevas: cinco en `QUESTIONS.md` (quién recibe aviso y cuándo, cómo suena, el
  ícono de la barra, el permiso negado y qué significa "visto").
- Cómo probar (5 minutos, con el Motorola por USB):
  1. Desde `backend/`: `uv run python manage.py migrate` y `uv run python manage.py runserver` (el
     `.env` ya trae `ARRIBO_FIREBASE_CREDENCIALES`). En otra ventana, `adb.exe reverse tcp:8000
     tcp:8000` y, desde `conductor/`, `flutter run`.
  2. En el celular, ingresar como un conductor y aceptar el permiso de notificaciones. En
     `/admin/` → Api → Tokens de dispositivo, su sesión aparece con push.
  3. Salir al inicio del celular (la app queda en segundo plano). En el panel, asignarle un servicio
     pendiente: el celular suena con "Nuevo servicio asignado". El detalle de la solicitud dice
     "Sin ver" en ese servicio.
  4. Tocar la notificación: se abre la lista con el servicio. Recargar el detalle de la solicitud:
     "Visto por el conductor" muestra la hora.
  5. Reasignar ese servicio a otro conductor: al primero le llega "Servicio reasignado" y el
     servicio desaparece de su lista al tocarla. En `/admin/` → Api → Notificaciones push se ve cada
     aviso con su estado.
  6. Reenvío: `uv run python manage.py enviar_notificaciones_pendientes` muestra "Avisos push: N
     enviados, N por reintentar, N fallidos.". Para ver un reintento: desconectar el PC de internet,
     asignar (el aviso queda pendiente), reconectarlo y correr el comando un minuto después.
     Quitar la variable del `.env` no sirve para esto: sin credenciales el aviso queda fallido, no
     pendiente.

### 1a-08b Personal y grúas (15 de noviembre de 2026)
- Hecho: sección nueva "Personal y grúas" (`/personal/`, solo administrador) registrada en
  `panel/secciones.py`, con tres listas y sus formularios:
  - Conductores: nombre, celular, grúa, PIN sí/no, activo y si puede entrar a la app. "Nuevo
    conductor" pide nombre, celular, PIN (dos veces) y grúa opcional y, en una transacción, crea el
    usuario interno de la app (`conductor-<celular>`, grupo conductor, contraseña inutilizable: no
    entra al panel), la ficha y la asignación a la grúa desde ahora. Por conductor: habilitar para la
    app, cambiar PIN, cambiar de grúa (cierra la vigente y abre la nueva en el mismo instante; si la
    grúa la tiene otro, dice quién), desactivar (con confirmación que dice cuántos servicios activos
    tiene; revoca sus sesiones de la app y con ellas el token de push) y reactivar.
  - Usuarios de oficina: nombre, usuario, contraseña (validadores de Django, mensajes en español) y
    rol (Logística, Facturación o Administrador). Cambiar rol, restablecer contraseña, desactivar y
    reactivar.
  - Grúas: placa, descripción, capacidad (1 o 2) y estado operativo; al editar, también activa.
- Decidido:
  - Sección aparte de "Flota y documentos": aquella responde "¿qué documentos están al día?" y esta
    "¿quién trabaja aquí y con qué grúa?". Así la de documentos no cambia (solo su texto de lista
    vacía, que mandaba al admin y ahora manda aquí). El código va en la app `flota` (la 1a-02 era
    "Flota y usuarios"): `flota/operaciones.py`, `formularios.py`, `views.py`, `urls.py`.
  - Reglas reutilizadas, no reescritas: formato del PIN (`nucleo/ingreso.py`, vía `fijar_pin`),
    celular (`nucleo/identificacion.py`), traslapes (restricciones de la base y `full_clean`),
    revocar sesiones (`api.ingreso.revocar_tokens`). Reglas nuevas en `nucleo/personal.py`: nombre
    del usuario interno del conductor y "nunca cero administradores activos" (cuentan los usuarios
    activos con rol administrador y las cuentas con acceso total), y nadie se desactiva a sí mismo.
    Al quitar un administrador se bloquean las filas de los administradores, para que dos cambios a la
    vez no dejen el panel sin ninguno.
  - Habilitar para la app sirve también para el caso que vivió el dueño: un conductor enlazado a un
    usuario de oficina. Se le crea su propio usuario de conductor y el de oficina no se toca.
    Desactivar o reactivar un conductor solo cambia su usuario si es de conductor.
  - La cuenta con acceso total (la del dueño, `john`) aparece como "Acceso total": desde la pantalla
    no se le cambia el rol ni el estado, y solo ella misma cambia su contraseña (si no, cualquiera con
    rol administrador podría quedarse con ella). Pregunta en `QUESTIONS.md`.
  - `AUTH_PASSWORD_VALIDATORS` no estaba configurado (Django no validaba nada): se agregaron los
    cuatro estándar en `config/settings.py`. No afecta a los usuarios ya creados.
  - Sin HTMX ni CSS nuevo: formularios normales con `parciales/campo.html` y los componentes de
    `arribo.css`. No hay botón de borrar en ninguna pantalla.
  - Sin historial nuevo: la flota no tenía un patrón de historial; las asignaciones conductor–grúa sí
    quedan como historial (se cierran, no se borran). Pregunta en `QUESTIONS.md`.
- Superusuario sin grupos: `tiene_rol` lo deja pasar siempre, así que `john` ve esta sección y todas
  las de administrador (probado en `test_el_superusuario_sin_roles_entra`).
- En la base local: hoy "juan" ya aparece con usuario de conductor y "Puede entrar", y "Flaco" como
  inactivo. No se modificó ningún dato real; el administrador temporal usado para mirar la pantalla en
  el puerto 8770 se borró al terminar.
- Prueba que cambió: `test_las_secciones_son_las_pedidas_en_orden` (`tests/panel/test_navegacion.py`)
  incluye la sección nueva en su lista.
- Verificado: `uv run pytest -q` (1917 pruebas, 83 nuevas), `uv run ruff check .` y
  `manage.py makemigrations --check` sin cambios (la tarea no tiene migraciones). Pruebas nuevas
  contra PostgreSQL en `tests/flota/test_personal_*.py` y `tests/nucleo/test_personal.py`.
- Sin hacer: editar nombre o celular de un conductor (sigue en `/admin/`); historial de personal.
- Preguntas abiertas nuevas: cuatro en `QUESTIONS.md` (grúas que se ofrecen, historial de personal,
  la cuenta con acceso total, editar nombre y celular).
- Cómo probar (5 minutos):
  1. `uv run python manage.py runserver` y entrar como `john`: en la barra aparece "Personal y grúas".
  2. "Nueva grúa": placa "prueba-1", capacidad 1. Se guarda como PRUEBA1.
  3. "Nuevo conductor": nombre "Prueba", un celular que no sea de nadie, PIN 123456 dos veces y la
     grúa PRUEBA1. Probar antes un PIN de 4 dígitos y el celular de juan: salen los errores en rojo.
  4. En la app (o con `curl -X POST http://127.0.0.1:8000/api/v1/ingresar/ -H "Content-Type:
     application/json" -d "{\"celular\":\"<celular>\",\"pin\":\"123456\",\"dispositivo_id\":\"prueba\"}"`),
     el conductor entra.
  5. En su ficha, "Desactivar conductor": la confirmación dice cuántos servicios activos tiene.
     Confirmar y volver a ingresar: la app responde que no tiene acceso. "Reactivar" se lo devuelve.
  6. "Nuevo usuario" con contraseña "12345678": sale "La contraseña está completamente numérica" (o
     similar). En la ficha de `john` no hay botones de rol ni de desactivar.
  Para no dejar datos de prueba: desactivar al conductor y la grúa al terminar (nada se borra).

### 1a-08c Simplificar el panel (15 de noviembre de 2026)

Tras la primera prueba del dueño: el panel era difícil de operar (no había cómo volver a una solicitud)
y redundante. Las reglas de negocio no cambiaron; esto es navegación y pantallas.

- **Lista de solicitudes** (sección Solicitudes, logística y administrador): número, fecha, cliente,
  tipo, vehículos (placa o VIN), conductores, cuándo y estado. Filtros Activas (por defecto: borrador,
  abierta, en curso), Por asignar, Borradores, Programadas, Terminadas y Todas. Búsqueda por teléfono o
  nombre del cliente (quien pide o quien paga), placa o VIN (como se digiten, también una parte),
  número de solicitud y referencia externa; una búsqueda desde el inicio busca en todas. 25 por página.
  El estado se deriva con `nucleo.estados.estado_solicitud` sobre los servicios precargados; el filtro
  en la base usa la misma definición y una prueba lo compara con el núcleo en todas las combinaciones
  de hasta dos servicios. Consultas fijas (cota en la prueba): `solicitudes/consultas.py`.
- **Inicio útil** (`/` y la sección Tablero, `panel.views.tablero`): botón "Nueva solicitud", la
  búsqueda y, en orden, servicios por asignar (inmediatos primero, luego programados por hora, con
  botón "Asignar" que lleva a la solicitud), borradores con lo que les falta, alertas abiertas (las que
  ya crea la sincronización, con enlace a su solicitud) y lo que está en curso por conductor. Adelanto
  mínimo de la 1a-18: sin comando ni umbrales (anotado en la tarea). Facturación sigue con su inicio.
- **Una sola sección "Flota y personal"** (solo administrador): conductores (celular, grúa, resumen de
  documentos, app, activo), grúas (capacidad, estado, documentos, activa), usuarios de oficina y el
  enlace a tipos de documento. Los documentos de cada uno se ven y registran en su página (las mismas
  pantallas de `documentos`). Todo vive bajo `/flota/`; `/personal/...` redirige. Una grúa nueva lleva
  a su página para registrar sus documentos.
- **Nueva solicitud con un solo "Guardar"**: si falta algo, queda en borrador y dice qué falta. En el
  detalle de un borrador, arriba: "Completar borrador" si le falta algo, o "Abrir solicitud" si ya
  tiene todo (`registro.abrir_borrador`, con la fila bloqueada).
- **Menú e inicio sin "Aún no disponible"**: Cobros y Panel del dueño no aparecen hasta tener
  pantalla; su URL directa sigue protegida por rol. El 403 ofrece "Volver al inicio" a cualquier rol
  del panel.
- **Corregir nombre y celular del conductor** en su página (celular normalizado, único; si choca:
  "Ya hay un conductor con el celular … : …"). El PIN no cambia; entra con el celular nuevo.
- Decisiones y supuestos en `QUESTIONS.md` (sesiones al cambiar celular; qué es terminada y
  programada; gravedad del resumen de documentos). CSS nuevo: ninguno. Sin migraciones.
- Verificado: `uv run pytest -q` (1979 pruebas, 62 más que en 1a-08b), `uv run ruff check .` y
  `makemigrations --check` sin cambios. Pruebas que cambiaron por la nueva conducta (sin quitar
  cobertura): navegación y acceso del panel, `/personal/` → `/flota/`, la matriz de documentos pasó a
  resumen en la lista y detalle en cada página, y `accion=borrador` (ahora un borrador se crea dejando
  un obligatorio vacío). La cota de consultas de la lista de Flota subió de 12 a 16 (cuatro consultas
  fijas del resumen de documentos) y ahora también comprueba que no crece con más conductores.
- `solicitudes` sigue sin importar `alertas` (prueba de 1a-10): por eso el tablero vive en `panel`.
- Recorrido en el navegador contra la base aparte `arribo_recorrido` (puerto 8772): entrar, inicio,
  crear grúa (redirige a su página con SOAT y Tecnomecánica en "Falta") y conductor, probar un celular
  repetido (mensaje claro), registrar una solicitud con un solo Guardar, ir a Configuración, volver
  por el inicio (aparece en Por asignar) y buscarla por "rec 321", por teléfono y por nombre, asignarla,
  verla en "En curso por conductor", registrar una licencia vencida y ver al conductor bloqueado en su
  página, en la lista y en la asignación (su servicio en curso sigue). También: un borrador incompleto
  sale en el inicio con "Falta el destino"; uno completo muestra "Abrir solicitud" y se abre.
- Cómo probar (5 minutos, sin el admin):
  1. `uv run python manage.py runserver` y entrar: el inicio muestra Por asignar, Borradores, Alertas
     y En curso; el menú ya no tiene secciones "Aún no disponible".
  2. "Nueva solicitud": solo hay un botón Guardar. Registre una sin destino: queda en borrador y en el
     inicio aparece con "Falta el destino". Ábrala, "Completar borrador", ponga el destino y Guardar.
  3. Vaya a otra pantalla y vuelva con "Arribo": la solicitud está en "Por asignar". Escriba su placa
     en "Buscar solicitud" y ábrala desde la lista.
  4. Asígnela: en el inicio aparece bajo el conductor, en "En curso por conductor".
  5. "Flota y personal": pulse el conductor, corrija su nombre; registre su licencia con fecha pasada:
     su página dice "No recibe servicios nuevos" y la lista lo muestra "Vencido". Renueve la licencia
     (fecha futura) para dejarlo como estaba.

### 1a-08d Restablecer datos de prueba (15 de noviembre de 2026)

Pedido del dueño: "un botón para restablecer de fábrica la app ya que los datos que pongo o creo son
de prueba".

- En **Configuración**, al final, "Restablecer datos de prueba…" (solo administrador). La pantalla
  muestra cuánto se borra y pide escribir BORRAR. Borra solicitudes, servicios, eventos, fotos,
  clientes, cobros, alertas, grúas, conductores, documentos registrados (y sus archivos), sesiones de
  la app y notificaciones, y los usuarios salvo quien restablece y los superusuarios. Conserva la
  configuración con su historial y los tipos de documento. Los números vuelven a empezar en 1.
  Cierra las sesiones del panel de los demás.
- Es la única excepción a "nada se borra": `configuracion/restablecer.py` usa TRUNCATE (los eventos y
  los historiales no se dejan borrar por los modelos, a propósito). Quien cambió la configuración no
  se puede borrar (su historial se conserva) y se desactiva.
- Interruptor `ARRIBO_PERMITIR_RESTABLECER`: vacío = activo con `ARRIBO_DEBUG=1` y **apagado en
  producción**; con él apagado no hay botón y la URL da 404. Documentado en `.env.example`.
- Pruebas: `tests/configuracion/test_restablecer.py` (15). Recorrido en el navegador contra la base
  aparte `arribo_recorrido`: Configuración → Restablecer → BORRAR → inicio vacío con el aviso; Flota
  vacía y el usuario administrador intacto.
- El admin de Django sigue en `/admin/` (solo superusuarios); el panel nunca lo enlazó.
- Cómo probar (2 minutos): entrar con su superusuario, Configuración → "Restablecer datos de
  prueba…", leer los conteos, escribir BORRAR y "Borrar todo": el inicio queda vacío. Luego crear de
  nuevo grúa y conductor en Flota y personal; en el celular, volver a ingresar.

### 1a-08e Tablero visual, admin de consulta y grúa del conductor (15 de noviembre de 2026)

Pedido del dueño: "el panel principal de quien realiza las asignaciones debe ser más dinámico, paneles
llamativos", "deja el admin solo de consulta", y al darle grúa a un conductor creado sin ella "no
tiene botón de actualizar información".

- **Tablero** (`/` de logística y administrador; datos en `panel/tablero.py`): cinco cifras de colores
  arriba (por asignar, con cuántos esperan de más; en curso; entregados hoy; conductores libres;
  alertas). Por asignar en tarjetas con la espera ("Inmediato · espera 27 min") y en rojo si pasó el
  umbral de la configuración (`alerta_sin_asignar_minutos`; un programado, si faltan menos de
  `alerta_programado_sin_asignar_horas`). Cada tarjeta trae la lista de conductores (los bloqueados
  deshabilitados, con su motivo) y "Asignar": usa la misma vista y las mismas reglas que la solicitud y
  vuelve al tablero. Alertas en tarjetas con "Marcar resuelta" (`/alertas/<id>/resolver/`, logística y
  administrador; adelanto de la 1a-18). A la derecha, una tarjeta por conductor activo: libre, en
  servicio, grúa llena o bloqueado (con el motivo), su grúa con barra de ocupación y su ronda con el
  estado de cada vehículo. Se actualiza solo cada minuto con HTMX, salvo mientras se elige un conductor.
  CSS nuevo en `arribo.css` (sección "Tablero de logística"): tarjetas, cifras, etiquetas y barra; no
  había componentes de tablero. La hoja se pide con `?v=2` para que el navegador baje la nueva.
- **Admin de Django solo de consulta** (`panel/admin_consulta.py`, aplicado en `PanelConfig.ready`):
  solo entra un superusuario; nada se agrega, edita ni borra; sin acciones; sin Usuarios ni Grupos.
  Se quitaron las pruebas que escribían por el admin (crear clientes, vehículos y solicitudes, fijar
  PIN, revocar sesiones, resolver alertas por acción): esas reglas siguen probadas en sus modelos y en
  el panel (`test_clientes_y_telefonos`, `test_tarifas`, `test_asignaciones`, `test_vehiculos`,
  `test_registro_ii`, `test_pin`, `test_personal_conductores`). Las que solo abren listas ahora
  comprueban que no se puede agregar. Prueba nueva de que `manage.py check` pasa: el autocompletar de
  usuario en el admin del conductor impedía arrancar el servidor y las pruebas no lo veían.
- **Página del conductor**: nombre, celular y grúa en un solo formulario con "Guardar cambios" (arriba,
  antes de los documentos); si no hay grúas, enlace "Crear una grúa". Si la grúa falla, no cambia nada.
  Se quitó la ruta aparte `/flota/conductores/<id>/grua/`; sus pruebas pasaron al formulario único.
- Recorrido en el navegador (base aparte): crear conductor sin grúa, crear grúa, darle la grúa desde su
  página; tablero con 3 por asignar (uno urgente en rojo), asignar desde la tarjeta, resolver la alerta,
  recarga automática sin duplicar, celular (375 px) sin desplazamiento horizontal; el admin rechaza a
  un administrador que no es superusuario.
- **"Guardar" ya no deja borradores en silencio** (el dueño registró una solicitud sin destino, quedó
  en borrador y no encontraba cómo asignarla): si falta algo, no guarda, marca el campo ("Falta el
  destino para poder asignarla.") y ofrece "Guardar como borrador" a propósito
  (`registro.faltantes_de_datos`, la misma regla del núcleo leída del formulario). En el detalle de un
  borrador, la sección "Asignar conductores" dice por qué todavía no se puede y lleva a completarlo.
  Las pruebas que guardaban borradores con "Guardar" ahora usan el botón de borrador (el ayudante
  `formulario()` lo pone por defecto); cuatro pruebas nuevas cubren "Guardar" con faltantes.
- **Celular por USB de raíz**: `arrancar.ps1` en la raíz arranca el panel (o usa el que ya corre) y
  revisa cada 3 segundos el túnel `adb reverse`, recreándolo si el celular se desconectó, se bloqueó o
  adb se reinició (causa de "No hay conexión con el servidor"). Probado: se quitó el túnel a mano y el
  script lo recreó en menos de 7 segundos; el celular volvió a llegar al panel. En CLAUDE.md y en
  `conductor/README.md`.
- Cómo probar (5 minutos): entrar; el inicio muestra las cifras y las tarjetas. Asignar un servicio
  desde su tarjeta. Nueva solicitud sin destino y "Guardar": no se guarda y marca el destino. En Flota y personal, abrir un conductor sin grúa, elegirla y "Guardar cambios". Abrir
  /admin/ con el superusuario: todo se ve, nada se puede cambiar.

### 1a-08f · Ida y regreso visibles (corrección)

- El dueño reportó "se me duplicó un servicio": era un evento con regreso. La regla escrita crea por
  cada vehículo un servicio de regreso (destino a origen, en la fecha de regreso); los datos estaban
  bien, pero el formulario de asignar, la ronda y la tarjeta del conductor en el tablero mostraban la
  misma placa dos veces sin decir cuál era el regreso. Ahora dicen "ida" / "regreso" (y en la tabla de
  servicios, la fecha del regreso). La app del conductor ya lo marcaba "(regreso)".
- Prueba nueva: `test_detalle_y_tablero_distinguen_el_regreso_de_la_ida`.
- Cómo probar: abrir la solicitud 2; el N.º 3 dice "Regreso del N.º 2" con su fecha; en el inicio, la
  tarjeta de Flaco muestra "ASD345" con la etiqueta de regreso.

### 1a-08g · Panel con aspecto profesional y regreso en color

- Pedido del dueño: "los servicios de regreso deben ir marcados de otro color" y "que el panel se vea
  más profesional, más premium".
- **Regreso en color**: verde azulado propio (`--regreso`), distinto de todos los estados. Etiqueta
  `etiqueta--regreso` con flecha ↩ en la tabla de servicios, el formulario de asignar, la ronda, la
  tarjeta "Por asignar" (con fondo teñido, `tarjeta--regreso`) y la ronda de cada conductor en el
  tablero; las filas de regreso llevan una franja de ese color. La ida va en una etiqueta neutra.
- **Corrección encontrada al hacerlo**: en el tablero, un regreso por asignar mostraba la hora y el
  trayecto de la ida y se ponía "urgente" cuando se acercaba la ida (aunque el regreso fuera días
  después). Ahora usa `nucleo.trayecto` (`hora_programada`, `puntos_del_servicio`) para la hora, el
  trayecto y la urgencia, y `consultas.por_asignar` ordena por la hora propia de cada servicio.
- **Aspecto**: misma hoja `arribo.css` con los mismos nombres de clase (ninguna pantalla cambió de
  estructura salvo el buscador y los filtros). Barra lateral oscura con logotipo, superficies blancas
  con sombra suave, títulos más marcados, encabezados de tabla en versalitas, etiquetas de estado tipo
  píldora con punto, cifras del tablero con franja de color arriba, buscador en una fila con lupa,
  filtros de la lista como pestañas. CSS nuevo justificado: `.cabecera-pagina`, `.pestanas`,
  `.buscador`, `.marca-logo`, `.etiqueta--regreso/--ida`, `.fila--regreso`, `.tarjeta--regreso`.
  Versión de la hoja a `?v=3` para que el navegador la recargue.
- Revisado con capturas a 1440 px (tablero, detalle, lista, nueva, flota, ingreso) y a 375 px sin
  desplazamiento horizontal.
- Pruebas nuevas: `test_el_regreso_por_asignar_usa_su_propia_hora_y_va_del_destino_al_origen`;
  `test_detalle_y_tablero_distinguen_el_regreso_de_la_ida` actualizada a la etiqueta de color.
- Cómo probar (3 minutos): recargar con Ctrl+F5. Ver el tablero y la solicitud 2: el N.º 3 aparece
  con la etiqueta verde azulada "↩ Regreso del N.º 2". En Solicitudes, los filtros son pestañas.

### 1a-08h · El regreso espera a su ida

- Pregunta del dueño: "¿por qué dejó llenar primero el regreso que la ida?". No había regla escrita;
  el dueño decidió bloquearlo: no se recoge en el destino un vehículo que todavía no ha llegado allá.
- **Regla** (`nucleo/trayecto.py`, `regreso_bloqueado`): un regreso no pasa a En camino, Recogido ni
  Entregado hasta que su ida esté entregada; la Novedad sí se puede reportar. Casos en
  `docs/casos-reglas.json` (`regreso`), recorridos por las pruebas del servidor y de la app.
- **Servidor**: si llega igual (app vieja o sin actualizar), no se rechaza: se guarda como conflicto
  `ida_sin_entregar` (motivo nuevo, migración `0007` de la restricción) y abre alerta a logística.
  Si la ida se entrega y el regreso arranca en el mismo lote sin señal, se aplican en orden.
- **Contrato 1.3** (`docs/api-conductor.md`): cada servicio trae `regreso_de` y `espera_ida`.
- **App**: etiqueta "Espera la ida" con candado en la lista y el detalle; en lugar de "Marcar En
  camino" dice "Disponible cuando se entregue la ida."; la cola no guarda ese toque. Al marcar
  Entregado en la ida (aunque no haya señal) el regreso se desbloquea de inmediato; cuando el
  servidor confirma la ida entregada, también. Migración local 5 (dos columnas y olvidar el ETag
  para bajar la lista completa).
- **Panel**: "Espera la ida" junto al regreso en el detalle, en la tarjeta "Por asignar" y en la
  ronda del conductor. Se puede asignar con anticipación, como antes.
- Pendiente en `QUESTIONS.md`: si la ida se cancela, por ahora logística cancela el regreso a mano.
- No probado en el celular real: el celular no estaba conectado. Lo cubren las pruebas de la app
  (cola, pantalla del servicio y casos compartidos).
- Cómo probar (5 minutos): instalar la app nueva (`flutter run` con el celular conectado). Crear un
  evento con regreso y asignar ida y regreso al mismo conductor. En el celular, el regreso dice
  "Espera la ida" y no ofrece En camino; marcar la ida En camino, Recogido y Entregado; el regreso
  ya ofrece En camino. En el panel, la etiqueta "Espera la ida" desaparece al entregarse la ida.

### 1a-08i · Fotos de evidencia en el panel

- Pedido del dueño: "En los servicios completados se deben ver las fotos para hacerle auditoría. Se
  guardan arrumadas en una carpeta, no se sabe a qué servicio pertenece ese vehículo". La base sí
  sabía de qué servicio era cada foto; lo que faltaba era una pantalla para verlas.
- **Panel**: sección "Fotos" en el detalle de la solicitud, agrupada por servicio (N.º, vehículo,
  ida o regreso, estado). Cada foto dice si es de recogida o de entrega, la hora en que el conductor
  marcó el paso en la app, quién la tomó y quién entregó o recibió el vehículo. Al tocarla se abre
  completa en otra pestaña.
- **Auditoría** (`nucleo.evidencia.foto_esperada`): si el conductor marcó Recogido o Entregado en la
  app y no llegó ninguna foto de ese paso, sale en rojo "Sin foto de entrega/recogida" (puede estar
  subiendo todavía). Lo que se cambia desde el panel no pide foto. Una foto que llega antes que su
  toque no cuenta como faltante.
- **Seguridad**: las fotos no tienen dirección pública. Solo se ven con sesión de logística o
  administrador (los mismos roles del detalle) y solo desde la solicitud a la que pertenecen.
- **Carpeta**: las fotos nuevas se guardan en
  `media/evidencias/solicitud-<N.º>/servicio-<N.º>/<recogida|entrega>-<id>.jpg`, con los mismos
  números del panel. Las fotos que ya estaban (`media/evidencias/<servicio>/<id>.jpg`) no se movieron;
  el panel las muestra igual.
- Recorrido hecho: un celular simulado por HTTP marcó la ida y el regreso de un evento y subió 4 fotos
  de verdad; la entrega del regreso sin foto quedó señalada. Revisado a ancho de escritorio y de
  celular.
- Cómo probar (5 minutos): abrir una solicitud cuyo servicio ya se entregó desde la app. Bajar hasta
  "Fotos": se ven las de recogida y entrega con hora, conductor y quién recibió; tocar una para verla
  completa. Cerrar sesión y pegar la dirección de la foto: pide ingresar. Hacer un servicio nuevo
  desde el celular y mirar `backend/media/evidencias/`: queda en `solicitud-N/servicio-N/`.

### 1a-16b · Cobro en el panel

- **Sección Cobros** (facturación y administrador; ya aparece en el menú). Pestañas con su cuenta:
  Pendientes (sin valor y por facturar, la más antigua primero), Sin valor, Por facturar, Facturadas
  sin pagar, Pagadas, Todas y Cancelados. Búsqueda por pagador, placa o VIN, N.º de servicio o de
  solicitud y número de factura.
- **Página de cada línea**: pagador, valor, factura y el servicio (tipo, ida o regreso, vehículo,
  trayecto, conductor y grúa, hora de entrega). Debajo, solo lo que se puede hacer en su estado:
  digitar o ajustar el valor, facturar con número, marcar pagada, o anular la factura con motivo.
  El historial muestra quién, cuándo, el valor anterior y el nuevo, la factura y el motivo.
- **Tarifa propuesta**: si la línea está sin valor y el pagador tiene tarifa vigente para ese tipo
  de servicio, la página la muestra y la deja escrita en el campo; se guarda solo al tocar "Guardar
  valor". (Si la tarifa ya existía al entregar, la línea nace por facturar con ese valor, desde 1a-16a.)
- **Valores escritos a mano** (`nucleo.cobro.leer_pesos` y `formato_pesos`): acepta "180000",
  "180.000", "$ 180.000" y "180.000,50"; muestra "$ 180.000". Siempre `Decimal`.
- **Quién ve valores** (Configuración, por defecto administrador y facturación): a quien no los ve
  no se le muestran en ninguna pantalla, no se le propone la tarifa y no puede cambiar el valor (403).
  Sí puede facturar, marcar pagada y anular, que no muestran ni cambian el valor. *Decidido así
  porque no estaba escrito; si prefiere que tampoco facture, es un cambio pequeño.*
- **Detalle de la solicitud**: columna "Cobro" con el estado de cobro de cada servicio; el valor solo
  si el rol lo ve; y el enlace a la línea solo si el rol entra a Cobros. Con la configuración por
  defecto, logística ve "Por facturar" pero no el valor.
- **Cancelados**: los servicios cancelados después de asignarse (la grúa pudo salir) aparecen en su
  pestaña con el motivo de la cancelación y el botón "Marcar cobrable", que crea su línea. Los que
  nunca tuvieron conductor no aparecen.
- Recorrido hecho con las vistas reales en la base del recorrido: tarifa propuesta, digitar, valor
  mal escrito rechazado, ajustar, facturar, cambiar el valor ya facturado (rechazado), anular con
  motivo, pagar; logística ve el estado sin el valor y no entra a Cobros.
- Sin hacer (son de la 1a-17): relación de cobro por pagador y fechas, exportar a Excel o CSV.
  Dos pagadores por servicio es de la fase 1b.
- Cómo probar (5 minutos): entrar como administrador o con un usuario de facturación, abrir Cobros.
  Abrir una línea sin valor, escribir 180.000 y guardar; facturar con un número; marcar pagada. En
  otra, facturar y luego anular con motivo: vuelve a por facturar y el historial lo dice. Entrar con
  un usuario de logística y abrir la solicitud: la columna Cobro dice el estado, sin valor.

### 1a-17 · Relación de cobro y exportación

- **Relaciones de cobro** (botón en Cobros, para quien ve valores): se elige pagador y fechas; la
  pantalla muestra qué líneas por facturar entran, con número de caso, fecha, vehículo y valor, el
  total y las que quedan por fuera por no tener valor. "Armar la relación" la guarda.
- **Reglas** (`nucleo/relacion.py`): entra la línea por facturar del pagador cuya fecha de servicio
  está en el rango (extremos incluidos). Armada → Facturada (número obligatorio) → Pagada; una
  armada se puede descartar con motivo, no se borra. Una relación sin líneas no se arma.
- **Reserva**: mientras la relación está armada, sus líneas no entran en otra ni se facturan
  sueltas (la página de la línea lleva a la relación). PostgreSQL impide que una línea esté reservada
  en dos relaciones. Al facturar o descartar, la línea queda libre: si después le anulan la
  factura, puede entrar en otra relación.
- **Facturar la relación** factura cada línea con el mismo número y su historial (quién, cuándo).
  **Marcarla pagada** marca pagadas las líneas que siguen con esa factura; si a alguna le anularon
  la factura, la deja y lo avisa.
- **Fecha del servicio**: la de Entregado (hora del celular si la mandó) en hora de Colombia. Un
  servicio entregado a las 10 p. m. del 31 de octubre es de octubre aunque en UTC ya sea noviembre.
- **Exportación** (`nucleo/exportacion.py`): una interfaz `Exportador` y una implementación,
  `CsvGenerico`, elegida por `formato_exportacion` de la configuración. UTF-8 con BOM, punto y
  coma, valores sin miles y con coma decimal (Excel los suma), fila de total. Un texto que empiece
  con `=`, `+`, `-` o `@` va con apóstrofo para que Excel no lo ejecute como fórmula.
- Supuestos anotados en `QUESTIONS.md` (fecha que cuenta, quién arma, columnas del archivo).
- Cómo probar (5 minutos): entrar como administrador, abrir Cobros → Relaciones de cobro. Elegir
  un pagador con líneas por facturar y las fechas; revisar la lista y el total; Armar. Descargar y
  abrir el archivo en Excel: una fila por servicio, tildes bien y el total sumado. Abrir una de sus
  líneas: dice que está en la relación y no deja facturarla sola. Volver, facturar la relación con
  un número; abrir la línea: Facturada con ese número. Marcar la relación pagada.

### 1a-18 · Alertas y tablero

- **Alertas por umbral** (reglas en `nucleo/alertas.py`, umbrales de Configuración):
  - Servicio sin asignar: inmediato, desde que pasan los minutos configurados (10) después de
    registrada la solicitud; programado, desde las horas configuradas (2) antes de su hora (en un
    regreso, la fecha de regreso). Un borrador no alerta.
  - Recogido sin Entregado: desde las horas configuradas (4) después de marcar Recogido.
  - Documento por vencer o vencido: según los días de anticipación de cada tipo, de grúas y
    conductores activos.
  - Conflicto de sincronización: ya la abría la sincronización desde la 1a-10; no cambia.
- **Se cierran solas** cuando se atiende lo que las abrió (asignar, entregar, renovar el
  documento); el tablero dice "Se cierra sola cuando se atiende" y no deja marcarlas resueltas a
  mano. Una alerta no se repite mientras siga abierta (lo garantiza la base).
- **Comando** `manage.py evaluar_alertas`: abre y cierra las alertas y dice cuántas. En producción
  se programa cada minuto (1a-21). El tablero también las evalúa al cargarse y se recarga solo cada
  minuto, así que en local no hace falta correr nada.
- **Tablero**: cada alerta lleva a su solicitud; la de documento, al documento (solo el
  administrador, que es quien entra a Flota). El tablero hace 9 consultas fijas más por la
  evaluación (siguen sin crecer con las filas; la prueba de la cota se subió de 20 a 29).
- **Búsqueda de solicitudes**: además de lo que ya buscaba (cliente, teléfono, placa, VIN, número,
  referencia), ahora busca por conductor, placa de la grúa, número de factura exacto y fecha
  ("18/11/2026", "18/11" o "2026-11-18": registrada, programada o de regreso, en hora de Colombia).
- Supuestos en `QUESTIONS.md` (se cierran solas, desde cuándo cuenta, vencido incluido, qué fecha).
- Sin hacer (fase 1b): las alertas de sin "En camino", sin facturar y sin pagar; avisos por correo
  y el horario nocturno.
- Cómo probar (5 minutos): entrar como logística. Registrar una solicitud inmediata y no
  asignarla. En Configuración (administrador) bajar "sin asignar" a 1 minuto; volver al inicio
  y esperar un minuto (o recargar): aparece "Servicio sin asignar" con el enlace a la solicitud.
  Asignarla: al recargar, la alerta ya no está. En Flota, registrar a una grúa un SOAT que venza
  en 10 días: en el inicio aparece "Documento por vencer o vencido". Buscar arriba por el nombre
  de un conductor, la placa de una grúa o una fecha como 18/11/2026.

### 1a-19 · Panel del dueño mínimo

- **Sección Panel del dueño** (solo administrador; ya sale en el menú). Por defecto muestra hoy;
  se puede elegir otro día o un periodo.
- **Cifras arriba**: servicios, no concretadas, cuánto hay por cobrar hoy (y cuántas líneas sin
  valor) y documentos por atender.
- **Servicios por estado**: todos los estados, también en cero, con el total. Un servicio es del
  día para el que se programó (un regreso, el de su fecha de regreso) o, si es inmediato, del día
  en que se registró, en hora de Colombia. Los borradores no cuentan.
- **No concretadas por motivo**: todos los motivos con su cuenta, por el día de la llamada.
- **Por cobrar por pagador**: sin valor, por facturar y facturado sin pagar de cada pagador, del
  que más debe al que menos, con la fila de total. Es lo pendiente hoy, sin importar el periodo.
- **Documentos por vencer o vencidos**, el más urgente primero, con enlace a cada documento.
- Los totales salen de `nucleo/resumen.py` (pruebas puras) y se comprueban contra la base con
  datos conocidos en `tests/panel/test_dueno.py`.
- Con esto todas las secciones tienen pantalla; la vista "Aún no disponible" sigue para la próxima
  que se registre sin pantalla (su prueba usa una sección inventada).
- Supuestos en `QUESTIONS.md` (qué es "del día", periodo de no concretadas y de cobros).
- Sin hacer (fase 1b): el panel del dueño completo (tendencias, comparaciones, por conductor).
- Cómo probar (5 minutos): entrar como administrador y abrir Panel del dueño. Comparar con lo que
  sabe del día: cuántos servicios entregados y en curso, cuántas llamadas no concretadas y por qué.
  Comparar el total por cobrar de un pagador con la sección Cobros. Elegir el periodo del mes y
  tocar Ver.

### 1a-20 · Datos ficticios

- **`manage.py demo_cargar`** (desde `backend/`) carga una operación de muestra:
  - Flota: 3 grúas (DEMO01 a DEMO03) y 3 conductores (Carlos, Diana y Esteban), cada uno con su
    grúa y su usuario para la app.
  - Clientes: un concesionario con tarifa de traslado ($ 180.000), contacto y teléfono; una
    aseguradora; y un particular.
  - Servicios en los siete estados. Hay un evento de concesionario con regreso, un borrador y una
    llamada no concretada.
  - Líneas de cobro en cuatro estados: sin valor, por facturar, facturado (DEMO-0001) y pagado
    (DEMO-0002).
  - Documentos: un SOAT por vencer, una tecnomecánica vencida (Diana queda bloqueada) y los demás
    vigentes.
  - Alertas activas: un servicio sin asignar, uno Recogido sin Entregado, un conflicto de
    sincronización y dos de documentos.
  - Los nombres de clientes y conductores terminan en «(demo)», y las placas de vehículos
    empiezan por DMO.
- **Se carga con las operaciones reales.** Asignar, los toques del conductor en la app, facturar,
  pagar y registrar documentos se hacen como en la operación, con horas en el pasado relativas a
  los umbrales de la configuración. Quedan eventos, historial, líneas y alertas como en el uso
  real.
- **No se carga dos veces.** Tampoco se carga si una placa, un celular o un teléfono de la demo
  ya existe en datos reales; en ese caso no carga nada y dice cuál choca.
- **`manage.py demo_borrar`** pide escribir «si» antes de borrar (o se corre con `--noinput`).
  - Borra lo marcado como demo y lo que cuelga de ello, en una transacción. Eso incluye eventos,
    historial de cobro, alertas, asignaciones y el usuario de cada conductor de demo.
  - Es la única excepción a "nada se borra": los eventos y el historial de la demo nunca fueron
    reales.
  - Si un dato real usa algo de la demo, no borra nada y dice qué lo impide. Ejemplos: una
    solicitud real con un cliente de demo, o un servicio real asignado a un conductor de demo.
- **Verificación.**
  - `tests/panel/test_demo.py` (12 pruebas) toma una foto de todas las filas y valores de las
    tablas, carga y borra la demo, y comprueba que la base queda idéntica.
  - En la base del recorrido (234 filas reales) se cargó y se borró la demo, y la base quedó
    idéntica.
  - El código está en `backend/panel/demo.py`.
- Supuestos en `QUESTIONS.md`: quién figura en lo que hace la demo, y el PIN de sus conductores.
- **Cómo probar (5 minutos).** Hacerlo en una copia de la base o antes de cargar datos reales.
  1. Correr `uv run python manage.py demo_cargar`.
  2. Abrir el tablero: hay pendientes, conductores con servicios, Diana bloqueada por documento
     vencido y alertas.
  3. Abrir Panel del dueño y Cobros: aparecen los clientes «(demo)».
  4. Correr `uv run python manage.py demo_borrar` y escribir «si». El tablero vuelve a como estaba.
  5. Para probar la app con un conductor de demo, ponerle un PIN desde Flota y personal.

### 1a-21 · Despliegue y APK (preparado; falta el servidor del dueño)

- **Servidor con Docker Compose** (`despliegue/`):
  - Caddy pone el HTTPS (certificado automático, http redirige a https) y entrega los estáticos.
  - `web`: Django con gunicorn; al arrancar aplica las migraciones y junta los estáticos.
  - `tareas`: corre cada minuto `evaluar_alertas` y `enviar_notificaciones_pendientes`.
  - `db`: PostgreSQL 18.
  - `respaldo`: copia diaria de la base en el servidor; se guardan 14.
  - Las fotos y documentos quedan en un volumen que sobrevive a los despliegues.
  - La cuenta de servicio de Firebase se monta desde una carpeta del servidor, fuera del
    repositorio y de la imagen.
- **Desplegar** es `./desplegar.sh` en el VPS: trae `main`, reconstruye, levanta y termina
  comprobando `https://DOMINIO/salud/`. La guía paso a paso (VPS, dominio, Docker, `.env`,
  administrador, APK) está en `docs/despliegue.md`.
- **Producción en `settings.py`** (con `ARRIBO_DEBUG=0`):
  - Cookies solo por HTTPS, HSTS de un día y orígenes de formularios desde el dominio.
  - No arranca sin dominio ni clave secreta.
  - Registro a la consola.
  - Carpetas de fotos y estáticos configurables.
  - `manage.py check --deploy` pasa sin advertencias.
  - Se silenciaron tres avisos con su motivo: HSTS sin subdominios ni precarga, y la redirección a
    https, que hace Caddy.
- **Dependencia nueva: `gunicorn`.** Es el servidor de aplicaciones de Python estándar y pequeño,
  sin dependencias propias. `runserver` no sirve para producción.
- **APK firmado:**
  - `conductor/crear-llave.ps1` crea la llave una sola vez. Deja el `.jks` en `Documentos\arribo`
    y escribe `android/key.properties`; ninguno de los dos se sube.
  - `conductor/compilar-apk.ps1 -Servidor https://DOMINIO` exige HTTPS, la llave y el
    `google-services.json`, y comprueba que el servidor responda antes de compilar.
  - Gradle firma con esa llave si existe; si no, con la de depuración, que sirve para pruebas.
- **Pruebas:** `tests/test_despliegue.py` (21) comprueba:
  - que `check --deploy` pasa y que los ajustes de producción quedan como se espera;
  - que producción no arranca sin dominio o sin clave;
  - que los scripts llaman comandos que existen;
  - que `.env`, llaves, `google-services.json` y respaldos quedan fuera del repositorio, y `.env`
    fuera de la imagen;
  - que los scripts del servidor van con fin de línea Unix.

  Docker no corre en este PC (regla del proyecto), así que la imagen no se construyó aquí. El
  primer `./desplegar.sh` en el VPS es su prueba real.
- **Sin hacer:** el despliegue real y la prueba de la tarea (`/salud/` en el dominio y el APK
  instalado iniciando sesión). Para eso el dueño necesita contratar el VPS y el dominio
  (`docs/despliegue.md`, pasos 1 a 5).
- **Cómo probar (cuando haya VPS):**
  1. Seguir `docs/despliegue.md`.
  2. Abrir `https://DOMINIO/salud/`.
  3. Compilar el APK con `compilar-apk.ps1`, instalarlo e ingresar con un conductor.

### Corrección (21/11/2026) · "No hay conexión con el servidor" en el celular, de raíz

- **Causa.** En desarrollo el celular llega al PC por el túnel USB `adb reverse`. Solo lo creaba y
  mantenía `arrancar.ps1`: si el panel se arrancaba con `manage.py runserver` a secas, o si el túnel
  se perdía (cable, reinicio del celular o de adb) sin ese script abierto, la app quedaba sin
  servidor aunque el panel estuviera corriendo. Eso fue lo que pasó esta vez.
- **Solución.** El propio `runserver` (solo en desarrollo) vigila el túnel cada 3 segundos y lo crea
  o recrea si falta (`backend/panel/tunel_usb.py`, arrancado desde `PanelConfig.ready`). Ya no
  importa cómo se arranque el panel. `arrancar.ps1` queda solo para arrancarlo.
- **Prueba sin señal.** Como el túnel vuelve solo, quitarlo a mano ya no simula la falta de señal.
  Para eso están `manage.py sin_senal` (lo quita y lo deja apagado) y `manage.py con_senal`. Se
  actualizaron `docs/prueba-sin-senal.md` y `conductor/README.md`.
- **Verificado con el Motorola conectado.**
  - El túnel apareció solo cuando el servidor del dueño recargó con el cambio.
  - Se quitó a mano y volvió a los 2 segundos.
  - Se reinició adb (`kill-server`) y volvió solo.
  - En cada caso, desde el celular `http://127.0.0.1:8000/salud/` respondió `ok`.
  - Con `sin_senal` el celular no llega al servidor y el túnel no vuelve; con `con_senal` llega de
    nuevo.
  - 17 pruebas nuevas en `tests/panel/test_tunel_usb.py`, con un adb falso.
- **En producción** no hay túnel: la app apunta al dominio con HTTPS (`docs/despliegue.md`).
- **Cómo probar (2 minutos).**
  1. Arrancar el panel como sea y conectar el celular: la consola dice "Celular conectado".
  2. Desconectar y volver a conectar el cable: la consola dice "se volvió a crear el túnel USB" y la
     app entra sin hacer nada más.

### Corrección (21/11/2026) · Cobros no abría: migraciones sin aplicar

- **Causa.** La base del PC no tenía tres migraciones de las últimas tareas
  (`cobros.0002_relacion_de_cobro`, `alertas.0003_alertas_por_umbral`,
  `solicitudes.0007_ida_sin_entregar_es_conflicto`). Al traer el código nuevo nadie corrió
  `manage.py migrate`, el panel arrancó igual y Cobros falló porque su tabla nueva
  (`cobros_relacioncobro`) no existía. Las tres solo cambian la estructura: no tocan datos.
- **Solución de raíz.** En desarrollo, `runserver` aplica las migraciones pendientes antes de
  atender y lo dice en la consola ("Aplicando 1 migración(es) pendiente(s): ..."), igual que
  producción ya lo hace al arrancar (`despliegue/servidor.sh`). Es un `runserver` propio en
  `backend/panel/management/commands/runserver.py` (el de Django con estáticos, más la migración);
  para que gane, `panel` va antes que `django.contrib.staticfiles` en `INSTALLED_APPS`. Si la
  migración falla, la consola lo dice con el comando a correr y el panel arranca igual.
- **Verificado** en la base de recorrido: se desaplicó `cobros.0002`, se arrancó `runserver`, la
  consola avisó y aplicó la migración, y `/cobros/` respondió 200. 7 pruebas nuevas en
  `tests/panel/test_runserver.py`.
- **Cómo probar (1 minuto).** Cerrar el panel (Ctrl+C) y volver a arrancarlo. La consola dice
  "Aplicando 3 migración(es) pendiente(s)" y "Migraciones aplicadas". Entrar a Cobros: abre.

### Propuesta (21/11/2026) · Orden de facturación

- El dueño pidió una forma de pasarle al facturador los datos exactos para evitar errores al
  facturar. Se escribió la propuesta en `docs/propuesta-orden-facturacion.md` y la tarea 1a-19b
  (sin aprobar). Las cuatro preguntas que faltan (IVA, datos de facturación del cliente, quién
  factura y qué programa usan) están en `QUESTIONS.md`. No se construyó nada.

### 1a-19b (21/11/2026) · Orden de facturación (borrador)

- **Qué se hizo.** Respuestas del dueño: IVA del 19 % sumado al facturar; los datos de facturación
  los guarda el cliente; por ahora un borrador; sin información del programa de facturación.
  - `nucleo/facturacion.py`: subtotal, IVA redondeado al peso y total; verificación del total
    digitado y del número repetido. Configuración → Facturación: IVA y datos de la empresa.
  - La relación de cobro armada es la orden: muestra subtotal, IVA y total, avisa qué datos le
    faltan al pagador y permite completarlos (se guardan en el cliente). "Ver orden de facturación"
    abre una página para imprimir o guardar en PDF, con "No es una factura".
  - Al registrar la factura (relación o línea suelta) se pide número **y total**: un total distinto
    o un número ya usado no se registran y el mensaje dice la diferencia o dónde está el número.
  - El IVA queda fijo en la relación al armarla. El Excel/CSV trae subtotal, IVA y total.
  - Pruebas nuevas en `tests/nucleo/test_facturacion.py` y `tests/cobros/test_orden_de_facturacion.py`;
    las de facturar en pantalla ahora mandan el total.
- **Recorrido** en la base de recorrido: relación de tres servicios (525.000 + IVA 99.750 =
  624.750); con 642.750 no se facturó; con 624.750 quedaron las tres líneas en FE-2001; una línea
  suelta con "fe-2001" fue rechazada y con FE-2002 se facturó. El servidor aplicó solo las tres
  migraciones nuevas al arrancar.
- **Cómo probar (5 minutos).** Cerrar y volver a arrancar el panel (aplica las migraciones).
  1. Configuración → Facturación: escribir el nombre y NIT de la empresa; el IVA ya está en 19.
  2. Cobros → Relaciones de cobro: armar una de un cliente con servicios por facturar. Ver subtotal,
     IVA y total; completar los datos del pagador.
  3. "Ver orden de facturación" e "Imprimir o guardar en PDF".
  4. Registrar la factura con un total equivocado: no deja y dice la diferencia. Con el total
     correcto: todas las líneas quedan facturadas.
- **Pendiente.** Quién factura, datos de la empresa y programa de facturación (`QUESTIONS.md`).
  No hay pantalla de Clientes en el panel: los datos de facturación se editan desde la relación.

### Cambio de regla (24/11/2026) · Número de bodega como tercera identificación

- **Qué se hizo.** El dueño indicó que un vehículo también se identifica por el número que tiene en
  la bodega. Ahora es obligatorio al menos uno de tres: placa, VIN o número de bodega. El desvare
  sigue exigiendo la placa.
  - `nucleo/identificacion.py` (y su copia en la app): la regla y la normalización del número
    (mayúsculas, sin espacios; letras, dígitos o guiones, hasta 20). Casos nuevos en
    `docs/casos-reglas.json`, que recorren el servidor y la app.
  - Vehículo: campo `numero_bodega` (no único) con restricción en la base. El formulario de la
    solicitud tiene el campo "Número de bodega"; la lista, el detalle, el tablero y Cobros muestran
    "bodega B-7731" cuando no hay placa ni VIN, y la búsqueda de Solicitudes y Cobros lo encuentra.
  - La orden de facturación y el Excel/CSV de la relación lo traen (columna nueva después de VIN).
  - API revisión 1.4: el vehículo trae `numero_bodega`. La app lo guarda (base local versión 6), lo
    muestra y no pide digitar placa ni VIN al recoger si el vehículo ya tiene número de bodega.
  - Pruebas nuevas: `tests/solicitudes/test_numero_de_bodega.py`, más casos en núcleo, exportación,
    orden y API; en la app, `requisitos_test.dart` y `servicio_test.dart`.
- **Decidido** (supuestos en `QUESTIONS.md`): no es único; lo escribe la oficina; a un vehículo ya
  guardado se le completa si no tenía, sin cambiar uno que ya tenga.
- **Recorrido** en la base de recorrido: solicitud registrada con solo "b-77 31" → guardado
  "B-7731"; la búsqueda "b-7731" la encuentra; con "al asignar" se asignó; sin ningún dato no se
  asignó ("El vehículo necesita placa, VIN o número de bodega (al menos uno)."); un desvare con solo
  número de bodega tampoco; "12/4" lo rechazó el formulario.
- **Cómo probar (menos de 5 minutos).** Cerrar y volver a arrancar el panel (aplica la migración).
  1. Solicitudes → Nueva: dejar placa y VIN vacíos y escribir un número de bodega. Guardar.
  2. En la lista, buscar ese número: aparece como "bodega …".
  3. Asignarla a un conductor: se deja (con cualquiera de los dos momentos configurados).
  4. En el celular (APK nuevo): el servicio muestra "Bodega …" y al recogerlo no pide placa ni VIN.
- **Pendiente.** El APK del celular hay que volver a compilarlo e instalarlo para ver el número de
  bodega en la app (el APK actual lo ignora y, sin placa ni VIN, pide digitarlos al recoger).
- **Pruebas:** servidor 2356 (`uv run pytest -q`), ruff sin errores; app 464 (`flutter test`).

## Escalamientos

Ninguno todavía.
