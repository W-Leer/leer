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

### Step 2 — Wrapper/runtime hardening
Output:
- stronger sync / async / streaming parity
- better partial-failure behavior
- safer artifact and finalization behavior

Focus:
- request exceptions
- stream interruptions
- partial finalization
- duplicate artifact prevention
- correct step status under failures
- wrapper parity between sync and async paths
- stable artifact attachment patterns

Expected deliverables:
- stricter wrapper behavior in OpenAI and Anthropic integrations
- tests covering runtime edge cases
- explicit behavior for partial stream or wrapper failure scenarios

Constraints:
- no broad architecture rewrite
- no replay logic
- avoid introducing provider-specific UI requirements

### Step 3 — Compare + run-detail non-regression
Output:
- safer rendering for hardened provider edge cases
- compare handling for sparse / malformed / partial provider outcomes
- better empty/fallback states where needed

Focus:
- malformed or sparse `llm` metadata
- output_summary gaps
- one-sided compare states
- media-only / tool-only / refusal-like outputs
- usage-less outputs
- partial provider metadata
- compare safety with mixed multimodal / MCP / retrieval / tool flows

Expected deliverables:
- UI fallback improvements
- compare routing refinements
- no-crash guarantees for hardened cases
- high-signal diff behavior where possible

Constraints:
- no large new UI subsystem
- no provider-specific compare branches unless truly necessary

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
- Step 2 — Wrapper/runtime hardening: not started
- Step 3 — Compare + run-detail non-regression: not started
- Step 4 — Demo + QA signoff: not started

Next action:
- begin **Step 2 — Wrapper/runtime hardening** (or pause to validate
  Step 1 in real workloads first).
