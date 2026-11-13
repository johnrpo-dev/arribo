# Fase 1a: demo esencial

Tareas en orden de dependencia. Cada una se completa y se verifica en una sesión de Claude Code.
Las horas son las del dueño (revisar, probar, corregir) y son estimaciones: unas 86 en total, 9 semanas
a 10 horas por semana. Marcar `[x]` al terminar.

Cómo pedir una tarea: "Haz la tarea 1a-NN de docs/fase-1a-tareas.md".
Toda tarea termina con `uv run pytest -q` y `uv run ruff check .` en verde, más su verificación manual.

## Base

- [ ] **1a-01 Entorno** (2 h). Depende de: nada.
  Crear la base PostgreSQL local y el `.env`; instalar Flutter y crear el proyecto en `conductor/`
  (comando en `conductor/README.md`).
  Verificar: `uv run pytest -q` pasa contra PostgreSQL; `flutter test` pasa; la app vacía abre en el celular.

- [x] **1a-02 Flota y usuarios** (2 h). Depende de: 01.
  App `flota`: Grúa (capacidad, estado), Conductor, asignación conductor–grúa con inicio y fin.
  Roles como grupos: administrador, logística, facturación, conductor. Todo editable en el admin.
  Verificar: pruebas de que no hay asignaciones traslapadas por conductor ni por grúa; crear una grúa y un conductor en `/admin/`.

- [x] **1a-03 Clientes** (1 h). Depende de: 02.
  App `clientes`: Cliente con tipo, teléfonos únicos, modalidad de cobro; Contacto; Tarifa.
  Verificar: prueba de teléfono único; crear un cliente con tarifa en el admin.

- [x] **1a-04 Solicitudes y servicios** (2 h). Depende de: 03.
  App `solicitudes`: Solicitud, Vehículo, Servicio, Evento de estado, Evidencia. El modelo Servicio
  cambia de estado solo a través de `nucleo/estados.py`.
  Verificar: pruebas de que el modelo rechaza lo mismo que el núcleo y de que cada cambio deja un evento; validación de placa y VIN.

- [x] **1a-05 Configuración** (5 h). Depende de: 04.
  App `configuracion`: registro único con las opciones de `docs/arquitectura.md` y pantalla propia
  (no el admin) para cambiarlas en vivo, con el costo de cada opción de retención de fotos.
  Verificar: prueba de valores por defecto; cambiar el mínimo de fotos en la pantalla y verlo guardado.

## Registro y asignación

- [x] **1a-06 Registro de solicitud I** (6 h). Depende de: 05.
  Formulario único: buscar por teléfono, cargar cliente e historial o crearlo ahí mismo; solicitante y
  pagador; contactos; tipo; origen y destino en texto; un vehículo; inmediato o programado; guardar como Borrador.
  Verificar: pruebas de la vista; registrar a mano una solicitud completa en menos de 60 segundos.

- [x] **1a-07 Registro de solicitud II** (7 h). Depende de: 06.
  Varios vehículos; referencia externa obligatoria si paga aseguradora; momento de placa o VIN según
  configuración; advertencia de duplicado por placa o VIN con servicio activo; pregunta de regreso
  obligatoria en eventos, que crea el servicio de regreso invertido; cierre como No concretada con motivo.
  Verificar: una prueba por cada regla; registrar un evento con regreso y ver los dos servicios enlazados.

- [x] **1a-08 Asignación** (7 h). Depende de: 07.
  Asignar cada vehículo a un conductor (la grúa sale de su asignación vigente y queda guardada), orden de
  ronda, reasignar. Lista de conductores con disponibilidad y capacidad. Un Borrador no se puede asignar.
  Verificar: pruebas de disponibilidad y de que el servicio conserva la grúa aunque el conductor cambie después; repartir una solicitud de 3 vehículos entre 2 conductores.

## Conductor

- [x] **1a-09 API: ingreso y asignaciones** (2 h). Depende de: 08.
  App `api`: ingreso con celular y PIN, token revocable por dispositivo, lista de asignaciones del conductor.
  Verificar: prueba de que la respuesta no contiene ningún valor de cobro y de que un conductor no ve servicios de otro.

- [x] **1a-10 API: sincronización** (3 h). Depende de: 09.
  Recibir lotes de eventos con `nucleo/sincronizacion.py`, guardar hora de sincronización, abrir alerta en
  conflicto, revalidar capacidad. Subida de fotos con reintento.
  Verificar: pruebas de lote repetido, evento sobre servicio cancelado y foto subida dos veces.

- [x] **1a-11 App: ingreso y lista** (5 h). Depende de: 10.
  Ingreso, base local, lista de asignaciones por orden de ronda, llamar al contacto con un toque, abrir
  la dirección en Google Maps o Waze. La lista se ve sin señal.
  Verificar: `flutter test`; en el celular, abrir la lista en modo avión.

- [ ] **1a-12 App: estados y cola sin señal** (7 h). Depende de: 11.
  Botones En camino, Recogido, Entregado y Novedad. Cada toque se guarda como evento en la cola local y
  se envía al abrir la app o al recuperar señal. Indicador "pendiente por enviar".
  Verificar: pruebas de la cola (no pierde eventos, no los duplica, respeta la secuencia); puntos 1 a 4 de `docs/prueba-sin-senal.md`.

- [ ] **1a-13 App: fotos y capacidad** (8 h). Depende de: 12.
  Recogido y Entregado exigen el mínimo de fotos configurado y el nombre de quien entrega o recibe. Fotos
  comprimidas en el celular, subida en cola. Bloqueo por capacidad mostrando qué falta entregar.
  Verificar: pruebas del bloqueo y del mínimo de fotos; puntos 5 a 9 de `docs/prueba-sin-senal.md`.

- [ ] **1a-14 Push al conductor** (5 h). Depende de: 13.
  Requiere que el dueño cree un proyecto de Firebase (gratis) y descargue sus credenciales.
  La app registra su token; el servidor envía la notificación al asignar; marca "visto por el conductor".
  Verificar: prueba de que asignar encola una notificación; asignar desde el panel y que suene el celular.

## Panel

- [ ] **1a-15 Documentos** (3 h). Depende de: 08.
  App `documentos`: tipos configurables, vencimiento, "aún no aplica". Alerta desde 30 días antes. Grúa o
  conductor con documento vencido no es asignable.
  Verificar: pruebas de bloqueo y de que un servicio en curso no se interrumpe; vencer un SOAT y ver al conductor bloqueado.

- [ ] **1a-16 Cobro** (4 h). Depende de: 10.
  App `cobros`: la línea nace cuando el servicio queda Entregado, con `nucleo/cobro.py`. Valor digitado o
  propuesto por tarifa, historial de cambios, permisos según los roles que ven valores.
  Verificar: pruebas de historial y de que logística no ve valores con la configuración por defecto.
  Nota: la tarea se partió en dos. **1a-16a (modelo) está hecha** (PC1): app `cobros` con la línea,
  sus restricciones en PostgreSQL, el historial y las operaciones; la línea nace al quedar Entregado.
  **Falta la 1a-16b** (PC4): las pantallas del panel, la propuesta de tarifa en pantalla y los
  permisos por rol sobre los valores.

- [ ] **1a-17 Relación de cobro y exportación** (3 h). Depende de: 16.
  Agrupar líneas por pagador y fechas, con número de caso. Exportador con una interfaz única y una
  implementación Excel/CSV. Registrar el número de factura.
  Verificar: prueba del contenido del archivo; abrir el Excel generado.

- [ ] **1a-18 Alertas y tablero** (6 h). Depende de: 15, 16.
  App `alertas`: comando que evalúa cuatro alertas (sin asignar, Recogido sin Entregado, documento por
  vencer, conflicto de sincronización) con los umbrales configurados. La pantalla principal muestra lo
  que requiere acción. Búsqueda por cliente, teléfono, placa, VIN, conductor, grúa, caso, factura y fecha.
  Verificar: una prueba por alerta con el reloj controlado; cambiar un umbral y ver aparecer la alerta.
  Nota: la app `alertas` ya existe desde la 1a-10 con lo mínimo (modelo Alerta, `abrir_alerta`,
  `resolver_alerta` y el admin); la sincronización ya abre las alertas de conflicto, de capacidad
  excedida y de evento rechazado. Faltan el comando con los umbrales, las otras tres alertas y el tablero.

- [ ] **1a-19 Panel del dueño mínimo** (3 h). Depende de: 18.
  Servicios del día por estado, no concretadas por motivo, cobros pendientes por pagador, documentos por vencer.
  Verificar: pruebas de los totales con datos conocidos.

## Cierre

- [ ] **1a-20 Datos ficticios** (3 h). Depende de: 19.
  `demo_cargar` y `demo_borrar`: grúas, conductores, clientes (uno con tarifa), servicios en todos los
  estados, alertas activas, documentos por vencer. Marcados para borrarse sin tocar datos reales.
  Verificar: prueba de que `demo_borrar` deja intactos los registros reales.

- [ ] **1a-21 Despliegue y APK** (2 h). Depende de: 20.
  Requiere que el dueño contrate el VPS y el dominio. Docker Compose, HTTPS, APK firmado apuntando al servidor.
  Documentar el comando de despliegue en `CLAUDE.md`.
  Verificar: `/salud/` responde en el dominio; el APK instalado inicia sesión.

- [ ] **1a-22 Ensayo** (semanas 10 y 11). Depende de: 21.
  Checklist completo de `docs/prueba-sin-senal.md` en carretera y ensayo de la demo de principio a fin.
