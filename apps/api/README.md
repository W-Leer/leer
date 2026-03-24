# leer-api

FastAPI backend for Leer.

## Setup

```bash
cd apps/api
uv sync
```

## Environment

Copy or edit `.env`:

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/leer
APP_ENV=development
```

## Database

Create the Postgres database, then run migrations:

```bash
createdb leer
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`.

- Health check: `GET /health`
- Ingestion: `POST /v1/ingest/runs`
- Docs: `GET /docs`

## Migrations

```bash
# Apply all migrations
uv run alembic upgrade head

# Generate a new migration after model changes
uv run alembic revision --autogenerate -m "description"

# View current revision
uv run alembic current

# Rollback one step
uv run alembic downgrade -1
```
