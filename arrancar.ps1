# Arranca Arribo en el PC para probar con el celular por USB.
#
#   powershell -ExecutionPolicy Bypass -File .\arrancar.ps1
#
# Arranca el panel (runserver) en http://127.0.0.1:8000, o avisa si ya hay uno corriendo.
# El túnel USB del celular (adb reverse) lo mantiene el propio runserver: lo crea al conectar el
# celular y lo recrea solo si se pierde (backend/panel/tunel_usb.py). Da igual arrancar con este
# script o con `uv run python manage.py runserver`.
# Para terminar: Ctrl+C.
param([int]$Puerto = 8000)

$backend = Join-Path $PSScriptRoot "backend"

try {
    $responde = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$Puerto/salud/").StatusCode -eq 200
} catch { $responde = $false }

if ($responde) {
    Write-Host "El panel ya está corriendo en http://127.0.0.1:$Puerto y mantiene el túnel USB del celular."
    exit 0
}

Write-Host "Arrancando el panel en http://127.0.0.1:$Puerto (Ctrl+C para terminar)..."
Set-Location $backend
uv run python manage.py runserver "127.0.0.1:$Puerto"
