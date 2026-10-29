# Presupuesto anual · Iniciativa Complutense

Sistema de elaboración, aprobación y ratificación del presupuesto anual. El documento rector
es [`CLAUDE.md`](CLAUDE.md). **Estado: Fase 1 de 8 (cimientos).**

## Arranque con Docker (un solo comando)

```bash
docker compose up --build
```

Abre <http://localhost:8000>. Para crear el primer Tesorero define `TESORERO_USUARIO` y
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

Decisiones técnicas: [`docs/decisiones/`](docs/decisiones/).
