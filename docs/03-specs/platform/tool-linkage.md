# Tool Linkage

Defines how Leer links LLM-emitted tool calls to concrete tool execution steps and related artifacts.

This is the permanent linkage spec that complements:
- `tool-lifecycle.md`
- `tool-artifacts.md`

---

## Goal

Link tool calls and tool executions in a way that is:
- deterministic when possible
- transparent when heuristic
- stable across providers
- useful in both run detail and compare

---

## Problem Statement

Most AI traces contain at least two distinct records:
- an LLM step that emitted one or more tool calls
- one or more tool steps that later executed

Without explicit linkage, users must mentally reconstruct the flow.

Leer should do that reconstruction once, clearly, and with visible confidence.

---

## Canonical Linkage Priority

When linking a tool call to a tool step, use this priority order:

### 1. Exact identifier match

Use a shared explicit id when available:
- provider call id
- framework call id
- application-level invocation id

This is the strongest linkage and should be labeled `exact`.

### 2. Explicit parent/child metadata

Use framework metadata that directly states:
- this tool step came from this LLM step/call

Label as `high` if the mapping is explicit but not based on one shared id.

### 3. Ordered structural match

Use all of the following together when exact ids are unavailable:
- same parent LLM step neighborhood
- same tool name
- same relative order among sibling calls
- matching arguments fingerprint when possible
- close temporal proximity

Label as `heuristic`.

### 4. No link

If none of the above is safe enough, leave the tool call unlinked.

Label as `unlinked`.

---

## One-to-One Bias

For v1, Leer should strongly prefer **one tool call -> one tool execution step**.

This matches the most common real-world pattern and keeps the model understandable.

More complex cases may exist later:
- one tool call fan-out
- retries generating multiple tool steps
- one orchestration step wrapping multiple external calls

These can be supported later with richer linkage graphs.

---

## Matching Dimensions

When exact ids are unavailable, safe linkage should consider:

- `tool_name`
- call order within the LLM step
- argument fingerprint or normalized hash
- temporal proximity
- same run
- same project
- same local execution neighborhood

No single heuristic dimension should be treated as sufficient by itself except an explicit identifier.

### v1 implementation

The heuristic fallback (`buildToolCallLinkage()` in `apps/web/src/lib/tool-linkage.ts`) uses:

1. **Exact `tool_call_id` match** — always wins, confidence = `exact`
2. **Tier 1 candidates**: unclaimed child tool steps (`parent_step_id === llmStep.id`) with same tool name
3. **Tier 2 candidates**: unclaimed tool steps after the LLM step (by `sequence_index`) with same tool name
4. **Ordered alignment**: nth unresolved call → nth name-compatible candidate
5. If no compatible candidate exists, the call remains `unlinked`

Tool-step name resolution: `metadata.tool_name` > `step.name`. Empty tool-call name → always unlinked.

The heuristic is intentionally conservative. It does not use argument fingerprinting or temporal proximity for matching — only name, parent/child relationship, and order. This avoids false positives at the cost of occasional missed links in complex multi-call scenarios.

---

## Linkage Confidence

Every linked pair should conceptually carry a confidence level:

- `exact`
- `high`
- `heuristic`
- `unlinked`

This confidence should be available to the UI layer even if the first UI only uses it lightly.

### v1 implementation

v1 uses a 3-level confidence model: `exact | heuristic | unlinked`.

`high` is not implemented. It would require explicit parent/child metadata that is not a shared id — no current provider produces this distinctly from exact id matching. If a use case emerges, it can be added without breaking existing behavior.

---

## Artifact-Assisted Linkage

Artifacts can strengthen linkage.

Examples:
- `tool_call` artifact contains `call_id`
- `tool_request` artifact contains normalized arguments
- `tool_response` artifact contains matching execution metadata

Artifacts should support linkage, but the authoritative relationship should live in the lifecycle/linkage model rather than being inferred ad hoc in the UI.

---

## Failure Cases

### Tool call emitted but never executed

This should remain visible as an unmatched/planned call.

### Tool step executed with no visible originating call

This should remain visible as an unlinked tool execution.

### Multiple possible matches

Leer should avoid pretending certainty.
If ambiguity remains after heuristics, prefer unlinked over wrong linkage.

### Retry behavior

If retries produce multiple tool steps for what appears to be one call, v1 may:
- link the first matching execution
- leave later retries visible but not deeply modeled

This should be documented as a v1 limitation.

---

## Compare Implications

Compare should be able to ask:
- did both sides emit the same tool calls?
- did both sides link successfully?
- did either side fail to execute a call?
- did execution status differ?
- did call counts diverge?

Full graph diffing is out of scope for v1.

### v1 implementation

Compare aligns tool calls across runs using:
1. Id-based matching (same `tool_call_id` on both sides)
2. Positional-name fallback (same name at same array index)
3. Unmatched remainder shown as one-sided ("only in A" / "only in B")

Per-call diffs surface: name, id, `arguments_hash`, lifecycle badges, and one-sided presence. Tool-step compare cards show confidence badges derived from step metadata.

Compare-side lifecycle derivation is best-effort — it scans the compare step list for matching tool steps, not the full run timeline. This is a known limitation.

---

## UI Expectations

### Run detail

Run detail should make linked relationships obvious.
Examples:
- tool call row can jump to linked tool step
- tool step can show originating call
- unmatched states are labeled clearly

### Compare

Compare should not require full graph visualizations in v1.
Badges, summaries, and linkage-state sections are sufficient.

---

## Non-Goals for v1

- full DAG provenance
- multi-hop result-consumption tracking
- branching orchestration visualizations
- retry lineage modeling beyond basic visibility
- framework-specific graph semantics
- backend-computed linkage
- argument-fingerprint or temporal-proximity matching in heuristics

---

## v1 Status

Tool linkage v1 is shipped. Current state:

- Exact id matching works when `tool_call_id` exists on both LLM call and tool step
- Heuristic fallback uses parent/child + same name + ordered alignment
- Unmatched calls visible with `unmatched` / `unlinked` badges
- Run detail shows bidirectional jump navigation (LLM call ↔ tool step)
- Compare shows aligned tool calls with lifecycle and confidence badges
- All linkage is frontend-derived from existing timeline API data

### v1 Limitations

- **No backend linkage**: computed at render time on every page load. Backend-computed linkage would be more efficient and could support richer confidence signals.
- **No `high` confidence level**: only `exact | heuristic | unlinked` implemented.
- **Conservative heuristics**: no argument fingerprinting, no temporal proximity. May miss links when multiple same-name tool steps exist without parent/child context.
- **No ambiguity detection**: when multiple candidates exist, ordered matching picks the first compatible one rather than explicitly surfacing ambiguity.
- **Compare lifecycle is best-effort**: derived from compare step rows, not full timelines.

---

## What Comes Later

Beyond v1:
- backend-computed linkage for stronger guarantees and performance
- `high` confidence level for explicit parent/child metadata
- argument-fingerprint assisted matching
- retry lineage modeling
- framework-specific adapters
