# Retrieval Artifacts

Defines the artifact taxonomy for retrieval / RAG tracing.

---

## Goal

Provide stable, explicit artifact types for retrieval workflows so large retrieval payloads are inspectable without bloating step metadata or timeline responses.

---

## Required v1 Artifact Types

### `retrieval_request`
Represents the query and retrieval options.

Typical payload:
- query text
- filters
- top_k
- backend/index parameters

### `retrieval_candidates`
Represents the initial candidate set returned by retrieval.

Typical payload:
- documents/chunks
- scores
- metadata
- rank positions

### `retrieval_rerank`
Represents reranked candidates or reranking output.

Typical payload:
- reranked list
- rerank scores
- rationale/metadata if available

### `retrieval_selected`
Represents the subset chosen for downstream use.

Typical payload:
- selected documents/chunks
- ordering
- selection metadata

### `retrieval_context`
Represents the final context actually sent to an LLM or downstream step.

Typical payload:
- packed context blocks
- chunk ordering
- token or size estimates

---

## Optional Later Artifact Types

- `retrieval_query_embedding`
- `retrieval_filter_plan`
- `retrieval_hybrid_merge`
- `retrieval_eval`
- `retrieval_feedback`

---

## Shared Metadata Fields

Recommended artifact metadata for retrieval artifacts:
- `capability_kind="retrieval"`
- `retrieval_stage`
- `retrieval_backend`
- `index_name`
- `candidate_count` when applicable
- `selected_count` when applicable
- `parent_llm_step_id` when applicable
- `query_id` or `request_id` when useful

---

## Storage Expectations

### Usually inline
- `retrieval_request`
- small `retrieval_selected`
- small `retrieval_context`

### Frequently blob-backed
- `retrieval_candidates`
- `retrieval_rerank`
- large `retrieval_context`

The existing blob storage system is sufficient.

---

## UI Expectations

### v1

Generic JSON artifact rendering plus good metadata is acceptable.

Users should be able to inspect:
- request payload
- candidate lists
- selected context
- blob-backed large payloads via lazy load

### Later

Possible richer retrieval-specific views:
- candidate table with score columns
- rerank before/after diff
- selected-context preview
- context packing visualization

---

## Compare Expectations

Compare may initially rely on summaries and counts rather than artifact-level diffing.
Artifact presence and lazy-load safety matter more than rich retrieval diffing in v1.

---

## v1 Status Target

Retrieval artifact support v1 is complete when Leer can:
- create and store the required retrieval artifact types
- blob-store large candidate/context payloads safely
- expose enough metadata for run-detail and compare
- inspect retrieval artifacts without special backend schema work