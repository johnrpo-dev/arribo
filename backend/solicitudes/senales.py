"""Señales que `solicitudes` envía a otras apps sin importarlas.

`servicio_entregado` se envía con `send` (no `send_robust`) desde el punto único donde
`solicitudes/operaciones.py` aplica un cambio de estado, dentro de su transacción y con la fila del
servicio bloqueada. Si un receptor falla, la excepción sube y la transacción entera se deshace: el
servicio no queda Entregado y no se guarda el evento.

Argumentos: `servicio` (ya guardado como Entregado) y `actor` (el usuario del panel, o None si el
cambio vino de la app del conductor).
"""
from django.dispatch import Signal

servicio_entregado = Signal()
