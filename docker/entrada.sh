#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py sincronizar_configuracion
if [ -n "$TESORERO_USUARIO" ] && [ -n "$TESORERO_CLAVE" ]; then
    python manage.py crear_tesorero
fi
exec "$@"
