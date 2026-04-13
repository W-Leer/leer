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

### `tool_request`

Represents the payload actually sent into the tool execution.

Typical contents:
- normalized arguments
- framework-specific execution payload
- execution context subset if relevant

Usually JSON.

### `tool_response`

Represents the successful output from a tool execution.

Typical contents:
- structured JSON output
- returned text
- derived media/file references

May be JSON or binary-backed via related file/media artifacts.

### `tool_error`

Represents a failed tool execution.

Typical contents:
- error type
- message
- structured details
- traceback or stack summary when available

Usually JSON or text.

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

## v1 Delivery Target

Tool artifacts are considered good enough when:
- tool call, request, response, and error payloads are preserved consistently
- large tool outputs can be blob-backed safely
- media/file outputs can be represented as first-class artifacts
- run detail can inspect them without ambiguity
