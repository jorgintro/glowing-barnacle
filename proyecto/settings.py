"""Configuración de Django. Lo sensible se lee del entorno (sin secretos en el repositorio)."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _entorno_bool(nombre: str, defecto: bool) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes"}


DEBUG = _entorno_bool("DJANGO_DEBUG", False)

_CLAVE_DESARROLLO = "inseguro-solo-para-desarrollo"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _CLAVE_DESARROLLO if DEBUG else "")
if not SECRET_KEY or (not DEBUG and SECRET_KEY == _CLAVE_DESARROLLO):
    raise ImproperlyConfigured(
        "Falta DJANGO_SECRET_KEY. Defínela en el entorno "
        "(o activa DJANGO_DEBUG solo en desarrollo)."
    )


def _lista(nombre: str, defecto: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


ALLOWED_HOSTS = _lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Origen(es) desde los que se accede, p. ej. http://192.168.1.50:8000 (necesario tras proxy).
CSRF_TRUSTED_ORIGINS = _lista("DJANGO_CSRF_ORIGENES")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.usuarios",
    "apps.presupuesto",
    "apps.auditoria",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.usuarios.middleware.RolActivoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "proyecto.urls"
WSGI_APPLICATION = "proyecto.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.usuarios.contexto.rol_activo",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "presupuesto"),
        "USER": os.environ.get("POSTGRES_USER", "presupuesto"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "presupuesto" if DEBUG else ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "usuarios.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "usuarios:entrar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "usuarios:entrar"

# Sesiones con caducidad por inactividad (§13.2).
SESION_MINUTOS = int(os.environ.get("SESION_MINUTOS", "30"))
SESSION_COOKIE_AGE = SESION_MINUTOS * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

_COOKIES_SEGURAS = _entorno_bool("COOKIES_SEGURAS", not DEBUG)
SESSION_COOKIE_SECURE = _COOKIES_SEGURAS
CSRF_COOKIE_SECURE = _COOKIES_SEGURAS
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Los importes se escriben y leen en formato español: 1.234,56
USE_THOUSAND_SEPARATOR = True
LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Ficheros de configuración (cuadro de cuentas, parámetros legales, reglas orgánicas).
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", BASE_DIR / "config"))

# Desactívalo (PERMITIR_DATOS_DEMO=0) cuando empieces a trabajar con datos reales.
PERMITIR_DATOS_DEMO = _entorno_bool("PERMITIR_DATOS_DEMO", True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
