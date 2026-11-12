# Arquitectura: Arribo

Decisión aprobada el 12 de noviembre de 2026.

## Qué entendí

Una empresa de grúas de Medellín (10 grúas, 1 persona en despacho) gestiona hoy con cuaderno, Excel y
WhatsApp. Se olvidan llamadas y servicios, y no hay claridad de qué cobrar a quién. Arribo se presenta
como producto propio, lo mantiene una sola persona con 10 horas semanales, y se construye con Claude Code.
Los conductores usan celulares Android que entrega la empresa. No hay datos internos del cliente antes
de la demo: todo lo que dependa de él es configurable.

## Decisión

- **Lenguaje y framework:** Python con Django 5.2 LTS. Panel con plantillas + HTMX; API con Django REST Framework.
- **App del conductor:** Flutter, solo Android, instalada por APK directo.
- **Persistencia:** PostgreSQL en el servidor; SQLite local en el celular.
- **Fotos:** disco del servidor en la fase 1a; Cloudflare R2 desde la fase 1b.
- **Push:** Firebase Cloud Messaging al conductor. Alertas a logística y administrador en el panel y por correo.
- **Hosting:** un VPS con Docker Compose. Una instancia por empresa cliente.
- **Costo mensual estimado:** COP 40.000–55.000. Costo anual: dominio (COP 50.000–130.000).

## Por qué, y qué descarté

- **AppSheet.** Cumple offline con fotos, pero cobra unos COP 425.000 al mes por 13 usuarios y no se puede
  vender como producto propio. Con un solo cliente sale más barato los primeros 20 meses (contando las horas
  de desarrollo a COP 50.000); construir gana desde ahí, y antes si hay un segundo cliente.
- **Glide.** Sin offline real. **GruasApp y similares:** sin cobro por pagador, documentos ni alertas, y no adaptables.
- **PWA para el conductor.** En Android es viable, pero Chrome suele cerrarse al abrir la cámara en gama
  media, los datos locales se borran al limpiar el navegador y exige mucho JavaScript. Ganaría en que se actualiza sola.
- **Flask + SQLAlchemy.** Habría que rearmar usuarios, permisos, migraciones y pantallas de administración.
- **Plataformas gestionadas y Supabase.** Más caras a esta escala; las reglas terminarían en SQL difícil de mantener.
- **Multiempresa.** Complica cada consulta para un segundo cliente que aún no existe.

## Sincronización sin señal

Cada toque del conductor es un evento con id generado en el celular, secuencia, hora del dispositivo y
ubicación si está disponible. Se guarda en la base local y se envía cuando hay señal. El servidor lo
aplica una sola vez. Las fotos suben aparte y se reanudan; el estado no espera a las fotos y el servicio
muestra "evidencia pendiente" hasta que lleguen. El servidor manda sobre las asignaciones; el conductor
manda sobre lo que hizo físicamente. Un evento que ya no encaja se guarda y abre una alerta a logística.

## Modelo de datos

| Entidad | Contenido y restricciones |
|---|---|
| Cliente | Tipo (particular, concesionario, aseguradora/asistencia), teléfonos únicos, modalidad de cobro, firma obligatoria |
| Tarifa | Cliente o convenio, tipo de servicio, valor propuesto |
| Contacto | Nombre y teléfono; en origen o destino de un servicio |
| Solicitud | Solicitante, tipo, origen y destino en texto con pin opcional, fecha, respuesta de regreso, motivo de no concretada |
| Vehículo | Placa o VIN (cada uno único si existe), marca, línea, color |
| Servicio (vehículo-en-solicitud) | Vehículo, estado, estado previo, conductor y grúa guardados, orden de ronda, referencia externa, enlace a la ida si es regreso |
| Evento de estado | Id del celular (único), secuencia, quién, hora del dispositivo, hora de sincronización, ubicación, resultado |
| Evidencia | Foto, tipo (recogida, entrega, soporte), evento |
| Grúa | Capacidad (1 o 2), estado operativo |
| Conductor | Usuario, celular, PIN, token de push |
| Asignación conductor–grúa | Inicio y fin; sin traslapes por conductor ni por grúa |
| Tipo de documento y Documento | Aplica a grúa o conductor; vencimiento, "aún no aplica" con fecha, foto |
| Línea de cobro | Servicio × pagador (máximo dos), valor, estado, número de factura |
| Cargo adicional | Tipo, valor, soporte |
| Relación de cobro | Pagador, rango de fechas, líneas incluidas |
| Alerta | Tipo, registro al que apunta, abierta o resuelta |
| Configuración | Opciones de la tabla de abajo |
| Historial | Cambios por registro, con valor anterior |

## Máquinas de estado

Implementadas en `backend/nucleo/` con sus pruebas. Resumen en `CLAUDE.md`.

- **Operativa:** Pendiente de asignar → Asignado → En camino → Recogido → Entregado. Cancelado con motivo.
  Novedad bloqueante que se resuelve reanudando, reasignando o cancelando.
- **Solicitud:** Borrador → Abierta → En curso → Completada o Cancelada (derivado). No concretada, con motivo.
- **Cobro (por línea):** Sin valor → Por facturar → Facturado → Pagado. No cobrable. Anulación de factura con motivo.

## Opciones configurables

| Opción | Valor por defecto | Alcance |
|---|---|---|
| Momento en que se exige placa o VIN | Al recoger | Global |
| Modalidad de cobro | Por servicio | Por cliente |
| Precio | Digitado; si hay tarifa, se propone y se puede ajustar | Tarifa por cliente o convenio |
| Firma | Opcional | Por pagador |
| Mínimo de fotos en Recogido y Entregado | 4 | Global |
| Roles que ven valores | Administrador y facturación (área contable) | Por rol |
| Tipos de documento | SOAT, tecnomecánica, licencia; alerta desde 30 días antes | Lista editable |
| Retención de fotos | 12 meses (opciones: 6, 12, 24, indefinida) | Global |
| Umbrales de alertas | Sin asignar 10 min; programado sin asignar 2 h antes; sin "En camino" 15 min; Recogido sin Entregado 4 h; sin facturar 5 días; sin pagar 30 días | Global |
| Horario nocturno | 7 p. m. a 6 a. m.; las alertas van también al administrador | Global |
| Exportación de factura | Excel/CSV genérico | Adaptadores después |

En la fase 1a, firma y horario nocturno se pueden editar pero aún no tienen efecto.

Costo mensual de la retención de fotos en el pico (50 servicios al día, unos 4 GB al mes):
6 meses, COP 700; 12 meses, COP 1.900; 24 meses, COP 4.200; indefinida, sube unos COP 200 cada mes.

## Plan

Horas estimadas, no medidas. Suponen desarrollo con Claude Code y 10 horas semanales de revisión.

| Fase | Semanas | Horas | Contenido |
|---|---|---|---|
| 1a. Demo esencial | 1–9 | ~86 | `docs/fase-1a-tareas.md` |
| Ensayo y colchón | 10–11 | | Prueba sin señal en carretera, ensayo de la demo |
| 1b. Demo completa | 12–18 | ~65 | Subida de fotos con la app cerrada, R2, firma, dos pagadores, cargos adicionales, ubicación, resto de alertas, panel del dueño completo, push web del panel |
| 2. Ajuste tras el cliente | 19–23 | ~50 | Sus respuestas, importación de clientes, PDF |
| 3. Producción | 24–27 | ~40 | Respaldo con restauración probada, Ley 1581, recordatorios escalonados, borrado de fotos por retención |

## Riesgos y cuándo esta decisión deja de servir

1. **Plazo.** A 10 horas semanales, un desvío de 20 horas son dos semanas.
2. **Fotos sin sincronizar.** Se pierden si el celular se daña antes de subirlas. La app muestra "pendiente por subir".
3. **Actualización del APK.** Sin tienda no hay actualización automática: la app compara su versión con la mínima del servidor.
4. **Un servidor y un desarrollador.** El respaldo diario limita la pérdida a un día.
5. **Hora del celular mal puesta.** Se guardan las dos horas; el orden lo da la secuencia.
6. **Caducidad.** Más de unas 5 empresas cliente (toca multiempresa) o GPS continuo.

## Primeros pasos

Seguir `docs/fase-1a-tareas.md` desde la tarea 1a-01.
