# leer-api

FastAPI backend for Leer.

## Setup

```bash
cd apps/api
uv sync
```

## Environment

```bash
cp .env.example .env
```

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/leer
APP_ENV=development
```

The URL must use the `postgresql+psycopg://` driver, because `psycopg`
(v3) is the only Postgres driver installed. Environment variables override
`.env`.

## Database

Create the `leer` database, then run migrations. Either use a local
Postgres:

```bash
createdb leer
uv run alembic upgrade head
```

or use Docker, which creates the database for you:

```bash
docker run -d --name leer-postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=leer -p 5432:5432 postgres:17
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive docs are at
`/docs`.

| Method | Path                                         | Purpose                                                    |
| ------ | -------------------------------------------- | ---------------------------------------------------------- |
| GET    | `/health`                                    | Health check                                               |
| POST   | `/v1/ingest/runs`                            | Ingest one complete run (what the SDK sends)               |
| GET    | `/v1/projects/{project_slug}/runs`           | List runs (`q`, `status`, `sort`, `limit`, `offset`)       |
| GET    | `/v1/runs/{run_id}`                          | Run detail                                                 |
| GET    | `/v1/runs/{run_id}/timeline`                 | Steps, events, and artifact references for a run           |
| GET    | `/v1/runs/{run_id}/compare/{other_run_id}`   | Step-by-step diff of two runs                              |
| GET    | `/v1/artifacts/{artifact_id}`                | Artifact metadata, plus JSON data for non-binary artifacts |
| GET    | `/v1/artifacts/{artifact_id}/content`        | Raw artifact content with its MIME type                    |

Projects are created on first ingest.

## Blob storage

Artifacts larger than `BLOB_INLINE_THRESHOLD_BYTES` (default 256 KB) are
stored outside Postgres. The default backend is `local` (`.leer/blobs`).
S3 and Azure are also supported; see the `blob_*` settings in
`app/config.py` and `docs/04-execution/blob-storage-setup.md`.

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
