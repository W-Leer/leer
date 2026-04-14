# Provider Support Roadmap

This document defines the execution order for provider support expansion.

---

# COMPLETED

## 1. Tool Calling [DONE]

### Goal

Make tool calls debuggable end-to-end.

### Delivered

- tool call → execution → result linkage
- first-class tool steps
- timeline linkage UX
- compare support for tool flows

---

## 2. Async Support [DONE]

### Goal

Support async SDK usage with clean parent/child semantics.

### Delivered

- async-friendly parent/child step modeling
- timeline support
- compare support for parent_step_id
- demo validation

---

## 3. Structured Outputs [DONE]

### Goal

Make structured responses readable across run detail and compare.

### Delivered

- canonical structured renderer
- generic structured rendering
- LLM structured rendering
- compare structured rendering
- showcase demo

---

## 4. Streaming [DONE]

### Goal

Capture token streams and render them meaningfully.

### Tasks

- stream event capture
- final aggregation behavior
- artifact strategy
- timeline / UI rendering
- compare behavior rules

### Why

High debugging value, now completed across SDK + UI + compare.

---

## 5. Blob Storage [DONE]

### Goal

Handle large payloads safely and scalably.

### Tasks

- inline vs blob threshold
- storage abstraction
- local / S3 / Azure backends
- blob-backed artifact writes
- retrieval endpoint
- run UI lazy loading
- compare-page blob-backed stream loading
- setup docs and QA checklist

### Why

Foundational for scale. Required before serious multimodal, large tool outputs, and very large stream artifacts.

### Complexity

High

---

## 6. Multimodal [DONE]

### Goal

Support image, audio, document, spreadsheet, and video inputs/outputs in a provider-agnostic way.

### Tasks

- define canonical multimodal content-part schema
- define provider mapping rules (OpenAI, Anthropic first)
- define multimodal artifact taxonomy
- store binary/media as artifacts, blob-backed when large
- support lightweight previews + lazy loading in UI
- add rendering strategy by mime type
- ship rich v1 support for images and documents/PDFs, with generic fallback for other media types

### Notes

- provider APIs are not standardized enough to mirror directly
- Leer should normalize multimodal content into a stable internal model
- blob storage is the foundation for real multimodal support

### Complexity

Very High

---

## 7. Tool-calling lifecycle / linkage polish [DONE]

### Delivered

Make tool-call intent, execution, linkage, artifacts, and compare behavior visible and reliable.

### Tasks

- enriched tool-call summaries with id and arguments_hash
-    lifecycle states in run detail
-    exact / heuristic / unlinked linkage confidence
-    heuristic fallback linking
-    first-class tool_call artifacts
-    compare support for aligned tool calls, args changes, lifecycle differences, one-sided calls
-    deterministic demo and QA checklist

### Notes

- exact linkage should win over heuristic linkage whenever possible
-    unmatched calls should remain visible rather than disappearing
-    wrong linkage is worse than incomplete linkage
-    this is core to Leer’s agent observability story

### Complexity

High

---

# LATER

## 8. MCP / Skills / RAG

### Goal

Trace external agent protocols, tool servers, and retrieval flows cleanly.

### Subtracks

#### MCP tracing

```
•	client ↔ server request/response lifecycle
•	tool/server identity
•	protocol metadata and errors
```

#### Skills modeling

```
•	represent reusable skills/tools/servers as first-class entities
•	distinguish local tools vs remote skill servers
•	show invocation lineage in the UI
```

#### RAG tracing

```
•	retrieval request / retrieved chunks / reranking / final context
•	source attribution and artifact capture
•	compare and inspect retrieval behavior across runs
```

### Tasks

- protocol tracing model
- server / skill identity model
- retrieval artifact taxonomy
- UI representation for protocol calls, skills, and retrieval chains
- compare support
- demo + QA

### Complexity

High

---

# DO NOT DO (FOR NOW)

- full provider SDK parity
- obscure provider-specific features
- provider-specific UI branches unless unavoidable

---

# Execution Order

## Recommended order:

1. tool calling
2. async support
3. structured outputs
4. streaming
5. blob storage
6. multimodal
7. Tool-calling lifecycle / linkage polish
8. MCP / Skills / RAG

---

# Principle

Always prioritize:

> maximum debugging value per unit of complexity

