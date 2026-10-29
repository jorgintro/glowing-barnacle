#!/bin/sh
# Restaura una copia, SUSTITUYENDO todo el contenido actual de la base de datos.
# Uso: sh /app/restaurar.sh /copias/fichero.sql.gz[.enc] SI
# Requiere las variables PGHOST PGUSER PGPASSWORD PGDATABASE (y COPIAS_CLAVE si está cifrada).
set -eu
export PGOPTIONS="-c client_min_messages=warning"
FICHERO="${1:?Indica el fichero de copia}"
[ "${2:-}" = "SI" ] || { echo "Esto borra los datos actuales. Repite el comando añadiendo SI al final."; exit 1; }
psql -v ON_ERROR_STOP=1 -q -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
if [ "${FICHERO%.enc}" != "$FICHERO" ]; then
    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:COPIAS_CLAVE -in "$FICHERO" | gunzip | psql -v ON_ERROR_STOP=1 -q
else
    gunzip -c "$FICHERO" | psql -v ON_ERROR_STOP=1 -q
fi
echo "Restauración completada. Reinicia el contenedor web."
