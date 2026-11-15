# Arranca Arribo en el PC para probar con el celular por USB.
#
#   powershell -ExecutionPolicy Bypass -File .\arrancar.ps1
#
# Hace dos cosas y las mantiene mientras esta ventana esté abierta:
#   1. El panel (runserver) en http://127.0.0.1:8000. Si ya hay uno corriendo, lo usa.
#   2. El túnel USB del celular (adb reverse tcp:8000 tcp:8000). El túnel se pierde cada vez que el
#      celular se desconecta, se bloquea o adb se reinicia; aquí se revisa cada 3 segundos y se
#      vuelve a crear solo.
# Para terminar: Ctrl+C (cierra el panel si lo abrió este script).
param([int]$Puerto = 8000)

$ErrorActionPreference = "Continue"
$adb = Join-Path $env:LOCALAPPDATA "Android\sdk\platform-tools\adb.exe"
$backend = Join-Path $PSScriptRoot "backend"

function Hora { Get-Date -Format "HH:mm:ss" }

function Servidor-Responde {
    try {
        (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$Puerto/salud/").StatusCode -eq 200
    } catch { $false }
}

$servidor = $null
if (Servidor-Responde) {
    Write-Host "$(Hora) El panel ya estaba corriendo en http://127.0.0.1:$Puerto (se usa ese)."
} else {
    Write-Host "$(Hora) Arrancando el panel en http://127.0.0.1:$Puerto ..."
    $servidor = Start-Process -FilePath "uv" -WorkingDirectory $backend -NoNewWindow -PassThru `
        -ArgumentList "run", "python", "manage.py", "runserver", "127.0.0.1:$Puerto"
}

if (-not (Test-Path $adb)) {
    Write-Host "$(Hora) No se encontró adb en $adb. El panel funciona, pero el celular no podrá conectarse por USB."
}

$estadoAnterior = ""
try {
    while ($true) {
        if ($servidor -and $servidor.HasExited) {
            Write-Host "$(Hora) El panel se detuvo (revise el error de arriba)."
            break
        }
        if (Test-Path $adb) {
            $conectado = ((& $adb get-state 2>$null) -eq "device")
            if ($conectado) {
                $tuneles = (& $adb reverse --list 2>$null) -join "`n"
                if ($tuneles -notmatch "tcp:$Puerto tcp:$Puerto") {
                    & $adb reverse "tcp:$Puerto" "tcp:$Puerto" | Out-Null
                }
                $estado = "Celular conectado: la app ya llega al panel."
            } else {
                $estado = "Esperando el celular: conecte el cable USB y acepte la depuración USB si la pide."
            }
            if ($estado -ne $estadoAnterior) {
                Write-Host "$(Hora) $estado"
                $estadoAnterior = $estado
            }
        }
        Start-Sleep -Seconds 3
    }
} finally {
    if ($servidor -and -not $servidor.HasExited) {
        Write-Host "$(Hora) Cerrando el panel..."
        & taskkill /T /F /PID $servidor.Id | Out-Null
    }
}
