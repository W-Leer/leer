# Provider Hardening — Implementation Plan

Execution plan for the OpenAI / Anthropic provider reliability pass.

This plan focuses on making Leer’s first two provider integrations feel production-grade before expanding into replay, execution, or broader provider coverage.

---

## Goal

Harden OpenAI and Anthropic support across:
- normalization
- wrapper/runtime behavior
- summaries
- run-detail rendering
- compare behavior
- demo and QA confidence

The intent is to maximize observability trust for the two current core providers.

---

## What this workstream is not

This workstream is **not**:
- replay
- execution engine
- retries / checkpoints
- new provider expansion
- a large provider-abstraction rewrite

We are explicitly prioritizing **best-in-class observability for OpenAI and Anthropic** before broader scope.

---

## Recommended Delivery Order

### Step 0 — Audit
Output:
- `docs/04-execution/provider-hardening-step-0-audit.md`

Questions to answer:
- what OpenAI wrapper paths exist today
- what Anthropic wrapper paths exist today
- where sync / async / streaming behavior diverges
- where summaries can drift from normalized output
- what known provider edge cases are already covered by tests
- what important edge cases are still untested
- what compare/run-detail surfaces are most fragile today
- whether Step 1 can start without schema changes

Expected outcome:
- a factual audit of current provider behavior
- a ranked list of weak spots
- confirmation that the hardening work can remain additive

### Step 1 — Normalization + summary hardening — COMPLETE

Implemented as a focused six-fix slice grounded in the Step 0 audit. All
changes are SDK-only, additive, OpenAI/Anthropic only, no schema
changes, no new step types, no replay work.

#### Behavior changes

1. **Wrapper enrich-failure fallback** — When `_enrich_step` raises
   mid-success in either wrapper (sync or streaming finalization), the
   step no longer silently completes with empty metadata. A new
   `_safe_partial_enrich` helper now populates baseline metadata
   (`provider`, `model`, `latency_ms`), tags the step with
   `metadata.capture = "partial"`, attaches the `llm_request` artifact
   in every case, and attaches the `llm_response` artifact whenever a
   response payload is available — so debugging context survives even
   when normalization fails.
2. **Preview / summary direction parity** — `_request_preview` now
   walks messages reversed (last user message wins), matching
   `_input_summary`. Multi-turn chats no longer disagree on which user
   message appears in summary vs preview. Applied to both providers.
3. **OpenAI chat completions `message.refusal`** — previously dropped
   silently. Now surfaces in `output.text` (with `[refusal] <text>`
   prefix when there is no other content) and in `meta.refusal` for
   structured detection in compare and run-detail. The Responses-API
   path also populates `meta.refusal` for parity, and refusal text now
   contributes to `output.text` in both code paths.
4. **Anthropic `total_tokens` math** — replaced `(0 or 0) → None`
   falsy fallback with explicit `is not None` checks.
   `(prompt=0, completion=0)` now returns `0` (a real value),
   `(prompt=None, completion=10)` returns `10`, and
   `(None, None)` still returns `None`.
5. **Anthropic image / document `source` malformed-payload safety** —
   `block.get("source")` may arrive as a list, string, or `None`.
   Normalization now guards with `isinstance(..., dict)` before
   accessing nested fields, so malformed payloads no longer crash and
   still produce a canonical media part. Same guard added to
   `_extract_base64_from_response`.
6. **Anthropic streaming model fidelity** — the
   provider-reported model captured in `ctx["model"]` from
   `message_start` now flows into `_assembled_to_anthropic_response`,
   so streaming behavior matches the non-streaming path where
   `response.model` is authoritative (e.g. when an alias is requested
   but a specific snapshot is served).

Schema-additive surface: `LLMMeta` gains an optional `refusal: str | None`
field (defaults to `None`). All existing parity tests pass with the
updated key set.

#### Stable contracts introduced by Step 1

These are small but load-bearing rules that consumers (run-detail,
compare, future replay, demos) can rely on. They are intentionally
called out so later steps do not drift them.

- **`metadata.capture = "partial"`** — set on an LLM step when the
  wrapper successfully captured the raw request and response, but
  canonical normalization (or summary generation) could not complete.
  Consumers should read it as **degraded observability, not failed
  model execution**: the underlying provider call may have succeeded
  exactly as the user requested, and the user-visible result is
  unchanged. The flag exists only so observability surfaces (compare,
  run-detail, exports) can render the step as "raw payloads
  preserved, canonical view incomplete" rather than as a clean
  success.
  - When the flag is set: `metadata.provider`, `metadata.model`, and
    `metadata.latency_ms` are populated; `llm_request` is always
    attached; `llm_response` is attached whenever a response payload
    was reachable.
  - When the flag is absent: the step has gone through the full
    `_enrich_step` path (canonical `metadata.llm`, summaries, all
    artifacts).
  - The flag is **never** set on a step that raised the original
    provider call — those steps are already marked `status="failed"`
    with an `error_summary`, and `_safe_enrich_error` runs instead.

- **Refusal dual-representation** — when a provider explicitly signals
  a refusal (OpenAI chat-completions `message.refusal` or Responses
  API `refusal` block), the refusal text is intentionally surfaced in
  **both** `output.text` (with `[refusal] ` prefix, for back-compat
  with existing renderers and full-text search) and
  `meta.refusal` (raw refusal string, for structured detection in
  compare and run-detail). This duplication is the rule, not an
  oversight — `output.text` keeps human-friendly rendering working
  unchanged, while `meta.refusal` gives consumers a typed flag they
  do not have to parse a prefix to detect. Future code should keep
  both in sync rather than collapse to one.

#### Files changed

- `apps/sdk-python/leer/integrations/normalize.py`
  (LLMMeta, chat-refusal, responses-refusal, anthropic usage math,
  anthropic source-block guards)
- `apps/sdk-python/leer/integrations/openai.py`
  (_safe_partial_enrich, sync enrich fallback, streaming-success and
  streaming-failure fallbacks, _request_preview direction)
- `apps/sdk-python/leer/integrations/anthropic.py`
  (_safe_partial_enrich, sync enrich fallback, streaming-success and
  streaming-failure fallbacks using ctx["model"] response model,
  _request_preview direction)

#### Tests added

- `apps/sdk-python/tests/test_normalize.py`
  - `TestOpenAIChatRefusal` (5 tests)
  - `TestOpenAIResponsesRefusalMeta` (2 tests)
  - `TestAnthropicUsageMath` (4 tests)
  - `TestAnthropicMalformedSourceBlocks` (5 tests)
  - `TestRefusalCrossProviderConsistency` (2 tests)
- `apps/sdk-python/tests/test_openai_wrapper.py`
  - `TestStep1PreviewSummaryDirectionParity` (2 tests)
  - `TestStep1PartialCaptureFallback` (4 tests)
- `apps/sdk-python/tests/test_anthropic_wrapper.py`
  - `TestStep1AnthropicPreviewSummaryDirectionParity` (2 tests)
  - `TestStep1AnthropicPartialCaptureFallback` (3 tests)
- `apps/sdk-python/tests/test_openai_streaming.py`
  - `TestStep1OpenAIStreamingPartialCapture` (2 tests)
- `apps/sdk-python/tests/test_anthropic_streaming.py`
  - `TestStep1ProviderReportedModel` (2 tests)
  - `TestStep1AnthropicStreamingPartialCapture` (2 tests)

Full SDK suite: 597 passed (288 covered by the focused slice above).

#### Constraints honored

- no schema changes
- no new step types
- no replay logic
- no provider-layer redesign
- backward compatible: `LLMMeta.refusal` defaults to `None`;
  `metadata.capture` is only set on the partial path; existing
  successful-path tests are unchanged.

#### Caveats / what remains for Step 2

- **Async wrappers** do not exist yet. Sync↔async parity becomes
  meaningful only once `wrap_async_openai_client` / its Anthropic
  equivalent are introduced — that is a separate workstream from
  hardening, and is explicitly deferred.
- **Stream interruption mid-tool-call deeper hardening** — current
  partial-failure behavior is correct; deeper assertions can wait for
  evidence of regression in real workloads.
- **Partial-capture path duplication between OpenAI and Anthropic** —
  `_safe_partial_enrich` is currently implemented twice (one per
  wrapper) because the provider tag and the streaming-only
  `response_model` argument differ. The shapes are very close. We are
  intentionally **not** refactoring this into a shared helper yet —
  Step 2 will add more wrapper/runtime hardening, and if a second
  shared concern surfaces we will extract a small shared helper then,
  rather than guess at the right shape now.
- **Duplicate artifact prevention** — there is a small theoretical
  risk that an `_enrich_step` failure that occurred *after*
  `llm_request` was already attached could result in two
  `llm_request` artifacts on the partial path. The most likely
  failure modes (normalize, media materialization, tool-call
  artifact creation) all run *before* artifact attachment, so this is
  not observed in practice. Deferred until evidence; do not
  prematurely harden the theoretical path.
- **Compare / run-detail UI hardening** for the new
  `metadata.capture = "partial"` flag and the new `meta.refusal`
  field — Step 3 by the plan's structure.
- **OpenAI Responses `instructions` vs in-message `system`
  precedence** — the existing test name is misleading but the actual
  behavior is consistent. Pure documentation; deferred.

### Step 2 — Sync↔streaming parity + cross-provider metadata consistency — COMPLETE

Implemented as a focused five-fix slice grounded in the gaps that
remained after Step 1. All changes are SDK-only, additive, OpenAI/
Anthropic only, no schema changes, no new step types, no replay work,
no UI work.

#### Behavior changes

1. **OpenAI Responses-API streaming canonical parity** — previously,
   `client.responses.create(stream=True)` events flowed through the
   chat-completions chunk processor, which sees no `choices` field and
   silently accumulates nothing. The wrapper now detects Responses-shape
   requests (`input` present, `messages` absent) and routes their stream
   events through a new `_process_openai_responses_event` handler that
   covers the load-bearing event types: `response.created`,
   `response.output_item.added` (function-call ids and names),
   `response.output_text.delta`, `response.refusal.delta`,
   `response.function_call_arguments.delta`, and `response.completed`
   (final usage including `input_tokens_details.cached_tokens`).
   Assembled streams are converted to a Responses-shape dict
   (`{"output": [...]}`) by a new `_assembled_to_responses_dict`, so the
   normalizer dispatch (`_normalize_openai_responses`) processes streamed
   captures exactly like non-streaming captures.

   Bonus ride-along on the same code path: chat-completions streaming
   now also captures `delta.refusal` (previously dropped). Both
   API-style streams now uphold the Step 1 refusal dual-representation
   contract — refusal text appears in `output.text` (with `[refusal] `
   prefix) and `meta.refusal` (raw string).

2. **Anthropic `thinking` / `redacted_thinking` blocks captured in
   streaming** — the non-streaming Anthropic path normalizes thinking
   blocks into `content_blocks`, but the streaming event processor
   dropped them silently. Streaming now handles
   `content_block_start` for `thinking` and `redacted_thinking` types,
   `content_block_delta` for `thinking_delta` and `signature_delta`,
   and round-trips the assembled blocks through
   `_assembled_to_anthropic_response` so `normalize_anthropic` produces
   the same canonical `{type: "thinking", thinking: "..."}` /
   `{type: "redacted_thinking"}` blocks as the non-streaming path.
   Thinking text stays structurally separate from `output.text`.

3. **`cached_tokens` canonical field across both providers** — both
   providers expose prompt-cache-read tokens in their usage payloads,
   and Leer dropped them all. `LLMUsage` now carries an additive
   `cached_tokens: int | None` (defaults to `None`, parity-preserving).
   Two small extractors do the provider-specific lookups:
   - `_extract_cached_tokens_openai`: reads
     `usage.prompt_tokens_details.cached_tokens` (chat completions) or
     `usage.input_tokens_details.cached_tokens` (responses), tolerating
     a non-dict details block.
   - `_extract_cached_tokens_anthropic`: reads
     `usage.cache_read_input_tokens`. Anthropic's
     `cache_creation_input_tokens` (cache *write* cost) is intentionally
     **not** mapped to `cached_tokens` — that is a different concept and
     would break cross-provider parity. The flat `metadata.usage`
     triplet on every LLM step now also exposes `cached_tokens`.

4. **Malformed `usage` payload tolerance** — three call sites in
   `normalize.py` (chat completions, Responses API, Anthropic) treated
   `response.get("usage") or {}` as a `dict`, which only works when
   `usage` is `None` or already a dict. Lists, strings, ints would
   crash on the next `.get()`. All three call sites now apply
   `usage_raw if isinstance(usage_raw, dict) else {}` so the normalizer
   degrades to "no usage reported" instead of raising.

5. **Anthropic streaming captures cached tokens** — needed to make
   Fix #3 useful on the streaming path. The collector's `append_usage`
   gains a `cached_tokens` parameter, and `_process_anthropic_event`
   now reads `cache_read_input_tokens` from both `message_start.usage`
   and `message_delta.usage`. The assembled response dict round-trips
   through `cache_read_input_tokens`, which `normalize_anthropic` picks
   up via Fix #3. `message_delta` overrides `message_start` when both
   report (final value wins, matching non-streaming where the final
   `response.usage` is authoritative).

#### Schema-additive surface

- `LLMUsage` gains `cached_tokens: int | None = None` (parity-safe;
  appears in `metadata.usage`, `metadata.llm.usage`, and the streaming
  assembled output).
- `StreamCollector` gains `append_thinking_*` / `begin_thinking_block` /
  `append_refusal_delta` push methods, an `assembled_thinking_blocks`
  property, an `assembled_refusal` property, and `cached_tokens` in
  `append_usage` and the assembled output dict. New stream event types:
  `thinking_start`, `thinking_delta`, `thinking_signature`,
  `refusal_delta`. All existing collector callers and stream-artifact
  consumers ignore unknown keys, so no downstream consumer breaks.
- `_StreamingIterator` (OpenAI) gains an `api_style` constructor arg
  (`"chat"` default, `"responses"` for Responses-API streams) that
  selects the chunk parser and the assembled-to-response converter.

#### Stable contracts introduced by Step 2

These are the additional load-bearing rules consumers (compare,
run-detail, future replay) can rely on. Future steps must not drift
them.

- **`metadata.usage.cached_tokens` semantics** — represents prompt
  cache-*read* tokens (tokens served from cache). `None` means the
  provider did not report it for this call. `0` is a real value
  (provider reported "no cache hit"). It is *never* used to encode the
  cache-write cost (`cache_creation_input_tokens` on Anthropic).
  Cross-provider parity: every OpenAI chat-completions, OpenAI
  Responses, and Anthropic step exposes this key under `metadata.usage`
  and `metadata.llm.usage`.

- **OpenAI streaming API-style detection** — when the request dict has
  `input` and not `messages`, the streaming pipeline treats the call
  as Responses-API. When it has `messages` (with or without `input`),
  it falls back to chat completions. This rule is duplicated only in
  `_is_responses_request` and matches the dispatch rule already used by
  `normalize_openai`. Future code must keep these two checks aligned.

- **Anthropic thinking-block parity** — streaming and non-streaming
  produce the same canonical `content_blocks` shape for thinking
  output. Non-streaming has had this since before Step 1; streaming now
  matches. Thinking text is structurally separate from `output.text`
  on both paths.

- **Canonical content channels are structurally distinct** — codified
  as Design Principle 7 in the provider-hardening spec. Short version:
  `output.text` is the human-readable assistant body; `thinking`,
  `refusal`, `tool_calls`, and media live in dedicated structured
  fields; refusal is intentionally mirrored into `output.text` (with
  `[refusal] ` prefix) for back-compat, thinking is *not* mirrored;
  canonical consumers should read the structured field when one
  exists rather than parse `output.text`. Step 3 UI work must follow
  this rule and not collapse the channels back into one.

#### Files changed

- `apps/sdk-python/leer/integrations/normalize.py`
  (LLMUsage.cached_tokens, two cached-token extractors, malformed-usage
  guards in all three normalizers)
- `apps/sdk-python/leer/integrations/streaming.py`
  (`_ThinkingAccumulator`, `cached_tokens`/refusal/thinking on
  `StreamCollector`, new push methods + assembled output keys)
- `apps/sdk-python/leer/integrations/openai.py`
  (`_is_responses_request`, `_StreamingIterator.api_style`,
  `_process_openai_responses_event`, `_assembled_to_responses_dict`,
  chat-completions `delta.refusal` capture, chat assembled response
  round-trips refusal + cached_tokens)
- `apps/sdk-python/leer/integrations/anthropic.py`
  (thinking + cache-read handling in `_process_anthropic_event`,
  thinking-blocks-first ordering and `cache_read_input_tokens`
  round-trip in `_assembled_to_anthropic_response`,
  `metadata.usage.cached_tokens` in `_enrich_step`)

#### Tests added

- `apps/sdk-python/tests/test_normalize_step2.py` (20 tests):
  - `TestCachedTokensOpenAIChat` (3)
  - `TestCachedTokensOpenAIResponses` (2)
  - `TestCachedTokensAnthropic` (3)
  - `TestCachedTokensCanonicalShape` (2 — incl. cross-provider key parity)
  - `TestMalformedUsageOpenAIChat` (4)
  - `TestMalformedUsageOpenAIResponses` (3 — incl. malformed
    `input_tokens_details`)
  - `TestMalformedUsageAnthropic` (3)
- `apps/sdk-python/tests/test_streaming_step2.py` (18 tests):
  - `TestOpenAIResponsesStreamingText` (3)
  - `TestOpenAIResponsesStreamingToolCall` (1)
  - `TestOpenAIResponsesStreamingRefusal` (1)
  - `TestOpenAIChatStreamingRefusalDelta` (1 — chat-completions bonus)
  - `TestAnthropicStreamingThinking` (3)
  - `TestAnthropicStreamingCachedTokens` (3)
  - `TestStreamCollectorStep2API` (6 — direct collector unit tests)

Full SDK suite: **635 passed** (597 from Step 1, 38 added in Step 2).

#### Constraints honored

- no schema changes
- no new step types
- no replay logic
- no UI work
- no provider-layer redesign
- no async wrappers introduced
- backward compatible: every new collector method is additive; new
  `LLMUsage.cached_tokens` defaults to `None` and slots into existing
  parity tests; the `_StreamingIterator.api_style` arg defaults to
  `"chat"` so existing callers (and tests) are unchanged.

#### Caveats / what remains for Step 3

- **Compare / run-detail UI for cached_tokens, thinking, refusal, and
  Responses-streaming captures** — Step 3 by the plan's structure.
  None of these surface specially in the UI yet; they are visible in
  raw artifact JSON and `metadata.llm` only.
- **OpenAI Responses streaming output ordering** — when the model
  interleaves text and function_call items in `response.output`, the
  assembled streamed response groups them (text first, then function
  calls, then refusal). This loses the original interleave order. None
  of the existing normalizer logic depends on order, but a future
  exact-replay path would need an ordered assembly. Deferred until that
  use case exists.
- **Cache *creation* tokens (Anthropic-only)** —
  `cache_creation_input_tokens` is a real cost signal but is not part
  of the canonical `LLMUsage`. It could be added as an Anthropic-only
  metadata extra without touching cross-provider parity. Skipped this
  step to keep Step 2 small.
- **Tool-call artifact extraction on the partial-capture path** —
  unchanged from Step 1: when `_enrich_step` raises, partial captures
  do not produce per-tool-call artifacts. Still no observed evidence;
  still deferred.
- **Async wrappers** still don't exist; sync↔async parity stays out of
  scope until the wrappers themselves are introduced.
- **Anthropic streaming `error` events** going to `mark_unknown` — the
  iterator's exception path already handles raised errors; pure
  event-only failures are a rare wire-protocol edge.

### Step 3 — Compare + run-detail non-regression

Mental model: this step is **UI visibility + non-regression for the
newly-hardened provider data**, not a compare or run-detail redesign.
Steps 1 and 2 introduced new canonical fields that consumers cannot see
yet; Step 3 makes them visible in the existing surfaces and proves
nothing else regressed.

Output:
- safer rendering for hardened provider edge cases
- compare handling for sparse / malformed / partial provider outcomes
- better empty/fallback states where needed

#### New data to surface

These are the only items Step 3 should add UI affordances for. They
are exactly the canonical fields introduced (or stabilized) by Steps
1 and 2:

1. **`metadata.capture = "partial"`** — a small, low-noise badge on
   the step header (run-detail and compare) that reads the step as
   "raw payloads preserved, canonical view incomplete". Per Step 1's
   contract, this is degraded observability, not failed execution; the
   badge wording should match.
2. **`meta.refusal`** — a refusal badge or row on LLM steps where the
   provider explicitly signaled refusal. Compare should treat refusal
   divergence as a high-signal insight. The `[refusal] ` prefix in
   `output.text` already renders for free; do not duplicate it.
3. **`metadata.usage.cached_tokens`** — a small column/row on LLM
   steps showing cache-read tokens when the field is set (`None`
   means not reported by the provider; render nothing, not zero).
   Cross-provider: same surface for OpenAI chat, OpenAI Responses,
   Anthropic.
4. **Anthropic thinking / redacted_thinking blocks** — basic
   visibility in run-detail (collapsible block or labelled section so
   users know thinking content was captured) without leaking thinking
   text into compare summaries. Per Design Principle 7, thinking is a
   separate channel and must not be merged into `output.text`-driven
   compare diffs.
5. **OpenAI Responses-API streamed captures** — verify they render
   exactly like non-streaming Responses captures now that Step 2 made
   them canonically equivalent. No special-case rendering; this is a
   non-regression check.

Beyond those five, Step 3 should also do the standard non-regression
sweep:

- malformed or sparse `llm` metadata
- output_summary gaps
- one-sided compare states
- media-only / tool-only / refusal-like outputs
- usage-less outputs
- partial provider metadata
- compare safety with mixed multimodal / MCP / retrieval / tool flows

Expected deliverables:
- targeted UI affordances for the five items above
- UI fallback improvements where the non-regression sweep finds gaps
- compare routing refinements only where existing routing breaks on
  the new data
- no-crash guarantees for hardened cases
- high-signal diff behavior where possible (e.g. refusal divergence,
  cached-tokens divergence)

Constraints:
- **not a compare or run-detail redesign**
- no large new UI subsystem
- no provider-specific compare branches unless truly necessary
- no new dedicated artifact viewers
- canonical content channels remain structurally distinct (spec
  Design Principle 7) — UI may surface multiple channels on one
  step, but must not collapse them into a single text blob

### Step 4 — Demo + QA signoff
Output:
- one or more deterministic demos for hardened provider edge cases
- provider hardening QA checklist
- support-boundary status update in docs/tasks

Possible deliverables:
- `examples/demo_provider_hardening_openai.py`
- `examples/demo_provider_hardening_anthropic.py`
- or a combined provider hardening demo if cleaner
- `docs/04-execution/provider-hardening-qa.md`

Focus:
- real edge cases, not just happy paths
- visual verification in run detail and compare
- explicit support matrix / known limitations

---

## Guiding Decisions

### 1. OpenAI and Anthropic only

Do not expand scope to more providers during this pass.

### 2. Canonical normalization beats provider mirroring

Fix the canonical layer first. Do not optimize around provider-native quirks unless needed for correctness.

### 3. Compare is part of correctness

A provider path is not hardened until compare remains readable and safe.

### 4. Replay stays deferred

Do not let hardening drift into replay-system design.

### 5. Schema changes should be avoided unless strictly necessary

This workstream should remain additive if possible.

---

## Likely audit targets

The Step 0 audit should inspect at least:
- `apps/sdk-python/leer/integrations/openai.py`
- `apps/sdk-python/leer/integrations/anthropic.py`
- `apps/sdk-python/leer/integrations/normalize.py`
- `apps/sdk-python/leer/integrations/streaming.py`
- current wrapper tests for OpenAI and Anthropic
- compare page routing for LLM output
- run-detail LLM rendering and fallback behavior

---

## Likely edge-case buckets to test

### Normalization
- empty response body with usage
- tool calls without text
- text without content blocks
- malformed argument strings
- duplicated tool-call blocks
- media without text
- refusal / stop / blocked style outputs where available

### Runtime
- exception before provider result exists
- exception during streaming collection
- partial streaming then failure
- async wrapper exception handling
- duplicate attach risks
- missing final usage/model/request_id fields

### Compare / UI
- one side empty, one side partial
- malformed summary shapes
- tool-only outputs
- media-only outputs
- sparse metadata
- step present only on one side
- provider/model missing on one side

---

## Deliverable quality bar

For this workstream to count as complete:
- the audit must identify the real edge cases, not generic possibilities
- the implementation must improve behavior, not just add docs
- tests must expand around the weak spots identified in the audit
- compare and run-detail must be visually verified for those cases
- the resulting docs must make the support boundary clearer

---

## Completion Criteria

The workstream is complete when:
- OpenAI and Anthropic wrappers behave consistently across sync/async/streaming for the hardened cases
- normalization and summaries are safer and more consistent
- compare and run-detail do not regress on sparse or partial provider outputs
- demos and QA prove the hardened behavior end to end
- replay remains intentionally deferred

---

## Status

- Step 0 — Audit: complete (`docs/04-execution/provider-hardening-step-0-audit.md`)
- Step 1 — Normalization + summary hardening: **complete**
- Step 2 — Sync↔streaming parity + cross-provider metadata consistency: **complete**
- Step 3 — Compare + run-detail non-regression: not started
- Step 4 — Demo + QA signoff: not started

Next action:
- begin **Step 3 — Compare + run-detail non-regression** (or pause to
  validate Steps 1+2 in real workloads first).
