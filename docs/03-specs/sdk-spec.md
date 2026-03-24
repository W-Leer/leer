# SDK Spec (Python)

This document defines the initial Python SDK for Leer.

---

## Purpose

The SDK allows developers to instrument AI workflows with minimal code.

The MVP SDK should:
- create runs
- create steps
- collect events
- buffer execution data in memory
- submit the full run payload to the API at the end

---

## Public API

The SDK must expose:

```python
from leer import configure, trace, step
```

---

## configure(...)

Configures the SDK client.

### Signature

```python
configure(
    api_base_url: str,
    project_slug: str,
)
```

### Behavior

Stores global SDK configuration:
- API base URL
- project slug

No auth is required in MVP.

---

## @trace(...)

Wraps a function and creates a workflow run.

### Example

```python
@trace(workflow_name="demo-agent")
def run_agent():
    ...
```

### Signature

```python
trace(
    workflow_name: str,
    metadata: dict | None = None,
)
```

### Behavior

When a traced function starts:
- create a run object
- mark run status as `running`
- record run events:
  - `run.created`
  - `run.started`

When the function completes successfully:
- mark run status as `completed`
- record `run.completed`
- capture output summary
- submit payload to API

When the function raises:
- mark run status as `failed`
- record `run.failed`
- capture error summary
- submit payload to API
- re-raise exception

---

## step(...)

Creates a step inside the current run.

### Example

```python
with step("llm_call", step_type="llm"):
    result = call_model(...)
```

### Signature

```python
step(
    name: str,
    step_type: str = "code",
    metadata: dict | None = None,
)
```

### Supported step types
- `llm`
- `tool`
- `code`
- `router`
- `human`
- `memory`
- `system`

### Behavior

When a step starts:
- create step object
- assign sequence index
- mark status as `running`
- record:
  - `step.created`
  - `step.started`

When step completes:
- mark status as `completed`
- record `step.completed`

When step raises:
- mark status as `failed`
- record `step.failed`
- capture error summary
- re-raise exception

---

## Runtime Model

The SDK uses in-memory runtime objects.

### TraceRun
Fields:
- id
- workflow_name
- status
- trigger_type
- source
- started_at
- ended_at
- input_summary
- output_summary
- error_summary
- metadata
- steps
- events
- artifacts

### TraceStep
Fields:
- id
- parent_step_id
- sequence_index
- name
- step_type
- status
- started_at
- ended_at
- input_summary
- output_summary
- error_summary
- metadata

### TraceEvent
Fields:
- id
- step_id
- event_type
- sequence_index
- timestamp
- payload

### TraceArtifact
Fields:
- id
- step_id
- artifact_type
- storage_kind
- mime_type
- inline_data
- blob_path
- metadata

---

## Context Management

The SDK must use `contextvars` to manage:
- current active run
- current step stack

Required context variables:
- current run
- current step stack

This avoids relying on unsafe global state.

---

## Submission Model

The MVP SDK uses:

### Buffer locally, submit on completion

Execution data is buffered in memory during the run.

At the end of the run, the SDK serializes:
- run
- steps
- events
- artifacts

And sends them to:

```text
POST /v1/ingest/runs
```

If the run fails, the SDK must still submit the failed trace.

---

## Serialization

The SDK must serialize runtime objects into the API contract shape.

The serializer should:
- convert datetimes to ISO8601 strings
- include project slug at top level
- preserve event ordering
- preserve step ordering

---

## Error Handling

### API submission failure
For MVP:
- do not crash the user application because of ingestion failure
- log or print the submission error
- preserve main application behavior

### Tracing failure
Tracing should never break the main workflow unless the user code itself fails.

---

## Non-goals (MVP)

Do not implement yet:
- streaming events
- retries
- async buffering
- auth / API keys
- replay execution
- blob upload flows
- framework-specific integrations

---

## Implementation Notes

### Language
Python

### Internal model style
Use `dataclasses` for runtime objects.

### HTTP client
Use `httpx`

### Goal
Keep SDK minimal, typed, and easy to adopt.
