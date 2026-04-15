# RAG Tracing

Defines how Leer traces retrieval-augmented generation workflows in a provider-agnostic, artifact-first way.

---

## Goal

Make retrieval behavior inspectable as a first-class part of AI workflow execution.

Leer should be able to show:
- what was asked of retrieval
- what candidates came back
- how reranking/selection behaved
- what context was finally given to the model
- how retrieval changed across runs

---

## Scope

This spec covers:
- retrieval request tracing
- candidate/result set tracing
- reranking/selection tracing
- final context tracing
- metadata and artifact strategy
- run-detail and compare expectations

This spec does **not** define:
- generic multimodal media handling
- MCP protocol wire semantics
- full semantic evaluation of retrieval quality

---

## Design Principles

### 1. Retrieval is artifact-first

Candidate sets and final contexts may be large.
They should be stored as artifacts, blob-backed when appropriate.

### 2. Summaries must stay lightweight

Run-detail and compare should rely on compact summary fields, not large inline candidate payloads.

### 3. Preserve the phases of retrieval

Retrieval should not collapse into one opaque blob if distinct phases are available:
- request
- candidates
- rerank
- selected
- final context

### 4. Retrieval should be provider-agnostic

Whether retrieval comes from a local vector DB, hosted search service, MCP server, or custom stack, Leer should expose stable internal phases.

---

## Canonical Retrieval Phases

### 1. Request
The query/filters/top-k/options sent into the retrieval system.

### 2. Candidates
The raw or lightly processed result set returned initially.

### 3. Rerank
Optional reranking/scoring stage.

### 4. Selected
The subset actually selected for downstream use.

### 5. Context
The final packed context supplied to an LLM or later step.

---

## Recommended v1 Step Representation

Retrieval in v1 may use existing step types:
- `tool`
- `code`

No new `step_type` is required for v1.

Instead, retrieval steps should carry metadata such as:
- `capability_kind="retrieval"`
- `retrieval_stage`
- `retrieval_backend`
- `collection_name` / `index_name`
- `query_count`
- `candidate_count`
- `selected_count`
- `context_token_estimate`

---

## Summary Fields

Suggested compact retrieval summary fields:

| Field | Type | Description |
|---|---|---|
| `retrieval_stage` | string | `request`, `candidates`, `rerank`, `selected`, `context`, `composite` |
| `retrieval_backend` | string \| null | e.g. `pgvector`, `pinecone`, `elasticsearch`, `custom`, `mcp` |
| `index_name` | string \| null | Retrieval index/collection name |
| `query_text` | string \| null | Compact request preview |
| `candidate_count` | number \| null | Number of initial candidates |
| `selected_count` | number \| null | Number selected for context |
| `latency_ms` | number \| null | Retrieval latency when known |

These may live in step metadata and/or summaries.

---

## UI Expectations

### Run-detail

Leer should be able to show:
- retrieval stage badge
- backend/index metadata
- counts and latency
- expandable artifacts for candidates/context

### Compare

Leer should be able to show:
- candidate count changes
- selected count changes
- query preview changes
- stage/backend/index differences
- no crashes when candidate sets are blob-backed

Full document-by-document diffing is out of scope for v1.

---

## Linkage to LLM

When retrieval feeds an LLM:
- use parent/child step hierarchy when available
- preserve parent LLM step id in metadata when helpful
- preserve final context artifact independently from the raw retrieval result set

This allows users to understand both:
- what the retriever saw
- what the LLM actually got

---

## Storage Rules

### Inline is fine for
- short query previews
- compact summaries
- tiny selected-context payloads

### Blob-backed artifacts should be used for
- large candidate sets
- full rerank result lists
- large final context payloads
- hybrid JSON payloads with many documents/chunks

---

## Non-Goals for v1

- semantic quality scoring built into the trace model
- full document-level compare UI
- built-in eval metrics for recall/precision
- retrieval graph replay

---

## v1 Status Target

RAG tracing v1 is complete when Leer can:
- capture the major retrieval phases as artifacts/summaries
- blob-store large candidate/context payloads safely
- show retrieval metadata cleanly in run detail
- compare retrieval-rich runs without crashing