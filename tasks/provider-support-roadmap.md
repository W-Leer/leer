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

# NOW

## 4. Streaming
### Goal
Capture token streams and render them meaningfully.

### Tasks
- stream event capture
- final aggregation behavior
- artifact strategy
- timeline / UI rendering
- compare behavior rules

### Complexity
High

---

# NEXT

## 5. Blob Storage
### Goal
Handle large payloads safely and scalably.

### Tasks
- inline vs blob threshold
- storage abstraction
- retrieval endpoints
- UI integration

---

## 6. Multimodal
### Goal
Support image, audio, and document payloads.

### Tasks
- normalized multimodal format
- artifact handling
- rendering strategy

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

# Principle

Always prioritize:

> maximum debugging value per unit of complexity