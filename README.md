# Presupuesto anual · Iniciativa Complutense

Sistema de elaboración, aprobación y ratificación del presupuesto anual. El documento rector
es [`CLAUDE.md`](CLAUDE.md). **Estado: Fase 6 (campaña y comparativa con ejecución real).** La fase 7 (Excel e informe HTML) sigue.

## Arranque con Docker (un solo comando)

```bash
docker compose up --build
```

Abre <http://localhost:8090>. Para crear el primer Tesorero define `TESORERO_USUARIO` y
`TESORERO_CLAVE` (véase `.env.ejemplo`) o ejecuta:

```bash
docker compose exec web python manage.py crear_tesorero
```

## Servidor doméstico (Debian + Portainer)

Guía paso a paso: [`docs/despliegue_homeserver.md`](docs/despliegue_homeserver.md).

## Desarrollo local

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py crear_tesorero
python manage.py runserver
```

Calidad: `pytest`, `ruff check .`, `ruff format --check .`, `mypy .`

Flujo de aprobación (votación, Junta, huella, certificados): [`docs/flujo.md`](docs/flujo.md).
Reglas de validación: [`docs/reglas_validacion.md`](docs/reglas_validacion.md).
Protección de datos: [`docs/proteccion_datos.md`](docs/proteccion_datos.md).
Configuración legal y contable: [`docs/configuracion.md`](docs/configuracion.md).
Datos de demostración (ficticios): [`docs/datos_demo.md`](docs/datos_demo.md).
Decisiones técnicas: [`docs/decisiones/`](docs/decisiones/).
