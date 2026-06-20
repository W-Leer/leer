# Structured Outputs Step 0 — Codebase Audit

Audit of how Leer **captures and normalizes** structured / schema-constrained
LLM outputs for OpenAI and Anthropic, across streaming and non-streaming.

Related docs:
- `docs/03-specs/llm-instrumentation/06-structured-outputs.md` (rendering/UX spec — see scope note below)
- `docs/04-execution/provider-hardening-qa.md` (capture/normalization contracts this builds on)

Date: 2026-06-20

---

## 0. Scope note — two different "structured outputs"

There are two distinct workstreams that share the name. They must not be conflated.

| | `06-structured-outputs.md` (existing spec) | This audit (roadmap item A) |
|---|---|---|
| Axis | **Rendering / UX** | **Capture / normalization correctness** |
| Question | "Does the UI render a dict/list nicely?" | "Is the structured payload + requested schema captured equivalently across providers and streaming?" |
| Status | Largely shipped (`StructuredValue` renderer used by the demo) | **Not validated — this audit** |

The existing spec explicitly scopes *out* schema enforcement, automatic JSON
parsing, and streaming structured deltas. This workstream is about whether the
**execution record** faithfully captures structured outputs — consistent with
Leer's "capture over replay, capture not enforce" principle. We are **not**
adding provider-side schema validation.

---

## 1. What works today

### 1.1 Requested schema is captured (all three paths)

The *request* side already preserves the schema the developer asked for:

- **OpenAI chat** — `response_format` is in `_OPENAI_CHAT_PARAMS`
  (`normalize.py:338`), so `{"type":"json_schema", json_schema:{...}}` and
  `{"type":"json_object"}` survive into `input.params.response_format`.
- **OpenAI Responses** — `text` is in `_OPENAI_RESPONSES_PARAMS`
  (`normalize.py:343`), so `text.format = {"type":"json_schema", ...}` survives
  into `input.params.text`.
- **Anthropic** — structured output is done via *forced tool use*; the tool
  definition (including `input_schema`) is captured into `input.tools`.

**Verdict: the requested schema is recoverable from the execution record for all
three providers.** Good foundation.

### 1.2 Structured payload is captured for `create(...)`

- **OpenAI chat `create(response_format=...)`** — the model returns the object
  as a **JSON string** in `message.content`; this lands in `output.text` (and a
  `text` content block). Streaming parity holds: the JSON arrives as
  `delta.content` text deltas and is reassembled into `output.text`.
- **OpenAI Responses `create(text={format:...})`** — the object arrives as an
  `output_text` JSON string → `output.text`. Streaming via `output_text.delta`
  → same `output.text`.
- **Anthropic forced tool use** — the structured object is the tool `input`,
  captured as `tool_calls[].arguments` (parsed into a dict via
  `_parse_arguments`, `normalize.py:418`). Streaming via `input_json_delta` is
  reassembled into the same dict (`test_streaming_step2.py:218`).

### 1.3 Refusals on structured outputs

Already covered by the Step 1 refusal channel: OpenAI `message.refusal`
(`normalize.py:395`), Responses `refusal` content block (`normalize.py:543`),
and Anthropic `stop_reason == "refusal"` (`normalize.py:752`) all surface to
`meta.refusal`. No additional work needed; include in the validation matrix.

---

## 2. Gaps

### G-A1 — `.parse()` helpers are not instrumented  ·  Severity: HIGH

`_WrappedCompletions` and `_WrappedResponses` intercept **only `create`**
(`openai.py:81`, `openai.py:92`). Everything else falls through `__getattr__`
to the raw SDK object (`openai.py:84`, `openai.py:95`). That means the idiomatic
structured-output entry points are **completely uninstrumented** — they produce
**no step at all** even inside an active `@trace`:

- `client.chat.completions.parse(...)`
- `client.responses.parse(...)`
- `client.beta.chat.completions.parse(...)` — `beta` itself falls through
  `_WrappedOpenAI.__getattr__` (`openai.py:64`), so the whole namespace is raw.

`.parse()` is the recommended OpenAI structured-output API (returns
`.parsed` / `output_parsed`). A developer using it inside a Leer trace gets a
**silent capture hole**. This is the most important gap.

### G-A2 — Streaming context-manager helpers not instrumented  ·  Severity: MEDIUM

Only `create(stream=True)` is captured. The streaming *helper* context managers
— `client.chat.completions.stream(...)` and `client.responses.stream(...)`
(`with ... as stream`, `stream.get_final_completion()`, `stream.parse()`) — also
fall through `__getattr__` and are uninstrumented. Structured streaming via
these helpers → no step.

### G-A3 — SDK-parsed object is dropped  ·  Severity: MEDIUM

Even where capture works, the normalizer reads the **JSON string** only.
`message.parsed` / `output_parsed` (the SDK's already-typed object) is never
referenced (`grep` for `parsed`/`output_parsed` in `normalize.py` → none). Data
loss is low (the JSON string is preserved in `output.text`), but the canonical
record has **no first-class structured payload** — every consumer must re-parse
text and guess validity.

### G-A4 — No canonical "structured output" concept; cross-provider asymmetry  ·  Severity: MEDIUM

The same logical thing lands in different canonical places:

- OpenAI structured output → `output.text` (a JSON **string**)
- Anthropic structured output → `tool_calls[].arguments` (a **dict**)

A consumer (compare, run-detail, future tooling) cannot uniformly ask "did this
step return a schema-constrained object, and what is it?" This is the core
*validation* gap: structured outputs are not a recognizable channel in the
canonical model.

### G-A5 — No JSON-validity signal  ·  Severity: LOW

Nothing in the canonical record distinguishes "`output.text` is valid JSON for a
requested schema" from "`output.text` is prose." Schema *enforcement* is a
non-goal (capture not enforce), but a cheap boolean like "output parsed as JSON:
yes/no" would materially help debugging and compare.

### G-A6 — Essentially zero test coverage  ·  Severity: MEDIUM (drift risk)

No dedicated tests exist for structured-output capture. The only `parsed`-named
test (`test_normalize.py:176`) covers tool-call argument parsing, not
`response_format` / `text.format` / `.parse()` / Anthropic forced-tool
structured output / streaming structured parity. High provider-drift exposure.

---

## 3. Schema / migration impact

**None required.** All proposed fixes are SDK-only and additive:

- Instrumenting `parse` / `stream` is wrapper-only (no record-shape change).
- Any new canonical field (e.g. `output.parsed`, `meta.output_is_json`) lands in
  `metadata.llm`, which is JSONB — additive, no migration, no replay impact.

Consistent with the hard constraints in `AGENTS.md` (additive only, no schema
breaks, no replay work, OpenAI + Anthropic only).

---

## 4. Recommended Step 1 scope (proposal — no code yet)

Ordered by value:

1. **Close G-A1 (must):** route `parse` through the existing
   `_instrumented_create` on chat completions + responses, and wrap
   `beta.chat.completions`. Capture the JSON string in `output.text` exactly as
   `create` does today. Highest leverage, low risk.
2. **Decide G-A3/G-A4/G-A5 (product call):** add an additive canonical signal so
   structured outputs are first-class — e.g. capture `parsed`/`output_parsed`
   into `output.parsed` when present, plus a `meta.output_is_json` flag. This is
   the one decision that needs your input (see below).
3. **Build the validation matrix (G-A6):** dedicated tests for `response_format`
   + `json_schema` (chat + responses, streaming + non-streaming), `.parse()`,
   Anthropic forced-tool structured output, and refusal-on-structured.
4. **Resolve G-A2:** either wrap the `.stream()` helpers or explicitly document
   them as unsupported/deferred (acceptable if `create(stream=True)` remains the
   supported streaming path).
5. **UI (only if step 2 adds a field):** surface the new signal additively and
   compactly. The existing `StructuredValue` renderer already covers
   JSON-in-text, so keep this minimal.

### Open decision for Step 1

Whether to introduce a canonical structured-output field (G-A4) or keep
provider-shaped representation (JSON-string for OpenAI, tool-args for Anthropic).
A canonical field gives uniform compare/inspection but adds one additive concept
to the record; provider-shaped keeps the model smaller but leaves the asymmetry.
Recommend deciding this before Step 1 implementation.

---

## 5. Step 1 outcome — SDK capture (implemented)

Decision taken: **add an additive canonical signal** (option chosen by product).

Implemented test-first (RED → GREEN), `apps/sdk-python/tests/test_structured_outputs.py`
(11 tests); full SDK suite green (680 passed).

**Canonical fields (additive, no migration):**
- `output.parsed: Any | None` — the structured object: an SDK-provided parsed
  object (`message.parsed` / `output_parsed`) when present, else the JSON
  object/array `output.text` decodes to. (`normalize.py` `LLMOutput`)
- `meta.output_is_json: bool` — whether `output.parsed` is populated.
  (`normalize.py` `LLMMeta`)
- Detection via `_detect_structured_output(text, sdk_parsed)`: only object/array
  JSON counts; scalar JSON and `[refusal] …` text are intentionally not flagged.
- Wired into all three normalizers (OpenAI chat, OpenAI responses, Anthropic).
  Streaming inherits it via the round-tripped response dict (parity verified).

**Closed G-A1:** `_WrappedCompletions.parse`, `_WrappedResponses.parse`, and a new
`_WrappedBeta` (wrapping `beta.chat.completions`) now route through the same
`_instrumented_create` as `create`. `.parse()` structured-output calls produce a
full LLM step instead of silently bypassing instrumentation. (`openai.py`)

**Cross-provider boundary (deliberate):** Anthropic structured-via-forced-tool
keeps its object in `tool_calls[].arguments` (not `output.parsed`), since forcing
arbitrary tool args into `output.parsed` would mislabel ordinary tool calls.
Uniform "did this step return a structured object?" detection therefore consults
`output.parsed` **or** `tool_calls`.

### UI surfacing (done)

`output.parsed` / `meta.output_is_json` are now exposed additively:
- `LLMShape` types extended (`apps/web/src/lib/types.ts`).
- Detection helpers `getParsedOutput` / `isJsonOutput` / `jsonOutputDiverges`
  (`apps/web/src/lib/provider-hardening.ts`) + 9 unit tests.
- Run-detail: a compact `JSON` badge on structured LLM steps; the output
  renderer prefers the canonical `output.parsed` (falling back to decoding
  `output.text`).
- Compare: a `JSON` / `JSON A|B only` badge (diff-highlighted when it diverges)
  and a "Structured-output divergence" insight.

### G-A2 — `.stream()` helpers (done)

`client.chat.completions.stream(...)` and `client.responses.stream(...)` are now
instrumented (`openai.py`):
- `_WrappedStreamManager` creates the step on `__enter__`, feeds every event
  through the same `StreamCollector` assembly as `create(stream=True)`, and
  finalizes on `__exit__` — so `.stream()` captures land in the identical
  canonical shape (incl. `output.parsed`).
- Chat `.stream()` events are higher-level; each underlying chunk arrives as a
  `chunk`-type event, processed via `_process_openai_chat_stream_event` (other
  semantic events are skipped to avoid double-counting).
- The entered stream proxies unknown attributes back to the underlying stream,
  preserving `get_final_completion()` / `get_final_response()`.
- Outside a trace, `.stream()` returns the raw manager unchanged.
- Covered by `apps/sdk-python/tests/test_openai_stream_helpers.py` (6 tests).

### Still open after Step 1

- **Request serialization** — `.parse()` is normally called with a pydantic
  *class* as `response_format`/`text_format`. Capture succeeds in-memory; verify
  the API client's JSON encoder tolerates non-serializable request kwargs (or
  redact them) before relying on `.parse()` in production.
