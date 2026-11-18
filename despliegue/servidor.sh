#!/bin/sh
# Arranque del servidor web: aplica migraciones, junta los estáticos y levanta gunicorn.
# Las migraciones de Django son idempotentes: en un despliegue sin cambios no hacen nada.
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
# gthread: los hilos atienden otras peticiones mientras una foto sube despacio con mala señal.
# El tiempo máximo supera los 2 minutos que la app espera por una foto (conductor/lib/api.dart).
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class gthread --workers 3 --threads 4 \
    --timeout 150 \
    --access-logfile - --error-logfile -
