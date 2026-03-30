# Leer — Artifact Model Spec

## Purpose
Artifacts store raw structured data for runs and steps.

Summaries = human-readable  
Artifacts = raw detail

---

## Core Model

Fields:
- id
- run_id
- step_id
- sequence_index
- kind
- role
- format
- storage_kind
- inline_data
- blob_path
- preview_text
- metadata
- created_at

---

## Enums

### kind
- llm_request
- llm_response
- tool_call
- tool_result
- file
- image
- audio
- document

### role
- input
- output
- intermediate

### format
- json
- text
- markdown
- file_ref

### storage_kind
- inline_json
- inline_text
- blob_ref

---

## Storage Rules

V1:
- small data → inline
- large data → blob (future)

---

## Artifact Examples

### LLM request
```json
{
  "kind": "llm_request",
  "role": "input",
  "format": "json",
  "inline_data": {
    "messages": [...]
  }
}
```

### LLM response
```json
{
  "kind": "llm_response",
  "role": "output",
  "format": "json",
  "inline_data": {
    "text": "..."
  }
}
```

---

## Key Rule
Do NOT store raw payloads inside output_summary.

Artifacts are the source of truth.
