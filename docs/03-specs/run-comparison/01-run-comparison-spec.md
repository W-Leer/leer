# Run Comparison Spec

This document defines Leer’s run comparison system.

---

## Goal

Allow a developer to compare two runs and quickly understand:

- what changed at the run level
- which steps truly correspond to each other
- which steps are missing on one side
- whether prompts, outputs, errors, metadata, or usage changed
- whether an LLM step changed semantically in a meaningful way

The comparison system should optimize for **truthful alignment** over forced pairing.

---

## Product Principle

Run comparison must not pretend two steps are equivalent just because they have the same position.

A bad comparison is worse than an incomplete comparison.

The system should:

- align confidently when possible
- show unmatched steps honestly
- render richer provider-aware diffs for LLM steps
- fall back cleanly for non-LLM steps

---

## Core Design

Comparison has three layers:

1. **Run-level comparison**
2. **Step matching**
3. **Step-level rendering**

---

## 1. Run-level Comparison

The compare view should always show:

- Run A summary
- Run B summary

Each summary should include:

- run id
- workflow name
- status
- created_at
- total steps
- total duration if available
- output summary preview if useful

Optional but useful:
- provider/model summary when present at run level
- token totals when available

---

## 2. Step Matching

### Why matching matters

Two runs may differ in structure because:

- a step was inserted
- a step was skipped
- a step was renamed
- a step was split into multiple steps
- a wrapper-generated LLM step exists only in one run
- a step failed early and later steps never happened

Therefore matching by pure `sequence_index` is not sufficient.

---

## Matching Strategy

The comparison backend should use a deterministic matching strategy with confidence ordering.

### Primary match
**Exact step name match**

If two steps share the same `name`, they should be matched first.

This is the strongest default signal for developer workflows.

### Secondary match
**Same step type + nearest unmatched sequence_index**

If no exact name match exists, compare remaining unmatched steps by:

- same `step_type`
- smallest absolute `sequence_index` distance

This is a fallback only, not the main rule.

### Final state
Any remaining unmatched steps are marked as:

- missing in A
- missing in B

The compare UI must show this explicitly.

---

## Matching Rules

### Rule 1
A step can be matched at most once.

### Rule 2
Exact name matches are resolved before fallback matches.

### Rule 3
Fallback matches should only happen when reasonably plausible:
- same `step_type`
- nearest unmatched sequence
- deterministic tie-breaking

### Rule 4
If no plausible fallback exists, do not force a match.

### Rule 5
The system should prefer **truthful missing steps** over misleading alignment.

---

## Matching Metadata

Each compared step entry should include enough metadata for the frontend to explain alignment quality.

Suggested fields:

- `match_kind`: `exact_name` | `fallback_type_index` | `missing`
- `exists_in_a`
- `exists_in_b`

This gives the product room to later surface:
- “matched by name”
- “approximate match”
- “missing in B”

Even if the UI does not show all of this initially, the backend should produce it.

---

## 3. Step-level Comparison

Each compared step block should include:

- sequence index A / B
- step name A / B
- step type A / B
- existence flags
- matched / missing label
- rich field comparisons

---

## Fields to Compare

### Common fields
For all steps compare:

- `status`
- `output_summary`
- `error_summary`

Also compare when useful:

- `input_summary`
- `duration_ms`
- `model_provider`
- `model_name`

### LLM-aware fields
If either side has `llm` data, compare richer normalized LLM fields:

#### Metadata
- provider
- model
- total tokens
- prompt tokens
- completion tokens
- latency
- finish reason

#### Input
- system prompt
- user messages
- developer messages if present
- params
- tools

#### Output
- output text
- tool calls
- content blocks

#### Error
- error summary
- missing output / missing response state

---

## Comparison Output Shape

```json
{
  "run_a": {
    "id": "uuid",
    "workflow_name": "demo-agent",
    "status": "completed",
    "created_at": "2026-03-24T12:00:00Z",
    "total_steps": 5,
    "total_duration_ms": 812
  },
  "run_b": {
    "id": "uuid",
    "workflow_name": "demo-agent",
    "status": "failed",
    "created_at": "2026-03-24T12:05:00Z",
    "total_steps": 2,
    "total_duration_ms": 1300
  },
  "steps": [
    {
      "match_kind": "exact_name",
      "exists_in_a": true,
      "exists_in_b": true,

      "sequence_index_a": 0,
      "sequence_index_b": 0,

      "name_a": "prepare_prompt",
      "name_b": "prepare_prompt",

      "step_type_a": "code",
      "step_type_b": "code",

      "status_a": "completed",
      "status_b": "completed",
      "status_diff": false,

      "output_summary_a": {
        "prompt_preview": "Summarize this text"
      },
      "output_summary_b": {
        "prompt_preview": "Summarize this text"
      },
      "output_diff": false,

      "error_summary_a": null,
      "error_summary_b": null,
      "error_diff": false,

      "llm_a": null,
      "llm_b": null
    },
    {
      "match_kind": "missing",
      "exists_in_a": true,
      "exists_in_b": false,

      "sequence_index_a": 1,
      "sequence_index_b": null,

      "name_a": "gpt-4.1",
      "name_b": null,

      "step_type_a": "llm",
      "step_type_b": null,

      "status_a": "completed",
      "status_b": null,
      "status_diff": true,

      "output_summary_a": {
        "text": "This is the summary"
      },
      "output_summary_b": null,
      "output_diff": true,

      "error_summary_a": null,
      "error_summary_b": null,
      "error_diff": false,

      "llm_a": {
        "provider": "openai",
        "model": "gpt-4.1",
        "input": {
          "system": "You are helpful.",
          "messages": [{"role": "user", "content": "Summarize this text"}],
          "tools": [],
          "params": {"temperature": 0.3}
        },
        "output": {
          "text": "This is the summary",
          "tool_calls": [],
          "content_blocks": [{"type": "text", "text": "This is the summary"}]
        },
        "usage": {
          "prompt_tokens": 98,
          "completion_tokens": 44,
          "total_tokens": 142
        },
        "meta": {
          "latency_ms": 1230,
          "finish_reason": "stop",
          "request_id": "chatcmpl-123"
        }
      },
      "llm_b": null
    }
  ]
}
```

---

## Backend Endpoint

### Route
`GET /v1/runs/{run_id}/compare/{other_run_id}`

### Purpose
Compare two runs and return:

- run-level summary for A and B
- matched and unmatched step comparisons
- rich provider-aware data when available

---

## Backend Behavior

### Validation
- both runs must exist
- both runs must belong to the same project

### Query behavior
- fetch both runs
- fetch steps for both runs
- fetch any provider-aware step data already exposed by the timeline/detail layer
- order source steps by `sequence_index ASC`

### Matching behavior
Implement the matching strategy described above:

1. exact name match
2. fallback same type + nearest unmatched sequence
3. remaining unmatched => missing

### Comparison behavior
For every matched/unmatched compare entry:
- compare common fields
- include llm payloads if present
- compute booleans such as:
  - `status_diff`
  - `output_diff`
  - `error_diff`

### Error cases
- return 404 if either run is missing
- return 400 if runs belong to different projects

---

## Compare UI Requirements

### Entry points

#### Run detail page
Provide a clear “Compare” action on the run header.

#### Compare page
Allow direct compare setup by selecting:
- Run A
- Run B

The compare page should not be a dead route.
It must support direct use without starting from a run detail page.

---

## Compare UI Layout

### Header
Show:
- “Compare Runs”
- Run A summary
- Run B summary

### Step blocks
Each compared step is shown as a vertical block.

The UI should support:
- exact matches
- approximate matches
- missing steps

### Step header
Show:
- sequence index A / B if useful
- step name
- step type
- match / missing label

Example:
- `#1 gpt-4.1 · llm · missing in B`
- `#0 prepare_prompt · code`
- `#2 rank_results · code · approx match`

---

## Rendering Rules

### For non-LLM steps
Use generic comparison rendering:
- status A vs B
- output_summary A vs B
- error_summary A vs B

### For LLM steps
Use provider-aware comparison rendering.

Render:

#### Metadata diff row
- provider A vs B
- model A vs B
- total tokens A vs B
- latency A vs B
- finish reason A vs B

#### Input diff
Structured:
- system prompt
- user/developer messages
- params
- tools

#### Output diff
Structured:
- output text
- tool calls
- content blocks if useful

#### Error diff
Structured:
- error presence
- error message
- missing output state

---

## Highlighting

Use color and labels to indicate differences.

### Same
- neutral

### Changed
- highlight clearly but calmly

### Missing
- strong explicit label such as:
  - `missing in A`
  - `missing in B`

### Error
- red emphasis

The compare page should prioritize clarity over visual noise.

---

## Ordering

Compared step blocks should be shown in a stable, readable order.

Recommended ordering:
- primarily by the earliest available sequence index among A/B
- unmatched steps should appear where they best fit structurally, not dumped randomly at the end

---

## UX Notes

### Truthful alignment
The UI should not imply equivalence when matching confidence is weak.

### Low-overlap runs
When two runs have very different structures, compare should still work but may show:
- many missing steps
- only a few meaningful matches

That is acceptable.

Optional later UX enhancement:
- small note like “Low structural overlap between these runs”

---

## Non-goals

- automatic semantic matching using embeddings or LLMs
- fully automatic text diff highlighting
- replay integration
- multi-run compare
- artifact-level raw side-by-side diff as the primary view

---

## Design Principles

- prefer truthful comparison over forced alignment
- exact name match is the strongest default
- fallback matching must be deterministic
- provider-aware LLM compare is first-class
- generic step compare remains supported
- the compare page should feel like the same product quality level as run detail

---

## Testing

### Backend tests
Add at least:
- compare identical runs
- compare runs with changed status/output
- compare runs with missing steps
- compare runs with same names but shifted sequence indexes
- compare runs with no exact-name LLM match
- compare runs with provider-aware LLM data on one or both sides

### UI tests
If practical:
- generic step compare rendering
- LLM compare rendering
- missing-step labeling

---

## Summary

Run comparison is not just a diff by position.

It is a structured developer workflow that should answer:

**What changed between these two runs, and which steps truly correspond to each other?**
