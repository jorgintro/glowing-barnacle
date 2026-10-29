# Despliegue en tu servidor doméstico (Debian + Docker + Portainer)

Equipo de referencia: Intel Pentium G2020, 4 GB de RAM. El sistema ocupa unos 400–600 MB.
Esta guía se puede repetir cada vez que se complete una fase: basta con **actualizar el stack**.

> ⚠️ El despliegue se ha preparado y probado sin Docker (con `gunicorn` y PostgreSQL reales),
> pero **el `docker-compose.prod.yml` aún no se ha ejecutado en un Docker de verdad**. Si algo
> falla al construir, copia el mensaje de error de Portainer y se corrige.

## 1. Antes de empezar

- Anota la **IP fija** del servidor en tu red (por ejemplo `192.168.1.50`). Conviene reservarla
  en el router para que no cambie.
- Crea en el servidor la **carpeta de copias**. Lo ideal es que esté en **otro disco** o en un NAS:
  ```bash
  sudo mkdir -p /srv/copias-presupuesto
  ```
- Si el repositorio de GitHub es privado, crea un **token de acceso personal** de solo lectura
  (GitHub → Settings → Developer settings → Fine-grained tokens, permiso *Contents: read*).

## 2. Crear el stack en Portainer

1. *Stacks → Add stack*. Nombre: `presupuesto`.
2. Método **Repository**:
   - *Repository URL*: `https://github.com/jorgintro/glowing-barnacle`
   - *Repository reference*: `refs/heads/claude/presupuesto-iniciativa-complutense-l2pes3`
   - *Compose path*: `docker-compose.prod.yml`
   - Si es privado: activa *Authentication* y pon tu usuario de GitHub y el token.
3. En **Environment variables** añade (modo avanzado, pegando el bloque):
   ```
   DJANGO_SECRET_KEY=<cadena larga y aleatoria>
   POSTGRES_PASSWORD=<contraseña larga>
   DJANGO_ALLOWED_HOSTS=192.168.1.50
   DJANGO_CSRF_ORIGENES=http://192.168.1.50:8000
   COOKIES_SEGURAS=0
   PUERTO=8000
   TESORERO_USUARIO=tesorero
   TESORERO_CLAVE=<contraseña de al menos 12 caracteres>
   COPIAS_RUTA=/srv/copias-presupuesto
   COPIAS_DIAS=30
   COPIAS_CLAVE=<contraseña para cifrar las copias; guárdala en un sitio seguro>
   ```
   Para generar una clave aleatoria: `openssl rand -base64 48`.
4. **Deploy the stack**. La primera construcción tarda varios minutos en este procesador.
5. Abre `http://192.168.1.50:8000` y entra con el Tesorero.

Tras el primer arranque puedes **borrar `TESORERO_CLAVE`** de las variables: solo se usa si todavía
no existe ningún Tesorero.

## 3. Acceso: HTTP en casa, HTTPS o VPN

- **Solo desde casa** (configuración anterior): funciona por HTTP, sin cifrar. Aceptable en una red
  doméstica de confianza.
- **Desde fuera de casa**: **no abras el puerto del router.** Hay datos de donantes y cuentas del
  partido. Usa una **VPN** (Tailscale o WireGuard) y accede por la IP de la VPN. Si el acceso va por
  HTTPS (proxy inverso con certificado), cambia `COOKIES_SEGURAS=1` y `DJANGO_CSRF_ORIGENES=https://tu-dominio`.

## 4. Actualizar a una versión nueva

En Portainer: *Stacks → presupuesto → Pull and redeploy* (marcando *Re-build image*).
Las migraciones de base de datos se aplican solas al arrancar y **los datos se conservan**
(viven en el volumen `datos_db`).

## 5. Copias de seguridad

- El contenedor `copias` hace una copia **diaria** de la base de datos en `COPIAS_RUTA`
  (ficheros `presupuesto_AAAAMMDD_HHMMSS.sql.gz.enc`, cifrados si pusiste `COPIAS_CLAVE`).
  Se conservan `COPIAS_DIAS` días.
- Comprueba de vez en cuando que aparecen ficheros nuevos y que **no están vacíos**.
- **Copia esa carpeta fuera del servidor** de vez en cuando (USB, otro equipo): si el disco falla,
  una copia en el mismo disco se pierde con él.
- Apunta `COPIAS_CLAVE` en un lugar seguro: **sin ella no se pueden descifrar las copias.**

### Restaurar una copia

1. En Portainer, abre el contenedor `presupuesto-web-1` y pulsa **Stop**.
2. Abre el contenedor `presupuesto-copias-1` → **Console** → `/bin/sh` → *Connect*.
3. Elige la copia más reciente y restáurala (esto **sustituye** todos los datos actuales):
   ```bash
   ls /copias
   sh /app/restaurar.sh /copias/presupuesto_20261029_030000.sql.gz.enc SI
   ```
4. Vuelve a arrancar `presupuesto-web-1` (**Start**).

Prueba una restauración en frío al menos una vez, **antes** de necesitarla.

## 6. Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| «Falta DJANGO_SECRET_KEY» o «Define POSTGRES_PASSWORD» al desplegar | Falta una variable en Portainer. |
| Error 400 «Bad Request» | `DJANGO_ALLOWED_HOSTS` no coincide con la IP o nombre que usas en el navegador. |
| «Verificación CSRF fallida» al entrar | `DJANGO_CSRF_ORIGENES` no coincide exactamente (esquema `http://`, IP y puerto). |
| Entras pero te pide entrar otra vez | `COOKIES_SEGURAS=1` estando en HTTP. Ponla a `0` o usa HTTPS. |
| La construcción se queda sin memoria | Cierra otros contenedores durante el primer despliegue. |
