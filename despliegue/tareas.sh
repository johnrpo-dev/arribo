#!/bin/sh
# Tareas de cada minuto: alertas por umbral y reintento de los avisos push pendientes.
# Si una falla, se anota en el registro (`docker compose logs tareas`) y la siguiente vuelta sigue.
set -u
while true; do
    python manage.py evaluar_alertas || echo "evaluar_alertas falló; se reintenta en un minuto"
    python manage.py enviar_notificaciones_pendientes \
        || echo "enviar_notificaciones_pendientes falló; se reintenta en un minuto"
    sleep 60
done
