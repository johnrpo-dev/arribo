"""Túnel USB del celular en desarrollo: el servidor lo mantiene vivo solo.

En desarrollo la app del conductor habla con `http://127.0.0.1:8000`, y el celular llega al PC por
el cable gracias a `adb reverse tcp:8000 tcp:8000`. Ese túnel se pierde cada vez que el cable se
desconecta, el celular se reinicia o adb se reinicia, y antes había que acordarse de volverlo a
crear (o de arrancar con `arrancar.ps1`). Si se arrancaba `manage.py runserver` a secas, la app
decía "No hay conexión con el servidor" aunque el panel estuviera corriendo.

Ahora `runserver` (solo con ARRIBO_DEBUG=1) revisa cada 3 segundos si hay un celular conectado y,
si le falta el túnel, lo crea. Para probar el modo sin señal a propósito, `manage.py sin_senal`
quita el túnel y lo deja apagado hasta `manage.py con_senal` (docs/prueba-sin-senal.md).

En producción no hay túnel: la app apunta al dominio con HTTPS (docs/despliegue.md).
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from django.conf import settings

PUERTO_POR_DEFECTO = 8000
INTERVALO_SEGUNDOS = 3

ESPERANDO = "Esperando el celular: conecte el cable USB y acepte la depuración USB si la pide."
CONECTADO = "Celular conectado: la app llega al panel por el cable (túnel tcp:{puerto})."
RECREADO = "Celular conectado: se volvió a crear el túnel USB (tcp:{puerto})."
SIN_SENAL = "Modo sin señal: el túnel USB está quitado a propósito (manage.py con_senal lo devuelve)."
SIN_ADB = "No se encontró adb: el panel funciona, pero el celular no podrá conectarse por USB."

# (código de salida, salida) de un comando de adb.
Adb = Callable[[list[str]], tuple[int, str]]


def marca_sin_senal() -> Path:
    """Archivo vacío que deja `manage.py sin_senal` (fuera del repositorio, en .gitignore)."""
    return Path(settings.BASE_DIR) / ".sin_senal"


def ruta_adb() -> str | None:
    candidatos = [
        shutil.which("adb"),
        os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "sdk", "platform-tools",
                     "adb.exe"),
    ]
    return next((c for c in candidatos if c and os.path.isfile(c)), None)


def ejecutor_adb(ruta: str) -> Adb:
    def ejecutar(argumentos: list[str]) -> tuple[int, str]:
        try:
            resultado = subprocess.run(
                [ruta, *argumentos], capture_output=True, text=True, timeout=10, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1, ""
        return resultado.returncode, resultado.stdout
    return ejecutar


def puerto_de_runserver(argv: list[str]) -> int | None:
    """El puerto en que escucha `runserver` según su línea de comando, o None si no es runserver.
    Acepta `8000`, `127.0.0.1:8000`, `0.0.0.0:9000` y `[::1]:8000`."""
    if "runserver" not in argv:
        return None
    resto = argv[argv.index("runserver") + 1:]
    direccion = next((a for a in resto if not a.startswith("-")), "")
    puerto = direccion.rsplit(":", 1)[-1]
    return int(puerto) if puerto.isdigit() else PUERTO_POR_DEFECTO


def debe_vigilar(argv: list[str], *, debug: bool, run_main: str | None) -> bool:
    """Solo en desarrollo, solo con runserver y en el proceso que atiende (con recarga automática,
    Django arranca dos procesos: el vigilante va en el hijo, RUN_MAIN=true)."""
    if not debug or puerto_de_runserver(argv) is None:
        return False
    return run_main == "true" or "--noreload" in argv


def revisar(adb: Adb, puerto: int, *, sin_senal: bool) -> str:
    """Una revisión: crea el túnel si hay celular y le falta, o lo quita en modo sin señal.
    Devuelve el estado para mostrarlo en la consola del servidor."""
    codigo, estado = adb(["get-state"])
    if codigo != 0 or estado.strip() != "device":
        return ESPERANDO
    tunel = f"tcp:{puerto} tcp:{puerto}"
    _, tuneles = adb(["reverse", "--list"])
    if sin_senal:
        if tunel in tuneles:
            adb(["reverse", "--remove", f"tcp:{puerto}"])
        return SIN_SENAL
    if tunel in tuneles:
        return CONECTADO.format(puerto=puerto)
    adb(["reverse", f"tcp:{puerto}", f"tcp:{puerto}"])
    return RECREADO.format(puerto=puerto)


def _avisar(texto: str) -> None:
    sys.stdout.write(f"{time.strftime('%H:%M:%S')} {texto}\n")
    sys.stdout.flush()


def vigilar(adb: Adb, puerto: int, *, vueltas: int | None = None,
            esperar: Callable[[float], None] = time.sleep,
            avisar: Callable[[str], None] = _avisar) -> None:
    """Revisa para siempre (o `vueltas` veces, en las pruebas) y avisa solo cuando cambia algo:
    un túnel recreado se avisa siempre; "conectado" no se repite mientras siga conectado."""
    anterior = ""
    hechas = 0
    while vueltas is None or hechas < vueltas:
        try:
            estado = revisar(adb, puerto, sin_senal=marca_sin_senal().exists())
        except Exception as error:  # noqa: BLE001 - el vigilante nunca tumba el servidor
            estado = f"No se pudo revisar el túnel USB: {error}"
        sigue_conectado = estado == CONECTADO.format(puerto=puerto) and anterior.startswith(
            "Celular conectado")
        if estado != anterior and not sigue_conectado:
            avisar(estado)
        anterior = estado
        hechas += 1
        esperar(INTERVALO_SEGUNDOS)


def iniciar_si_corresponde(argv: list[str] | None = None) -> threading.Thread | None:
    """Lo llama `PanelConfig.ready()`. No hace nada fuera de `runserver` en desarrollo."""
    argv = sys.argv if argv is None else argv
    if not debe_vigilar(argv, debug=settings.DEBUG, run_main=os.environ.get("RUN_MAIN")):
        return None
    ruta = ruta_adb()
    if ruta is None:
        _avisar(SIN_ADB)
        return None
    hilo = threading.Thread(
        target=vigilar, args=(ejecutor_adb(ruta), puerto_de_runserver(argv)),
        name="tunel-usb", daemon=True,
    )
    hilo.start()
    return hilo
