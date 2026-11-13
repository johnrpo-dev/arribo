# Progreso de la fase 1a

Se actualiza al final de cada tarea: qué se hizo, qué se decidió y cómo probarlo a mano.
Los escalamientos de nivel de agente se registran en la sección del final, con su motivo.

## Puntos de control

| Punto | Contenido | Tareas | Estado |
|---|---|---|---|
| PC1 | Modelo de datos y reglas probadas contra PostgreSQL | 1a-01 (Flutter), 1a-02, 1a-03, 1a-04, 1a-16a | Cerrado el 12 de noviembre de 2026 (748 pruebas; falta compilar el APK, pendiente del NDK) |
| PC2 | Configuración, registro de solicitud y asignación | 1a-05, 1a-06, 1a-07, 1a-08 (más la base del panel) | Cerrado el 13 de noviembre de 2026 (1097 pruebas). APK de prueba compilado; falta probarlo en el Motorola |
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

## Escalamientos

Ninguno todavía.
