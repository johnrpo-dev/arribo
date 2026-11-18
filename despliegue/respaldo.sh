#!/bin/sh
# Respaldo diario de la base: un archivo comprimido por día en la carpeta de respaldos del servidor
# (ARRIBO_RESPALDOS), y se guardan los últimos 14. Las fotos y documentos están en el volumen
# `media`: su copia fuera del servidor y la restauración probada son de la fase 3.
set -u
while true; do
    # Formato propio de PostgreSQL, ya comprimido; se restaura con pg_restore.
    archivo="/respaldos/arribo-$(date +%Y-%m-%d).dump"
    if pg_dump --format=custom --no-owner --file="$archivo.tmp"; then
        mv "$archivo.tmp" "$archivo"
        echo "Respaldo listo: $archivo"
    else
        rm -f "$archivo.tmp"
        echo "El respaldo falló; se reintenta en una hora"
        sleep 3600
        continue
    fi
    ls -1t /respaldos/arribo-*.dump | tail -n +15 | xargs -r rm -f
    sleep 86400
done
