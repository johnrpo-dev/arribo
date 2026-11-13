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

LOGIN_URL = "ingresar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "ingresar"

STATIC_URL = "static/"
# Fotos de evidencia en el disco del servidor durante la fase 1a (fuera del repositorio).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
