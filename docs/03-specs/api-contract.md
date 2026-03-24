# API Contract

This document defines the MVP ingestion payload between the Python SDK and the Leer backend.

---

## Endpoint

```text
POST /v1/ingest/runs
```

---

## Top-Level Request Shape

```json
{
  "project_slug": "demo-project",
  "run": {},
  "steps": [],
  "events": [],
  "artifacts": [],
  "replay": null
}
```

---

## Request Fields

### project_slug
String identifying the project.

Used to:
- resolve existing project
- or create a new project

---

## run

Represents the workflow run.

### Shape

```json
{
  "id": "uuid",
  "workflow_name": "demo-agent",
  "status": "completed",
  "trigger_type": "manual",
  "source": "sdk-python",
  "started_at": "2026-03-24T12:00:00Z",
  "ended_at": "2026-03-24T12:00:01Z",
  "input_summary": null,
  "output_summary": {
    "result_preview": "This is the summary"
  },
  "error_summary": null,
  "metadata": {}
}
```

### Required fields
- id
- workflow_name
- status
- trigger_type
- source
- started_at
- metadata

### Optional fields
- ended_at
- input_summary
- output_summary
- error_summary

---

## steps

Represents the ordered steps inside the run.

### Shape

```json
[
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
]
```

### Required fields
- id
- sequence_index
- name
- step_type
- status
- started_at
- metadata

### Optional fields
- parent_step_id
- ended_at
- input_summary
- output_summary
- error_summary

---

## events

Represents ordered execution events.

### Shape

```json
[
  {
    "id": "uuid",
    "step_id": null,
    "event_type": "run.started",
    "sequence_index": 0,
    "timestamp": "2026-03-24T12:00:00Z",
    "payload": {}
  }
]
```

### Required fields
- id
- event_type
- sequence_index
- timestamp
- payload

### Optional fields
- step_id

---

## artifacts

Represents payload objects associated with the run or steps.

### Shape

```json
[
  {
    "id": "uuid",
    "step_id": "uuid",
    "artifact_type": "prompt",
    "storage_kind": "inline",
    "mime_type": "application/json",
    "inline_data": {
      "text": "Summarize this text"
    },
    "blob_path": null,
    "metadata": {}
  }
]
```

### Required fields
- id
- artifact_type
- storage_kind
- metadata

### Optional fields
- step_id
- mime_type
- inline_data
- blob_path

### Notes
For MVP:
- inline artifacts are enough
- blob-backed artifacts may be added later

---

## replay

Replay metadata for derived runs.

### Shape

```json
null
```

Or:

```json
{
  "source_run_id": "uuid",
  "source_step_id": null,
  "replay_mode": "full",
  "reason": "manual replay",
  "metadata": {}
}
```

### Required fields when present
- source_run_id
- replay_mode
- metadata

### Optional fields
- source_step_id
- reason

For MVP:
- replay is optional
- most ingested runs will use `null`

---

## Example Full Payload

```json
{
  "project_slug": "demo-project",
  "run": {
    "id": "11111111-1111-1111-1111-111111111111",
    "workflow_name": "demo-agent",
    "status": "completed",
    "trigger_type": "manual",
    "source": "sdk-python",
    "started_at": "2026-03-24T12:00:00Z",
    "ended_at": "2026-03-24T12:00:01Z",
    "input_summary": null,
    "output_summary": {
      "result_preview": "This is the summary"
    },
    "error_summary": null,
    "metadata": {}
  },
  "steps": [
    {
      "id": "22222222-2222-2222-2222-222222222222",
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
    },
    {
      "id": "33333333-3333-3333-3333-333333333333",
      "parent_step_id": null,
      "sequence_index": 1,
      "name": "llm_call",
      "step_type": "llm",
      "status": "completed",
      "started_at": "2026-03-24T12:00:00Z",
      "ended_at": "2026-03-24T12:00:01Z",
      "input_summary": null,
      "output_summary": {
        "result_preview": "This is the summary"
      },
      "error_summary": null,
      "metadata": {
        "provider": "openai"
      }
    }
  ],
  "events": [
    {
      "id": "44444444-4444-4444-4444-444444444444",
      "step_id": null,
      "event_type": "run.created",
      "sequence_index": 0,
      "timestamp": "2026-03-24T12:00:00Z",
      "payload": {}
    },
    {
      "id": "55555555-5555-5555-5555-555555555555",
      "step_id": null,
      "event_type": "run.started",
      "sequence_index": 1,
      "timestamp": "2026-03-24T12:00:00Z",
      "payload": {}
    }
  ],
  "artifacts": [],
  "replay": null
}
```

---

## Contract Rules

- steps must preserve `sequence_index`
- events must preserve `sequence_index`
- datetimes must be ISO8601 strings
- ids must be UUID strings
- payload must be valid JSON

---

## Non-goals (MVP)

Do not add yet:
- auth headers
- user identity
- streaming transport
- multipart blob uploads
- diff response contracts
- replay execution contracts
