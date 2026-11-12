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

## Escalamientos

Ninguno todavía.
