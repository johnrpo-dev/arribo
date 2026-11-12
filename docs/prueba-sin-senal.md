# Prueba manual del modo sin señal

Se hace en un celular Android real, con el APK instalado y el panel abierto en un computador.
Repetir completa antes de la demo y después de cualquier cambio en la cola o en las fotos.

Preparación: cargar los datos ficticios, iniciar sesión como un conductor con grúa de capacidad 1 y
asignarle tres servicios desde el panel. "Sin señal" es modo avión, con Wi-Fi apagado.

Anotar en cada punto: fecha, versión del APK y resultado.

## Estados

1. [ ] **Lista sin señal.** Con señal, abrir la app y ver los tres servicios. Activar modo avión, cerrar
   la app del todo y abrirla. Esperado: la lista aparece igual, con teléfonos y direcciones.
2. [ ] **Cambio de estado sin señal.** En modo avión, marcar "En camino" en el primer servicio.
   Esperado: el botón responde de inmediato y aparece "pendiente por enviar". El panel aún muestra Asignado.
3. [ ] **Sincronización al volver.** Quitar el modo avión. Esperado: en menos de un minuto desaparece
   "pendiente por enviar" y el panel muestra En camino, con la hora del celular y la hora de sincronización distintas.
4. [ ] **Sin duplicados.** En modo avión marcar un estado, quitar el modo avión y volver a activarlo
   varias veces mientras sincroniza. Esperado: el historial del servicio en el panel tiene un solo evento por estado.

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
