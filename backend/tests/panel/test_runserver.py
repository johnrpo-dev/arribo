"""`runserver` en desarrollo aplica las migraciones pendientes antes de atender (pasó que Cobros
fallaba porque su tabla nueva no existía en la base del PC)."""
import pytest
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import get_commands, load_command_class

from panel.management.commands import runserver
from panel.management.commands.runserver import aplicar_pendientes, migraciones_pendientes


def test_runserver_es_el_del_panel_y_sigue_sirviendo_estaticos():
    assert get_commands()["runserver"] == "panel"
    comando = load_command_class("panel", "runserver")
    assert isinstance(comando.get_handler(use_static_handler=True, insecure_serving=True),
                      StaticFilesHandler)


@pytest.mark.django_db
def test_con_la_base_al_dia_no_hay_pendientes():
    assert migraciones_pendientes() == []


def test_si_hay_pendientes_las_aplica_y_lo_dice():
    avisos, migradas = [], []
    aplicar_pendientes(avisos.append, pendientes=lambda: ["cobros.0002_relacion_de_cobro"],
                       migrar=lambda: migradas.append(True))
    assert migradas == [True]
    assert "cobros.0002_relacion_de_cobro" in avisos[0]
    assert avisos[1].startswith("Migraciones aplicadas")


def test_sin_pendientes_no_migra_ni_avisa():
    avisos, migradas = [], []
    aplicar_pendientes(avisos.append, pendientes=list, migrar=lambda: migradas.append(True))
    assert migradas == [] and avisos == []


def test_si_migrar_falla_lo_dice_con_el_comando_y_deja_arrancar():
    def migrar_roto():
        raise RuntimeError("la base no responde")

    avisos = []
    aplicar_pendientes(avisos.append, pendientes=lambda: ["alertas.0003"], migrar=migrar_roto)
    assert "la base no responde" in avisos[-1]
    assert "manage.py migrate" in avisos[-1]


@pytest.mark.parametrize(("debug", "migra"), [(True, True), (False, False)])
def test_migra_solo_en_desarrollo(monkeypatch, settings, debug, migra):
    settings.DEBUG = debug
    llamadas = []
    monkeypatch.setattr(runserver, "aplicar_pendientes", lambda escribir: llamadas.append(1))
    monkeypatch.setattr(runserver.RunserverConEstaticos, "inner_run",
                        lambda self, *a, **k: llamadas.append(2))
    runserver.Command().inner_run()
    assert llamadas == ([1, 2] if migra else [2])
