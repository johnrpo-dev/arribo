# Preguntas para el dueño

Aquí se anota toda regla de negocio que no esté en `CLAUDE.md` ni en `docs/arquitectura.md`.
Quien la encuentre no la inventa: la anota, sigue con lo que no dependa de ella y lo informa.

Formato: fecha, tarea, pregunta, qué se asumió mientras tanto (si se asumió algo) y qué cambia según la respuesta.

## Abiertas

- **2026-11-12, 1a-02. ¿Se puede asignar un conductor a una grúa inactiva o fuera de servicio, o un
  conductor inactivo a una grúa?** Asumido: el modelo no lo bloquea; solo se impiden los traslapes.
  Si la respuesta es "no", se agrega la validación en la asignación y una prueba (y la tarea 1a-08 no
  ofrecería esos conductores como disponibles).
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
