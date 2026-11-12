# Arribo

Sistema de gestión de servicios de grúa (traslados, eventos de concesionario y desvares) para una
empresa de 10 grúas en Medellín. Existe para que no se pierdan llamadas, servicios ni cobros.
Lo construye Claude Code; el dueño del proyecto dedica unas 10 horas semanales a revisar, probar
y corregir. Cada sesión debe dejar algo que él pueda verificar sin leer todo el código.

Documentos de referencia:
- `docs/arquitectura.md`: decisión aprobada, modelo de datos, máquinas de estado, opciones configurables.
- `docs/fase-1a-tareas.md`: tareas de la fase 1a en orden de dependencia. **Trabaja una tarea por sesión.**
- `docs/prueba-sin-senal.md`: checklist manual del modo sin señal en celular real.

## Arquitectura

- `backend/`: Django 5.2 LTS + PostgreSQL. Panel web renderizado en servidor (plantillas + HTMX) para
  logística, facturación y dueño. API REST (DRF) solo para la app del conductor.
- `conductor/`: app Flutter, solo Android, distribuida por APK directo (sin tiendas). Base local SQLite
  y cola de salida; push con Firebase Cloud Messaging.
- Producción: un VPS con Docker Compose. Fotos en el disco del servidor durante la fase 1a (R2 después).
- Una instancia por empresa cliente. No hay multiempresa.

### Estructura del backend

- `config/`: settings, urls, wsgi. Sin lógica.
- `nucleo/`: reglas de negocio en Python puro. **No importa Django** (lo vigila `tests/test_arranque.py`).
- Apps de Django por dominio, creadas cuando la tarea las pida: `flota`, `clientes`, `solicitudes`,
  `cobros`, `documentos`, `alertas`, `configuracion`, `api`. No por capa técnica.
- `tests/`: `tests/nucleo/` para reglas puras; `tests/<app>/` para modelos, vistas y API.

## Comandos

Desde `backend/` (PowerShell):

```
uv sync                                  # instalar dependencias
uv run pytest -q                         # todas las pruebas
uv run pytest tests/nucleo -q            # solo reglas de negocio (menos de 1 s)
uv run ruff check .                      # linter
uv run python manage.py check            # comprobación de Django
uv run python manage.py migrate          # aplicar migraciones
uv run python manage.py runserver        # panel en http://127.0.0.1:8000
```

Desde `conductor/` (cuando exista el proyecto Flutter, tarea 1a-01):

```
flutter test                             # pruebas de la app
flutter run                              # correr en el celular conectado
flutter build apk --release              # APK para instalar
```

Datos ficticios (tarea 1a-20): `manage.py demo_cargar` y `manage.py demo_borrar`.
Despliegue (tarea 1a-21): todavía no existe; al crearlo, documentar aquí el comando exacto.

## Antes de dar una tarea por terminada

1. `uv run pytest -q` y `uv run ruff check .` pasan (y `flutter test` si se tocó la app).
2. La tarea tiene pruebas nuevas para lo que agrega. Una regla de negocio sin prueba no está terminada.
3. Informar al dueño: qué cambió, cómo verificarlo a mano en menos de 5 minutos, y qué quedó sin hacer.
4. Marcar la tarea en `docs/fase-1a-tareas.md`. No adelantar tareas de fases posteriores.

## Reglas de trabajo por tarea

- Una rama por tarea (`tarea/1a-NN-nombre`), commits pequeños. Se fusiona en `main` solo con todas las pruebas en verde.
- Pruebas automáticas para cada regla de negocio tocada. Prohibido desactivar, saltar o debilitar pruebas para que pasen.
- Toda regla que dependa de PostgreSQL (restricciones, unicidad, transacciones) se prueba contra la base, no solo en `nucleo/`.
- Una regla de negocio que no esté escrita no se inventa: se anota en `QUESTIONS.md` y se sigue con lo independiente.
- Al terminar, actualizar `PROGRESS.md`: qué se hizo, qué se decidió, cómo lo prueba el dueño a mano.
- Detenerse y preguntar antes de: cambiar la arquitectura, agregar una dependencia grande, desplegar, borrar
  datos, o cuando una prueba siga fallando tras 3 enfoques distintos.
- Cuentas y servicios externos (Firebase, VPS, dominio, correo) los crea el dueño: darle los pasos.
- Sin Docker en local. PostgreSQL nativo; la app se prueba en un Android físico por USB, no en emulador.
- App: minSdk 26. Cámara y cola sin señal pensadas para gama media con poca memoria: fotos a disco, nunca
  retenidas en memoria; el estado de la pantalla sobrevive a que el sistema mate la app al abrir la cámara.

## Git y GitHub

- Remoto: `origin` en https://github.com/johnrpo-dev/arribo.git. La rama principal es `main`.
- Cada tarea se trabaja en una rama propia; puede quedarse local. Al terminar se fusiona en `main`.
- Después de cada tarea fusionada, subir `main` a GitHub (`git push origin main`) como respaldo.
- No abrir pull requests salvo que el dueño lo pida. Nunca hacer force push a `main`.
- Antes de cada push, revisar que no vayan `.env`, bases locales ni credenciales.
- El JSON de cuenta de servicio de Firebase (el que usa el servidor para enviar notificaciones) es una
  credencial: nunca va al repositorio. Se entrega por variable de entorno o en una ruta fuera del repositorio.

## Reglas de negocio críticas

Están implementadas y probadas en `nucleo/`. Los modelos, vistas y la API **llaman** a esas funciones;
no reimplementan la regla. Si una regla cambia, se cambia en `nucleo/` con su prueba primero.

**Estados del servicio** (`nucleo/estados.py`). Un servicio es un vehículo dentro de una solicitud.
- Pendiente de asignar → Asignado → En camino → Recogido → Entregado. Sin saltos ni retrocesos.
- Cancelado: desde cualquier estado no terminal, con motivo obligatorio. Entregado y Cancelado son terminales.
- Novedad: desde Asignado, En camino o Recogido, con motivo. Es bloqueante, no terminal: recuerda el
  estado previo y solo se sale resolviéndola (reanudar, reasignar o cancelar).
- El estado de la solicitud se deriva de sus servicios; nunca se guarda a mano.
- "No concretada" (nunca se aceptó) es de la solicitud y es distinto de "Cancelado".
- La solicitud incompleta es un "Borrador": no se puede asignar hasta completar los obligatorios.

**Capacidad** (`nucleo/capacidad.py`). Una grúa no lleva más vehículos montados que su capacidad.
- "Montado" es Recogido, o Novedad cuyo estado previo era Recogido (`a_bordo`).
- Se valida en el celular antes de marcar Recogido y se revalida en el servidor.
- Al bloquear, se le muestra al conductor qué vehículo le falta marcar como Entregado.
- A un conductor sí se le pueden asignar más vehículos que su capacidad: los atiende en rondas.

**Cobro por línea** (`nucleo/cobro.py`). El estado de cobro vive en la línea (servicio × pagador), no en el servicio.
- Sin valor → Por facturar → Facturado (número obligatorio) → Pagado. No cobrable aparte.
- Máximo dos pagadores por servicio y las partes suman el total.
- El valor no cambia después de facturar. Anular factura devuelve a Por facturar, con motivo.
- Todo cambio de valor queda en el historial: quién, cuándo y valor anterior.
- El conductor nunca recibe valores: los serializadores de la API no los incluyen.
- Dinero siempre en `Decimal`, nunca `float`.

**Eventos idempotentes** (`nucleo/sincronizacion.py`). Cada toque del conductor es un evento.
- El id (UUID) se genera en el celular. Un evento repetido no se aplica dos veces.
- Lo que el conductor hizo físicamente nunca se rechaza ni se descarta. Si no encaja (servicio cancelado,
  reasignado, salto de estado), el resultado es CONFLICTO: se guarda el evento y se abre una alerta a logística.
- Desde la app solo se aceptan los destinos En camino, Recogido, Entregado y Novedad; cualquier otro
  (por ejemplo, cancelar) es CONFLICTO.
- El orden lo da la secuencia del dispositivo, no su reloj. Se guardan hora del dispositivo y hora de sincronización.
- Los eventos son de solo agregar: no se editan ni se borran.

**Otras reglas fijas**
- Nada se borra: se cancela con motivo. Historial de cambios por registro.
- Placa o VIN, al menos uno; desvare exige placa. VIN: 17 caracteres alfanuméricos sin I, O, Q; sin dígito verificador.
- Documento vencido: bloquea asignaciones nuevas; no interrumpe un servicio en curso.
- Cada servicio guarda el conductor y la grúa con que se hizo; cambiar al conductor de grúa no altera el historial.
- Zona horaria America/Bogota; en base de datos todo en UTC con `USE_TZ`.
- Todo lo que depende del cliente es configuración (ver `docs/arquitectura.md`), nunca una constante en el código.

## Convenciones

- Dominio en español: nombres de modelos, funciones, variables y pruebas (`Servicio`, `verificar_recogida`).
- Los nombres de las pruebas describen la regla: `test_cancelar_exige_motivo`.
- Las vistas son delgadas: validan entrada, llaman al núcleo o a un servicio de la app y responden.
- Carpetas nuevas solo cuando ya hay tres archivos que las piden.
- Dependencias nuevas: agregar con `uv add` o `flutter pub add` (resuelven la versión vigente) y justificar en el informe.
- Secretos solo en `.env`; nunca en el repositorio. Los datos de demo llevan marca propia para poder borrarlos sin tocar los reales.

## Fuera de alcance (no construir sin que el dueño lo pida)

iPhone, publicación en tiendas, portal de clientes, GPS continuo, factura electrónica ante la DIAN,
integración por API con software de facturación, WhatsApp, multiempresa.
