"""Despliegue (1a-21): la configuración de producción es segura, los archivos de despliegue llaman a
comandos que existen y ningún secreto entra al repositorio ni a la imagen.

Docker no corre en el PC de desarrollo: lo que se prueba aquí es lo que se puede probar sin él.
La prueba en el servidor real es `/salud/` en el dominio (docs/despliegue.md).
"""
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import get_commands

BACKEND = Path(__file__).resolve().parent.parent
RAIZ = BACKEND.parent
DESPLIEGUE = RAIZ / "despliegue"
DOMINIO = "arribo.ejemplo.co"


def con_entorno_de_produccion(*argumentos, **cambios):
    """Corre Python en un proceso aparte con las variables de producción (los ajustes de Django se
    leen al arrancar, así que no se pueden cambiar dentro de esta misma prueba)."""
    entorno = {
        **os.environ,
        "ARRIBO_DEBUG": "0",
        "ARRIBO_SECRET_KEY": secrets.token_urlsafe(50),
        "ARRIBO_ALLOWED_HOSTS": DOMINIO,
        "PYTHONUTF8": "1",  # mensajes con tildes, también en la consola de Windows
        **cambios,
    }
    return subprocess.run(
        [sys.executable, *argumentos], cwd=BACKEND, env=entorno, capture_output=True,
        text=True, encoding="utf-8", timeout=120, check=False,
    )


def ajustes_de_produccion(**cambios) -> dict:
    codigo = (
        "import json, django; from django.conf import settings; django.setup(); "
        "print(json.dumps({n: getattr(settings, n, None) for n in ("
        "'DEBUG', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'CSRF_TRUSTED_ORIGINS', "
        "'SECURE_PROXY_SSL_HEADER', 'SECURE_HSTS_SECONDS', 'ARRIBO_PERMITIR_RESTABLECER', "
        "'MEDIA_ROOT', 'STATIC_ROOT')}, default=str))"
    )
    resultado = con_entorno_de_produccion(
        "-c", codigo, DJANGO_SETTINGS_MODULE="config.settings", **cambios
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def test_la_revision_de_seguridad_de_django_pasa_en_produccion():
    resultado = con_entorno_de_produccion(
        "manage.py", "check", "--deploy", "--fail-level", "WARNING"
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_en_produccion_las_cookies_viajan_solo_por_https():
    ajustes = ajustes_de_produccion()
    assert ajustes["DEBUG"] is False
    assert ajustes["SESSION_COOKIE_SECURE"] is True
    assert ajustes["CSRF_COOKIE_SECURE"] is True
    assert ajustes["SECURE_HSTS_SECONDS"] > 0
    # Caddy recibe el https y avisa con este encabezado; los formularios se aceptan del dominio.
    assert ajustes["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert ajustes["CSRF_TRUSTED_ORIGINS"] == [f"https://{DOMINIO}"]


def test_en_produccion_no_se_puede_restablecer_datos_de_prueba():
    assert ajustes_de_produccion()["ARRIBO_PERMITIR_RESTABLECER"] is False


def test_fotos_y_estaticos_van_a_las_carpetas_del_servidor():
    ajustes = ajustes_de_produccion(
        ARRIBO_MEDIA_ROOT="/datos/media", ARRIBO_STATIC_ROOT="/datos/estaticos"
    )
    assert Path(ajustes["MEDIA_ROOT"]) == Path("/datos/media")
    assert Path(ajustes["STATIC_ROOT"]) == Path("/datos/estaticos")


@pytest.mark.parametrize(
    ("variable", "mensaje"),
    [("ARRIBO_ALLOWED_HOSTS", "ARRIBO_ALLOWED_HOSTS"), ("ARRIBO_SECRET_KEY", "ARRIBO_SECRET_KEY")],
)
def test_produccion_no_arranca_sin_dominio_ni_clave(variable, mensaje):
    cambios = {variable: ""}
    if variable == "ARRIBO_SECRET_KEY":
        cambios[variable] = "solo-para-desarrollo-no-usar-en-produccion"
    resultado = con_entorno_de_produccion("manage.py", "check", **cambios)
    assert resultado.returncode != 0
    assert mensaje in resultado.stderr


def test_los_scripts_del_servidor_llaman_comandos_que_existen():
    comandos = set(get_commands())
    usados = set()
    for script in DESPLIEGUE.glob("*.sh"):
        usados |= set(re.findall(r"manage\.py (\w+)", script.read_text(encoding="utf-8")))
    assert {"migrate", "collectstatic", "evaluar_alertas",
            "enviar_notificaciones_pendientes"} <= usados
    assert usados <= comandos, f"Comandos que no existen: {usados - comandos}"


def test_el_servidor_corre_con_gunicorn_sobre_la_aplicacion_de_django():
    servidor = (DESPLIEGUE / "servidor.sh").read_text(encoding="utf-8")
    assert "gunicorn config.wsgi:application" in servidor
    assert (BACKEND / "config" / "wsgi.py").exists()


def test_la_comprobacion_del_servidor_usa_la_ruta_de_salud(client):
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/salud/" in compose
    assert "/salud/" in (DESPLIEGUE / "desplegar.sh").read_text(encoding="utf-8")
    assert client.get("/salud/").json() == {"estado": "ok", "servicio": "arribo"}


def test_el_usuario_del_servidor_es_el_que_dice_la_guia():
    """La guía le entrega la carpeta de secretos al usuario 10001: la imagen debe usar ese."""
    assert "--uid 10001" in (DESPLIEGUE / "Dockerfile").read_text(encoding="utf-8")
    assert "chown -R 10001 /opt/arribo/secretos" in (
        RAIZ / "docs" / "despliegue.md").read_text(encoding="utf-8")


def test_los_scripts_del_servidor_tienen_fin_de_linea_unix():
    for archivo in [*DESPLIEGUE.glob("*.sh"), DESPLIEGUE / "Caddyfile",
                    DESPLIEGUE / "Dockerfile"]:
        assert b"\r\n" not in archivo.read_bytes(), f"{archivo.name} tiene CRLF"


def git(*argumentos):
    return subprocess.run(["git", *argumentos], cwd=RAIZ, capture_output=True, text=True,
                          check=False)


@pytest.mark.parametrize("ruta", [
    "despliegue/.env",
    "backend/.env",
    "conductor/android/key.properties",
    "conductor/android/app/google-services.json",
    "arribo-conductor.jks",
    "despliegue/respaldos/arribo-2026-11-18.dump",
    "cuenta-de-servicio-firebase-adminsdk-x.json",
])
def test_los_secretos_y_respaldos_no_entran_al_repositorio(ruta):
    assert git("check-ignore", "-q", ruta).returncode == 0, f"{ruta} no está en .gitignore"


def test_las_plantillas_de_entorno_si_entran_al_repositorio():
    for ruta in ("despliegue/.env.ejemplo", "backend/.env.example"):
        assert git("check-ignore", "-q", ruta).returncode == 1, f"{ruta} quedó ignorada"


def test_la_plantilla_de_produccion_no_trae_secretos():
    for linea in (DESPLIEGUE / ".env.ejemplo").read_text(encoding="utf-8").splitlines():
        if linea.startswith(("ARRIBO_SECRET_KEY=", "POSTGRES_PASSWORD=")):
            assert linea.endswith("="), f"La plantilla trae un valor: {linea.split('=')[0]}"


def test_la_imagen_no_lleva_entornos_ni_datos_locales():
    excluidos = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for patron in ("**/.env", "**/.env.*", "backend/media", "conductor", ".git"):
        assert patron in excluidos
