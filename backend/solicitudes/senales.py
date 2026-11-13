"""Señales que `solicitudes` envía a otras apps sin importarlas.

Todas se envían con `send` (no `send_robust`) desde `solicitudes/operaciones.py`: si un receptor
falla, la excepción sube y la transacción en curso se deshace entera.

`servicio_entregado`: desde el punto único donde se aplica un cambio de estado, dentro de su
transacción y con la fila del servicio bloqueada. Si el receptor falla, el servicio no queda
Entregado y no se guarda el evento. Argumentos: `servicio` (ya guardado como Entregado) y `actor`
(el usuario del panel, o None si el cambio vino de la app del conductor). La escucha `cobros`.

`evento_del_conductor_guardado`: cada vez que se guarda un evento de la app (aplicado o en
conflicto), en la misma transacción que el evento. Argumentos: `evento` (el EventoEstado) y
`montados` (los vehículos que la grúa ya llevaba, si el Recogido excedió la capacidad). La escucha
`alertas`: si la alerta no se puede abrir, el evento no se guarda y el celular lo reenvía.

`evento_del_conductor_rechazado`: un evento de la app que no se pudo guardar (id reutilizado con
otro contenido, servicio que no existe, datos ilegibles). Argumentos: `conductor`, `motivo`
(`nucleo.sincronizacion.Motivo`), `contenido` (lo que llegó) y `original` (el EventoEstado que ya
tenía ese id, o None). La escucha `alertas`.
"""
from django.dispatch import Signal

servicio_entregado = Signal()
evento_del_conductor_guardado = Signal()
evento_del_conductor_rechazado = Signal()
