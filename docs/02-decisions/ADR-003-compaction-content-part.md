# ADR-003: Compaction content part

## Context
Both providers can compact a long conversation into a shorter context window:

- OpenAI `responses.compact()` returns the conversation's user messages plus
  one `compaction` item; `responses.create()` with `context_management`
  returns a `compaction` item when it compacts automatically. The item is
  encrypted (`encrypted_content`).
- Anthropic's beta compaction returns a `compaction` content block whose
  `content` is a readable summary (or `null` when compaction failed).

The normalizer labelled both as generic `file` parts ("unknown output item"),
and `compact()` itself was not recorded. A compaction changes what the model
sees on every later turn, so the record must show it.

## Decision
- Add one canonical content part, `compaction`, with `summary` (readable text
  or `null`), `id` when the provider sends one, `provider`,
  `provider_part_type`, `preview_text`, and for OpenAI `compact()`
  `retained_messages` (how many conversation messages were carried over).
- Opaque fields (`encrypted_content`, `signature`, `tool_changes`) are not
  copied; they stay in the raw response artifact, as in ADR-002.
- A compaction summary is not assistant text: it is never added to
  `output.text`.
- `responses.compact()` is recorded as an ordinary `llm` step.

Spec: `docs/03-specs/platform/compaction-and-responses-websocket.md`.

## Why
- One shape for the same operation on both providers.
- Keeps `output.text` the assistant's answer (Design Principle 7) while
  making the compaction visible.

## Consequences
- Additive: a new part type. Records written before this keep their `file`
  parts.
- The UI renders it with the generic part card (type label + preview) until
  a dedicated renderer is worth it.
- Anthropic streaming must apply `compaction_delta`, or streamed compaction
  blocks lose their summary.
