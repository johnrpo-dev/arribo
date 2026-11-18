#!/bin/sh
# Despliegue de Arribo en el VPS. Se corre en el servidor, desde la carpeta despliegue/:
#   ./desplegar.sh
# Trae lo último de main, reconstruye la imagen, levanta los servicios (las migraciones corren al
# arrancar el servidor web) y comprueba /salud/ por HTTPS en el dominio.
set -eu
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "Falta despliegue/.env: copie .env.ejemplo a .env y complételo (ver docs/despliegue.md)."
    exit 1
fi
dominio=$(sed -n 's/^ARRIBO_DOMINIO=//p' .env)
if [ -z "$dominio" ]; then
    echo "Falta ARRIBO_DOMINIO en despliegue/.env."
    exit 1
fi

git pull --ff-only origin main
docker compose build
docker compose up -d --wait
docker image prune -f > /dev/null

echo "Comprobando https://$dominio/salud/ ..."
intentos=0
until curl -fsS "https://$dominio/salud/"; do
    intentos=$((intentos + 1))
    if [ "$intentos" -ge 30 ]; then
        echo
        echo "No responde. Revise: docker compose logs caddy web"
        exit 1
    fi
    sleep 5
done
echo
echo "Arribo desplegado en https://$dominio/"
