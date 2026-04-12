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

NOW

## 6. Multimodal
### Goal
Support image, audio, document, spreadsheet, and video inputs/outputs in a provider-agnostic way.

### Tasks
- define canonical multimodal content-part schema
- define provider mapping rules (OpenAI, Anthropic first)
- define multimodal artifact taxonomy
- store binary/media as artifacts, blob-backed when large
- support lightweight previews + lazy loading in UI
- add rendering strategy by mime type
- ship in phases: images → documents/PDFs → audio → video

### Notes
- provider APIs are not standardized enough to mirror directly
- Leer should normalize multimodal content into a stable internal model
- blob storage is the foundation for real multimodal support

### Complexity
Very High

---

# LATER

## 7. MCP / Skills / RAG
### Goal
Trace external agent protocols and tool servers cleanly.

### Tasks
- protocol tracing
- skill / server modeling
- UI representation

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
7. MCP

---

# Principle

Always prioritize:

> maximum debugging value per unit of complexity