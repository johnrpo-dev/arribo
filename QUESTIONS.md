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
- **2026-11-12, 1a-02. ¿Cómo se escriben las placas de grúa?** Asumido: se guardan en mayúsculas y sin
  espacios, pero el guion se conserva, así que "ABC-123" y "ABC123" son placas distintas. Si deben ser
  la misma, la normalización también quita guiones (afecta igual a la placa de vehículo de la 1a-04).
- **2026-11-12, 1a-02. ¿El celular del conductor se normaliza?** Asumido: se guarda tal cual se digita
  y la unicidad es exacta ("300 123 4567" y "3001234567" serían distintos). Si se normaliza (solo
  dígitos, con o sin +57), cambia la unicidad y el ingreso por celular de la 1a-09.

## Resueltas

Ninguna todavía.
