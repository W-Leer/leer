# Structured Outputs

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

## Questions / decisions

At this point there is only one product decision worth confirming:

### Decision: default renderer style

Recommended default:

- object: key/value block rendering
- array of scalars: compact vertical list
- array of objects: stacked mini-cards / blocks
- strings: monospaced text block only when multiline or long

---

## Relationship to Other Systems

- Works with async parent/child steps
- Works with compare
- Works with normalized LLM shape
- Compatible with streaming (future)

---
