# Backend Spec (FastAPI)

This document defines the MVP FastAPI backend for Leer.

---

## Purpose

The backend receives fully serialized run payloads from the SDK and stores them in Postgres.

The MVP backend should:
- expose a health endpoint
- expose an ingestion endpoint
- validate incoming payloads
- insert project, run, steps, events, and artifacts
- use a single transaction for ingestion

---

## Stack

- FastAPI
- SQLAlchemy 2.0
- Pydantic
- Postgres
- Alembic

---

## App Structure

```text
apps/api/app/
  main.py
  config.py
  db.py
  models.py
  schemas.py
  routes/
    health.py
    ingest.py
  services/
    ingestion.py
```

---

## Endpoints

### GET /health

Returns a simple health response.

Example response:

```json
{
  "status": "ok"
}
```

Purpose:
- local verification
- deployment health checks

---

### POST /v1/ingest/runs

Receives a fully serialized run payload from the SDK.

Responsibilities:
- validate request body
- resolve or create project by slug
- insert run
- insert steps
- insert events
- insert artifacts
- commit transaction
- return created response

---

## Database Responsibilities

The backend persists data into:
- projects
- runs
- steps
- events
- artifacts
- replays (not used yet in MVP ingestion, but schema exists)

MVP ingestion must support:
- project creation if slug does not exist
- insertion of completed or failed runs
- insertion of ordered steps
- insertion of ordered events
- insertion of inline artifacts

---

## ORM Models

The backend must define SQLAlchemy models for:
- Project
- Run
- Step
- Event
- Artifact
- Replay

These should follow the schema defined in:
- `docs/03-specs/db-schema.md`

---

## Request Validation

Use Pydantic request schemas for ingestion.

The request body must contain:
- `project_slug`
- `run`
- `steps`
- `events`
- `artifacts`
- `replay`

The backend should validate:
- required fields
- enum-like values where defined in schemas
- reasonable shape of nested objects

---

## Ingestion Service

Business logic should live in:

```text
services/ingestion.py
```

### Responsibilities

- resolve or create project by slug
- create run row
- create step rows
- create event rows
- create artifact rows
- wrap everything in one transaction

### Behavior

If any insert fails:
- rollback transaction
- return error response

---

## Transaction Model

Each ingestion request should be handled in a single transaction.

This guarantees:
- no partial run ingestion
- consistency across run / steps / events / artifacts

---

## Response Behavior

### Success
Return HTTP `201 Created`

Suggested body:

```json
{
  "status": "ok",
  "run_id": "uuid"
}
```

### Failure
Return appropriate 4xx or 5xx response.

For MVP:
- clear error messages
- no need for complex error taxonomy

---

## Config

The backend should load configuration from environment variables.

Minimum settings:
- `DATABASE_URL`
- `APP_ENV`

Keep config simple.

---

## Non-goals (MVP)

Do not implement yet:
- auth / API keys
- multi-user auth model
- replay execution endpoints
- diff endpoints
- artifact blob uploads
- worker queues
- schedules
- approvals
- UI-serving backend

---

## Implementation Notes

### ORM
Use SQLAlchemy 2.0 style.

### Migrations
Use Alembic from the start.

### Code style
- minimal
- typed where reasonable
- simple route/service separation

### Goal
Provide a clean ingestion backend that can evolve later without rework.
