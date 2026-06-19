# Provider Hardening

Defines the provider-reliability workstream for Leer’s first two core providers: OpenAI and Anthropic.

This document is the product and technical spec for improving correctness, consistency, and debuggability across provider wrappers, normalization, summaries, streaming behavior, compare, and run-detail rendering.

---

## Goal

Make OpenAI and Anthropic support feel production-grade, trustworthy, and boringly reliable under real-world edge cases.

Leer should be able to:
- capture provider calls consistently across sync, async, and streaming flows
- normalize provider-native responses into stable canonical shapes
- preserve useful debugging detail without leaking provider-specific complexity into the product model
- avoid silent drops or inconsistent summaries in edge cases
- render and compare odd or partial provider outputs safely
- define a clear support boundary for what is guaranteed today vs deferred

---

## Why this workstream exists

Leer already has strong observability foundations:
- tool calling
- async support
- structured outputs
- streaming
- blob storage
- multimodal
- tool lifecycle / linkage polish
- MCP / skills / RAG tracing

The next highest-leverage move is not replay.
It is making the existing OpenAI and Anthropic integrations feel fully hardened.

This workstream exists to improve:
- correctness under weird provider payloads
- consistency across provider adapters
- trust in compare and run-detail
- OSS/demo confidence for the first two supported providers

---

## Scope

This workstream covers **OpenAI and Anthropic only**.

### In scope

- OpenAI wrapper hardening
- Anthropic wrapper hardening
- normalization consistency across both providers
- output summary correctness and stability
- streaming finalization correctness
- sync / async parity validation
- compare non-regression for provider edge cases
- run-detail rendering safety for malformed / partial / sparse data
- support-matrix clarification
- demo and QA signoff

### Out of scope

- replay execution
- execution engine
- retries / checkpoints
- new provider integrations
- new backend schema for provider-specific entities
- provider-specific UI branches unless unavoidable
- rich rendering for every future provider-specific feature
- broadening support beyond OpenAI and Anthropic

---

## Design Principles

### 1. Canonical model first

Provider wrappers may preserve provider-native request/response payloads for debugging, but the product surface should depend on canonical normalized shapes.

### 2. Wrong normalization is worse than incomplete normalization

If a provider-native shape is ambiguous, Leer should prefer a conservative fallback over inventing false structure.

### 3. Compare safety matters as much as capture correctness

A capture path is not “done” unless run detail and compare both remain understandable and stable.

### 4. Async and streaming are first-class correctness concerns

Provider support is not only about one-shot sync requests. Finalization, partial streams, and async parent/child semantics must behave predictably.

### 5. Summary fields are product data, not convenience text

`input_summary`, `output_summary`, and compact metadata shapes must be stable and compare-friendly. They should never depend on brittle heuristics if a safer canonical representation exists.

### 6. Preserve edge-case visibility

We should not hide strange provider behavior. Empty responses, refusals, tool-only responses, malformed arguments, and partial stream endings should remain visible as real observability events.

### 7. Canonical content channels are structurally distinct

Provider responses surface several semantically distinct content channels — assistant text, refusals, internal/extended thinking, tool calls, media. Leer treats these as structurally separate even when a provider conflates them on the wire.

The rule for canonical consumers (run-detail, compare, exports, future replay) is:

- **`output.text` is the main human-readable assistant text.** It is the primary surface for run-detail bodies, compare summaries, and full-text search.
- **`thinking`, `refusal`, `tool_calls`, and media blocks are separate semantic channels.** They live in dedicated structured fields (`content_blocks` of typed shapes; `meta.refusal`; `tool_calls`; etc.).
- **For backward compatibility, refusal text is also inlined into `output.text`** with a `[refusal] ` prefix (the dual-representation rule introduced by Step 1). Thinking text is *not* mirrored into `output.text` — it has no human-friendly inline representation.
- **Canonical consumers should prefer the structured field when available.** UIs that just need to render an assistant body can keep reading `output.text`; UIs that need to detect, color, badge, or filter on a channel must read the structured field directly. Future code should not collapse the channels back into one.

This rule applies uniformly across providers and across sync/streaming paths. New channels added later (e.g. tool-result content, citations) should follow the same shape: typed structured field as the source of truth, optional human-readable mirror in `output.text` only when the inline form is genuinely useful.

---

## Main Problem Areas

The hardening pass should focus on five recurring classes of problems.

### 1. Normalization drift

The same semantic outcome may currently normalize slightly differently depending on:
- provider
- endpoint shape
- sync vs streaming path
- wrapper-specific summary logic

Examples:
- text-only outputs
- tool-call-only outputs
- text + tool-call mixed outputs
- refusal-like outputs
- multimodal outputs with sparse fields
- empty `content_blocks`

### 2. Wrapper/runtime edge cases

Wrapper behavior can drift from ideal-path normalization in cases like:
- exception during request
- exception during stream collection
- partial provider response objects
- duplicated artifact creation
- missing final usage fields
- async finalization ordering
- step status not matching actual outcome

### 3. Summary mismatch

`output_summary` and compare-safe compact shapes can become misleading when:
- provider output is partial
- arguments are malformed or not parseable
- a response contains only media or only tool calls
- stream finalization differs from one-shot behavior

### 4. Compare fragility

Compare can become noisy or misleading when:
- step matching is approximate
- one side is partial
- provider fields are present only on one side
- summaries omit the key thing that changed
- ordering shifts make naive diffs look larger than they are

### 5. UI trust gaps

Run detail and compare must never make users wonder whether Leer dropped or misread data.

That means:
- safe empty states
- explicit partial/unmatched behaviors where appropriate
- stable rendering for malformed or sparse payloads
- obvious provider/model display
- safe fallback rendering rather than crashes or blank panels

---

## What “Done” Looks Like

A hardened provider layer should satisfy all of the following.

### OpenAI and Anthropic wrappers

- sync and async paths behave consistently
- one-shot and streaming paths produce compatible normalized outputs
- artifacts are attached once and in a predictable way
- partial failures preserve useful debugging context
- wrapper tests cover edge cases, not only happy paths

### Normalization

- equivalent semantic outcomes normalize to equivalent canonical shapes across providers when practical
- fallback behavior is conservative and documented
- malformed or sparse provider payloads do not crash normalization
- content ordering is preserved
- summaries remain aligned with normalized outputs

### Run detail

- no crashes on partial or malformed metadata
- meaningful rendering for empty/partial outputs
- provider/model visibility stays clear
- canonical content remains readable even when provider payloads are odd

### Compare

- no regressions with sparse or malformed shapes
- major provider-output differences surface clearly
- one-sided or partial states render safely
- compare continues to rely on compact product-safe summaries where possible

### Docs and QA

- support boundaries are documented
- at least one QA/demo pass proves the hardened cases visually
- known limitations are explicit rather than implicit

---

## Hardening Areas

### A. Normalization consistency

This area focuses on canonical output correctness and parity.

Examples of cases to audit and harden:
- text-only response
- tool-call-only response
- text + tool call mixed response
- empty output with usage
- refusal / blocked response if surfaced by provider
- multimodal output with artifact-linked content blocks
- malformed tool arguments payloads
- repeated / duplicated provider blocks
- sparse metadata / missing request_id / missing finish_reason

Expected outcomes:
- stable canonical shapes
- stable compact summaries
- no provider-specific product drift without a good reason

### B. Wrapper runtime behavior

This area focuses on wrapper execution paths.

Examples:
- request exceptions before response object exists
- stream collector interrupted mid-stream
- finalizer called on partial stream state
- duplicate artifact creation risk
- inconsistent step status on errors
- async wrapper behavior mismatch vs sync wrapper

Expected outcomes:
- step state matches reality
- artifacts remain inspectable
- stream and non-stream paths converge to the same semantic final result where appropriate

### C. Compare and UI robustness

This area focuses on safe rendering and diffing.

Examples:
- malformed `llm` metadata
- absent usage fields
- output_summary missing some keys
- media-only outputs
- tool-only outputs
- retrieval / MCP / multimodal coexistence with provider outputs
- side A only / side B only states

Expected outcomes:
- no crashes
- no blank sections when meaningful data exists
- readable fallback rendering
- useful insight messages where high-signal divergence exists

### D. Support boundary documentation

This area focuses on explicitness.

Document:
- what OpenAI endpoints/shapes are supported now
- what Anthropic shapes are supported now
- what is normalized canonically
- what falls back to generic behavior
- what is intentionally deferred

---

## v1 Hardening Strategy

This workstream is not about adding many new product concepts.
It is about improving reliability using the current architecture.

### Use existing primitives

Continue to rely on:
- `TraceStep`
- `TraceArtifact`
- `metadata["llm"]`
- `input_summary` / `output_summary`
- blob-backed artifacts where relevant
- existing compare and run-detail surfaces

### Prefer additive changes

Good hardening changes include:
- normalization helper refinement
- safer summary builders
- stricter tests
- compare routing improvements
- UI fallback handling
- better demo scripts and QA docs

### Avoid architectural detours

Do not turn this into:
- replay design
- execution engine design
- broad provider abstraction redesign
- new persistence layer

---

## Known Non-Goals

This hardening pass should explicitly avoid:
- implementing replay for tool/MCP/retrieval workflows
- guaranteeing provider parity for every obscure provider-native feature
- supporting every OpenAI or Anthropic API surface immediately
- introducing a new provider plugin architecture unless truly necessary
- broadening beyond the first two providers before their support feels solid

---

## Architecture Notes

### Existing architecture to preserve

- provider wrappers remain the capture boundary
- normalized LLM shapes remain the product-facing model
- raw provider payloads may remain available through artifacts / metadata
- compare should continue to operate mostly on compact summaries and canonical metadata

### Acceptable implementation tools

- additional normalization helpers
- summary helper refinement
- stricter stream finalization logic
- more explicit metadata flags if needed
- new tests, demos, QA checklists

### Possible additive metadata

If useful, small additive metadata fields are acceptable when they improve trust and rendering, for example:
- partial / incomplete hints
- wrapper-path hints for debugging
- safer provider mode labels

But these should be minimal and justified.

---

## Risks

### 1. Over-hardening one provider path but not its twin

A fix made only in sync or only in async, or only in OpenAI but not Anthropic, can create hidden inconsistency.

### 2. Summary drift from canonical output
n
If summaries are hardened independently of normalization, compare can become cleaner but less truthful.

### 3. Too much provider-specific branching

If provider-specific logic spreads into the UI, the product model becomes harder to reason about.

### 4. Expanding scope into replay or execution

That would slow the workstream and dilute the observability wedge.

---

## Success Criteria

This workstream is successful when:
- OpenAI and Anthropic support feel reliable enough for serious usage
- weird outputs do not cause confusing compare or run-detail behavior
- canonical shapes are more consistent and explicitly bounded
- demos and QA checks cover the real edge cases people will hit
- the project is better positioned for future replay work without having to solve replay now

---

## Recommended Execution Order

1. audit current provider edge cases
2. harden normalization and summaries
3. harden wrapper/runtime behavior
4. harden compare and UI non-regression
5. demo + QA signoff

---

## Status

**Complete.** Tracked under the **Provider Reliability Pass** workstream. All five steps (0–4) are done; OpenAI and Anthropic support is assessed production-ready for the v1 observability scope (see QA report).

- **Step 0 — Audit**: complete (`docs/04-execution/provider-hardening-step-0-audit.md`)
- **Step 1 — Normalization + summary hardening**: complete. Introduced `metadata.capture = "partial"` and refusal dual-representation (`output.text` + `meta.refusal`). See plan for stable contracts.
- **Step 2 — Sync↔streaming parity + cross-provider metadata consistency**: complete. Introduced `LLMUsage.cached_tokens`, OpenAI Responses-API streaming canonical parity, Anthropic streaming `thinking` / `redacted_thinking` capture, and malformed-`usage` tolerance. See plan for stable contracts.
- **Step 3 — UI visibility + non-regression for newly hardened provider data**: complete. Surfaced the Step 1/2 canonical fields in the existing surfaces (no redesign): `metadata.capture = "partial"` and `meta.refusal` badges on run-detail + compare step headers, `usage.cached_tokens` in run-detail/compare usage views, a dedicated collapsed Thinking section in run-detail (thinking kept structurally separate from `output.text` per Design Principle 7, never fed into compare summaries), refusal/cached-tokens compare insights, and stream-event legibility for the new canonical event types. Frontend-only; detection rules centralized in `apps/web/src/lib/provider-hardening.ts` with `bun test` coverage. See plan for details.
- **Step 4 — Demo + QA signoff**: complete (`docs/04-execution/provider-hardening-qa.md`). A deterministic, offline validation matrix (`apps/sdk-python/tests/test_provider_hardening_qa.py`, 34 tests) drives the real wrappers across every OpenAI Chat / OpenAI Responses / Anthropic scenario and asserts execution-record quality. The review surfaced two parity gaps — Anthropic refusals (`stop_reason == "refusal"`) were not mapped to `meta.refusal`, and OpenAI streaming recorded the requested model instead of the provider-resolved one — both now fixed and regression-tested. Full SDK suite: 669 passed. Verdict: close the workstream; remaining items are documented limits or deferred feature work.

The canonical content-channels rule (Design Principle 7) is the durable contract that Step 3's UI work respects: thinking is surfaced as its own channel and is never merged into `output.text` or compare diffs.
