# Compila el APK firmado que se instala a los conductores, apuntando al servidor (tarea 1a-21).
# Desde conductor/:
#
#   powershell -ExecutionPolicy Bypass -File .\compilar-apk.ps1 -Servidor https://arribo.suempresa.co
#
# Exige HTTPS (el APK de release no habla http), la llave de firma (crear-llave.ps1) y el
# google-services.json de Firebase. Antes de compilar comprueba que el servidor responda /salud/.
param(
    [Parameter(Mandatory = $true)][string]$Servidor,
    [switch]$SinComprobarServidor
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Servidor = $Servidor.TrimEnd("/")
if ($Servidor -notmatch "^https://[A-Za-z0-9.-]+(:\d+)?$") {
    Write-Host "El servidor va como https://dominio, sin ruta (por ejemplo https://arribo.suempresa.co)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "android\key.properties")) {
    Write-Host "Falta la llave de firma: corra primero .\crear-llave.ps1 (una sola vez)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "android\app\google-services.json")) {
    Write-Host "Falta android\app\google-services.json (consola de Firebase, ver README)." -ForegroundColor Red
    exit 1
}
if (-not $SinComprobarServidor) {
    try {
        $salud = Invoke-RestMethod "$Servidor/salud/" -TimeoutSec 15
    } catch {
        Write-Host "El servidor no responde en $Servidor/salud/. Despliéguelo primero (docs/despliegue.md)." -ForegroundColor Red
        exit 1
    }
    if ($salud.estado -ne "ok") {
        Write-Host "$Servidor/salud/ no respondió como Arribo." -ForegroundColor Red
        exit 1
    }
}

flutter build apk --release "--dart-define=ARRIBO_API=$Servidor"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$version = (Select-String -Path pubspec.yaml -Pattern "^version:\s*(\S+)").Matches[0].Groups[1].Value -replace "\+", "-"
$destino = "build\arribo-conductor-$version.apk"
Copy-Item "build\app\outputs\flutter-apk\app-release.apk" $destino -Force
$huella = (Get-FileHash $destino -Algorithm SHA256).Hash

Write-Host ""
Write-Host "APK listo: $(Resolve-Path $destino)" -ForegroundColor Green
Write-Host "Apunta a:  $Servidor"
Write-Host "SHA-256:   $huella"
