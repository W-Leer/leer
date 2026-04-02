# Provider Support Matrix

This document defines the current level of support for LLM providers in Leer, what is fully supported, partially supported, and not yet supported.

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

- **Supported** → implemented, tested, and usable in the main product flow
- **Partial** → works, but important depth, edge cases, or UX are still missing
- **Not supported** → not implemented

---

# OpenAI

## Supported

- non-streaming calls
  - chat/completions
  - responses API (basic coverage)
- streaming calls
- request / response artifacts
- `llm_stream` artifact capture
- normalized LLM shape
- metadata
  - tokens
  - latency
  - finish_reason
  - request_id
- summaries
  - input
  - output
  - error
- structured output rendering
- tool call capture
- run detail UI
- compare UI
- error handling

## Partial

- responses API full surface
- advanced response formats
- multimodal inputs / outputs
- very large payload handling
- async parity, if any edge cases remain

## Not supported

- blob-backed large artifacts
- provider-specific obscure features
- replay / remote execution

---

# Anthropic

## Supported

- messages.create (non-streaming)
- streaming calls
- request / response artifacts
- `llm_stream` artifact capture
- normalized LLM shape
- metadata
  - tokens
  - latency
  - finish_reason
  - request_id
- summaries
  - input
  - output
  - error
- structured output rendering
- tool_use capture
- run detail UI
- compare UI
- error handling

## Partial

- thinking / content block rich rendering
- complex content block edge cases
- multimodal inputs
- advanced tool workflows
- async parity, if any edge cases remain

## Not supported

- blob-backed large artifacts
- replay / remote execution
- provider-specific obscure streaming features

---

# Cross-Provider Capabilities

## Supported

- unified normalized LLM shape
- provider-aware metadata
- request / response artifacts
- stream artifact capture
- stream metadata + latency breakdown
- structured output rendering
- tool calling visibility
- run timeline UI
- compare UI
- streamed vs non-streamed compare behavior

## Partial

- full tool lifecycle modeling beyond current explicit tracing
- schema-aware structured output UX
- rich thinking / reasoning block rendering
- error normalization across all edge cases
- large artifact storage strategy
- multimodal abstraction

## Not Supported

- blob storage
- multimodal rendering
- MCP / skills / RAG tracing
- replay execution
- remote tool execution

---

# Major Missing Areas

## 1. Blob Storage

Missing:
- inline vs blob threshold
- large artifact offloading
- retrieval layer
- UI integration for blob-backed payloads

Complexity: **High**

---

## 2. Multimodal

Missing:
- image / audio / document normalization
- artifact handling for media
- media rendering in UI

Complexity: **Very High**

---

## 3. MCP / Skills / RAG

Missing:
- protocol tracing
- tool server / skill modeling
- UI support

Complexity: **High**

---

## 4. Replay / Execution

Missing:
- replay model
- execution boundary definition
- secure remote execution strategy
- user-side registry / adapter approach

Complexity: **Very High**

---

# Summary

Leer currently provides:

> Strong observability for OpenAI and Anthropic across non-streaming and streaming LLM flows, including structured outputs, tool visibility, stream artifacts, and compare UX.

It does NOT yet provide:

> Full provider SDK parity, blob-backed scale primitives, multimodal support, or replay execution.

---

# Guiding Principle

We prioritize:

1. **Debuggability**
2. **Clarity**
3. **Determinism**

Over:
- feature completeness
- provider parity
- provider-specific surface area
