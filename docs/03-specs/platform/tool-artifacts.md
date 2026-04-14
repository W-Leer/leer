# Tool Artifacts

Defines the permanent artifact model for tool-call and tool-execution data in Leer.

This document complements `tool-lifecycle.md` by specifying the physical payloads Leer should preserve for debugging and UI rendering.

---

## Goal

Store tool-related payloads in a way that is:
- explicit
- debuggable
- blob-friendly
- compatible with lifecycle linking

---

## Design Principle

Lifecycle and artifacts are separate layers.

- lifecycle answers **what happened**
- artifacts preserve **what data was involved**

Leer should not force tool-call arguments, tool inputs, and tool outputs into step metadata when they are better represented as artifacts.

---

## Core Tool Artifact Types

### `tool_call`

Represents the normalized tool-call intent emitted by an LLM.

Typical contents:
- tool name
- call id
- arguments
- sequence index
- provider metadata

Usually JSON.

#### v1 shape

Created by `create_tool_call_artifacts()` in `normalize.py`. One artifact per emitted tool call, attached to the LLM step.

Payload (`inline_data`):
```json
{
  "tool_name": "get_weather",
  "arguments": {"city": "Paris"},
  "tool_call_id": "call_123",
  "arguments_hash": "6e1e312d537b",
  "call_index": 0
}
```

Metadata:
```json
{
  "tool_name": "get_weather",
  "tool_call_id": "call_123",
  "call_index": 0,
  "provider": "openai",
  "model": "gpt-4.1"
}
```

`tool_call_id`, `arguments_hash`, `provider`, and `model` are present only when available. `tool_call` artifacts are always inline JSON (never blob-backed).

Both OpenAI and Anthropic wrappers produce these automatically.

### `tool_request`

Represents the payload actually sent into the tool execution.

Typical contents:
- normalized arguments
- framework-specific execution payload
- execution context subset if relevant

Usually JSON.

#### v1 shape

Created automatically by the `tool_step` context manager from `step.input`. Metadata includes linkage fields:
```json
{
  "tool_name": "get_weather",
  "tool_call_id": "call_123",
  "parent_llm_step_id": "step_abc"
}
```

Fields are present only when available in the tool step's metadata.

### `tool_response`

Represents the successful output from a tool execution.

Typical contents:
- structured JSON output
- returned text
- derived media/file references

May be JSON or binary-backed via related file/media artifacts.

#### v1 shape

Created automatically by the `tool_step` context manager from `step.output`. Same linkage metadata as `tool_request`. May be blob-backed for large payloads.

### `tool_error`

Represents a failed tool execution.

Typical contents:
- error type
- message
- structured details
- traceback or stack summary when available

Usually JSON or text.

#### v1 shape

Created automatically by the `tool_step` context manager when the tool raises. Payload contains `error_type`, `message`, and `traceback`. Same linkage metadata as `tool_request`.

---

## Related Media/File Tool Artifacts

Tool execution may produce files or media.

These should use the broader multimodal/media artifact taxonomy rather than being hidden inside `tool_response`.

Examples:
- `output_image`
- `output_document`
- `output_file`
- `output_audio`
- `output_video`

The `tool_response` artifact may still contain lightweight structured metadata that references these outputs.

---

## Storage Rules

### Keep small JSON inline when reasonable

Examples:
- compact arguments
- small tool outputs
- small structured error payloads

### Offload heavy payloads to blob-backed artifacts

Examples:
- large API responses
- query result tables
- generated files
- screenshots
- PDFs
- audio/video outputs

### Preserve preview text

When possible, every tool artifact should carry a short preview string suitable for timelines and artifact headers.

---

## Artifact Shape Requirements

Tool-related artifacts should preserve:
- `artifact_type`
- `role`
- `format`
- `mime_type`
- `filename` when relevant
- `preview_text`
- `size_bytes`
- `sha256`
- `storage_kind`
- metadata needed for linkage/debugging

---

## Linkage Expectations

Artifacts should make linkage easier, not harder.

Recommended metadata fields when available:
- `tool_name`
- `call_id`
- `provider_call_id`
- `sequence_index`
- `parent_llm_step_id`
- `tool_step_id`

These fields do not replace lifecycle modeling, but they strengthen deterministic linking.

### v1 implementation

All four tool artifact types (`tool_call`, `tool_request`, `tool_response`, `tool_error`) carry linkage metadata when available:
- `tool_name` — always present
- `tool_call_id` — present when the source call has an id
- `parent_llm_step_id` — present on tool-step artifacts when the tool step has a parent

`tool_call` artifacts additionally carry `provider`, `model`, and `call_index`.

`tool_step_id` and `provider_call_id` are not yet used as distinct artifact metadata fields.

---

## UI Expectations

### Run detail

Run detail should be able to show:
- the call payload
- the executed request payload
- the result payload
- the error payload
- any related generated files/media

### Compare

Compare does not need full artifact-body diffing in v1.
It should still remain stable when any of these artifacts are blob-backed.

---

## Non-Goals for v1

- semantic diffing of arbitrary tool outputs
- automatic redaction pipelines
- provider/framework-specific artifact taxonomies beyond what is needed for debugging
- full provenance graphs for every derived output

---

## v1 Status

Tool artifacts v1 is shipped. Current state:

- `tool_call` artifacts created automatically by OpenAI and Anthropic wrappers (one per emitted call)
- `tool_request`, `tool_response`, `tool_error` artifacts created automatically by `tool_step` context manager
- All carry linkage metadata for debugging and future backend linkage
- `tool_call` artifacts are always inline JSON; `tool_request`/`tool_response`/`tool_error` may be blob-backed for large payloads
- Run detail and compare remain stable with any mix of inline and blob-backed tool artifacts
- Compare does not read tool artifact payloads directly — it uses `output_summary` for tool call comparison

### v1 Limitations

- Compare does not provide artifact-level diff for tool payloads (uses summary-level comparison only)
- No automatic redaction of sensitive tool arguments
- `tool_step_id` not yet carried as explicit artifact metadata (linkage uses `step_id` on the artifact record itself)
