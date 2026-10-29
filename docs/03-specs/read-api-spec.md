# Read API Spec

This document defines the first read endpoints for Leer.

These endpoints exist to support the MVP UI.

---

## Goals

The read API should support:

- listing recent runs for a project
- viewing a single run
- viewing the timeline for a run

The API should be minimal and optimized for clarity.

Do not implement yet:
- auth
- pagination
- filtering
- search
- replay endpoints
- diff endpoints

---

## Endpoints

- `GET /v1/projects`
- `GET /v1/projects/{project_slug}/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/timeline`

---

## GET /v1/projects

Lists every project, so the UI can pick one. Projects are created by
ingestion; there is no create or delete endpoint.

### Response shape

```json
{
  "projects": [
    {
      "id": "uuid",
      "name": "demo-project",
      "slug": "demo-project",
      "run_count": 12,
      "last_run_at": "2026-03-24T12:00:00Z"
    }
  ]
}
```

### Notes

- ordered by `last_run_at` DESC (projects without runs last), then name
- not paginated; the number of projects is expected to stay small

---

## GET /v1/projects/{project_slug}/runs

Returns recent runs for a project.

### Response shape

```json
{
  "project": {
    "id": "uuid",
    "name": "demo-project",
    "slug": "demo-project"
  },
  "runs": [
    {
      "id": "uuid",
      "workflow_name": "demo-agent",
      "status": "completed",
      "source": "sdk-python",
      "created_at": "2026-03-24T12:00:00Z",
      "started_at": "2026-03-24T12:00:00Z",
      "ended_at": "2026-03-24T12:00:01Z",
      "total_steps": 2,
      "completed_steps": 2,
      "failed_steps": 0,
      "total_duration_ms": 1200,
      "model_provider": null,
      "model_name": null,
      "output_summary": {
        "result_preview": "This is the summary"
      }
    }
  ]
}

### Notes

- runs should be ordered by created_at DESC
- keep response minimal
- include enough information for list UI cards

---

## GET /v1/runs/{run_id}

Returns a single run.

### Response shape

```json
{
  "run": {
    "id": "uuid",
    "project_id": "uuid",
    "workflow_name": "demo-agent",
    "status": "completed",
    "trigger_type": "manual",
    "source": "sdk-python",
    "created_at": "2026-03-24T12:00:00Z",
    "started_at": "2026-03-24T12:00:00Z",
    "ended_at": "2026-03-24T12:00:01Z",
    "input_summary": null,
    "output_summary": {
      "result_preview": "This is the summary"
    },
    "error_summary": null,
    "metadata": {},
    "total_steps": 2,
    "completed_steps": 2,
    "failed_steps": 0,
    "total_duration_ms": 1200,
    "model_provider": null,
    "model_name": null
  }
}

---

## GET /v1/runs/{run_id}/timeline

Returns the run plus ordered steps, events, and artifacts.

### Response shape

```json
{
  "run": {
    "id": "uuid",
    "workflow_name": "demo-agent",
    "status": "completed",
    "created_at": "2026-03-24T12:00:00Z",
    "started_at": "2026-03-24T12:00:00Z",
    "ended_at": "2026-03-24T12:00:01Z",
    "output_summary": {
      "result_preview": "This is the summary"
    },
    "error_summary": null,
    "total_steps": 2,
    "completed_steps": 2,
    "failed_steps": 0,
    "total_duration_ms": 1200
  },
  "steps": [
    {
      "id": "uuid",
      "parent_step_id": null,
      "sequence_index": 0,
      "name": "draft_prompt",
      "step_type": "code",
      "status": "completed",
      "started_at": "2026-03-24T12:00:00Z",
      "ended_at": "2026-03-24T12:00:00Z",
      "input_summary": null,
      "output_summary": {
        "prompt_preview": "Summarize this text"
      },
      "error_summary": null,
      "metadata": {}
    }
  ],
  "events": [
    {
      "id": "uuid",
      "step_id": null,
      "event_type": "run.started",
      "sequence_index": 0,
      "timestamp": "2026-03-24T12:00:00Z",
      "payload": {}
    }
  ],
  "artifacts": []
}

### Notes

- steps must be ordered by sequence_index ASC
- events must be ordered by sequence_index ASC
- artifacts can be empty for MVP
- keep the response simple and predictable
