"""Configuración para las pruebas automáticas (nunca para uso real)."""

import os

os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
