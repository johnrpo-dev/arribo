# Preguntas para el dueño

Aquí se anota toda regla de negocio que no esté en `CLAUDE.md` ni en `docs/arquitectura.md`.
Quien la encuentre no la inventa: la anota, sigue con lo que no dependa de ella y lo informa.

Formato: fecha, tarea, pregunta, qué se asumió mientras tanto (si se asumió algo) y qué cambia según la respuesta.

## Abiertas

- **2026-11-12, 1a-02. ¿Se puede asignar un conductor a una grúa inactiva o fuera de servicio, o un
  conductor inactivo a una grúa?** Asumido: el modelo no lo bloquea; solo se impiden los traslapes.
  Si la respuesta es "no", se agrega la validación en la asignación y una prueba (y la tarea 1a-08 no
  ofrecería esos conductores como disponibles).
  **Aplicado en 1a-08 lo más conservador, del lado de los servicios** (`nucleo/disponibilidad.py`):
  un conductor inactivo, o cuya grúa vigente esté inactiva o fuera de servicio, no recibe
  servicios nuevos (ni al asignar ni al reasignar) y la lista lo muestra bloqueado con el motivo; lo
  que ya lleva en curso no se interrumpe. La asignación conductor–grúa en Flota sigue sin
  bloquearse. Si la respuesta es "sí se puede", se quitan esos motivos de `motivos_de_bloqueo`.
- **2026-11-12, 1a-02. ¿El motivo es obligatorio en una asignación temporal?** Asumido: es opcional
  en todas. Si es obligatorio, se agrega una restricción en la base (temporal ⇒ motivo no vacío) y su prueba.
- **2026-11-12, 1a-03. ¿Un convenio de tarifa se comparte entre varios clientes?** `docs/arquitectura.md`
  dice "Tarifa: cliente o convenio". Asumido: cada tarifa es de un cliente y el convenio es solo su
  descripción; una tarifa común a varios clientes se repite en cada uno. Si un convenio agrupa clientes,
  se crea un modelo Convenio y `tarifa_propuesta` lo consulta cuando el cliente no tiene tarifa propia.
- **2026-11-12, 1a-03. ¿El documento o NIT del cliente debe ser único?** Asumido: no (es opcional y
  puede repetirse, por ejemplo sedes de un mismo concesionario registradas como clientes distintos).
  Si debe ser único, se normaliza (solo dígitos, sin dígito de verificación o con él) y se agrega la
  restricción en la base.
- **2026-11-12, 1a-04. ¿Qué datos son obligatorios para que una solicitud deje de ser borrador? En
  particular, ¿un desvare tiene destino?** Asumido: en el modelo, origen y destino pueden quedar
  vacíos (así se guarda un borrador incompleto); la base solo exige lo de los eventos (respuesta de
  regreso) y lo de no concretada. Los obligatorios del formulario los fijan las tareas 1a-06 y 1a-07;
  si un desvare no tiene destino, el formulario no lo pedirá en ese tipo.
  **Aplicado en 1a-06** (`nucleo/registro.py`, `faltantes_para_abrir`): para quedar abierta, una
  solicitud necesita solicitante, tipo, origen y al menos un vehículo; destino en traslado y evento,
  no en desvare. Sin solicitante ni tipo no se guarda ni como borrador (la base los exige). Sigue
  abierta hasta que el dueño la confirme; si cambia, se cambia esa función con su prueba.
- **2026-11-12, 1a-06. ¿Qué cuenta como "un vehículo" para salir de borrador?** Asumido: cualquier
  dato del vehículo (placa, VIN, marca, línea o color); la placa o el VIN no se exigen al registrar,
  sino al recoger (y en 1a-07 según la configuración). Así, un desvare sin placa puede quedar
  abierto y se bloquea al marcar Recogido. Si el desvare debe exigir placa ya al registrar, se agrega
  a `faltantes_para_abrir` con su prueba.
- **2026-11-12, 1a-06. ¿Un contacto nuevo queda ligado al cliente solicitante?** Asumido: no; el
  contacto se guarda sin cliente y se reutiliza si ya existe uno con el mismo nombre y teléfono.
  Si debe quedar ligado (por ejemplo, para sugerir los contactos del cliente), se asigna al crear.
- **2026-11-12, 1a-16a. ¿Cuánto se cobra un servicio cancelado que se marca cobrable (la grúa se
  desplazó y el vehículo no estaba)?** Asumido: nace igual que al entregar, con la tarifa vigente del
  pagador para ese tipo de servicio (o sin valor si no hay) y se ajusta a mano antes de facturar. Si
  hay un valor propio de "desplazamiento en falso", se agrega a la tarifa y `marcar_cobrable` lo
  propone en vez de la tarifa del servicio.
- **2026-11-12, 1a-16a. ¿Se puede marcar cobrable un servicio cancelado antes de asignarlo?**
  (ninguna grúa salió). Asumido: sí, el sistema no lo impide; quien lo marca decide. Si la respuesta
  es "no", `marcar_cobrable` exige que el servicio haya tenido conductor y se agrega su prueba.
- **2026-11-12, 1a-16a. ¿Quién deja una línea como "no cobrable" y desde qué estado** (por ejemplo,
  una garantía o una cortesía)? El modelo y la base admiten el estado, pero ninguna operación lo
  produce todavía. Asumido: nada hasta la 1a-16b. Según la respuesta, se agrega la operación (desde
  sin valor o por facturar, con motivo en el historial) y sus pruebas.
- **2026-11-12, 1a-16a. Si el pagador de la solicitud cambia después de entregado el servicio, ¿la
  línea cambia de pagador?** Asumido: no; la línea guarda el pagador que tenía la solicitud al
  quedar Entregado. Cambiarlo sería una operación nueva (antes de facturar, con historial).
- **2026-11-13, 1a-07. ¿La referencia externa de la aseguradora es una por vehículo o una por
  solicitud?** El modelo la tiene en el servicio (un número de caso por vehículo). Asumido: si el
  pagador (que por defecto es quien llama) es una aseguradora, cada vehículo necesita su referencia
  para salir de borrador; el servicio de regreso copia la de su ida. Si es una por solicitud, se
  pide una sola vez en el formulario y se copia a todos los servicios (cambia `faltantes_de`).
- **2026-11-13, 1a-07. ¿Cuándo se puede cerrar una solicitud como no concretada?** Asumido (lo más
  conservador): desde borrador o abierta, con motivo, solo si ningún servicio se asignó nunca (ni
  ahora ni antes: un servicio que se asignó y volvió a la cola o se canceló ya movió una grúa; esos
  se cancelan con motivo). Sus servicios no se cancelan, porque "no concretada" es distinto de
  "Cancelado": quedan pendientes de asignar pero no se pueden asignar, y las listas y alertas
  futuras deben ignorarlos. El detalle es opcional, también con el motivo "Otro". No se guarda
  quién la cerró (la solicitud aún no tiene historial). No se puede deshacer.
- **2026-11-13, 1a-07. ¿El regreso de un evento tiene una fecha por vehículo?** Asumido: no; la
  fecha de regreso es de la solicitud y vale para todos sus vehículos. El servicio no tiene origen
  ni destino propios: el de regreso va del destino al origen de la solicitud, y lo marca su enlace
  al de ida (`regreso_de`). Los regresos se crean una sola vez, cuando la solicitud queda abierta.
  Si cada vehículo vuelve en una fecha distinta, se agrega la fecha al servicio.
- **2026-11-13, 1a-07. ¿Quitar un vehículo de un borrador lo cancela?** Asumido: sí, porque nada
  se borra; el servicio queda Cancelado con el motivo "Se quitó el vehículo al completar el
  borrador" y se sigue viendo en el detalle. Si se prefiere que un servicio de borrador se pueda
  descartar sin dejar rastro, habría que permitir borrar solo en ese caso.
- **2026-11-13, 1a-07. ¿Qué cuenta como duplicado?** Asumido: el mismo vehículo (por placa o VIN)
  con un servicio no terminal en otra solicitud en borrador o abierta; las no concretadas no
  cuentan. Es solo una advertencia: el operador la confirma pulsando de nuevo Guardar.
- **2026-11-13, 1a-08. ¿Cómo se fija el orden de ronda?** Asumido (lo más simple consistente):
  cada servicio asignado o reasignado entra al final de la ronda de su conductor; el operador lo
  sube o lo baja un puesto. El puesto es único por conductor entre sus servicios no terminales
  (restricción en la base); al terminar o volver a la cola un servicio, su puesto queda libre y la
  ronda puede tener huecos hasta el siguiente movimiento (el orden relativo no cambia). No se
  ordena solo por hora programada ni por cercanía. Si el orden debe salir de la hora programada, o
  el operador debe digitar el puesto, cambia `nucleo/ronda.py`.
- **2026-11-13, 1a-08. ¿Reasignar exige motivo?** Asumido: no; la operación lo admite opcional y
  la pantalla lo pide como "Motivo del cambio (opcional)"; queda en el evento. Si es obligatorio,
  se exige en `operaciones.reasignar` con su prueba.
- **2026-11-13, 1a-08. ¿Se puede reasignar al mismo conductor?** Asumido: no (no tendría efecto
  y, desde En camino, lo devolvería a Asignado); `operaciones.reasignar` lo rechaza y la lista no
  ofrece al conductor actual.
- **2026-11-13, 1a-09. ¿Quién fija el PIN del conductor?** Asumido: el administrador, en el admin
  (Flota → Conductores → "Nuevo PIN de la app"); el conductor no lo cambia desde la app. Si debe
  elegirlo o cambiarlo él, se agrega a la API "cambiar PIN" (pidiendo el actual) con su prueba.
- **2026-11-13, 1a-09. ¿El token de la app vence?** Asumido: no; sirve hasta cerrar sesión, que lo
  revoquen en el admin o que el conductor vuelva a ingresar en el mismo celular. Si debe vencer (por
  ejemplo, tras 30 días sin uso), la regla usa el `ultimo_uso` que ya se guarda.
- **2026-11-13, 1a-09. ¿Cambiar el PIN cierra las sesiones abiertas del conductor?** Asumido: no;
  para cerrarlas se revocan sus tokens en el admin. Si sí, guardar un PIN nuevo en el admin revoca
  los tokens del conductor (y se agrega la prueba).
- **2026-11-13, 1a-09. ¿Desactivar a un conductor que tiene servicios en curso le corta la app?**
  Aplicado lo que pidió la tarea: sí, todo responde 401, también el envío de eventos de la 1a-10; lo
  que haga queda en la cola del celular hasta que lo reactiven, y logística resuelve esos servicios
  desde el panel. Choca con "lo que ya lleva en curso no se interrumpe" (1a-08, 1a-15). Si debe poder
  terminar lo que lleva, un conductor inactivo conservaría acceso solo a sus servicios en curso.
- **2026-11-13, 1a-09. ¿El conductor ve el nombre del cliente?** Asumido: no; la lista trae tipo,
  vehículo, direcciones, contactos de origen y destino y referencia externa, como pidió la tarea. Si
  debe verlo, se agrega un campo con el nombre del solicitante (nunca el pagador ni valores).
- **2026-11-13, 1a-10. ¿Qué es una foto de "soporte", quién la sube y a qué acompaña?** El modelo
  tiene los tipos recogida, entrega y soporte, pero solo están escritas las fotos de Recogido y
  Entregado. Asumido: desde la app solo se suben `recogida` (acompaña a un Recogido) y `entrega`
  (a un Entregado); `soporte` responde 400. Si el conductor debe subir soportes (por ejemplo, en
  una novedad o un cargo adicional), se agrega a `nucleo/evidencia.py` a qué evento acompaña.
- **2026-11-13, 1a-10. ¿Quién resuelve una alerta y cuándo se da por resuelta?** Asumido: una
  persona la marca como resuelta a mano (por ahora en el admin; queda quién y cuándo) y no se
  cierra sola al corregir el estado del servicio. Mientras siga abierta no se abre otra igual para
  el mismo registro. Si deben cerrarse solas (por ejemplo, al marcar a mano el estado que el
  conductor reportó) o solo ciertos roles pueden resolverlas, lo define la 1a-18.
- **2026-11-13, 1a-10. ¿El conductor puede cerrar sesión con eventos o fotos sin enviar?** El
  servidor toma como conductor del evento al del token. Si Ana toca botones sin señal, cierra sesión
  y Beto ingresa en ese celular, los toques de Ana llegarían como de Beto (conflictos con alerta).
  Asumido en el contrato: la app no deja cerrar sesión con pendientes (lo construye la 1a-12). Si
  debe poder cerrarla, la app guarda el token junto a cada evento pendiente y los envía con él.
- **2026-11-13, 1a-10. ¿Hasta cuándo puede un conductor subir fotos de un servicio que ya no es
  suyo?** Asumido: siempre que lo tenga o lo haya tenido (hay un evento suyo en el historial),
  también entregado, cancelado o reasignado, sin plazo; para uno que nunca fue suyo, no. Si debe
  haber un plazo o debe abrir alerta la foto de un servicio reasignado, se agrega a
  `solicitudes/evidencias.py` con su prueba.

## Resueltas

- **2026-11-12, 1a-04 → resuelta en 1a-04. ¿El conductor puede cancelar un servicio desde la app?**
  Decisión: no. La app solo tiene los botones En camino, Recogido, Entregado y Novedad, y el servidor
  solo acepta esos cuatro destinos desde la app (`DESTINOS_DESDE_LA_APP` en
  `nucleo/sincronizacion.py`). Cualquier otro, por ejemplo un Cancelado, se guarda como conflicto
  y el servicio no cambia: cancelar es de logística, con motivo. Decisión del orquestador.

- **2026-11-12, 1a-02 → resuelta en 1a-03. ¿Cómo se escriben las placas de grúa?** Decisión: se
  guardan en mayúsculas y solo con letras y dígitos (se quitan espacios, guiones y cualquier otro
  símbolo), así que "abc-123", "ABC 123" y "ABC123" son la misma placa. La base lo exige
  (`grua_placa_normalizada`) y la migración normalizó las grúas ya guardadas. La misma función
  (`nucleo/identificacion.py`, `normalizar_placa`) servirá para la placa de vehículo de la 1a-04.
  Decisión técnica del orquestador; el dueño puede cambiarla.
- **2026-11-12, 1a-02 → resuelta en 1a-03. ¿El celular del conductor se normaliza?** Decisión: sí.
  Se guarda solo con dígitos y sin el indicativo 57 cuando viene antepuesto a un número de 10 dígitos;
  debe quedar entre 7 y 15 dígitos. "+57 300 123 4567", "300-123-4567" y "3001234567" son el mismo
  celular, así que la unicidad no se burla con el formato. La base exige solo dígitos
  (`conductor_celular_solo_digitos`). La misma regla aplica a los teléfonos de clientes y contactos,
  y la usará el ingreso por celular de la 1a-09. Decisión técnica del orquestador; el dueño puede cambiarla.
