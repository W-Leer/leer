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

---

## v1 Implementation Status

All v1 targets are met. No schema migrations were required.

### SDK helpers (`leer/retrieval_artifacts.py`)

- `create_retrieval_request_artifact()` — `artifact_type="retrieval_request"`, `role="input"`, metadata: `capability_kind="retrieval"`, `retrieval_stage="request"`, plus backend/index/query
- `create_retrieval_candidates_artifact()` — `artifact_type="retrieval_candidates"`, `role="output"`, stage `"candidates"`; human-readable preview with explicit count when provided
- `create_retrieval_rerank_artifact()` — `artifact_type="retrieval_rerank"`, `role="output"`, stage `"rerank"`; carries `candidate_count` + `selected_count`
- `create_retrieval_selected_artifact()` — `artifact_type="retrieval_selected"`, `role="output"`, stage `"selected"`; human-readable preview with explicit count when provided
- `create_retrieval_context_artifact()` — `artifact_type="retrieval_context"`, `role="output"`, stage `"context"`; if `data` is a `str`, uses `create_text_artifact()` path; otherwise uses `create_json_artifact()` path

All helpers delegate metadata construction to `retrieval_metadata()` from `leer/metadata.py` — single source of truth for key names and `capability_kind="retrieval"` injection.

All exported from top-level `leer` package.

### Metadata and preview conventions

- Artifact metadata always includes `capability_kind="retrieval"` and `retrieval_stage`
- Preview text uses explicit count parameters when provided (e.g., "50 candidates"); falls back to generic JSON preview otherwise — no payload-sniffing
- `_INLINE_DATA_ARTIFACT_TYPES` was not expanded — retrieval artifact content is fetched via artifact endpoint, keeping timeline responses lightweight

### UI

Retrieval artifacts render through existing `ArtifactViewer` as generic JSON (or plain text for `retrieval_context` text payloads). No dedicated retrieval artifact viewers were built for v1.