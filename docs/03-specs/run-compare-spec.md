# Run Compare Spec

This document defines the first run comparison feature for Leer.

---

## Goal

Allow a developer to compare two runs and quickly see what changed.

This feature should answer:

- which steps changed?
- did a status change?
- did output change?
- did an error appear or disappear?

The MVP should stay simple and deterministic.

---

## Scope

### In scope
- compare two runs
- match steps by `sequence_index`
- compare:
  - `status`
  - `output_summary`
  - `error_summary`
- expose a backend endpoint
- show a minimal diff UI

### Out of scope
- prompt-level semantic diff
- artifact diff
- token diff
- replay integration
- automatic run suggestions
- advanced text diffing
- side-by-side raw artifact comparison

---

## Backend Endpoint

### Route

`GET /v1/runs/{run_id}/compare/{other_run_id}`

### Purpose

Compare two runs and return a structured diff.

---

## Comparison Rules

### Run-level comparison
Return basic metadata for:
- run A
- run B

### Step matching
Match steps by:
- `sequence_index`

If one run has a step at a sequence index and the other does not:
- mark the step as missing on one side

### Fields to compare per step
- `status`
- `output_summary`
- `error_summary`

### Equality rule
For MVP:
- simple JSON equality is enough for summaries
- exact string equality is enough for errors/status

---

## Response Shape

```json
{
  "run_a": {
    "id": "uuid",
    "workflow_name": "demo-agent",
    "status": "completed",
    "created_at": "2026-03-24T12:00:00Z"
  },
  "run_b": {
    "id": "uuid",
    "workflow_name": "demo-agent",
    "status": "failed",
    "created_at": "2026-03-24T12:05:00Z"
  },
  "steps": [
    {
      "sequence_index": 0,
      "name_a": "draft_prompt",
      "name_b": "draft_prompt",
      "step_type_a": "code",
      "step_type_b": "code",
      "exists_in_a": true,
      "exists_in_b": true,
      "status_a": "completed",
      "status_b": "completed",
      "status_diff": false,
      "output_summary_a": {
        "prompt_preview": "Summarize this text"
      },
      "output_summary_b": {
        "prompt_preview": "Summarize this text"
      },
      "output_diff": false,
      "error_summary_a": null,
      "error_summary_b": null,
      "error_diff": false
    },
    {
      "sequence_index": 1,
      "name_a": "llm_call",
      "name_b": "llm_call",
      "step_type_a": "llm",
      "step_type_b": "llm",
      "exists_in_a": true,
      "exists_in_b": true,
      "status_a": "completed",
      "status_b": "failed",
      "status_diff": true,
      "output_summary_a": {
        "result_preview": "This is the summary"
      },
      "output_summary_b": null,
      "output_diff": true,
      "error_summary_a": null,
      "error_summary_b": {
        "message": "LLM timeout"
      },
      "error_diff": true
    }
  ]
}
```

---

## Backend Behavior

### Validation
- both runs must exist
- both runs must belong to the same project for MVP

### Query behavior
- fetch both runs
- fetch steps for both runs
- order steps by `sequence_index ASC`

### Comparison logic
For each unique `sequence_index` across both runs:
- align step A and step B
- compare fields
- return a normalized comparison object

### Error cases
- return 404 if either run is missing
- return 400 if runs belong to different projects

---

## UI Requirements

### Entry point
On run detail page:
- add a simple `Compare` action

### Minimal UX
For MVP, it is enough to:
- let the user enter or select another run ID
- load compare view
- show compared steps in order

### Compare View Layout

For each compared step show:
- sequence index
- name
- type
- status A vs status B
- output summary A vs output summary B
- error summary A vs error summary B
- highlight if different

### Highlighting
Use simple visual cues:
- green/neutral if same
- yellow/red if different

---

## Design Principles

- optimize for clarity
- do not over-design
- prefer explicit booleans like `status_diff`
- keep response predictable for frontend rendering

---

## Testing

### Backend tests
Add at least:
- compare identical runs
- compare runs with changed status/output
- compare runs with missing step on one side

### UI tests
Optional for now

---

## Future Extensions

Later this feature can expand into:
- prompt diff
- artifact diff
- token/cost diff
- compare against parent replay
- compare multiple runs

---

## Summary

Run comparison is the next major feature after observability.

It makes Leer useful for answering:

**What changed between these two runs?**
