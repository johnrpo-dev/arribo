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

- [x] **1a-08b Personal y grúas** (2 h). Depende de: 08.
  Pantalla del panel (solo administrador) para crear y administrar conductores (con su acceso a la app:
  celular, PIN y grúa, sin tocar usuarios ni grupos), usuarios de oficina con un rol, y grúas. Cambiar
  PIN, cambiar de grúa sin traslapes, desactivar y reactivar (revoca las sesiones de la app), habilitar
  para la app a un conductor existente. Nada se borra; nunca queda el panel sin administrador.
  Verificar: crear un conductor desde el panel e ingresar con él en la app; desactivarlo y ver que la app ya no lo deja entrar.

- [x] **1a-08c Simplificar el panel** (3 h). Depende de: 08b. Agregada tras la primera prueba del dueño.
  Lista de solicitudes (filtros Activas, Por asignar, Borradores, Programadas, Terminadas y Todas;
  búsqueda por teléfono o nombre del cliente, placa, VIN, número y referencia; páginas). Inicio de
  logística y administrador con lo que requiere acción (adelanto mínimo de la 1a-18). Una sola sección
  "Flota y personal" (une Flota y documentos con Personal y grúas; `/personal/` redirige). Un solo
  "Guardar" en Nueva solicitud y botón "Abrir solicitud" en un borrador completo. El menú y el inicio
  ocultan las secciones sin pantalla. Corregir nombre y celular del conductor.
  Verificar: registrar una solicitud, salir y encontrarla desde el inicio y con la búsqueda; asignarla
  y verla en curso en el inicio; registrar un documento vencido y ver al conductor bloqueado.

- [x] **1a-08d Restablecer datos de prueba** (0,5 h). Depende de: 08c. Pedida por el dueño.
  En Configuración, solo administrador: borra todo lo operativo (y los usuarios salvo quien restablece
  y los superusuarios), conserva configuración y tipos de documento; pide escribir BORRAR. Apagado en
  producción (`ARRIBO_PERMITIR_RESTABLECER`).
  Verificar: restablecer y ver el inicio y Flota vacíos, con el administrador intacto.

- [x] **1a-08e Tablero visual y admin de consulta** (1 h). Depende de: 08d. Pedida por el dueño.
  Tablero de logística con cifras del día, tarjetas por asignar con su espera (urgente según la
  configuración) y asignación ahí mismo, alertas que se resuelven ahí y una tarjeta por conductor con
  su grúa, ocupación y ronda; se actualiza solo cada minuto. Admin de Django solo de consulta y solo
  para superusuarios, sin usuarios ni grupos. Nombre, celular y grúa del conductor con un solo Guardar.
  Verificar: asignar desde el tablero y resolver una alerta; darle grúa a un conductor creado sin ella.

- [x] **1a-08f Ida y regreso visibles** (0,5 h). Depende de: 08e. Reporte del dueño ("servicio duplicado").
  El regreso de un evento se marca como tal en asignar, ronda y tablero, con su fecha.
  Verificar: en un evento con regreso, el N.º del regreso dice "Regreso del N.º …" con su fecha.

- [x] **1a-08g Panel con aspecto profesional y regreso en color** (1,5 h). Depende de: 08f. Pedida por el dueño.
  Hoja de estilos renovada (barra lateral oscura, sombras suaves, tipografía y tablas más claras,
  buscador en una fila, filtros como pestañas) y color propio para el regreso. En el tablero, el
  regreso por asignar usa su propia hora (fecha de regreso) y su trayecto al revés para la urgencia y el orden.
  Verificar: el regreso se ve en verde azulado en el tablero y en el detalle; no sale urgente por la hora de la ida.

- [x] **1a-08h El regreso espera a su ida** (3 h). Depende de: 08g. Decisión del dueño.
  Regla `nucleo.trayecto.regreso_bloqueado` con casos compartidos; en el servidor, un avance de un
  regreso con la ida sin entregar es conflicto `ida_sin_entregar` con alerta; contrato 1.3
  (`regreso_de`, `espera_ida`); la app muestra el candado y lo quita en cuanto se entrega la ida,
  también sin señal; el panel marca "Espera la ida".
  Verificar: en la app, el regreso no ofrece En camino hasta entregar la ida; Novedad sí.

- [x] **1a-08i Fotos de evidencia en el panel** (2 h). Depende de: 08h. Pedido del dueño.
  Sección "Fotos" en el detalle de la solicitud, por servicio, con tipo, hora, conductor y quién
  recibió; señala el Recogido o Entregado de la app sin foto (`nucleo.evidencia.foto_esperada`).
  Las fotos solo se ven con sesión y rol. Las nuevas se guardan en
  `evidencias/solicitud-N/servicio-N/`.
  Verificar: en una solicitud entregada desde la app se ven sus fotos; sin sesión, la foto pide ingresar.

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

- [x] **1a-12 App: estados y cola sin señal** (7 h). Depende de: 11.
  Botones En camino, Recogido, Entregado y Novedad. Cada toque se guarda como evento en la cola local y
  se envía al abrir la app o al recuperar señal. Indicador "pendiente por enviar".
  Verificar: pruebas de la cola (no pierde eventos, no los duplica, respeta la secuencia); puntos 1 a 4 de `docs/prueba-sin-senal.md`.

- [x] **1a-13 App: fotos y capacidad** (8 h). Depende de: 12.
  Recogido y Entregado exigen el mínimo de fotos configurado y el nombre de quien entrega o recibe. Fotos
  comprimidas en el celular, subida en cola. Bloqueo por capacidad mostrando qué falta entregar.
  Verificar: pruebas del bloqueo y del mínimo de fotos; puntos 5 a 9 de `docs/prueba-sin-senal.md`.
  Corregido en 1a-13b: con "placa/VIN al recoger", un vehículo sin placa ni VIN bloqueaba el
  Recogido ("llame a logística") y sin señal no se podía recoger. Ahora el conductor digita la placa
  o el VIN en la pantalla del Recogido y viajan en el evento (contrato 1.1); punto 9c de
  `docs/prueba-sin-senal.md`.

- [x] **1a-14 Push al conductor** (5 h). Depende de: 13.
  Requiere que el dueño cree un proyecto de Firebase (gratis) y descargue sus credenciales.
  La app registra su token; el servidor envía la notificación al asignar; marca "visto por el conductor".
  Verificar: prueba de que asignar encola una notificación; asignar desde el panel y que suene el celular.

## Panel

- [x] **1a-15 Documentos** (3 h). Depende de: 08.
  App `documentos`: tipos configurables, vencimiento, "aún no aplica". Alerta desde 30 días antes. Grúa o
  conductor con documento vencido no es asignable.
  Verificar: pruebas de bloqueo y de que un servicio en curso no se interrumpe; vencer un SOAT y ver al conductor bloqueado.

- [x] **1a-16 Cobro** (4 h). Depende de: 10.
  App `cobros`: la línea nace cuando el servicio queda Entregado, con `nucleo/cobro.py`. Valor digitado o
  propuesto por tarifa, historial de cambios, permisos según los roles que ven valores.
  Verificar: pruebas de historial y de que logística no ve valores con la configuración por defecto.
  Nota: la tarea se partió en dos. **1a-16a (modelo) está hecha** (PC1): app `cobros` con la línea,
  sus restricciones en PostgreSQL, el historial y las operaciones; la línea nace al quedar Entregado.
  **1a-16b (pantallas) está hecha**: sección Cobros (facturación y administrador) con pestañas por
  estado, búsqueda y la página de cada línea (digitar o ajustar el valor con la tarifa propuesta,
  facturar, pagar, anular con motivo, historial); los cancelados asignados se marcan cobrables; el
  detalle de la solicitud muestra el estado de cobro y el valor solo a quien lo ve.

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
  Adelantado en la 1a-08c: el inicio de logística y del administrador (`/` y la sección Tablero,
  `panel.views.tablero`) ya muestra servicios por asignar (inmediatos primero, luego programados por
  hora), borradores con lo que les falta, las alertas abiertas que ya existen y lo que está en curso
  por conductor; y la lista de solicitudes ya busca por teléfono, nombre, placa, VIN, número y
  referencia. Falta lo de esta tarea: el comando con umbrales, las alertas nuevas, resolver alertas
  desde el panel y buscar por conductor, grúa, factura y fecha.

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
