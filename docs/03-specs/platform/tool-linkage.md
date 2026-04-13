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

---

## Linkage Confidence

Every linked pair should conceptually carry a confidence level:

- `exact`
- `high`
- `heuristic`
- `unlinked`

This confidence should be available to the UI layer even if the first UI only uses it lightly.

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

---

## v1 Delivery Target

Tool linkage is considered done enough when:
- exact matches work when ids exist
- ordered fallback linking works for common cases
- unmatched calls remain visible
- run detail and compare both stay stable
- the UI can distinguish exact vs heuristic vs unlinked states
