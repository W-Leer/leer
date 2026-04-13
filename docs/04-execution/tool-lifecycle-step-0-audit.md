# Tool Lifecycle — Step 0 Audit

Factual audit of current tool-calling lifecycle and linkage behavior in Leer.

Source of truth for what we want:
- `docs/03-specs/platform/tool-lifecycle.md`
- `docs/03-specs/platform/tool-artifacts.md`
- `docs/03-specs/platform/tool-linkage.md`
- `tasks/tool-lifecycle-implementation-plan.md`

---

## 1. What Already Exists

### SDK — tool step creation (`leer/tool.py`)

- `tool_step()` context manager creates a `TraceStep` with `step_type="tool"`.
- `parent_step_id` defaults to `current_step().id` if not explicitly passed. This means a `tool_step` opened while the LLM step context is still active gets parented to it automatically. If the LLM step has already exited (popped from the stack), the tool step is **not** automatically parented — the caller must pass `parent_step_id` explicitly.
- `tool_call_id` is accepted as an optional argument and stored in `metadata["tool_call_id"]`. It is **not** a field on `TraceStep` itself.
- Additional metadata stored: `tool_name`, optionally `provider`, `model`.
- On step exit, `input_summary` and `output_summary` are auto-generated from `s.input` and `s.output` via `make_json_safe`.

### SDK — tool artifacts (`leer/tool.py`)

Three artifact types are created automatically:
- **`tool_request`** — from `s.input` on step exit (JSON artifact, `role="input"`)
- **`tool_response`** — from `s.output` on successful exit (JSON artifact, `role="output"`)
- **`tool_error`** — from the exception on failed exit (JSON artifact, `role="error"`, contains `type`, `message`, `traceback`)

All three use `step_id=s.id` and include `preview_text`. Creation is wrapped in try/except to avoid masking the original error.

### SDK — normalized tool calls (`leer/integrations/normalize.py`)

`LLMOutput.tool_calls` is a `list[dict[str, Any]]`. Each normalized tool call has:
- `id` — the provider call identifier (OpenAI `tool_calls[].id`, Responses API `call_id`/`id`, Anthropic `tool_use` block `id`)
- `name` — tool name
- `arguments` — parsed to dict when possible, raw string fallback

Tool calls are also added to `content_blocks` as `{"type": "tool_call", **tc}`.

### SDK — OpenAI normalization

- **Chat completions:** `tool_calls` from `choices[0].message.tool_calls`. Each maps `id`, `function.name`, `function.arguments`.
- **Responses API:** `function_call` items map `call_id` (or `id`) → `id`, `name`, `arguments`.
- **Streaming:** `StreamCollector` assembles `tool_call_id` → normalized `id`.

### SDK — Anthropic normalization

- `tool_use` blocks map `id`, `name`, `input` → normalized `id`, `name`, `arguments`.
- **Streaming:** `StreamCollector` assembles `id` from accumulated tool-use events.

### SDK — output summaries

Both OpenAI and Anthropic `_output_summary` include tool calls as `[{"name": ...}]` — **names only**. Full tool call data (including `id` and `arguments`) lives in `metadata["llm"]["output"]["tool_calls"]`.

### Backend — DB schema

- `steps` table has: `parent_step_id` (nullable FK to `steps.id`), `step_type` (constrained to include `'tool'`), `metadata` (JSONB).
- **No `tool_call_id` column.** Tool call identifier rides in `metadata` JSONB.
- `artifacts` table has `step_id` FK. No tool-specific columns.
- Index exists on `parent_step_id`.

### Backend — ingestion (`ingestion.py`)

- Steps are persisted generically. No `if step_type == "tool"` logic.
- `parent_step_id` is passed through directly from the ingest payload.
- `metadata` is stored as-is (includes `tool_call_id`, `tool_name`, `provider`, `model` when set by the SDK).

### Backend — timeline API (`routes/runs.py`)

- `_enrich_step` pops `llm` from `metadata`, passes remaining metadata (including `tool_call_id`) to the response.
- `TimelineStep` schema exposes: `parent_step_id`, `step_type`, `metadata`, `llm`, `artifacts`.
- **No computed linkage enrichment.** Tool linkage is left to the frontend.

### Backend — compare API (`services/compare.py`)

- Step matching: Phase 1 = exact name match; Phase 2 = same `step_type` + nearest `sequence_index` (max distance 3); Phase 3 = remaining → missing.
- `CompareStepDiff` exposes: `parent_step_id_a/b`, `metadata_a/b`, `llm_a/b`.
- **No tool-specific comparison logic.** Tool calls are compared only via `output_summary` equality (which only has names, not ids/args).

### Frontend — types (`types.ts`)

- `TimelineStep` has `parent_step_id`, `step_type`, `metadata`, `llm`, `artifacts`.
- `LLMShape.output.tool_calls` is `Record<string, unknown>[]` — loose typed.
- `CompareStepDiff` has `metadata_a/b`, `llm_a/b`. No dedicated tool fields.
- **No `tool_call_id` in any typed interface.** Always accessed via `metadata.tool_call_id` or `tc.id` at runtime.

### Frontend — run detail (`runs/[id]/page.tsx` + `llm-step-detail.tsx`)

- **Two global maps built from timeline steps:**
  - `toolCallIdToToolStep`: for tool steps with `metadata.tool_call_id` → step
  - `toolCallIdToLlmStep`: for LLM steps with `llm.output.tool_calls[].id` → step
- **LLM → tool jump:** `ToolCallsSection` shows each call with truncated `id`, link status (`#{index}` or "untraced"), jump button ("→") when linked.
- **Tool → LLM jump:** `sourceLlmStep` from `toolCallIdToLlmStep`, fallback to `parentStep` via `parent_step_id`. Shows "from step" link.
- **`ToolCallLinkInfo`** interface: `toolStepId`, `toolStepName`, `toolStepIndex`, `toolStepStatus`.

### Frontend — compare (`compare/page.tsx`)

- **`ToolLinkageDiff`** component: shows for `step_type === "tool"` steps. Displays provider, model, and `tool_call_id` from metadata. Color-coded pills.
- **LLM tool calls in compare output:** `OutputContent` shows tool call name + args. **No call ids, no linkage status, no jump.**
- **`StepDiffHeader`**: shows tool-aware provider/model badges when `isTool`.

---

## 2. What Is Missing

### Against `tool-lifecycle.md` spec

| Spec requirement | Current state |
|---|---|
| **Tool call as lifecycle item** with `status` (planned/dispatched/completed/failed/unmatched) | Not modeled. Tool calls are raw dicts in `LLMOutput.tool_calls`. No status field. |
| **`linkage_confidence`** (exact/high/heuristic/unlinked) | Not computed anywhere. Frontend does binary linked/unlinked. |
| **`tool_step_id` on tool call record** | Not modeled. Frontend infers this at render time from `tool_call_id` map. |
| **`llm_step_id` on tool call record** | Not modeled. Frontend infers from the LLM step that contains the tool call. |
| **Unmatched tool calls visible** | Partially — "untraced" badge in run detail, but no lifecycle status. |
| **Multiple tool calls each as own lifecycle item** | Each call is preserved in order, but they are plain dicts, not lifecycle records. |

### Against `tool-artifacts.md` spec

| Spec requirement | Current state |
|---|---|
| **`tool_call` artifact type** | **Does not exist.** LLM-emitted tool calls live in `metadata["llm"]["output"]["tool_calls"]`, not as separate artifacts. |
| **`tool_request`** | Exists. Created by `tool_step`. |
| **`tool_response`** | Exists. Created by `tool_step`. |
| **`tool_error`** | Exists. Created by `tool_step`. |
| **Linkage metadata on artifacts** (`tool_name`, `call_id`, `parent_llm_step_id`) | Partially. `tool_request/response/error` artifacts have `step_id` (the tool step). No `call_id`, no `parent_llm_step_id` in artifact metadata. |

### Against `tool-linkage.md` spec

| Spec requirement | Current state |
|---|---|
| **Exact identifier match** (shared `call_id`) | Works when both sides set `tool_call_id`. Frontend matches `llm.output.tool_calls[].id` ↔ `metadata.tool_call_id`. |
| **Ordered structural match** (name + order + args fingerprint) | Not implemented. Falls back to parent_step_id only. |
| **Linkage confidence labeling** | Not computed. |
| **Multiple possible matches handled** | Not handled. First match wins in the Map. |
| **Tool call emitted but never executed → visible** | Partially — "untraced" badge. No explicit "unmatched" state. |
| **Tool step with no originating call → visible** | Not explicitly handled. Falls back to parent link or nothing. |

---

## 3. Current Linkage Model

Linkage today is **frontend-only, id-based, single-dimension:**

1. SDK `tool_step(tool_call_id=...)` stores the id in `metadata["tool_call_id"]`.
2. SDK normalizers preserve `id` on each tool call in `LLMOutput.tool_calls`.
3. Backend passes both through as-is (metadata JSONB, no transformation).
4. Frontend builds `toolCallIdToToolStep` and `toolCallIdToLlmStep` maps from the timeline.
5. Match is purely `string === string` on the call id.
6. No fallback heuristics (name, order, args) exist if the id is missing.
7. No confidence labeling.
8. No backend-side linkage computation.

**When `tool_call_id` is present on both sides, linkage works correctly.** This covers OpenAI (chat completions and Responses API) and Anthropic `tool_use` blocks, which all provide stable call ids.

**When `tool_call_id` is missing** (e.g. custom tools, non-provider tool calls), linkage falls back to `parent_step_id` for the tool→LLM direction only. LLM→tool direction is completely broken without the id.

---

## 4. Artifact Coverage Status

| Artifact type | Created by | Attached to | Present? |
|---|---|---|---|
| `llm_request` | OpenAI/Anthropic wrappers | LLM step | Yes |
| `llm_response` | OpenAI/Anthropic wrappers | LLM step | Yes |
| `llm_stream` | OpenAI/Anthropic wrappers (streaming) | LLM step | Yes |
| `tool_call` | — | — | **Missing.** Tool call intents are not persisted as artifacts. They live only in `metadata["llm"]["output"]["tool_calls"]`. |
| `tool_request` | `tool_step` on exit | Tool step | Yes |
| `tool_response` | `tool_step` on success | Tool step | Yes |
| `tool_error` | `tool_step` on failure | Tool step | Yes |

The `tool_call` artifact gap means there is no standalone, addressable record of the LLM's tool-call intent separate from the LLM response blob. The spec says this should exist. However, the data is fully preserved — it just lives inside the `llm_response` artifact and `metadata["llm"]` rather than as its own artifact.

---

## 5. Run-Detail UI Status

### What works well
- Tool calls are displayed in a dedicated `ToolCallsSection` with call id, name, arguments.
- Jump from LLM tool call → tool step works when `tool_call_id` matches.
- Jump from tool step → originating LLM step works (via `toolCallIdToLlmStep` or `parent_step_id` fallback).
- "untraced" badge appears when no linked tool step is found.
- Tool step detail shows `StepDetailPanel` with input/output/error and artifact viewer.

### What is missing or incomplete
- No lifecycle status (planned/dispatched/completed/failed/unmatched) on tool calls.
- No linkage confidence indicator (exact vs heuristic vs unlinked).
- "untraced" is the only unmatched indicator — no distinction between "never executed" and "executed but not linked."
- Tool step → originating call direction does not show the specific call payload (name, args) from the LLM side.
- No explicit rendering of tool steps that have no originating call.

---

## 6. Compare-Page Status

### What works
- `ToolLinkageDiff` shows for tool-type steps: provider, model, `tool_call_id` side-by-side.
- LLM output section shows tool call names + arguments in `OutputContent`.
- Step matching (name-based, then type+index fallback) works for tool steps.
- No crashes with tool data.

### What is missing or incomplete
- **No tool-call-level comparison.** LLM tool calls are compared via `output_summary` equality, which only has names (no ids, no args). Two runs with same tool names but different arguments or different call counts show no diff in the summary.
- **No linkage status comparison.** Cannot see "Run A linked tool call X; Run B left it unmatched."
- **No call-id comparison in LLM output.** Compare output shows name + args but not id.
- **No tool-call count diff.** If Run A has 2 tool calls and Run B has 3, this is not surfaced explicitly.

---

## 7. DB / Schema / API Readiness

### What is ready
- `steps.parent_step_id` — exists, indexed, nullable FK.
- `steps.step_type` — exists, includes `'tool'` in check constraint.
- `steps.metadata` — JSONB, already carries `tool_call_id`, `tool_name`, `provider`, `model`.
- `artifacts.step_id` — FK to steps, so tool artifacts are already linked to tool steps.
- `StepPayload` / `TimelineStep` / `CompareStepDiff` all expose `parent_step_id` and `metadata`.

### What is NOT ready (but may not be needed for v1)
- **No `tool_call_id` column on `steps`.** Currently metadata-only. Adding a column would enable backend-side linkage queries but is not strictly required if linkage stays frontend-only.
- **No `linked_call_id` on tool call records.** Because tool call records don't exist as separate entities.
- **No linkage confidence field anywhere.** Would need a new column or a new metadata convention.
- **No backend linkage computation.** Timeline and compare responses are tool-linkage-naive.

### Schema changes needed?
For a v1 that keeps linkage frontend-only and improves normalization + rendering:
- **No schema changes are required.**
- `metadata` JSONB is sufficient for `tool_call_id`, and `output_summary` can be enriched without new columns.
- If we later want backend-computed linkage or queryable `tool_call_id`, that's a future migration.

---

## 8. Biggest Risks / Ambiguities

1. **`tool_call_id` availability varies.** Provider wrappers always produce ids. But manual `tool_step()` calls depend on the user passing `tool_call_id`. If they don't, linkage is entirely broken for LLM→tool direction. No fallback heuristic exists.

2. **`parent_step_id` is context-dependent.** A `tool_step` only gets `parent_step_id` pointing to the LLM step if it is opened while the LLM step is still the `current_step()`. Framework/user code that runs tool calls after the LLM step exits gets `parent_step_id=None` or pointing to the wrong parent. This is a real-world pattern (LLM returns, then tools execute sequentially).

3. **`output_summary` for tool calls is too thin.** Only names, no ids or args. This means compare-level diffing of tool calls is effectively impossible from summaries alone. The full data is in `metadata["llm"]["output"]["tool_calls"]`, but compare doesn't use it.

4. **No fallback linkage heuristics.** When `tool_call_id` is absent, the system gives up on LLM→tool linking. The spec calls for name + order + args fingerprint fallback. This is the single biggest gap.

5. **`tool_call` artifact does not exist.** The spec calls for it. The data is preserved inside `llm_response`, but there is no standalone artifact to link, inspect, or reference independently. Adding it is low risk but needs a decision on whether to create it during normalization or at ingest time.

6. **Lifecycle status is unmodeled.** The spec defines planned/dispatched/completed/failed/unmatched. None of this exists as data. It can be derived at render time from linkage + tool step status, but it's not computed or stored.

---

## 9. Recommended Implementation Order

### Step 1 — Enrich tool-call normalization and output summaries

- Add `id` and `arguments` (or args hash) to `output_summary.tool_calls` so compare can diff tool calls properly.
- Ensure `tool_call_id` is always populated in tool step metadata when the SDK wrapper creates tool steps.
- Optionally: derive lifecycle status (planned, completed, failed, unmatched) at frontend render time from existing data.
- **No schema changes needed.**

### Step 2 — Add heuristic fallback linkage (frontend)

- When `tool_call_id` matching fails, try ordered structural match: same `parent_step_id` neighborhood + same tool name + sequence order.
- Add linkage confidence labeling: `exact` (id match), `heuristic` (structural match), `unlinked`.
- Surface confidence in the UI.
- **No schema changes needed.**

### Step 3 — Run-detail UX polish

- Show lifecycle status on tool calls (derived from linkage + tool step status).
- Show originating call payload on tool step detail.
- Distinguish "never executed" from "executed but not linked."
- Polish unlinked/unmatched states.

### Step 4 — Compare improvements

- Compare tool calls by id, name, and arguments (from enriched summary or `metadata["llm"]`).
- Show tool-call count differences.
- Show linkage status differences.
- Keep stable with blob-backed tool artifacts.

### Step 5 — Optional: `tool_call` artifact + backend linkage

- Create `tool_call` artifacts during normalization (one per call in the LLM step).
- Optionally compute linkage on the backend (timeline enrichment).
- This step is deferrable and may not be needed for v1.

---

## 10. Direct Answer: Can Step 1 Start Without Schema Changes?

**Yes.**

All the data needed for Step 1 already exists in the system:
- Tool call `id`, `name`, `arguments` are preserved in `metadata["llm"]["output"]["tool_calls"]`.
- Tool step `tool_call_id` is in `metadata["tool_call_id"]`.
- `parent_step_id` is a column on `steps`.
- `output_summary` is a JSONB column that can be enriched without migration.

Step 1 work is:
1. Enrich `output_summary.tool_calls` in the SDK normalizers (add `id`, optionally `arguments_hash`).
2. Ensure wrapper-created tool steps always have `tool_call_id` in metadata.
3. Optionally derive lifecycle status in the frontend from existing linkage + step status.

No new DB columns, no new API fields, no new migrations. The existing `metadata` JSONB and `output_summary` JSONB provide all the extensibility needed.
