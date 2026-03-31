# Structured Outputs — Implementation Plan

## Goal

Make structured outputs a first-class debugging surface in Leer so developers can clearly inspect:

- JSON/object outputs from LLM steps
- schema-constrained outputs
- structured tool results
- nested dictionaries and arrays
- comparison diffs for structured summaries

This phase is about **representation and UX**, not about adding provider-specific schema enforcement or backward-compatibility layers.

---

## What we want at the end

A developer should be able to open a run and immediately understand:

- whether a step returned plain text or structured data
- the shape of the structured output
- the important top-level fields without opening raw JSON
- the full structured payload when expanded
- the difference between two structured outputs in compare view

The UI should feel devtool-grade: compact by default, readable, expandable when needed.

---

## Scope

### In scope

- Improve how structured `input_summary` / `output_summary` are displayed
- Promote structured LLM outputs when available
- Add compact structured rendering in run detail
- Improve compare rendering for structured dict/list payloads
- Keep raw toggle available
- Work for both regular steps and LLM steps
- Preserve provider-agnostic behavior

### Out of scope

- provider-side response schema enforcement
- automatic JSON parsing of arbitrary plaintext outputs
- semantic diffing
- schema registry
- replay execution changes
- artifact storage redesign
- streaming structured deltas

---

## Core product rules

### Rule 1 — Structured beats flattened key-value text

If a summary is a dict/list, render it as structured data, not as flattened `key value` lines unless there is no better renderer.

### Rule 2 — Text stays text

If output is scalar text, keep today’s text-oriented rendering.

### Rule 3 — Compact first, full on demand

The default UI should show a compact readable structured rendering, not a wall of JSON.

### Rule 4 — No provider coupling

Structured output UX must work for:

- OpenAI
- Anthropic
- tool steps
- code steps
- future providers

### Rule 5 — Compare should stay readable

For compare, show structure side-by-side without turning the page into a giant raw JSON dump.

---

## Ordered implementation steps

### Step 0 — confirm data contract

Validate what the backend already sends for summaries and LLM payloads.

Must confirm:

- `input_summary` can be dict / list / scalar / null
- `output_summary` can be dict / list / scalar / null
- `error_summary` can be dict / list / scalar / null
- LLM normalized output may contain:
  - `text`
  - `tool_calls`
  - `content_blocks`

No code changes unless a missing field is discovered.

---

### Step 1 — create canonical structured value renderer

Build one reusable frontend renderer for structured values.

It must support:

- null
- string
- number
- boolean
- arrays
- objects

It must provide:

- compact rendering by default
- predictable nesting
- stable ordering for object keys
- lightweight visual hierarchy
- optional truncation for very large values

This becomes the shared primitive used across run detail and compare.

---

### Step 2 — replace generic summary rendering in run detail

Use the structured renderer in all non-LLM step sections:

- Input
n- Output
- Error

for:

- code steps
- tool steps
- future generic steps

The goal is to stop rendering structured dicts as awkward flattened rows.

---

### Step 3 — improve LLM output rendering for structured payloads

Upgrade `LlmStepDetail` so it can render structured output more clearly.

Cases to support:

- text-only output
- tool-call-only output
- text + tool calls
- structured content blocks when present
- future structured response payload summaries

Important:

- keep existing text UX where it works
- do not regress current tool-call linkage UI
- do not dump raw JSON by default

---

### Step 4 — improve compare for structured values

Use the same structured renderer in compare rows for:

- input diff
- output diff
- error diff
- tool step structured input/output

Requirements:

- side A / side B stay readable
- unchanged large objects do not feel overwhelming
- missing side remains visually obvious
- raw toggle still works where it already exists

---

### Step 5 — add structured output showcase demo

Create one demo workflow that intentionally returns multiple output shapes.

Must include:

- simple text output
- flat object output
- nested object output
- array output
- tool output with nested structure
- one compare-friendly pair of runs with a changed field

This is the visual QA fixture.

---

### Step 6 — targeted visual QA pass

Validate these exact scenarios:

1. code step with nested dict output
2. tool step with nested dict output
3. LLM step with text-only output
4. LLM step with tool calls
5. compare view with unchanged structured output
6. compare view with one-field changed structured output
7. missing-side compare row for structured step
8. deeply nested object still readable

---

## Recommended execution order

1. Step 0 — data contract check
2. Step 1 — structured renderer primitive
3. Step 2 — run detail generic steps
4. Step 3 — LLM step structured UX
5. Step 4 — compare integration
6. Step 5 — showcase demo
7. Step 6 — visual QA

---

## What I will provide during implementation

We should execute this like the async phase:

- one step at a time
- one exact Cursor prompt per step
- you run it
- you paste diff/screenshots
- we validate before moving on

---

## Questions / decisions

At this point there is only one product decision worth confirming:

### Decision: default renderer style

Recommended default:

- object: key/value block rendering
- array of scalars: compact vertical list
- array of objects: stacked mini-cards / blocks
- strings: monospaced text block only when multiline or long

This is the direction I recommend unless you want a more JSON-like aesthetic.

---

## No migration / backward-compatibility work

Per current project status:

- no backward-compatibility layer required
- no versioned rollout required
- no legacy renderer preservation required

We should simply implement the correct shape cleanly.
