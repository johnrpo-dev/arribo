# Prueba manual del modo sin señal

Se hace en un celular Android real, con el APK instalado y el panel abierto en un computador.
Repetir completa antes de la demo y después de cualquier cambio en la cola o en las fotos.

Preparación: cargar los datos ficticios, iniciar sesión como un conductor con grúa de capacidad 1 y
asignarle tres servicios desde el panel. "Sin señal" es modo avión, con Wi-Fi apagado. Si la app
habla con el computador por el cable USB (en desarrollo), el modo avión no basta: además, desde
`backend/`, correr `uv run python manage.py sin_senal` (quita el túnel USB y lo deja apagado; el
servidor ya no lo recrea) o desconectar el cable. Para "volver a tener señal":
`uv run python manage.py con_senal` (ver `conductor/README.md`).

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

El mínimo de fotos es el de Configuración en el panel (4 por defecto). El servicio debe estar En
camino y su vehículo debe tener placa o VIN.

5. [ ] **Mínimo de fotos.** En el detalle del servicio tocar "Marcar Recogido": se abre la pantalla
   de fotos. Tocar "Tomar foto" tres veces (se abre la cámara del celular; al aceptar cada foto
   aparece su miniatura y dice "Lleva 3 de 4 fotos."), escribir el nombre de quien entrega y tocar
   "Marcar Recogido". Esperado: no deja y dice "Falta 1 foto: lleva 3 de 4.". Borrar el nombre,
   tomar la cuarta foto y tocar "Marcar Recogido": tampoco deja y pide el nombre de quien entrega.
6. [ ] **Fotos sin señal.** En modo avión, con 4 fotos y el nombre escrito, tocar "Marcar
   Recogido". Esperado: vuelve al detalle con el estado Recogido, "Pendiente por enviar" y "4 fotos
   por subir"; arriba de la lista dice "Hay 4 fotos pendientes por subir. Se suben solas cuando haya
   señal." y la tarjeta del servicio tiene la marca "4 fotos por subir".
7. [ ] **Cierre forzado con fotos pendientes.** Sin quitar el modo avión, forzar el cierre de la app y
   reiniciar el celular. Abrir la app. Esperado: las 4 fotos siguen pendientes, ninguna se perdió.
   En el menú, "Cerrar sesión" no deja y explica por qué.
8. [ ] **Subida al volver.** Quitar el modo avión y dejar la app abierta y a la vista (o deslizar la
   lista hacia abajo). Esperado: primero se envía el cambio de estado y enseguida suben las fotos,
   una por una; el aviso de arriba va bajando ("Hay 3 fotos pendientes…") hasta desaparecer junto con
   la marca "fotos por subir" del servicio. En `/admin/` → Solicitudes → Evidencias aparecen las 4
   fotos unidas al evento de Recogido (el panel aún no las muestra). Cortar la señal a mitad de la
   subida y restaurarla: las que faltan suben después (la app reintenta sola cada 30 segundos como
   máximo con la app a la vista) y en Evidencias no queda ninguna repetida. La subida solo avanza
   con la app abierta.
9. [ ] **Capacidad.** Con el primer vehículo Recogido (grúa de capacidad 1), abrir el segundo
   servicio, marcarlo En camino y tocar "Marcar Recogido". Esperado: no abre la pantalla de fotos;
   dice "La grúa va llena" y, bajo "Falta marcar como Entregado:", la placa del primer vehículo.
   Funciona igual en modo avión, también si el Recogido del primero todavía no se ha enviado.
9b. [ ] **La cámara mata la app.** En Ajustes → Opciones de desarrollador activar "No conservar
   actividades". Abrir "Marcar Entregado" en el primer servicio, tomar una foto, escribir medio
   nombre y tocar "Tomar foto" otra vez; tomar la foto y aceptarla. Esperado: la app vuelve a la
   misma pantalla con las dos fotos y el nombre como iba. Desactivar la opción al terminar.
9c. [ ] **Vehículo sin placa, sin señal.** Con "Placa/VIN al recoger" en Configuración (la de
   fábrica), registrar en el panel un traslado sin placa ni VIN, asignarlo a Ana y, en la app,
   marcarlo En camino. Activar el modo avión y tocar "Marcar Recogido". Esperado: se abre la
   pantalla de fotos con "Identificación del vehículo" y los campos Placa y VIN. Con las fotos y el
   nombre pero sin placa ni VIN, "Marcar Recogido" no deja y dice "El vehículo necesita placa o VIN
   (al menos uno).". Escribir una placa y marcar: vuelve al detalle con la placa arriba y
   "Pendiente por enviar"; la lista también la muestra. Quitar el modo avión: en el panel el
   vehículo queda con esa placa. Repetir con la placa de otro vehículo ya registrado: el Recogido
   se aplica igual, el vehículo sigue sin placa y en `/admin/` → Alertas aparece "Placa o VIN
   digitado por revisar".

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
