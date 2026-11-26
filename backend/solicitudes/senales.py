"""Señales que `solicitudes` envía a otras apps sin importarlas.

Todas se envían con `send` (no `send_robust`) desde `solicitudes/operaciones.py`: si un receptor
falla, la excepción sube y la transacción en curso se deshace entera.

`servicio_entregado`: desde el punto único donde se aplica un cambio de estado, dentro de su
transacción y con la fila del servicio bloqueada. Si el receptor falla, el servicio no queda
Entregado y no se guarda el evento. Argumentos: `servicio` (ya guardado como Entregado) y `actor`
(el usuario del panel, o None si el cambio vino de la app del conductor). La escucha `cobros`.

`evento_del_conductor_guardado`: cada vez que se guarda un evento de la app (aplicado o en
conflicto), en la misma transacción que el evento. Argumentos: `evento` (el EventoEstado),
`montados` (los vehículos que la grúa ya llevaba, si el Recogido excedió la capacidad),
`sin_finalizar` (los servicios que el conductor tenía iniciados sin finalizar, si el En camino
excedió la capacidad de la grúa) e
`identificacion_por_revisar` (los `nucleo.identificacion.DatoPorRevisar` de la placa o el VIN que
el conductor digitó al recoger y que no quedaron en el vehículo; vacío si no hay). La escucha
`alertas`: si la alerta no se puede abrir, el evento no se guarda y el celular lo reenvía.

`evento_del_conductor_rechazado`: un evento de la app que no se pudo guardar (id reutilizado con
otro contenido, servicio que no existe, datos ilegibles). Argumentos: `conductor`, `motivo`
(`nucleo.sincronizacion.Motivo`), `contenido` (lo que llegó) y `original` (el EventoEstado que ya
tenía ese id, o None). La escucha `alertas`.

`servicio_asignado`: al asignar o reasignar un servicio desde el panel, dentro de su transacción y
con la fila del servicio bloqueada. Argumentos: `servicio` (ya guardado con su conductor nuevo) y
`conductor_anterior` (el que lo tenía, al reasignar; None al asignar). La escucha `api`, que
encola en la misma transacción los avisos push a los conductores (1a-14). A diferencia de las
otras, su receptor no deja que una falla suya deshaga la asignación: la atrapa y la registra.
"""
from django.dispatch import Signal

servicio_entregado = Signal()
evento_del_conductor_guardado = Signal()
evento_del_conductor_rechazado = Signal()
servicio_asignado = Signal()
