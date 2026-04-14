# Tool Lifecycle

Defines Leer's platform-level model for tool calling as a first-class execution lifecycle.

This document is the permanent product and technical spec for how Leer models, stores, links, and renders tool invocation flows across providers and orchestration frameworks.

---

## Goal

Represent tool usage as a stable lifecycle rather than a loose collection of inferred events.

Leer should be able to:
- capture when an LLM decides to call a tool
- capture the tool call payload and identity
- capture the actual tool execution step
- capture the tool result or failure
- link the call and the execution deterministically
- render the lifecycle clearly in run detail and compare
- avoid provider-specific product semantics whenever possible

---

## Why This Exists

Tool use is one of the core realities of production AI workflows.

Without a lifecycle model, traces degrade into:
- one LLM step that emitted a tool call
- one or more tool steps somewhere else
- one later LLM step that consumed the result

That is not enough for fast debugging.

Leer needs to answer:
- which exact tool call produced this tool step?
- was the tool executed or only proposed?
- did the tool return successfully, fail, or never run?
- which result did the next LLM turn consume?
- did Run A and Run B follow the same tool path?

---

## Scope

Tool lifecycle in Leer includes:

### Tool-call intent
- tool call emitted by an LLM
- tool name
- call id / provider call identifier when available
- arguments / structured payload
- order among multiple calls

### Tool execution
- actual tool step created by the application or framework
- execution status
- timing
- input payload
- output payload
- error payload

### Tool result consumption
- later LLM step that receives tool results
- linkage from the tool execution back into the conversation flow

### Cross-step linkage
- LLM call -> tool execution
- tool execution -> tool result artifact
- tool result -> next LLM turn when inferable

---

## Design Principles

### 1. Lifecycle before rendering

Leer should model tool use explicitly before optimizing how it appears in the UI.

### 2. Linkage should be deterministic when possible

Prefer explicit identifiers over name-based guessing.

Priority order:
1. provider/tool call id
2. framework-generated linkage id
3. explicit parent/child relationship
4. ordered fallback heuristics

### 3. Tool execution is distinct from tool intent

A tool call emitted by a model is not the same as a tool step that executed.

They are separate lifecycle stages and must remain separate in the model.

### 4. Provider-agnostic core, provider-aware enrichment

Providers differ in how they encode tool calls.
Leer should normalize them into one stable internal lifecycle shape.
Provider-specific fields may still be preserved in metadata and raw artifacts.

### 5. Missing linkage must degrade gracefully

If deterministic linking is not possible, Leer should still:
- preserve the raw tool call
- preserve the raw tool step
- show linkage confidence clearly
- avoid silently inventing certainty

---

## Canonical Lifecycle Model

A complete tool lifecycle consists of up to four conceptual stages:

1. **planned**
   - an LLM emitted a tool call intent
2. **dispatched**
   - the application/framework decided to execute it
3. **completed** or **failed**
   - the tool step finished with output or error
4. **consumed**
   - a later LLM turn incorporated the tool result

Not every trace will contain every stage.

### v1 implementation

v1 implements a 3-status subset derived at render time in the frontend:

- **completed** — a linked tool step exists with `status == "completed"`
- **failed** — a linked tool step exists with `status == "failed"`
- **unmatched** — no linked tool step found, or linked step has a non-terminal status

`planned` and `dispatched` are deferred. They would require richer orchestration data than exists today (e.g. explicit dispatch events, framework-level intent tracking).

`consumed` is deferred. Tracking which later LLM turn incorporated a tool result requires message-level provenance that is not modeled yet.

---

## Canonical Entities

### Tool call record

Represents an LLM-emitted tool call.

Conceptual fields:
- `tool_name`
- `call_id` nullable
- `sequence_index`
- `arguments`
- `provider`
- `provider_call_type`
- `status` (`planned`, `dispatched`, `completed`, `failed`, `unmatched`)
- `llm_step_id`
- `tool_step_id` nullable
- `linkage_confidence` (`exact`, `high`, `heuristic`, `unlinked`)

#### v1 implementation

Tool call records are not a dedicated database entity. They exist in two forms:

1. **`output_summary.tool_calls`** on the LLM step — compact array with `{name, id?, arguments_hash?}`. This is the primary source for compare and summary rendering.
2. **`tool_call` artifacts** on the LLM step — one JSON artifact per emitted call, with full `arguments`, `tool_call_id`, `arguments_hash`, `call_index`, `provider`, and `model` in payload and metadata.

Lifecycle status and linkage confidence are derived at render time in the frontend, not stored.

### Tool step record

Represents the actual tool execution.

Conceptual fields:
- `tool_step_id`
- `tool_name`
- `status`
- `started_at`
- `ended_at`
- `input_artifact_ids`
- `output_artifact_ids`
- `error_artifact_ids`
- `linked_call_id` nullable

#### v1 implementation

Tool steps are standard `TraceStep` records with `step_type="tool"`. Key metadata fields:
- `metadata.tool_name` — canonical tool name
- `metadata.tool_call_id` — when available, enables exact linkage
- `metadata.provider` / `metadata.model` — source LLM context
- `parent_step_id` — when set to the LLM step id, strengthens heuristic linkage

Artifacts (`tool_request`, `tool_response`, `tool_error`) are created automatically by the `tool_step` context manager and carry linkage metadata (`tool_name`, `tool_call_id`, `parent_llm_step_id`).

---

## Lifecycle Rules

### Planned

A tool call becomes **planned** when a normalized LLM output contains a tool-call content part.

### Dispatched

A tool call becomes **dispatched** when Leer can link it to a concrete tool step.

### Completed

A dispatched tool call becomes **completed** when the linked tool step succeeds.

### Failed

A dispatched tool call becomes **failed** when the linked tool step fails.

### Unmatched

If an LLM emits a tool call but Leer cannot link it to a concrete tool step, it remains **unmatched**.

This is valid and must be visible in the UI.

---

## Multiple Tool Calls

A single LLM step may emit multiple tool calls.

Requirements:
- preserve original order
- preserve each call as its own lifecycle item
- allow one-to-one linkage to different tool steps
- do not collapse multiple calls into one summary object

If two calls target the same tool name, order and id must still distinguish them.

---

## Streaming Considerations

In streaming flows, tool calls may emerge incrementally.

Requirements:
- partial tool-call deltas may be captured during stream playback
- final assembled tool call must become the canonical tool-call record
- lifecycle linking should use the final assembled call, not transient deltas

---

## Compare Implications

In compare, Leer should support:
- presence/absence of tool calls
- tool name changes
- argument shape changes
- linkage success vs unmatched state
- tool execution status changes
- timing differences between linked executions

v1 compare does not require full semantic diffing of arbitrary tool outputs.

### v1 implementation

Compare uses `output_summary.tool_calls` as the source of truth. Tool calls are aligned across runs using id-based matching first, then positional-name fallback. The compare page surfaces:
- tool call count differences
- per-call name, id, and `arguments_hash` diffs
- one-sided calls ("only in A" / "only in B")
- lifecycle badges per call per side (derived by scanning compare tool steps)
- tool-step confidence badges (`exact` / `heuristic` / `unlinked`)
- insight block for tool failure divergence and call-count divergence

Compare-side lifecycle derivation is best-effort: it scans the compare step list, not the full run timeline. When the compare API cannot structurally match a tool step, lifecycle may report `unmatched` even if the step exists in the full timeline.

---

## UI Requirements

### Run detail

Run detail should make the lifecycle obvious:
- which LLM step emitted the call
- which tool step executed it
- whether it succeeded or failed
- where the result is stored

#### v1 implementation

Run detail renders per-call badges for lifecycle (`completed` / `failed` / `unmatched`) and confidence (`exact` / `heuristic` / `unlinked`). Jump navigation works bidirectionally: LLM tool call → tool step, and tool step back-link → source LLM step.

Linkage is computed entirely in the frontend via `buildToolCallLinkage()` in `apps/web/src/lib/tool-linkage.ts`, using the timeline step data from the existing API.

### Compare

Compare should show:
- did both sides emit the same calls?
- did both sides execute them?
- were they matched cleanly?
- did execution status differ?

### Confidence visibility

If linkage was heuristic rather than exact, the UI should be able to show that.

---

## Non-Goals for v1

The first lifecycle milestone explicitly avoids:
- perfect consumption tracking into every later LLM turn
- semantic diffing of arbitrary tool outputs
- framework-specific orchestration trees
- provider-specific UI branches unless unavoidable
- full DAG visualization
- backend-computed linkage (all linkage is frontend-derived in v1)
- stored lifecycle status (derived at render time)

---

## v1 Status

Tool lifecycle v1 is shipped. Current state:

- LLM-emitted tool calls normalized via `output_summary.tool_calls` with `{name, id?, arguments_hash?}`
- Each tool call preserved as a `tool_call` artifact on the LLM step
- Tool steps linked to calls via exact `tool_call_id` or heuristic name/parent/order matching
- Unmatched calls visible with `unmatched` / `unlinked` badges
- Run detail shows lifecycle and confidence badges, bidirectional jump navigation
- Compare shows aligned tool calls with per-field diffs, lifecycle badges, confidence badges, and insight detection
- No schema changes were needed — all behavior is additive

### v1 Limitations

- **3-status lifecycle**: only `completed`, `failed`, `unmatched`. No `planned` / `dispatched` / `consumed`.
- **Frontend-derived linkage**: linkage and lifecycle are computed at render time from timeline data, not stored or backend-computed. This means linkage is recomputed on every page load.
- **Heuristic matching is conservative**: uses parent preference + ordered alignment + first compatible candidate. Does not perform dedicated ambiguity detection. When multiple same-name candidates exist, ordered matching may not pick the "best" one in all cases.
- **Compare lifecycle is best-effort**: scans compare step rows, not full run timelines. May report `unmatched` when the compare API couldn't structurally match a tool step.
- **No full artifact-level compare**: compare reads `output_summary` data, not `tool_call` artifact payloads.
- **`high` confidence level not implemented**: the spec defines `exact | high | heuristic | unlinked` but v1 only uses `exact | heuristic | unlinked`. `high` would require explicit parent/child metadata that isn't a shared id, which no current provider produces distinctly from exact.

---

## What Comes Later

Beyond v1:
- `planned` / `dispatched` / `consumed` lifecycle stages
- result-consumption tracking into later LLM turns
- backend-computed linkage for stronger guarantees
- richer compare diff for arguments and outputs
- orchestration graphs
- framework-specific adapters for MCP, LangGraph, OpenAI Agents SDK, etc.
- `high` confidence level if a distinct use case emerges
