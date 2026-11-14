# Prueba manual del modo sin señal

Se hace en un celular Android real, con el APK instalado y el panel abierto en un computador.
Repetir completa antes de la demo y después de cualquier cambio en la cola o en las fotos.

Preparación: cargar los datos ficticios, iniciar sesión como un conductor con grúa de capacidad 1 y
asignarle tres servicios desde el panel. "Sin señal" es modo avión, con Wi-Fi apagado. Si la app
habla con el computador por el cable USB (`adb reverse`, en desarrollo), el modo avión no basta:
además hay que quitar el túnel (`adb.exe reverse --remove-all`) o desconectar el cable; para
"volver a tener señal", repetir `adb.exe reverse tcp:8000 tcp:8000` (ver `conductor/README.md`).

Anotar en cada punto: fecha, versión del APK y resultado.

## Estados

1. [ ] **Lista sin señal.** Con señal, abrir la app y ver los tres servicios. Activar modo avión, cerrar
   la app del todo y abrirla. Esperado: la lista aparece igual, con teléfonos y direcciones.
2. [ ] **Cambio de estado sin señal.** En modo avión, abrir el primer servicio, tocar "Marcar En
   camino" y confirmar ("Sí, marcar En camino"). Esperado: el estado cambia de inmediato a En camino
   con la marca "Pendiente por enviar" (en el detalle y en la tarjeta de la lista), el botón pasa a
   ser "Marcar Recogido" y arriba de la lista dice "Hay 1 cambio pendiente por enviar". El panel aún
   muestra Asignado. Cerrar la app del todo y abrirla: sigue En camino y pendiente. En el menú,
   "Cerrar sesión" no deja y explica por qué.
3. [ ] **Sincronización al volver.** Quitar el modo avión y dejar la app abierta y a la vista.
   Esperado: en menos de un minuto (la app reintenta sola cada 30 segundos como máximo; deslizar la
   lista hacia abajo lo envía de inmediato) desaparecen "Pendiente por enviar" y el aviso de arriba, y
   el panel muestra En camino, con la hora del celular y la hora de sincronización distintas. Con la
   app en segundo plano el envío puede esperar hasta que se vuelva a abrir.
4. [ ] **Sin duplicados.** En modo avión marcar un estado, quitar el modo avión y volver a activarlo
   varias veces mientras sincroniza (deslizando la lista para forzar envíos). Esperado: el historial
   del servicio (en `/admin/` → Solicitudes → Eventos de estado, mientras el panel no lo muestre)
   tiene un solo evento por estado, y en Alertas no aparece ningún conflicto.

## Fotos

5. [ ] **Mínimo de fotos.** Intentar marcar Recogido con 3 fotos. Esperado: no deja y dice cuántas faltan.
6. [ ] **Fotos sin señal.** En modo avión, marcar Recogido con 4 fotos y nombre. Esperado: el estado
   cambia y las fotos quedan como "pendientes por subir".
7. [ ] **Cierre forzado con fotos pendientes.** Sin quitar el modo avión, forzar el cierre de la app y
   reiniciar el celular. Abrir la app. Esperado: las 4 fotos siguen pendientes, ninguna se perdió.
8. [ ] **Subida al volver.** Quitar el modo avión. Esperado: las fotos llegan al panel; mientras suben,
   el servicio muestra "evidencia pendiente". Cortar la señal a mitad de la subida y restaurarla: la subida continúa.
9. [ ] **Capacidad.** Con el primer vehículo Recogido, intentar marcar Recogido en el segundo.
   Esperado: la app lo bloquea y muestra cuál vehículo falta marcar como Entregado. Funciona igual en modo avión.

## Conflictos

10. [ ] **Cancelado mientras estaba sin señal.** Con el celular en modo avión, cancelar desde el panel un
    servicio asignado. En el celular, marcarlo "En camino". Quitar el modo avión. Esperado: el servicio sigue
    Cancelado, el evento queda guardado en su historial y logística ve una alerta de conflicto. La app muestra el servicio como cancelado.
11. [ ] **Reasignado mientras estaba sin señal.** Igual que el anterior, reasignando a otro conductor.
    Esperado: alerta de conflicto; el servicio desaparece de la lista del primer conductor.
12. [ ] **Hora del celular mal puesta.** Atrasar un día el reloj del celular y marcar dos estados seguidos
    sin señal. Esperado: el panel los muestra en el orden en que se tocaron y marca la diferencia de hora.

## Jornada larga

13. [ ] **Horas sin señal.** Dejar el celular en modo avión al menos 3 horas, completando dos servicios
    enteros (8 fotos cada uno). Esperado: al volver la señal todo sube sin intervención.
14. [ ] **Carretera real.** Repetir el punto 13 en un trayecto con señal intermitente, sin modo avión.
15. [ ] **Batería y almacenamiento.** Con menos del 15 % de batería y el ahorro de energía activo, repetir
    el punto 6. Esperado: nada se pierde, aunque la subida espere.

## Push (con señal)

16. [ ] **Asignación.** Con la app cerrada, asignar un servicio desde el panel. Esperado: el celular suena
    y, al abrir la notificación, aparece el servicio. El panel marca "visto por el conductor".
17. [ ] **Asignación sin señal.** Con el celular en modo avión, asignar un servicio. Esperado: el panel lo
    muestra como "no visto". Al volver la señal, llega la notificación.

Si un punto falla, no se presenta la demo hasta corregirlo y repetir la lista completa.
