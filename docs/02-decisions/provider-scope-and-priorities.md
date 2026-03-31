# Provider Scope and Priorities

This document defines how Leer approaches LLM provider support.

---

## Core Philosophy

Leer is NOT trying to:

- fully wrap every provider feature
- mirror entire SDKs
- support every edge case

Leer IS trying to:

> Provide the best possible debugging and observability layer for real-world LLM usage.

---

## Scope Definition

We focus on:

- the most common production flows
- the highest debugging value features
- deterministic behavior

---

## What We Optimize For

1. clarity in UI
2. consistent normalized shape
3. reliable instrumentation
4. minimal magic

---

## What We Avoid

- premature support for rare SDK features
- provider-specific branching in UI
- over-abstraction

---

## Priority Strategy

### Tier 1 (Must Have)

- non-streaming calls
- request/response artifacts
- summaries
- metadata
- compare support

---

### Tier 2 (High Value)

- tool calling lifecycle
- structured outputs
- async support

---

### Tier 3 (Advanced)

- streaming
- blob storage
- large payload handling

---

### Tier 4 (Later)

- multimodal
- MCP / skills
- agent execution protocols

---

## Decision Rules

When evaluating a feature:

### 1. Does it improve debugging?
If no → do not build

### 2. Is it widely used?
If no → defer

### 3. Does it introduce complexity across:
- SDK
- backend
- UI
- compare

If yes → delay unless critical

---

## Current Decision

We are **NOT** pursuing full provider parity.

We are building:

> The best developer experience for understanding what happened inside an LLM workflow.

---

## Key Tradeoff

We accept:

- incomplete provider coverage

In exchange for:

- extremely high clarity and reliability

---

## Future Evolution

If needed, Leer can evolve into:

- execution engine
- agent runtime
- protocol layer

But current scope remains:

> Observability first