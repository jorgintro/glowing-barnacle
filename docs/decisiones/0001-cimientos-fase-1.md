# 0001 · Decisiones de la Fase 1 (cimientos)

Fecha: 29/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

Se mantiene el stack por defecto de `CLAUDE.md` §9.2. Decisiones de detalle:

1. **Sin panel de administración de Django.** `django.contrib.admin` permitiría cambiar roles
   o datos saltándose el registro de auditoría. Los usuarios se gestionan desde pantallas
   propias del Tesorero.
2. **Un usuario puede tener varios roles, pero actúa con uno por sesión** (`AsignacionRol` +
   rol activo en sesión). Retirar un rol no lo borra: se anula con fecha y motivo.
3. **Los usuarios no se borran**: se dan de baja con fecha y motivo.
4. **Auditoría inmutable en la base de datos**: disparadores de PostgreSQL rechazan `UPDATE`,
   `DELETE` y `TRUNCATE`. Única excepción: filas `es_demo` mientras el comando de borrado de
   demostración activa `presupuesto.modo_demo`.
5. **Contraseñas**: hasher por defecto de Django (PBKDF2-SHA256), mínimo 12 caracteres.
   Argon2 exigiría una dependencia adicional; se puede añadir en la Fase 8 si se desea.
6. **Pruebas**: con PostgreSQL real (no SQLite), porque la inmutabilidad depende de él.
7. **Contenedores**: `docker-compose.yml` preparado, pero **no se ha podido probar en el entorno
   de desarrollo** (sin servicio Docker). Pendiente de verificar en una máquina con Docker.
8. **Roles de demostración**: las excepciones pedidas por el Tesorero para la demostración
   (el Tesorero vota en la CP y registra la ratificación) se aplicarán mediante
   `reglas_organicas.yaml` de demostración, nunca como comportamiento por defecto. Ver
   discrepancia con `CLAUDE.md` §4 y principio 8.
9. **Despliegue en servidor doméstico**: se añaden `gunicorn` (servidor de aplicaciones) y
   `whitenoise` (ficheros estáticos), dos dependencias ligeras, para poder probar cada fase en
   el servidor del Tesorero. `docker-compose.prod.yml` incluye un contenedor de copias diarias
   (cifrado opcional) y un script de restauración. Probado: arranque con gunicorn sin modo
   desarrollo, estáticos, entrada por HTTP, copia y restauración (también cifrada) sobre una base
   con contenido. **No probado**: ejecución real en Docker.
