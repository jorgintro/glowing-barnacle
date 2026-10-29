#!/bin/sh
set -e
python manage.py migrate --noinput
if [ -n "$TESORERO_USUARIO" ] && [ -n "$TESORERO_CLAVE" ]; then
    python manage.py crear_tesorero
fi
exec "$@"
