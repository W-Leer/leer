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

### Step 0 — Audit
Output:
- `docs/04-execution/mcp-skills-rag-step-0-audit.md`

Questions to answer:
- what already exists in artifacts / metadata / UI / compare
- what can be done metadata-only
- whether MCP v1 needs a new step type
- whether retrieval v1 can reuse existing artifact plumbing cleanly
- whether Step 1 can begin without schema changes

### Step 1 — Canonical metadata models
Output:
- canonical metadata conventions for MCP steps
- canonical capability/skill fields
- canonical retrieval summary fields

Target:
- add metadata helpers / conventions first
- no schema changes

Deliverables likely include:
- shared metadata helpers
- lightweight summary enrichment
- typed frontend interfaces where needed

### Step 2 — Artifact capture plumbing
Output:
- MCP artifacts (`mcp_request`, `mcp_response`, `mcp_error`)
- retrieval artifacts (`retrieval_request`, `retrieval_candidates`, `retrieval_rerank`, `retrieval_selected`, `retrieval_context`)
- linkage metadata on those artifacts

Target:
- reuse current artifact model and blob plumbing
- no migration if possible

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