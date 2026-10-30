# Compaction and the Responses WebSocket

Status: compaction implemented (Part 1). WebSocket capture is designed and
decided (Part 2), not built; scheduled after the live recorder.

Source finding: "Found while checking D-H5 against `openai` 3.41.0" in
`docs/04-execution/provider-drift-assessment-2026-10.md`.

---

## Part 1 — Compaction

### Gap

- `client.responses.compact()` (`POST /responses/compact`) runs a model over a
  conversation and returns a `CompactedResponse`: `id`, `created_at`,
  `object: "response.compaction"`, `output`, `usage`. No `model`, no `status`.
  The wrapper forwards it through `__getattr__`, so the call, its tokens and
  its result are missing from the record.
- Its `output` is every user message of the conversation followed by one
  `compaction` item (`id`, `encrypted_content`, `created_by`). The normalizer
  turns the user messages' `input_text` blocks into "unknown output block"
  `file` parts and the `compaction` item into an "unknown output item" part.
- The same `compaction` item appears in normal `responses.create()` output
  when `context_management` compacts automatically.
- Anthropic's beta compaction returns a `compaction` content block (`content`
  = readable summary or `null` when compaction failed, `encrypted_content`,
  `signature`, `tool_changes`). It also falls back to a `file` part. When
  streamed, Leer ignores `compaction_delta`, so the streamed block has no
  summary while the non-streamed one would.

### Decisions

1. **`responses.compact()` is an `llm` step**, captured exactly like
   `responses.create()`: same step name (the model), `llm_request` and
   `llm_response` artifacts, usage, error and partial-capture paths. It is a
   model call; nothing new in the data model.
2. **New canonical content part `compaction`** (ADR-003), used by both
   providers wherever a compaction item/block appears:

   ```json
   {
     "type": "compaction",
     "id": "cmp_1",
     "summary": "User asked about …",
     "retained_messages": 2,
     "provider": "openai",
     "provider_part_type": "compaction",
     "preview_text": "context compacted (encrypted)"
   }
   ```

   - `summary`: readable summary when the provider gives one (Anthropic
     `content`); `null` otherwise (OpenAI is always encrypted).
   - `id` only when the provider sends one (OpenAI).
   - `retained_messages`: OpenAI `compact()` only — how many of the
     conversation's messages were carried into the compacted window.
   - `encrypted_content`, `signature`, `tool_changes` are not copied; they
     stay in the raw response artifact (ADR-002 rule for opaque blobs).
   - `preview_text`: the summary (truncated), else
     `"context compacted (encrypted)"`, else for a failed Anthropic
     compaction `"compaction produced no summary"`.
3. **Carried-over messages are not model output.** In the Responses
   normalizer, `message` output items whose `role` is not `assistant` are not
   added to `output.text` or `content_blocks`; they are counted into the
   `retained_messages` of the compaction part. They stay in the raw artifact.
4. **Streaming parity.** Anthropic stream rebuild applies `compaction_delta`
   the way the SDK does (sets `content` and `encrypted_content`). OpenAI
   streams already normalize the terminal `response`, which carries the
   compaction item; `response.compaction.compacting` stays ignored.
5. **Summaries.** When an output has no text or tool calls, step summaries and
   the response preview use the compaction part's `preview_text`, so a
   compaction step is not shown as an empty response.

### Not in scope

- Async clients: Leer does not wrap `AsyncOpenAI` today.
- Linking a later call to the compaction it reuses (the compacted window is
  sent back as `input` and is visible there).

---

## Part 2 — `responses.connect()` (WebSocket) — design, not built

### Surface (`openai` 3.41.0)

`client.responses.connect(...)` returns a `ResponsesConnectionManager`. Its
`__enter__` / `enter()` opens a `ResponsesConnection`:

- client → server: `send(event)`, `response.create(**params)` (same fields as
  `POST /responses` plus `stream_id`, the WebSocket lane), `response.steer(input,
  previous_response_id)`. The manager's own `send()` queues events before the
  socket opens.
- server → client: `recv()`, `recv_bytes()` (raw JSON), `for event in
  connection`, and push-style `on(...)` handlers + `dispatch_events()`.
- The server streams the same `response.*` events as HTTP streaming, ending in
  `response.completed` / `incomplete` / `failed` with the full `response`.
- The server can start responses itself: after steering or a normal finish
  it may emit an automatic successor (`response.created` with no matching
  client `response.create`) that inherits the previous settings.
- Reconnects are automatic and can replay queued sends.

### Capture design

- **One `llm` step per server response**, opened at `response.created`,
  closed at its terminal event and normalized from the terminal `response`
  through the existing Responses normalizer — the same path HTTP streaming
  uses, so streamed-over-HTTP and streamed-over-WebSocket records match.
- **Requests** come from the client's `response.create` on the same lane
  (`stream_id`, default lane otherwise), matched in send order.
- Wrap the manager and the connection (proxy), observing `send` and every
  receive style; `recv_bytes()` is parsed best-effort. The SDK objects and
  return values are untouched.
- Steps belong to the run that was active when `connect()` was called, since
  `dispatch_events()` handlers may run on another thread.

### Decisions (2026-10-29)

1. **Automatic successors are their own `llm` steps.** Their request is the
   `previous_response_id` plus the accepted steering input; there is no client
   `response.create` to pair them with.
2. **Steering is recorded twice:** as an event on the step being steered, and
   as input on the successor response.
3. **Unfinished responses at close or disconnect are `failed`**, like an
   aborted HTTP stream.
4. **Built after the live recorder (E step 3).** WebSocket mode is newer and
   less used than HTTP.
