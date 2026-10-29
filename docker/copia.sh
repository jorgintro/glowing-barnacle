#!/bin/sh
# Copia diaria de PostgreSQL. Se ejecuta dentro del contenedor "copias" (imagen postgres:16).
# Variables: PGHOST PGUSER PGPASSWORD PGDATABASE, COPIAS_DIAS (retención), COPIAS_CLAVE (cifrado opcional).
set -eu
DIR=/copias
mkdir -p "$DIR"
while true; do
    FICHERO="$DIR/presupuesto_$(date +%Y%m%d_%H%M%S).sql.gz"
    if pg_dump --no-owner | gzip > "$FICHERO.tmp"; then
        if [ -n "${COPIAS_CLAVE:-}" ]; then
            openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:COPIAS_CLAVE -in "$FICHERO.tmp" -out "$FICHERO.enc"
            rm -f "$FICHERO.tmp"
        else
            mv "$FICHERO.tmp" "$FICHERO"
        fi
        echo "$(date) copia hecha"
    else
        rm -f "$FICHERO.tmp"
        echo "$(date) ERROR: la copia ha fallado" >&2
    fi
    find "$DIR" -name 'presupuesto_*' -mtime +"${COPIAS_DIAS:-30}" -delete
    sleep 86400
done
