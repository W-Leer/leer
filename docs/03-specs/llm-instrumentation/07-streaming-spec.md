# Streaming Spec

## Goal

Capture LLM streaming in a way that is:
- truthful
- debuggable
- provider-agnostic
- cheap enough for production use
- compatible with Leer's existing Run → Step → Event → Artifact model

This spec defines the first production-grade streaming model for Leer.

---

## Product Principle

Streaming is not just "show tokens live".

Leer should answer:

- what streamed?
- in what order?
- what was the final assembled output?
- did the stream terminate cleanly?
- did tool calls emerge during streaming?
- what changed between two streamed runs?

The model must preserve both:
- the final canonical output
- enough streaming detail to debug failures and weird behavior

It must not flood Postgres with token-level writes.

---

## Non-Goals

Not in scope for this phase:

- pixel-perfect live token playback
- per-token analytics dashboards
- multimodal streaming
- websocket push from server to UI
- streaming compare at token diff granularity
- replay from partial stream checkpoints

This phase is about correct capture, storage shape, and useful UI.

---

## Canonical Mental Model

A streamed LLM step has **three layers**:

1. **Live chunks**
   - incremental provider events/chunks/deltas
   - useful for debugging
   - not ideal for direct long-term query patterns

2. **Assembled final output**
   - the canonical result after stream completion
   - this should behave like today's final LLM output

3. **Streaming summary**
   - a compact structured description of the stream
   - counts, finish reason, tool-call emergence, duration, truncation flags, etc.

Leer should store all three, but at different fidelity levels.

---

## Required Invariants

### Invariant 1 — Final output remains canonical
A streamed step must still end with the same normalized final LLM shape used for non-streaming calls.

Streaming must not create a second-class representation.

### Invariant 2 — Chunks are append-only
Streaming chunks/events are append-only during capture. Do not rewrite historical chunk payloads.

### Invariant 3 — Timeline stays step-centric
The run detail page remains centered on steps, not individual stream tokens.

Streaming is a detail mode inside an LLM step.

### Invariant 4 — Compare is final-first
Compare should compare final assembled output first.
Streaming metadata is secondary context.

### Invariant 5 — Partial / failed streams remain truthful
If a stream fails midway, Leer must preserve:
- partial assembled text/tool-call state if available
- stream termination reason
- chunk count observed so far

Never pretend a failed partial stream is a complete final result.

### Invariant 6 — No token-level DB hot path
Do not write every token/chunk directly to the main API/database in real time.

The SDK should aggregate locally and submit once at step completion/failure.

---

## Recommended Execution Order

1. SDK streaming capture model
2. normalized streaming shape
3. artifacts + summaries
4. demo + tests
5. backend field pass
6. run detail UI
7. compare rules
8. polish

---

## Data Model

## Step-level metadata additions

For streamed LLM steps, store these in `step.metadata["stream"]`:

```json
{
  "is_stream": true,
  "provider": "openai",
  "chunk_count": 42,
  "first_chunk_at": "2026-04-01T10:00:00Z",
  "last_chunk_at": "2026-04-01T10:00:01Z",
  "time_to_first_chunk_ms": 120,
  "stream_duration_ms": 980,
  "termination": "completed",
  "assembled_text_chars": 1240,
  "assembled_tool_calls": 1,
  "captured_chunk_bytes": 18234,
  "truncated_chunks": false
}
```

### Notes
- `is_stream`: explicit boolean
- `termination`: one of `completed | failed | interrupted | cancelled`
- `assembled_tool_calls`: number of final tool calls assembled from streamed deltas
- `truncated_chunks`: true only if SDK intentionally truncates stored chunk history for size reasons

---

## Artifact Strategy

A streamed LLM step should produce:

### 1. `llm_request`
Same as today.

### 2. `llm_response`
Final assembled normalized response, same as today.

### 3. `llm_stream`
New artifact type.

This artifact stores the captured chunk timeline in structured form.

Example:

```json
{
  "provider": "openai",
  "model": "gpt-4.1",
  "events": [
    {
      "index": 0,
      "type": "text_delta",
      "text": "Hello",
      "timestamp_offset_ms": 120
    },
    {
      "index": 1,
      "type": "text_delta",
      "text": " world",
      "timestamp_offset_ms": 160
    },
    {
      "index": 2,
      "type": "tool_call_delta",
      "tool_call_id": "call_123",
      "name_delta": "get_weather",
      "arguments_delta": "{\"city\":\"Paris\"}",
      "timestamp_offset_ms": 240
    }
  ]
}
```

### Storage rule
- small streams: inline JSON artifact
- large streams: same artifact contract, but move to blob storage later
- do not block streaming phase on blob storage phase

### First-phase size rule
Keep a conservative soft cap in the SDK, for example:
- capture full chunk list up to a configured byte ceiling
- if exceeded, preserve initial + final chunk windows and mark `truncated_chunks=true`

Do not silently drop without signaling.

---

## Normalized Streaming Event Shape

Use a provider-agnostic event envelope.

```json
{
  "index": 0,
  "type": "text_delta | tool_call_delta | message_start | message_stop | usage | unknown",
  "timestamp_offset_ms": 0,
  "payload": {}
}
```

For readability in artifacts, specialized flattened fields are allowed.

### Minimum event types for phase 1
- `text_delta`
- `tool_call_delta`
- `message_start`
- `message_stop`
- `usage`
- `unknown`

That is enough to support OpenAI and Anthropic initial coverage.

---

## Assembled Final Output Rules

At stream end, the SDK must assemble:

- final text
- final tool calls
- usage if provider gives it
- finish reason / stop reason
- request id if available

Then pass that through the existing normalized LLM shape.

This means streamed and non-streamed LLM steps share the same:
- `metadata["llm"]`
- `input_summary`
- `output_summary`

The only addition is streaming metadata + stream artifact.

---

## Failure Handling Rules

If stream fails after partial text:

- `step.status = "failed"`
- preserve partial assembled text in normalized output if available
- preserve stream metadata
- attach `llm_stream` artifact with captured chunks
- attach request artifact
- attach final response artifact only if there is a meaningful assembled normalized response
- error summary must clearly indicate stream failure

If stream fails before any usable chunk:
- still mark `is_stream = true`
- chunk_count may be 0
- no fake final output

---

## SDK API Shape

## Explicit first-class helper

Add a streaming wrapper/helper path that is explicit and inspectable.

Examples:

```python
client = wrap_openai_client(OpenAI())

with trace("my-workflow"):
    stream = client.chat.completions.create(
        model="gpt-4.1",
        messages=[...],
        stream=True,
    )

    for chunk in stream:
        ...
```

and similarly for Anthropic streaming APIs.

### Important
Do not require monkey-patch magic for phase 1.
The wrapper should detect `stream=True` and switch to streamed capture behavior.

---

## SDK Capture Model

The wrapper should:

1. detect streamed call
2. create one LLM step
3. start local stream collector
4. iterate provider chunks
5. append normalized stream events into in-memory collector
6. incrementally assemble final text/tool-call state
7. yield original chunks back to user unchanged
8. on normal completion:
   - finalize summaries
   - attach artifacts
   - finish step as completed
9. on exception:
   - finalize partial state best-effort
   - attach stream artifact
   - fail step
   - re-raise original exception

This is the key design:
**instrument around the iterator, not instead of it**

---

## Backend / API Changes

Phase 1 backend changes should be minimal.

### Timeline read API
No major new endpoint required.

Ensure timeline step payload includes the stream metadata already present in `metadata`.

Optional later:
- lightweight promoted `stream` field beside `llm`

But not required for phase 1.

### Compare API
Add no major new compare matching logic.
Compare should continue to align steps the same way.

Streaming-specific compare behavior should come from already-returned metadata.

Optional promoted fields later if needed:
- `is_stream_a/b`
- `chunk_count_a/b`
- `termination_a/b`

Not required if metadata is already available, but explicit promoted fields are cleaner if the compare UI starts depending heavily on them.

---

## UI — Run Detail

## Step header
For streamed LLM steps add a subtle stream badge:

- `stream`
- neutral blue-gray badge
- near step type / model badge

Optional tiny stats in header metadata row:
- `42 chunks`
- `ttfc 120ms`

## Expanded detail
Add a new section between Output and Tokens:

### Stream
Show:
- chunk count
- time to first chunk
- stream duration
- termination
- truncated or not

Then show a collapsible **Stream events** block:
- default collapsed
- raw-ish devtool view
- grouped by event type
- keep compact

### Final output stays primary
Do not let stream events visually overpower final assembled output.

Order:
1. Input
2. Output
3. Tool calls (if any)
4. Stream
5. Tokens / usage

---

## UI — Compare

Streaming compare should be **contextual, not primary**.

### Rules
- compare final assembled output exactly like today
- if either side is streamed, show a stream badge in header
- for streamed tool or LLM steps, optionally add a `Streaming` diff row showing:
  - streamed / not streamed
  - chunk count
  - ttfc
  - termination
  - truncated flag

### Do not do
- token-level diff
- event-by-event stream diff
- full chunk stream side-by-side by default

That is too noisy for first phase.

---

## Testing Requirements

## SDK tests
Must cover:

1. streamed text response success
2. streamed tool-call response success
3. partial failure after some chunks
4. zero-chunk failure
5. streamed call preserves original yielded chunks
6. streamed call produces final normalized LLM output
7. stream artifact attached
8. truncation flag behavior if chunk capture limit exceeded

## Backend tests
Must cover:
1. stream metadata survives ingestion
2. timeline returns stream metadata
3. compare preserves stream metadata access

## UI tests / manual QA
Must inspect:
1. simple streamed prose
2. streamed JSON text output
3. streamed tool-call deltas
4. failed partial stream
5. compare streamed vs streamed
6. compare streamed vs non-streamed

---

## Demo Requirements

Create a showcase demo run pair:

### Run A
- streamed text response
- streamed structured JSON response
- streamed tool-call response

### Run B
- same flow with changed values

Also create a failed partial stream demo.

These demos should make visual QA easy before public release.

---

## Implementation Phases

## Step 0 — audit provider streaming surfaces
Confirm exact OpenAI + Anthropic Python streaming APIs currently used in repo.

## Step 1 — SDK collector + normalized event shape
Build in-memory collector and assembly logic.

## Step 2 — OpenAI streaming wrapper
Implement first streamed provider path.

## Step 3 — Anthropic streaming wrapper
Match behavior and tests.

## Step 4 — artifacts + summaries + failure handling
Finalize stream metadata contract.

## Step 5 — backend / API field pass
Ensure timeline / compare can access stream data cleanly.

## Step 6 — run detail UI
Add stream badge + stream section.

## Step 7 — compare UI
Add compact stream diff context.

## Step 8 — showcase demos + QA
Ship fixture runs and validate visuals.

---

## Decisions

### Decision: stream events belong in artifacts, not rows in the steps table
Reason:
- avoids DB explosion
- keeps step model clean
- matches devtool UX better

### Decision: final assembled output is canonical
Reason:
- compare and replay depend on a stable final representation

### Decision: no live DB writes per token
Reason:
- too expensive
- unnecessary for first production-grade version

### Decision: no token diff compare in phase 1
Reason:
- low value relative to noise and implementation cost

---

## Acceptance Criteria

Streaming phase is done when:

- OpenAI streamed calls are captured correctly
- Anthropic streamed calls are captured correctly
- final normalized output is preserved
- stream artifacts exist
- partial failures are truthful
- run detail clearly shows stream context
- compare shows stream context without noise
- showcase demo runs exist
- docs and tests are complete
