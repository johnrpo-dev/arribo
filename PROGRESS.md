# Progreso de la fase 1a

Se actualiza al final de cada tarea: qué se hizo, qué se decidió y cómo probarlo a mano.
Los escalamientos de nivel de agente se registran en la sección del final, con su motivo.

## Puntos de control

| Punto | Contenido | Tareas | Estado |
|---|---|---|---|
| PC1 | Modelo de datos y reglas probadas contra PostgreSQL | 1a-01 (Flutter), 1a-02, 1a-03, 1a-04, 1a-16a | En curso |
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
- Preguntas abiertas nuevas: dos en `QUESTIONS.md` (cancelar desde la app, obligatorios del borrador).
- Cómo probar (5 minutos): `uv run pytest -q` (585 pruebas) y `uv run python manage.py migrate`.
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

## Escalamientos

Ninguno todavía.
