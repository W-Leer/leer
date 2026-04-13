# Tool Lifecycle / Linkage — Implementation Plan

Temporary implementation plan for delivering Leer's tool-calling lifecycle and linkage polish.

Permanent behavior/spec lives in:
- `docs/03-specs/platform/tool-lifecycle.md`
- `docs/03-specs/platform/tool-artifacts.md`
- `docs/03-specs/platform/tool-linkage.md`

Delete or archive this plan once the work is complete.

---

## Goal

Make tool use feel first-class in Leer rather than partially inferred.

That means:
- stable normalized tool-call records
- better linkage from LLM calls to tool steps
- clearer artifact expectations
- run-detail UX that makes the lifecycle obvious
- compare support that remains robust

---

## Workstreams

### 1. Audit current state
- inventory current normalized tool-call shape
- inventory current tool-step shape
- inventory current artifact types (`tool_request`, `tool_response`, `tool_error`, etc.)
- identify what linkage data already exists
- identify current run-detail and compare UI assumptions

### 2. Define canonical linkage data
- define minimum tool-call record fields
- define minimum linkage confidence model
- define exact vs heuristic linking rules
- define what remains visible when unlinked

### 3. Backend lifecycle/linkage implementation
- enrich normalized tool-call structures with stable ids/order where possible
- compute or expose linkage metadata on run/timeline responses
- preserve unmatched calls explicitly
- avoid UI-only inference when backend can provide better linkage

### 4. Artifact alignment
- ensure tool-call / request / response / error artifacts are consistent
- ensure artifact metadata supports linkage
- confirm blob-backed tool outputs remain safe in run detail and compare

### 5. Run-detail UX polish
- show tool call -> tool step relationship clearly
- show unlinked states clearly
- expose status and confidence cleanly
- support jumping between linked items

### 6. Compare support
- show tool-call count/name/linkage differences
- show execution status differences
- stay robust with blob-backed tool artifacts
- avoid crashes or confusing duplication

### 7. Demo + QA
- add deterministic demo if needed
- add QA checklist
- verify common cases: single call, multiple calls, failed tool, unmatched tool call

---

## Recommended Delivery Order

### Step 0 — Audit ✅
Output:
- `docs/04-execution/tool-lifecycle-step-0-audit.md`

Questions answered:
- what already exists
- where linkage already happens (tool_call_id matching, frontend-only)
- what is deterministic vs heuristic (id-only, no fallback)
- what is missing in run detail and compare

### Step 1 — Enrich summaries + derived lifecycle status ✅
Output:
- `output_summary.tool_calls` enriched with `id`, `arguments_hash` (SDK)
- `summarize_tool_call()` and `_arguments_hash()` helpers in `normalize.py`
- Frontend `deriveToolCallStatus()` → completed / failed / unmatched
- `ToolCallStatusBadge` in run-detail `ToolCallsSection`
- `ToolCallsDiff` component on compare page (count, name, id, args-hash diffs)
- 16 new tests in `test_normalize.py`

No schema changes. No new API endpoints. No DB migration.

### Step 1 — v1 decisions
- Lifecycle status is **derived at render time**, not stored. Derivation:
  - `completed` = linked tool step exists, tool step status == completed
  - `failed` = linked tool step exists, tool step status == failed
  - `unmatched` = no linked tool step found
- `planned` / `dispatched` statuses deferred (require richer data than exists today)
- Arguments hash uses sha256[:12] of canonicalized JSON (sort_keys, compact separators)
- Compare shows per-call diffs via `ToolCallsDiff`; full semantic diffing of args deferred
- `output_summary.tool_calls` shape is backward compatible: `name` field always present

### Step 2 — Heuristic Fallback Linkage ✅
Output:
- `buildToolCallLinkage()` reusable linker in `apps/web/src/lib/tool-linkage.ts`
- Confidence model: `exact | heuristic | unlinked`
- Lifecycle derivation: `completed | failed | unmatched` (strict, same rules as Step 1)
- Heuristic fallback: same parent + same tool name + ordered alignment
- `ToolCallConfidenceBadge` in run-detail alongside lifecycle badge
- Tool-step back-link UI shows confidence when linked
- `toolStepToLlm` reverse lookup for back-link confidence
- 21 new tests in `test_normalize.py` (Python mirror of TS linker — strong logic coverage, not implementation-parity)

No schema changes. No backend computation. No DB migration.
Frontend-derived linkage only, using existing timeline data.

### Step 2 — v1 decisions
- Heuristic matching priority:
  1. Exact tool_call_id match (always wins)
  2. Tier 1 candidates: unclaimed child tool steps (parent_step_id === llmStep.id) with same name
  3. Tier 2 candidates: unclaimed tool steps after LLM step (by sequence_index) with same name
  4. Ordered alignment: nth unresolved call → nth name-compatible candidate
  5. If no compatible candidate exists, the call remains unlinked
- Tool-step name resolution: `metadata.tool_name` > `step.name`
- Confidence vocabulary is purely frontend-derived, not stored
- Back-link confidence propagated to tool-step detail panel
- Empty tool-call name → always unlinked (no guessing)
- Heuristic matching is intentionally conservative, but not a full ambiguity solver.
  When multiple same-name candidates exist, the linker uses parent preference +
  ordered alignment + first compatible nearest-sequence candidate.
  It does not perform a dedicated ambiguity detection pass.

### Step 3 — Artifact alignment
Output:
- ensure tool-call / request / response / error artifacts are consistent
- ensure artifact metadata supports linkage
- confirm blob-backed tool outputs remain safe in run detail and compare

### Step 4 — Compare support
Output:
- compare sections for tool-call/linkage differences
- no regressions with blob-backed tool artifacts

### Step 5 — Demo + QA signoff
Output:
- demo script(s) if useful
- QA checklist
- status update in roadmap/specs

---

## Complexity

High.

Not because the raw data model is huge, but because the value comes from making the lifecycle feel obvious and trustworthy.
Wrong linkage is worse than incomplete linkage.

---

## Guardrails

- prefer explicit ids over heuristics
- prefer unlinked over falsely linked
- do not introduce provider-specific UI branches unless unavoidable
- do not require full graph modeling for v1
- do not hide ambiguity from the user

---

## Done Criteria

This track is done enough when:
- tool calls are clearly modeled as lifecycle items
- linked tool steps are obvious in run detail
- unmatched calls remain visible
- compare can highlight lifecycle/linkage differences
- artifact-heavy tool outputs do not break the experience
