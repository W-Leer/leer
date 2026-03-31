# Provider Support Matrix

This document defines the current level of support for LLM providers in Leer,
what is fully supported, partially supported, and not yet supported.

This is the **source of truth** for:
- SDK capabilities
- product expectations
- roadmap decisions

---

## Goals

- make support explicit and predictable
- avoid accidental scope creep
- guide prioritization

---

## Definitions

- **Supported** → fully implemented, tested, usable in production
- **Partial** → works but missing edge cases or UX depth
- **Not supported** → not implemented

---

# OpenAI

## Supported

- non-streaming calls
  - chat/completions
  - responses API (basic coverage)
- request/response artifacts
- normalized LLM shape
- metadata (tokens, latency, finish_reason, request_id)
- summaries (input/output)
- UI rendering (run view + compare)
- error handling

## Partial

- responses API full surface
- structured outputs (basic, not schema-aware UI)
- tool calls (captured but not fully modeled in UI)
- async support (depends on implementation completeness)

## Not Supported

- streaming
- multimodal (image/audio/file)
- large file/blob handling
- advanced response formats
- retries / partial responses

---

# Anthropic

## Supported

- messages.create (non-streaming)
- request/response artifacts
- normalized LLM shape
- metadata (tokens, latency, finish_reason)
- summaries (input/output)
- tool_use extraction (basic)
- UI rendering (run + compare)

## Partial

- tool calling lifecycle (no pairing with tool results)
- thinking blocks (not fully surfaced)
- async support (if not implemented)
- complex content blocks (edge cases)

## Not Supported

- streaming
- multimodal inputs (images, docs)
- advanced tool workflows
- blob storage for large payloads

---

# Cross-Provider Capabilities

## Supported

- unified normalized LLM shape
- provider-aware metadata
- artifacts (request/response)
- summaries
- run timeline UI
- compare UI (LLM-aware)

## Partial

- tool calling normalization (no lifecycle model)
- structured outputs (no schema-aware diff)
- error normalization across providers

## Not Supported

- streaming abstraction
- multimodal abstraction
- blob-backed artifacts
- MCP / skills / agent protocols

---

# Major Missing Areas

## 1. Streaming

Missing:
- token-level events
- partial outputs
- stream artifacts
- interruption handling

Complexity: **High**

---

## 2. Multimodal

Missing:
- image/audio/document input
- file artifacts
- UI rendering for media

Complexity: **Very High**

---

## 3. Tool Calling (Full Support)

Missing:
- tool call → execution → result lifecycle
- timeline linking
- compare support

Complexity: **Medium–High**

---

## 4. Structured Outputs

Missing:
- schema-aware validation
- UI rendering
- intelligent diff

Complexity: **Medium**

---

## 5. Async Support

Missing:
- async wrappers parity
- tests

Complexity: **Medium**

---

## 6. Blob Storage

Missing:
- large payload storage
- artifact streaming
- retrieval layer

Complexity: **High**

---

## 7. MCP / Skills

Missing:
- protocol tracing
- external tool servers
- UI support

Complexity: **High**

---

# Summary

Leer currently provides:

> Strong support for non-streaming LLM observability across OpenAI and Anthropic.

It does NOT yet provide:

> Full provider SDK coverage.

---

# Guiding Principle

We prioritize:

1. **Debuggability**
2. **Clarity**
3. **Determinism**

Over:

- feature completeness
- provider parity