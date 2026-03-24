# Data Model

Leer is built around a small set of core primitives that enable:
- observability
- replay
- diffing
- future execution control

---

## Core Concepts

### Run

A **Run** represents a full execution of an AI workflow.

Examples:
- a single agent request
- a background job
- a multi-step workflow

A run contains multiple steps and produces outputs.

Key properties:
- lifecycle (pending → running → completed/failed)
- timing
- aggregated metrics (tokens, cost, duration)
- parent/child relationships (for replay)

---

### Step

A **Step** represents a single unit of work within a run.

Examples:
- LLM call
- tool execution
- code function
- routing decision
- human approval

Each step is:
- independently inspectable
- replayable (when possible)
- timed and tracked

Key properties:
- input / output summaries
- status
- timing
- error information
- references to artifacts

---

### Event

An **Event** represents something that happened during execution.

Events are:
- append-only
- ordered
- lightweight

They power:
- timeline UI
- debugging
- streaming views (future)

Examples:
- step.started
- llm.completed
- tool.called
- step.failed

---

### Artifact

An **Artifact** stores payloads produced or consumed by runs and steps.

Examples:
- prompt text
- LLM response
- tool output
- JSON data
- files

Artifacts allow:
- separation of metadata vs payload
- efficient storage (inline vs blob)
- reproducible replay

---

### Replay

A **Replay** represents a new run derived from a previous run or step.

Replay enables:
- debugging
- experimentation
- comparison
- recovery

Replay modes:
- full run replay
- replay from step
- single step replay
- fork with modified config

---

## Relationships

Run
→ has many Steps

Step
→ belongs to Run
→ may have parent Step

Run / Step
→ emit Events

Run / Step
→ produce Artifacts

Replay
→ links source Run/Step to a new Run

---

## Design Principles

### 1. Inspectability
Every step must be independently inspectable.

### 2. Replayability
All core data needed for replay must be persisted.

### 3. Separation of concerns
- metadata → database
- large payloads → artifacts

### 4. Future-proofing
The model must support:
- retries
- checkpoints
- branching
- orchestration

---

## Summary

Leer models AI execution as:

Run → Steps → Events → Artifacts → Replay

This structure enables both:
- immediate debugging value
- future execution platform capabilities