"""Túnel USB del celular en desarrollo (panel/tunel_usb.py): `runserver` lo crea si falta, lo deja
quitado en modo sin señal y no hace nada fuera de desarrollo. Con un adb falso: no hace falta
celular ni Android SDK."""
from io import StringIO

import pytest
from django.core.management import call_command

from panel import tunel_usb
from panel.tunel_usb import (
    CONECTADO,
    ESPERANDO,
    RECREADO,
    SIN_SENAL,
    debe_vigilar,
    puerto_de_runserver,
    revisar,
    vigilar,
)


class AdbFalso:
    """Simula adb: un celular conectado o no y la lista de túneles."""

    def __init__(self, *, conectado=True, tuneles=()):
        self.conectado = conectado
        self.tuneles = set(tuneles)
        self.llamadas = []

    def __call__(self, argumentos):
        self.llamadas.append(argumentos)
        if argumentos == ["get-state"]:
            return (0, "device\n") if self.conectado else (1, "")
        if argumentos == ["reverse", "--list"]:
            return 0, "".join(f"UsbFfs {t} {t}\n" for t in sorted(self.tuneles))
        if argumentos[:2] == ["reverse", "--remove"]:
            self.tuneles.discard(argumentos[2])
            return 0, ""
        if argumentos[0] == "reverse":
            self.tuneles.add(argumentos[1])
            return 0, ""
        raise AssertionError(argumentos)


@pytest.fixture(autouse=True)
def marca_en_carpeta_temporal(tmp_path, settings):
    settings.BASE_DIR = tmp_path


# --- Cuándo vigila -------------------------------------------------------------------------------


@pytest.mark.parametrize(("argv", "puerto"), [
    (["manage.py", "runserver"], 8000),
    (["manage.py", "runserver", "9000"], 9000),
    (["manage.py", "runserver", "127.0.0.1:8001"], 8001),
    (["manage.py", "runserver", "--noreload", "0.0.0.0:8002"], 8002),
    (["manage.py", "runserver", "[::1]:8003"], 8003),
    (["manage.py", "migrate"], None),
])
def test_el_puerto_sale_de_la_linea_de_runserver(argv, puerto):
    assert puerto_de_runserver(argv) == puerto


def test_vigila_solo_runserver_en_desarrollo_y_en_el_proceso_que_atiende():
    runserver = ["manage.py", "runserver"]
    assert debe_vigilar(runserver, debug=True, run_main="true")
    assert debe_vigilar([*runserver, "--noreload"], debug=True, run_main=None)
    assert not debe_vigilar(runserver, debug=True, run_main=None)  # el proceso que recarga
    assert not debe_vigilar(runserver, debug=False, run_main="true")  # producción
    assert not debe_vigilar(["manage.py", "migrate"], debug=True, run_main="true")
    assert not debe_vigilar(["pytest"], debug=True, run_main="true")


def test_fuera_de_runserver_no_arranca_nada(settings):
    settings.DEBUG = True
    assert tunel_usb.iniciar_si_corresponde(["manage.py", "check"]) is None


# --- Una revisión --------------------------------------------------------------------------------


def test_si_falta_el_tunel_lo_crea():
    adb = AdbFalso(tuneles=())
    assert revisar(adb, 8000, sin_senal=False) == RECREADO.format(puerto=8000)
    assert "tcp:8000" in adb.tuneles


def test_si_el_tunel_ya_esta_no_lo_toca():
    adb = AdbFalso(tuneles={"tcp:8000"})
    assert revisar(adb, 8000, sin_senal=False) == CONECTADO.format(puerto=8000)
    assert ["reverse", "tcp:8000", "tcp:8000"] not in adb.llamadas


def test_sin_celular_espera_y_no_llama_a_reverse():
    adb = AdbFalso(conectado=False)
    assert revisar(adb, 8000, sin_senal=False) == ESPERANDO
    assert adb.llamadas == [["get-state"]]


def test_en_modo_sin_senal_quita_el_tunel_y_no_lo_recrea():
    adb = AdbFalso(tuneles={"tcp:8000"})
    assert revisar(adb, 8000, sin_senal=True) == SIN_SENAL
    assert "tcp:8000" not in adb.tuneles
    assert revisar(adb, 8000, sin_senal=True) == SIN_SENAL
    assert "tcp:8000" not in adb.tuneles


def test_otro_tunel_del_celular_no_cuenta_como_el_del_panel():
    adb = AdbFalso(tuneles={"tcp:5037"})
    assert revisar(adb, 8000, sin_senal=False) == RECREADO.format(puerto=8000)


# --- Vigilar en el tiempo ------------------------------------------------------------------------


def test_cuando_el_cable_se_desconecta_y_vuelve_el_tunel_se_recrea_solo():
    adb = AdbFalso(tuneles={"tcp:8000"})
    avisos = []
    vueltas = iter(range(10))

    def esperar(_segundos):
        n = next(vueltas)
        if n == 0:  # se desconecta el cable: el celular olvida el túnel
            adb.conectado = False
            adb.tuneles.clear()
        elif n == 1:  # vuelve a conectarse
            adb.conectado = True

    vigilar(adb, 8000, vueltas=4, esperar=esperar, avisar=avisos.append)

    assert "tcp:8000" in adb.tuneles
    assert avisos == [CONECTADO.format(puerto=8000), ESPERANDO, RECREADO.format(puerto=8000)]


def test_un_error_de_adb_no_tumba_al_vigilante():
    def adb_roto(_argumentos):
        raise OSError("adb se cerró")

    avisos = []
    vigilar(adb_roto, 8000, vueltas=2, esperar=lambda _s: None, avisar=avisos.append)
    assert avisos == ["No se pudo revisar el túnel USB: adb se cerró"]


# --- Comandos sin_senal y con_senal --------------------------------------------------------------


@pytest.fixture
def adb_de_comandos(monkeypatch):
    adb = AdbFalso(tuneles={"tcp:8000"})
    monkeypatch.setattr(tunel_usb, "ruta_adb", lambda: "adb")
    monkeypatch.setattr(tunel_usb, "ejecutor_adb", lambda _ruta: adb)
    return adb


def test_sin_senal_quita_el_tunel_y_deja_la_marca(adb_de_comandos):
    call_command("sin_senal", stdout=StringIO())
    assert tunel_usb.marca_sin_senal().exists()
    assert "tcp:8000" not in adb_de_comandos.tuneles
    # El vigilante respeta la marca: no lo vuelve a crear.
    vigilar(adb_de_comandos, 8000, vueltas=2, esperar=lambda _s: None, avisar=lambda _t: None)
    assert "tcp:8000" not in adb_de_comandos.tuneles


def test_con_senal_quita_la_marca_y_crea_el_tunel_al_momento(adb_de_comandos):
    call_command("sin_senal", stdout=StringIO())
    salida = StringIO()
    call_command("con_senal", stdout=salida)
    assert not tunel_usb.marca_sin_senal().exists()
    assert "tcp:8000" in adb_de_comandos.tuneles
    assert "Señal devuelta" in salida.getvalue()
