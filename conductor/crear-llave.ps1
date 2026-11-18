# Crea la llave con la que se firma el APK de los conductores (tarea 1a-21). Se corre UNA sola vez,
# en el PC donde se compila, desde conductor/:
#
#   powershell -ExecutionPolicy Bypass -File .\crear-llave.ps1
#
# Deja el archivo de la llave (.jks) FUERA del repositorio y escribe android/key.properties (que
# tampoco se sube) con su ruta y su clave. Guarde una copia del .jks y de la clave fuera del PC:
# si se pierden, un APK nuevo no se puede instalar encima del anterior y hay que desinstalar la app
# en cada celular (y con ella, lo que tenga sin sincronizar).
param(
    [string]$Destino = (Join-Path $env:USERPROFILE "Documents\arribo\arribo-conductor.jks")
)
$ErrorActionPreference = "Stop"
$propiedades = Join-Path $PSScriptRoot "android\key.properties"

if (Test-Path $propiedades) {
    Write-Host "Ya existe android\key.properties: la llave ya está creada. No se cambia." -ForegroundColor Yellow
    exit 1
}
if (Test-Path $Destino) {
    Write-Host "Ya existe $Destino. No se sobrescribe una llave." -ForegroundColor Yellow
    exit 1
}

$keytool = @(
    $(if ($env:JAVA_HOME) { Join-Path $env:JAVA_HOME "bin\keytool.exe" }),
    "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $keytool) {
    Write-Host "No se encontró keytool (viene con Android Studio)." -ForegroundColor Red
    exit 1
}

function Leer-Clave($texto) {
    $segura = Read-Host $texto -AsSecureString
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))
}
$clave = Leer-Clave "Clave de la llave (mínimo 8 caracteres, sin espacios)"
if ($clave.Length -lt 8 -or $clave -match "\s") {
    Write-Host "La clave debe tener al menos 8 caracteres y no llevar espacios." -ForegroundColor Red
    exit 1
}
if ((Leer-Clave "Repita la clave") -ne $clave) {
    Write-Host "Las claves no coinciden." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force (Split-Path $Destino) | Out-Null
& $keytool -genkeypair -keystore $Destino -storetype PKCS12 -keyalg RSA -keysize 2048 `
    -validity 10000 -alias arribo -dname "CN=Arribo conductor, O=Arribo, C=CO" `
    -storepass $clave -keypass $clave
if ($LASTEXITCODE -ne 0) {
    Write-Host "keytool no pudo crear la llave." -ForegroundColor Red
    exit 1
}

$ruta = $Destino -replace "\\", "/"
@(
    "storeFile=$ruta",
    "storePassword=$clave",
    "keyAlias=arribo",
    "keyPassword=$clave"
) | Set-Content -Encoding ascii $propiedades

Write-Host ""
Write-Host "Llave creada en $Destino" -ForegroundColor Green
Write-Host "Guarde una copia de ese archivo y de la clave fuera de este PC (por ejemplo, en su gestor de contraseñas)."
