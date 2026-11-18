"""Configuración de Django. Todo lo que cambia entre entornos sale de variables de entorno."""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("ARRIBO_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("ARRIBO_SECRET_KEY", "solo-para-desarrollo-no-usar-en-produccion")
if not DEBUG and SECRET_KEY.startswith("solo-para-desarrollo"):
    raise RuntimeError("Falta ARRIBO_SECRET_KEY en producción")

ALLOWED_HOSTS = [h for h in os.environ.get("ARRIBO_ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "flota",
    "clientes",
    "solicitudes",
    "cobros",
    "configuracion",
    "alertas",
    "documentos",
    "panel",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "plantillas"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "panel.contexto.navegacion",
            ],
        },
    },
]

# Solo PostgreSQL, también en desarrollo y en pruebas: no hay respaldo a SQLite a propósito,
# para que ninguna prueba pase sobre un motor distinto al de producción.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise RuntimeError("Falta DATABASE_URL de PostgreSQL en backend/.env (ver .env.example)")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=60)}

# Contraseñas de los usuarios de oficina (pantalla "Flota y personal", 1a-08b): los validadores
# estándar de Django, con sus mensajes en español. El conductor no tiene contraseña (celular y PIN).
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# API de la app del conductor (`api/`, contrato en docs/api-conductor.md): solo JSON y solo el token
# de celular, sin la sesión del panel. Toda vista exige un conductor habilitado salvo el ingreso.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["api.autenticacion.TokenDeCelular"],
    "DEFAULT_PERMISSION_CLASSES": ["api.autenticacion.EsConductor"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "api.errores.manejar_excepcion",
}

# Push al conductor (1a-14): ruta completa al JSON de la cuenta de servicio de Firebase, fuera del
# repositorio (es una credencial). Vacía = el servidor funciona igual y no envía avisos push.
ARRIBO_FIREBASE_CREDENCIALES = os.environ.get("ARRIBO_FIREBASE_CREDENCIALES", "").strip()

# Botón "Restablecer datos de prueba" en Configuración. Por defecto activo en desarrollo y apagado
# en producción (ARRIBO_DEBUG=0); se puede forzar con 1 o 0.
ARRIBO_PERMITIR_RESTABLECER = (
    os.environ.get("ARRIBO_PERMITIR_RESTABLECER", "").strip() or ("1" if DEBUG else "0")
) == "1"

LOGIN_URL = "ingresar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "ingresar"

STATIC_URL = "static/"
# `collectstatic` deja aquí los estáticos; en el servidor los entrega Caddy (despliegue/Caddyfile).
STATIC_ROOT = Path(os.environ.get("ARRIBO_STATIC_ROOT", "") or BASE_DIR / "estaticos")
# Fotos de evidencia y documentos en el disco del servidor durante la fase 1a (fuera del
# repositorio). En el servidor es un volumen de Docker que sobrevive a cada despliegue.
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("ARRIBO_MEDIA_ROOT", "") or BASE_DIR / "media")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Producción (ARRIBO_DEBUG=0, tarea 1a-21) ---------------------------------------------------
# El servidor queda detrás de Caddy, que recibe el HTTPS, renueva el certificado y redirige http a
# https. Django confía en el encabezado que pone Caddy para saber que la petición vino cifrada.
if not DEBUG:
    if not ALLOWED_HOSTS:
        raise RuntimeError("Falta ARRIBO_ALLOWED_HOSTS en producción (el dominio del panel)")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # La redirección a https la hace Caddy; en Django chocaría con la comprobación interna de
    # /salud/ que hace Docker por http dentro del servidor.
    SECURE_SSL_REDIRECT = False
    # W005 y W021: HSTS solo para este dominio, sin subdominios ni lista de precarga, para no atar
    # a https otros sitios que el dueño tenga en el mismo dominio.
    SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W005", "security.W021"]
    # Un día al principio: si el dominio cambia, el navegador no queda atado un año a https.
    SECURE_HSTS_SECONDS = int(os.environ.get("ARRIBO_HSTS_SEGUNDOS", "86400"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Registro a la salida estándar: Docker lo guarda (`docker compose logs web`).
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"consola": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["consola"], "level": "INFO"},
    }
