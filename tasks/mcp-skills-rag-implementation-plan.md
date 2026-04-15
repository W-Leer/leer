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

### Step 2 — Artifact capture plumbing
Output:
- MCP artifacts (`mcp_request`, `mcp_response`, `mcp_error`)
- retrieval artifacts (`retrieval_request`, `retrieval_candidates`, `retrieval_rerank`, `retrieval_selected`, `retrieval_context`)
- linkage metadata on those artifacts
- artifact creation helpers that use the Step 1 metadata conventions

Target:
- reuse current artifact model and blob plumbing
- no migration if possible
- use `mcp_metadata()` / `capability_metadata()` / `retrieval_metadata()` for artifact metadata

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