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

- `GET /v1/projects/{project_slug}/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/timeline`

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