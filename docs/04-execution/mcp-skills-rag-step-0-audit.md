# MCP / Skills / RAG — Step 0 Audit

Factual audit of the Leer codebase against the MCP tracing, skills model, RAG tracing, and retrieval artifacts specs.

Specs audited:
- `docs/03-specs/platform/mcp-tracing.md`
- `docs/03-specs/platform/skills-model.md`
- `docs/03-specs/platform/rag-tracing.md`
- `docs/03-specs/platform/retrieval-artifacts.md`
- `tasks/mcp-skills-rag-implementation-plan.md`

---

## 1. What already exists

### Step model

`TraceStep` (`apps/sdk-python/leer/models.py`) carries:
- `name: str`
- `step_type: str` (default `"code"`)
- `metadata: dict[str, Any]` (free-form JSONB)
- `input_summary / output_summary / error_summary: dict | None`
- `parent_step_id: str | None`
- `sequence_index: int`
- `status: str`
- `duration_ms: int | None`

`step()` (`apps/sdk-python/leer/step.py`) accepts any `step_type` string — the SDK does not validate.

`tool_step()` (`apps/sdk-python/leer/tool.py`) hardcodes `step_type="tool"` and auto-populates metadata: `tool_name`, `tool_call_id`, `provider`, `model`.

### Artifact model

`TraceArtifact` (`apps/sdk-python/leer/models.py`) carries:
- `artifact_type: str` (free-form)
- `storage_kind: str` (`"inline"` or `"blob"`)
- `role / format / mime_type / filename: str | None`
- `inline_data: dict | None`
- `blob_path: str | None`
- `binary_data: bytes | None`
- `preview_text: str | None`
- `metadata: dict[str, Any]`
- `step_id: str | None`
- `sequence_index: int | None`

Helpers in `apps/sdk-python/leer/artifacts.py`:
- `create_json_artifact()` — inline JSON, any `artifact_type` string
- `create_binary_artifact()` — blob-backed, any type
- `create_text_artifact()` — inline text, any type
- `attach_artifact()` — appends to current run

### Current artifact types in use

| Type | Created by | Attached to |
|------|-----------|-------------|
| `tool_call` | `create_tool_call_artifacts()` in `normalize.py` | LLM step |
| `tool_request` | `tool_step` context manager | Tool step |
| `tool_response` | `tool_step` context manager | Tool step |
| `tool_error` | `tool_step` context manager | Tool step |
| `llm_request` | OpenAI/Anthropic wrappers | LLM step |
| `llm_response` | OpenAI/Anthropic wrappers | LLM step |
| `llm_stream` | OpenAI/Anthropic wrappers | LLM step |
| `output_image` | `materialize_media_artifacts()` | LLM step |
| `output_document` | `materialize_media_artifacts()` | LLM step |
| `output_file` | `materialize_media_artifacts()` | LLM step |

### Database schema

**`steps` table** (`apps/api/alembic/versions/0001_initial_schema.py`):
- `step_type` column: `Text NOT NULL` with **CHECK constraint** `ck_steps_step_type` allowing only: `'llm'`, `'tool'`, `'code'`, `'router'`, `'human'`, `'memory'`, `'system'`
- `metadata` column: `JSONB NOT NULL` default `'{}'::jsonb` — no per-key schema
- `status` column: `Text NOT NULL` with CHECK constraint

**`artifacts` table**:
- `artifact_type` column: `Text NOT NULL` with **no CHECK constraint** — free-form
- `storage_kind` column: `Text NOT NULL` with CHECK `'inline' | 'blob'`
- `metadata` column: `JSONB NOT NULL` default `'{}'::jsonb`
- Storage consistency constraint enforces inline_data/blob_path alignment

**Critical finding**: new `artifact_type` values can be ingested without any migration. New `step_type` values (e.g. `"mcp"`) **cannot** — PostgreSQL will reject them at the CHECK constraint.

### Blob storage and lazy loading

Binary artifacts use `storage_kind="blob"` with `blob_path` pointing to local storage. The API serves blob content via:
- `GET /v1/artifacts/{id}` — JSON metadata + parsed data
- `GET /v1/artifacts/{id}/content` — raw bytes

The frontend `ArtifactViewer` (`apps/web/src/components/artifact-viewer.tsx`) handles both inline and blob-backed artifacts. Non-media artifacts render as generic `StructuredValue` (JSON tree). Media artifacts route to `MediaArtifactRenderer`.

### Timeline API

`GET /v1/runs/{id}/timeline` (`apps/api/app/routes/runs.py`):
- Returns `TimelineStep` with `metadata`, `llm` (extracted from `metadata.llm`), and `artifacts` (as `StepArtifactRef`)
- `StepArtifactRef.inline_data` is only populated for artifact types in `_INLINE_DATA_ARTIFACT_TYPES = {"llm_stream"}`. All other types get `inline_data=None` in the timeline response — content must be fetched separately via the artifact content endpoint.

### Compare API

`GET /v1/runs/{id}/compare/{other_id}` (`apps/api/app/services/compare.py`):
- Returns `CompareStepDiff` with paired `metadata_a/b`, `llm_a/b`, summaries, status
- `llm_*` extracted from `metadata.llm`
- Compare does not read artifacts directly — uses `output_summary` and `metadata` only

### Frontend UI rendering

**Run detail** (`apps/web/src/app/runs/[id]/page.tsx`):
- Rendering split: `step.llm` truthy → `LlmStepDetail`; otherwise → `StepDetailPanel`
- `StepDetailPanel` shows input/output/error summaries, artifacts list, and metadata key-value pairs
- `stepTypeBadge()`: LLM = blue, tool = amber, everything else = neutral gray
- Tool steps have dedicated rows for `provider`, `model`, `tool_call_id`, back-link confidence
- `TOOL_META_KEYS = ["tool_name", "tool_call_id", "provider", "model"]` — excluded from generic "Extra metadata" display
- Any metadata keys not in that list render as generic key-value pairs

**Compare** (`apps/web/src/app/compare/page.tsx`):
- `isTool = (step.step_type_a ?? step.step_type_b) === "tool"`
- `isLlm = !!step.llm_a || !!step.llm_b`
- Tool steps get `ToolLinkageDiff` (provider, model, call_id, confidence)
- LLM steps get `ToolCallsDiff` with lifecycle badges
- Generic steps get `DataDiffRow` for input/output/error

### Tool lifecycle/linkage (reusable)

`buildToolCallLinkage()` in `apps/web/src/lib/tool-linkage.ts`:
- Indexes tool steps by `metadata.tool_call_id`
- Matches against `llm.output.tool_calls[].id`
- Heuristic fallback: parent/child + same name + ordered alignment
- Returns `callLinks` (per-call lifecycle/confidence) and `toolStepToLlm` (reverse lookup)
- Confidence model: `exact | heuristic | unlinked`
- Lifecycle model: `completed | failed | unmatched`

This entire linkage system can be reused for MCP tool steps that carry `tool_call_id`.

---

## 2. MCP tracing readiness

### Can MCP interactions be represented as tool steps with enriched metadata?

**Yes.** The spec recommends `step_type="tool"` with MCP-specific metadata for v1. The existing `tool_step()` context manager already:
- Creates `step_type="tool"` steps
- Accepts arbitrary `metadata` dict
- Produces `tool_request` / `tool_response` / `tool_error` artifacts automatically
- Supports `tool_call_id` for linkage

An MCP tool call could use `tool_step()` directly with additional metadata keys:

```python
with tool_step("read_file", tool_call_id="call_abc", metadata={
    "protocol_kind": "mcp",
    "operation_kind": "tool_call",
    "target_name": "read_file",
    "server_name": "filesystem-server",
    "server_id": "fs-001",
    "transport_kind": "stdio",
}) as s:
    s.input = {"path": "/foo/bar"}
    s.output = {"content": "..."}
```

This works today without any changes. The step would appear in run detail with these metadata keys visible as generic key-value pairs.

### Protocol/server identity in metadata

**Does not exist today.** No current step or artifact carries `protocol_kind`, `server_name`, `server_id`, `transport_kind`, or `operation_kind`. These are purely additive metadata fields.

### Can MCP-specific artifacts be added?

**Yes, without schema changes.** The `artifact_type` column has no CHECK constraint. `mcp_request`, `mcp_response`, `mcp_error` can be ingested immediately. They would render as generic JSON in the artifact viewer.

However: for MCP artifacts to have their `inline_data` returned in the timeline response (instead of requiring a separate fetch), `_INLINE_DATA_ARTIFACT_TYPES` in `apps/api/app/routes/runs.py` would need to be extended. This is a one-line backend change, not a migration.

### What is missing for proper MCP trace model

| Missing | Scope | Notes |
|---------|-------|-------|
| MCP metadata conventions/helpers | SDK only | No server_name, protocol_kind, etc. conventions exist |
| MCP-specific artifact creation helpers | SDK only | Could mirror `create_tool_call_artifacts()` pattern |
| MCP badge in step header | Frontend | `stepTypeBadge()` and `StepDiffHeader` only style `llm` and `tool` |
| MCP metadata rows in StepDetailPanel | Frontend | Dedicated rows for server, operation, transport |
| MCP-aware compare sections | Frontend | `ToolLinkageDiff` could be extended with server/protocol fields |
| MCP metadata filtering from "Extra metadata" | Frontend | Like `TOOL_META_KEYS`, to avoid duplicate display |

### Is a new `step_type="mcp"` required for v1?

**No.** Using `step_type="tool"` with `metadata.protocol_kind="mcp"` is sufficient for v1. Adding `"mcp"` to the step_type CHECK constraint would require a DB migration. The UI can detect MCP steps via metadata instead.

If needed later, a migration to expand `ck_steps_step_type` is straightforward:
```sql
ALTER TABLE steps DROP CONSTRAINT ck_steps_step_type;
ALTER TABLE steps ADD CONSTRAINT ck_steps_step_type
  CHECK (step_type IN ('llm','tool','code','router','human','memory','system','mcp'));
```

But this is unnecessary for v1.

---

## 3. Skills / server modeling readiness

### Where tool identity metadata currently enters the system

- **SDK `tool_step()`**: sets `metadata.tool_name`, `metadata.tool_call_id`, `metadata.provider`, `metadata.model`
- **SDK OpenAI/Anthropic wrappers**: set `metadata.llm.provider`, `metadata.llm.model` on LLM steps; `tool_call` artifacts carry `provider`, `model`, `tool_name`
- **Frontend**: reads `metadata.tool_name`, `metadata.tool_call_id`, `metadata.provider`, `metadata.model` for tool steps; `step.llm.provider` / `step.llm.model` for LLM steps

### Can current step metadata carry capability/skill fields?

**Yes.** `metadata` is `JSONB` with no key restrictions. All of the following can be added today:
- `capability_kind` (`tool`, `mcp_tool`, `retrieval`, `skill`, `unknown`)
- `capability_name`
- `capability_label`
- `capability_namespace`
- `server_name` / `server_id`
- `skill_name` / `skill_label`

No schema change needed. The SDK `tool_step()` accepts an arbitrary `metadata` dict that gets merged.

### Is the UI too dependent on raw step.name / tool_name?

**Partially.** Current dependencies:

- `StepCard` header: uses `step.name` directly — this is the primary display name
- `StepDetailPanel` tool row: does not display `metadata.tool_name` (it's in `TOOL_META_KEYS` so it's excluded from "Extra metadata" but not shown in the dedicated row either — `step.name` serves as the tool name)
- `buildToolCallLinkage()`: resolves tool step name as `metadata.tool_name ?? step.name`
- Compare `ToolCallsDiff`: uses `output_summary.tool_calls[].name`
- Compare `ToolLinkageDiff`: does not display `tool_name`

**Impact**: the UI can already distinguish tools by `step.name`. Adding capability labels/badges would require new UI rows but no structural changes. If `capability_label` exists in metadata, it could override or supplement `step.name` in display.

### What would need to change for local vs MCP vs retrieval distinction

| Change | Scope | Details |
|--------|-------|---------|
| Capability badge in step header | Frontend | Read `metadata.capability_kind`, render colored badge |
| Server badge when MCP | Frontend | Read `metadata.server_name`, render pill |
| Skill grouping badge | Frontend | Read `metadata.skill_name`, render pill |
| Compare capability diff | Frontend | Add capability_kind / server_name to `ToolLinkageDiff` or new section |
| Metadata convention helpers | SDK | Helper to build canonical metadata dicts |

**This is entirely metadata + frontend work.** No backend or schema changes needed.

---

## 4. RAG tracing readiness

### How retrieval workflows would appear today

Retrieval steps would most naturally use:
- `step_type="tool"` via `tool_step("vector_search", ...)` for tool-wrapped retrieval
- `step_type="code"` via `step("retrieve_context", step_type="code")` for inline retrieval code

Both already work. The `tool_step` path gives automatic `tool_request` / `tool_response` artifacts; the `step` path requires manual artifact creation.

### Can current artifact plumbing support retrieval artifact types?

**Yes.** All of these can be created today without changes:

| Artifact type | Via | Blob-safe |
|---------------|-----|-----------|
| `retrieval_request` | `create_json_artifact(artifact_type="retrieval_request", ...)` | Yes (inline for small) |
| `retrieval_candidates` | `create_json_artifact(...)` or `create_binary_artifact(...)` | Yes (blob for large) |
| `retrieval_rerank` | `create_json_artifact(...)` | Yes |
| `retrieval_selected` | `create_json_artifact(...)` | Yes |
| `retrieval_context` | `create_json_artifact(...)` or `create_text_artifact(...)` | Yes |

The DB `artifact_type` column has no CHECK constraint. The existing blob storage system handles large payloads. The `ArtifactViewer` renders any JSON artifact as a structured tree.

### Can large candidate sets be blob-backed safely?

**Yes.** The `create_binary_artifact()` helper sets `storage_kind="blob"` and stores raw bytes. The ingest service handles blob upload. The frontend `ArtifactViewer` loads blob content lazily via `fetchArtifactContent()`.

For JSON payloads that are large but not binary, the ingest service already handles blob-backing based on payload size (configured server-side).

### Existing compare/run-detail behavior reusable for retrieval

- **Run detail**: `StepDetailPanel` shows `output_summary` as structured JSON, artifacts via `ArtifactList` → `ArtifactViewer`. Retrieval counts/metadata in `output_summary` would render automatically.
- **Compare**: `DataDiffRow` diffs `output_summary_a` vs `output_summary_b` as structured JSON. If retrieval summaries include `candidate_count`, `selected_count`, etc., they diff out of the box.
- **Limitation**: no retrieval-specific rendering (candidate tables, score columns, rerank before/after). v1 would use generic JSON rendering.

### What is missing for retrieval-specific rendering

| Missing | Scope | Notes |
|---------|-------|-------|
| Retrieval metadata conventions | SDK | No standard fields for `retrieval_stage`, `retrieval_backend`, etc. |
| Retrieval artifact creation helpers | SDK | Could mirror `create_tool_call_artifacts()` pattern |
| Retrieval summary enrichment | SDK | Compact `candidate_count`, `selected_count` in `output_summary` |
| Retrieval badge in step header | Frontend | Read `metadata.capability_kind=="retrieval"` |
| Retrieval metadata rows | Frontend | Stage, backend, counts, latency |
| Compare retrieval count diffs | Frontend | Dedicated section or inline in existing `DataDiffRow` |
| Timeline inline_data for retrieval artifacts | Backend (1 line) | Add types to `_INLINE_DATA_ARTIFACT_TYPES` if needed |

**All of this can be done without schema changes.**

---

## 5. Biggest gaps vs. the specs

### MCP gaps

| Gap | Severity | Scope |
|-----|----------|-------|
| No MCP metadata conventions or helpers | Medium | SDK metadata-only |
| No `mcp_request` / `mcp_response` / `mcp_error` artifact creation | Medium | SDK artifact-only |
| No MCP badge / protocol badge in UI | Medium | Frontend |
| No server/operation/transport metadata rows in run detail | Medium | Frontend |
| No MCP-aware compare sections | Low | Frontend |
| `_INLINE_DATA_ARTIFACT_TYPES` does not include MCP types | Low | Backend (1-line) |
| No `step_type="mcp"` | Low | Deferred by design for v1 |

### Skills/modeling gaps

| Gap | Severity | Scope |
|-----|----------|-------|
| No `capability_kind` / `capability_name` conventions | Medium | SDK metadata-only |
| No capability badge in UI | Medium | Frontend |
| No server badge in UI | Low | Frontend |
| No skill grouping badge in UI | Low | Frontend |
| No compare capability/server diff sections | Low | Frontend |
| `step.name` used as sole display label | Low | Frontend |

### RAG gaps

| Gap | Severity | Scope |
|-----|----------|-------|
| No retrieval metadata conventions or helpers | Medium | SDK metadata-only |
| No retrieval artifact creation helpers | Medium | SDK artifact-only |
| No retrieval badge / stage badge in UI | Medium | Frontend |
| No retrieval metadata rows (counts, backend, latency) | Medium | Frontend |
| No retrieval-specific artifact rendering | Low | Frontend (generic JSON works for v1) |
| No compare retrieval count diff section | Low | Frontend |
| `_INLINE_DATA_ARTIFACT_TYPES` does not include retrieval types | Low | Backend (1-line) |

---

## 6. Best v1 approach

### MCP v1 shape: tool-step + metadata first

Use `step_type="tool"` with MCP-enriched metadata. Reasons:
- Avoids a DB migration to expand `ck_steps_step_type`
- Reuses the entire tool lifecycle/linkage system (`tool_call_id`, confidence, bidirectional jumps)
- Reuses `tool_request` / `tool_response` / `tool_error` artifact creation from `tool_step()`
- MCP-specific artifacts (`mcp_request`, `mcp_response`, `mcp_error`) can be added alongside as supplementary protocol records
- The UI can detect MCP via `metadata.protocol_kind === "mcp"` and render MCP-specific badges/rows

### Skills v1 shape: metadata-only + badges/grouping first

Use `metadata.capability_kind`, `metadata.capability_name`, `metadata.server_name` etc. on existing steps. Reasons:
- All fields fit in the existing `JSONB` metadata column
- No backend changes needed
- The UI can read these fields and render badges/pills immediately
- Compare can diff them via the existing `metadata_a` / `metadata_b` fields on `CompareStepDiff`

### RAG v1 shape: artifact-first + summary metadata

Use existing artifact creation helpers with new `artifact_type` values, plus retrieval summary metadata in `output_summary`. Reasons:
- `artifact_type` is free-form in the DB — zero migration
- Large candidate sets naturally fit blob-backed artifacts
- Compact retrieval counts/metadata in `output_summary` diff automatically in compare
- The `ArtifactViewer` renders any JSON artifact as a structured tree — no special rendering needed for v1

---

## 7. Schema / API impact

### What can be done with no schema changes

Everything in v1 scope:
- All new metadata fields (`protocol_kind`, `server_name`, `capability_kind`, `retrieval_stage`, etc.) — JSONB metadata column is free-form
- All new artifact types (`mcp_request`, `mcp_response`, `mcp_error`, `retrieval_request`, `retrieval_candidates`, `retrieval_rerank`, `retrieval_selected`, `retrieval_context`) — `artifact_type` has no CHECK constraint
- All SDK helpers and conventions — pure additive code
- All frontend badges, metadata rows, compare sections — pure additive code
- MCP representation as `step_type="tool"` with metadata

### What probably needs a minor API change (not migration)

- `_INLINE_DATA_ARTIFACT_TYPES` in `apps/api/app/routes/runs.py`: currently `{"llm_stream"}`. If any MCP or retrieval artifact should have `inline_data` in the timeline response (avoiding a separate fetch), add its type to this set. This is a 1-line backend change.
- If MCP steps need `llm`-style promoted metadata (pulled out of `metadata` into a top-level response field), that would require a change in `_enrich_step()` in `apps/api/app/routes/runs.py`. But this is likely unnecessary for v1 — MCP metadata can stay in `metadata`.

### What truly needs a migration

**Nothing for v1.**

A migration would only be needed if:
- `step_type="mcp"` is introduced (requires altering `ck_steps_step_type`) — deferred
- A dedicated MCP/retrieval DB table is introduced — deferred
- New indexed columns are added to `steps` or `artifacts` — no need identified

---

## 8. Recommended implementation order after the audit

### Step 1 — Canonical metadata models

- Define MCP metadata conventions: `protocol_kind`, `operation_kind`, `target_name`, `server_name`, `server_id`, `transport_kind`
- Define capability metadata conventions: `capability_kind`, `capability_name`, `capability_label`, `capability_namespace`
- Define retrieval metadata conventions: `retrieval_stage`, `retrieval_backend`, `index_name`, `candidate_count`, `selected_count`, `context_token_estimate`
- Create SDK helpers (e.g. `mcp_metadata()`, `retrieval_summary()`) that produce canonical metadata dicts
- Add TypeScript interfaces for the new metadata shapes in `apps/web/src/lib/types.ts`
- Add focused tests for metadata helpers

### Step 2 — Artifact capture plumbing

- Create `create_mcp_artifacts()` helper in SDK (mirrors `create_tool_call_artifacts()` pattern)
- Create `create_retrieval_artifacts()` helper for each retrieval phase
- Wire MCP artifact creation into a new `mcp_tool_step()` helper or extend `tool_step()` with protocol metadata
- Wire retrieval artifact creation into a `retrieval_step()` helper or documented manual pattern
- Optionally extend `_INLINE_DATA_ARTIFACT_TYPES` in `apps/api/app/routes/runs.py` for small MCP/retrieval artifacts
- Add focused tests for artifact creation, metadata shapes, and blob safety

### Step 3 — Run-detail UI

- Add MCP badge detection: `metadata.protocol_kind === "mcp"` → protocol badge in `stepTypeBadge()` or `StepCard`
- Add capability badge: `metadata.capability_kind` → colored pill in step header
- Add MCP metadata rows in `StepDetailPanel`: server name, operation kind, target, transport
- Add retrieval metadata rows: stage, backend, index, counts, latency
- Extend `TOOL_META_KEYS` (or create equivalent for MCP/retrieval) to avoid duplicate display
- Ensure MCP and retrieval artifacts render cleanly via existing `ArtifactViewer`

### Step 4 — Compare support

- Extend `ToolLinkageDiff` or add parallel `McpLinkageDiff` for protocol/server/transport diffs
- Add capability_kind / server_name to compare step header badges
- Add retrieval count diffs to compare (candidate_count, selected_count from output_summary)
- Ensure no crashes when MCP/retrieval artifacts are blob-backed
- Reuse existing `alignToolCalls()` and `deriveCompareCallLifecycle()` for MCP-backed tool calls

### Step 5 — Demo + QA signoff

- Create `examples/demo_mcp_tracing.py`: fake MCP server interactions with protocol metadata and artifacts
- Create `examples/demo_rag_tracing.py`: fake retrieval pipeline with all phases and blob-backed candidates
- Create QA checklist covering MCP badges, retrieval badges, compare behavior, artifact inspection
- Verify heuristic linkage works for MCP tool steps
- Verify blob-backed retrieval artifacts load correctly

---

## 9. Direct answer

### Can Step 1 start without schema changes?

**Yes.**

Step 1 is metadata conventions and SDK helpers. It adds new keys to the existing `JSONB` metadata column and creates new `artifact_type` values — both are free-form in the database with no constraints that would block ingestion. The frontend work in Step 1 (TypeScript interfaces) is purely additive.

The only scenario requiring a migration would be introducing `step_type="mcp"`, which the specs explicitly defer for v1. As long as v1 uses `step_type="tool"` with `metadata.protocol_kind="mcp"`, no migration is needed for any part of the implementation plan.
