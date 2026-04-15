# MCP / Skills / RAG — Implementation Plan

This plan covers the next tracing area after tool lifecycle and multimodal.

Goal:
Add clean tracing for:
- MCP protocol interactions
- skill / server / capability identity
- retrieval / RAG workflows

The plan is intentionally metadata-first and artifact-first.

---

## Desired Outcome

Leer should be able to:
- distinguish local tools from MCP-backed operations and retrieval flows
- preserve protocol and retrieval payloads as artifacts
- expose stable metadata in run detail and compare
- avoid schema migrations unless absolutely necessary

---

## Delivery Strategy

Use the same pattern as previous workstreams:
1. specs + implementation plan
2. step 0 audit
3. incremental implementation
4. demo + QA signoff
5. later remove/archive the task plan once complete

---

## Recommended Delivery Order

### Step 0 — Audit ✅

Output:
- `docs/04-execution/mcp-skills-rag-step-0-audit.md`

Key findings:
- `artifact_type` is free-form in DB — new types require no migration
- `step_type` has a CHECK constraint — `step_type="mcp"` would need migration, so v1 uses `step_type="tool"` with metadata
- `metadata` is JSONB — all new keys work without changes
- Step 1 can proceed with zero schema changes

### Step 1 — Canonical metadata models ✅

Output:
- `apps/sdk-python/leer/metadata.py` — canonical metadata builder helpers
- `apps/web/src/lib/types.ts` — TypeScript interfaces for new metadata shapes
- `apps/sdk-python/tests/test_metadata.py` — 29 focused tests

Helpers added:
- `mcp_metadata()` — canonical keys: `protocol_kind="mcp"`, `operation_kind`, `target_name`, `server_name`, `server_id`, `transport_kind`, `tool_call_id`, `parent_llm_step_id`, `parent_tool_step_id`, `latency_ms`, `status`
- `capability_metadata()` — canonical keys: `capability_kind` (`tool` | `mcp_tool` | `retrieval` | `skill` | `unknown`), `capability_name`, `capability_label`, `capability_namespace`, `server_name`, `server_id`, `skill_name`, `skill_label`
- `retrieval_metadata()` — canonical keys: `capability_kind="retrieval"`, `retrieval_stage`, `retrieval_backend`, `index_name`, `query_text`, `query_count`, `candidate_count`, `selected_count`, `context_token_estimate`, `latency_ms`, `parent_llm_step_id`
- `retrieval_output_summary()` — compact compare-friendly summary with `kind="retrieval"` plus counts/stage/backend

TypeScript types added: `McpMetadata`, `CapabilityMetadata`, `RetrievalMetadata`, `RetrievalOutputSummary`, `CapabilityKind`

All helpers exported from `leer` package `__init__.py`.

No schema changes. No new step types. No artifact plumbing yet.

### Step 2 — Artifact capture plumbing ✅

Output:
- `apps/sdk-python/leer/mcp_artifacts.py` — MCP artifact creation helpers
- `apps/sdk-python/leer/retrieval_artifacts.py` — retrieval artifact creation helpers
- `apps/sdk-python/tests/test_mcp_artifacts.py` — 19 focused tests
- `apps/sdk-python/tests/test_retrieval_artifacts.py` — 22 focused tests

MCP artifact helpers added:
- `create_mcp_request_artifact()` — `artifact_type="mcp_request"`, `role="input"`, metadata carries `protocol_kind="mcp"` + MCP canonical fields
- `create_mcp_response_artifact()` — `artifact_type="mcp_response"`, `role="output"`, same metadata shape
- `create_mcp_error_artifact()` — `artifact_type="mcp_error"`, `role="error"`, structured payload with `error_type`, `message`, `details`, `error_code`; metadata includes `error_type` and `error_code` for surface-level inspection

Retrieval artifact helpers added:
- `create_retrieval_request_artifact()` — `artifact_type="retrieval_request"`, `role="input"`, metadata: `capability_kind="retrieval"`, `retrieval_stage="request"`, plus backend/index/query
- `create_retrieval_candidates_artifact()` — `artifact_type="retrieval_candidates"`, `role="output"`, stage `"candidates"`, human-readable preview with count
- `create_retrieval_rerank_artifact()` — `artifact_type="retrieval_rerank"`, `role="output"`, stage `"rerank"`, carries candidate_count + selected_count
- `create_retrieval_selected_artifact()` — `artifact_type="retrieval_selected"`, `role="output"`, stage `"selected"`
- `create_retrieval_context_artifact()` — `artifact_type="retrieval_context"`, `role="output"`, stage `"context"`, supports both JSON and plain-text payloads

All helpers exported from `leer` package `__init__.py`.

Decisions:
- No convenience wrappers (`mcp_tool_step` / `retrieval_step`) — premature; `tool_step()` + metadata is sufficient
- `_INLINE_DATA_ARTIFACT_TYPES` unchanged — MCP/retrieval payloads can be large; timeline stays lightweight; content fetched via artifact endpoint
- No schema changes, no migration, no new step types

### Step 3 — Run-detail UI
Output:
- MCP metadata rows / badges in step detail
- capability/server labeling
- retrieval metadata rows / badges
- safe artifact inspection paths

Target:
- readable run detail without dedicated complex widgets yet

### Step 4 — Compare support
Output:
- compare support for MCP/skills/retrieval metadata differences
- server / operation / stage / count differences
- no crashes on blob-backed payloads

Target:
- metadata-aware compare first
- rich artifact diffing later

### Step 5 — Demo + QA signoff
Output:
- demo scripts
- QA checklist
- status update in specs/tasks

Possible demo files:
- `examples/demo_mcp_tracing.py`
- `examples/demo_rag_tracing.py`
- or one combined demo if cleaner

---

## Practical v1 Decisions

### MCP v1
Preferred:
- keep `step_type="tool"`
- add MCP metadata + MCP artifacts

Why:
- cheapest path
- reuses tool lifecycle/linkage work
- enough for useful tracing now

### Skills/server modeling v1
Preferred:
- metadata-only capability model
- UI badges/labels from capability metadata

Why:
- avoids premature registry/schema work
- enough to distinguish local vs MCP vs retrieval

### RAG v1
Preferred:
- artifact-first retrieval tracing
- compact retrieval summaries in metadata/output_summary

Why:
- large candidate sets already fit existing blob/artifact system
- compare can start with counts and metadata differences

---

## Things to Avoid Early

Do not begin with:
- new DB tables for capabilities/servers
- new `step_type` values unless the audit proves necessary
- protocol-specific replay
- document-by-document retrieval diff UI
- overly provider-specific abstractions

---

## Success Criteria

This workstream is successful when:
- MCP interactions are clearly visible and linkable
- skill/server identity is explicit in the UI
- retrieval phases are inspectable with correct artifact handling
- compare handles all of the above without crashing
- most or all of it ships without schema migrations