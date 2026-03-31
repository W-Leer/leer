# Provider Support Roadmap

This document defines what to build next for provider support.

---

# NOW (Next Iterations)

~~## 1. Tool Calling (First-Class) [DONE]~~

### Goal
Make tool calls debuggable end-to-end.

### Tasks
- represent tool call + result lifecycle
- link tool call → execution → result
- improve UI display
- support compare for tool flows

### Why
High debugging value, moderate complexity.

---

~~## 2. Async Support [DONE]~~

### Goal
Support async SDK usage.

### Tasks
- async wrappers (OpenAI + Anthropic)
- tests
- ensure parity with sync behavior

### Why
Common in production usage.

---

## 3. Structured Outputs [CURRENT]

### Goal
Improve structured response visibility.

### Tasks
- detect structured outputs
- improve summary rendering
- optional schema display
- better compare behavior

### Why
Common use case, contained complexity.

---

# NEXT (After NOW)

## 4. Streaming

### Goal
Capture and display token streams.

### Tasks
- stream event capture
- aggregation into final output
- artifact strategy
- UI rendering

### Complexity
High

---

## 5. Blob Storage

### Goal
Handle large payloads correctly.

### Tasks
- inline vs blob threshold
- storage layer
- retrieval endpoints
- UI integration

### Why
Foundational for scaling

---

# LATER

## 6. Multimodal

### Goal
Support images, audio, documents.

### Tasks
- normalized multimodal format
- artifact handling
- UI rendering

### Complexity
Very High

---

## 7. MCP / Skills

### Goal
Support external agent protocols.

### Tasks
- protocol tracing
- tool server modeling
- UI

### Complexity
High

---

# DO NOT DO (FOR NOW)

- full provider SDK parity
- obscure API features
- provider-specific UI branching

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