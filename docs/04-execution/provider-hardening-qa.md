# Provider Hardening — Step 4 QA Report & Signoff

Demo-validation and QA signoff for the OpenAI / Anthropic provider-reliability
pass. This report validates that Leer captures realistic provider workloads
correctly, documents the remaining gaps found during the Step 4 review, records
the fixes applied, and gives a final production-readiness assessment.

Related docs:
- `docs/03-specs/platform/provider-hardening.md` (spec, Design Principle 7)
- `tasks/provider-hardening-implementation-plan.md` (Steps 0–3)
- `docs/04-execution/provider-hardening-step-0-audit.md` (audit template)

Scope guardrails honored: no architecture redesign, no new features, no replay,
no schema/API changes, OpenAI + Anthropic only.

---

## 1. Method

Validation is **deterministic and offline**. Rather than calling live provider
APIs (non-reproducible, costly, key-dependent), the matrix drives the *real*
wrappers (`wrap_openai_client`, `wrap_anthropic_client`) with fixtures that
mirror provider wire shapes, using the same in-memory `TraceRun` harness the
existing wrapper tests use. This exercises the full capture pipeline end to end:

```
request dict → wrapper → (stream collector) → normalize_* → metadata.llm
            → input/output summaries → llm_request / llm_response / llm_stream
            / tool_call artifacts → step status
```

The matrix lives in `apps/sdk-python/tests/test_provider_hardening_qa.py` and
runs in CI alongside the rest of the SDK suite. It is the executable form of
this report: every row in §2 maps to a test, and the two gaps in §3 each ship
with a regression test.

For every scenario the matrix asserts the **execution-record-quality**
checklist from the Step 4 plan:

| Check | How it is verified |
|---|---|
| request capture | `llm_request` artifact attached to the step |
| response capture | `llm_response` (non-stream) / `llm_stream` (stream) artifact |
| normalized output | `metadata.llm` present, canonical `provider/output/...` |
| metadata usage | `metadata.usage` has `prompt/completion/total/cached_tokens` |
| tool-call capture | `output.tool_calls` populated + one `tool_call` artifact each |
| stream artifacts | `metadata.stream.is_stream` + `llm_stream` on streamed steps |
| run-detail rendering | canonical fields present that run-detail reads (Step 3) |
| compare rendering | compact summaries + `metadata.llm` present (Step 3) |
| step status | `completed` on success, `failed` on raised provider error |
| error handling | failed call → `status=failed` + `error_type` + request preserved |
| partial capture | enrich failure → `status=completed` + `capture="partial"` |

---

## 2. Validated scenario matrix

All scenarios below **PASS** after the Step 4 fixes (34/34 in the QA module;
669/669 across the full SDK suite).

### OpenAI Chat Completions
| Scenario | Status | Notes |
|---|---|---|
| simple text | ✅ | text → `output.text`, `llm_response` artifact |
| single tool call | ✅ | `function` parsed, args JSON-decoded, `tool_call` artifact |
| multiple tool calls | ✅ | order preserved, one `tool_call` artifact per call |
| refusal | ✅ | `message.refusal` → `meta.refusal` + `[refusal]` inline text |
| streaming text | ✅ | deltas assembled, `llm_stream` + stream metadata |
| streaming tool call | ✅ | index-keyed arg deltas stitched + parsed |
| streaming refusal | ✅ | `delta.refusal` → `meta.refusal` (Step 2) |
| empty output + usage | ✅ | empty completion stays a real, inspectable record |
| mid-stream failure | ✅ | `status=failed`, partial text + `llm_stream` preserved |

### OpenAI Responses
| Scenario | Status | Notes |
|---|---|---|
| text output | ✅ | `output_text` blocks → `output.text` |
| tool call | ✅ | `function_call` item, `call_id` preserved |
| refusal | ✅ | `refusal` block → `meta.refusal` + inline text |
| streaming text | ✅ | `response.output_text.delta`, cached_tokens from `response.completed` |
| streaming tool call | ✅ | `output_item.added` + `function_call_arguments.delta` |
| streaming refusal | ✅ | `response.refusal.delta` → `meta.refusal` (Step 2) |

### Anthropic Messages
| Scenario | Status | Notes |
|---|---|---|
| simple text | ✅ | computed `total_tokens`, `llm_response` artifact |
| tool use | ✅ | `tool_use` block → tool call, `tool_call` artifact |
| thinking | ✅ | `thinking` channel separate from `output.text` (DP7) |
| redacted thinking | ✅ | typed placeholder preserved |
| refusal | ✅ | **fixed in Step 4** — `stop_reason="refusal"` → `meta.refusal` |
| cached tokens | ✅ | `cache_read_input_tokens` → `usage.cached_tokens` |
| streaming text | ✅ | `text_delta` assembled, `llm_stream` |
| streaming thinking | ✅ | `thinking_delta` + `signature_delta`, out of `output.text` |
| streaming tool use | ✅ | `input_json_delta` stitched + parsed |
| streaming refusal | ✅ | **fixed in Step 4** — inherited via round-tripped `stop_reason` |

### Cross-cutting (both providers)
| Scenario | Status | Notes |
|---|---|---|
| request exception | ✅ | `status=failed`, `error_type`, request artifact preserved, not `partial` |
| enrich failure → partial | ✅ | `status=completed`, `capture="partial"`, raw request+response kept |

---

## 3. Gaps discovered during Step 4 review

Two real gaps were found by code review and **proven by failing tests before
any code change** (TDD). Both are consistency/parity gaps — exactly the
"over-hardening one provider path but not its twin" risk called out in the spec
(Risks §1) — not crashes. Both were fixed; one observability comment was also
corrected.

### G1 — Anthropic refusals were invisible to the refusal channel — **High** — FIXED
- **Symptom:** OpenAI surfaces refusals via `meta.refusal` (Step 1), which the
  Step 3 UI uses for the refusal badge and the "Refusal divergence" compare
  insight. Anthropic signals refusals via `stop_reason == "refusal"` (not a
  content block), and `normalize_anthropic` never mapped it. So Anthropic
  refusals had `meta.refusal = null`: no badge, no compare insight, and a
  text-less refusal rendered as a confusing empty completed step.
- **Why it matters:** asymmetric hardening of a first-class Step 1 channel
  across the two supported providers; directly in the Step 4 matrix.
- **Fix:** `normalize_anthropic` now sets `meta.refusal` when
  `stop_reason == "refusal"` (refusal text = the model's explanation when
  present, else `"Model declined to respond."`), and inlines a `[refusal] `
  marker into `output.text` only when no other content was returned — mirroring
  the Step 1 dual-representation rule. Because it keys on `stop_reason`, the
  streaming path inherits the fix for free via the round-tripped response dict.
  No UI change was needed: detection is centralized on `meta.refusal`
  (`apps/web/src/lib/provider-hardening.ts`), so the badge and insight now fire
  for Anthropic automatically.
- **Tests:** `TestGapAnthropicRefusal` (non-streaming with text, non-streaming
  text-less inline marker, streaming, and an `end_turn` negative control).

### G2 — OpenAI streaming recorded the requested model, not the resolved one — **Medium** — FIXED
- **Symptom:** Non-streaming OpenAI records `response.model` (the resolved
  snapshot, e.g. `gpt-4.1-2025-04-14`). Anthropic streaming was fixed in Step 1
  to capture the provider-reported model from `message_start`. OpenAI streaming
  (both chat and Responses) still hard-coded `request_dict["model"]` in the
  assembled response, so a streamed call that requested the `gpt-4.1` alias
  recorded the alias while the equivalent non-streamed call recorded the
  snapshot — a sync↔streaming and cross-provider drift that pollutes compare
  (false "model divergence") and weakens debugging.
- **Fix:** `StreamCollector` gains a `set_response_model()` slot exposed as
  `model` in `assembled_output()`. The OpenAI chunk parser captures
  `chunk.model`; the Responses event parser captures `response.model` from
  `response.created` / `response.completed`. Both assembled-to-response
  converters now prefer `assembled.model` and fall back to the requested model
  when the stream carried none. Additive and parity-safe (Anthropic uses its
  existing `ctx["model"]` path, unaffected).
- **Tests:** `TestGapOpenAIStreamingModelFidelity` (chat resolved, Responses
  resolved, and a fallback-to-request control).

### G3 — Responses stream parser comment overclaimed traceability — **Low** — FIXED (comment)
- Unmodeled `response.*` events (e.g. `response.output_item.done`,
  `response.content_part.added`) hit a `pass` branch whose comment said they
  were "recorded for traceability." They are not recorded. Behavior is fine
  (the load-bearing data is captured via delta/usage events; dropping the
  structural events keeps the `llm_stream` artifact focused), but the comment
  was misleading. Corrected to describe the actual behavior. No code-path change.

---

## 4. Deferred items (no action this step)

These were evaluated and intentionally left out of Step 4. None block readiness.

- **OpenAI Responses `reasoning` items** (o-series) normalize to a generic
  `file` content block rather than a dedicated `thinking` channel. This is a
  cross-provider asymmetry with Anthropic thinking, but: reasoning content is
  usually encrypted/summarized/absent, it is outside the Step 4 matrix, and
  mapping it is additive *feature* work (not a regression). Defer to a future
  reasoning-channel step. Low/Medium.
- **Streamed chat-completions usage** requires the caller to pass
  `stream_options={"include_usage": true}`; otherwise OpenAI sends no usage
  chunk and `usage.*` is `null` on the streamed step. This is provider
  behavior, not a Leer defect — documented in the support matrix (§6).
- **Chat completions `n > 1`** — only `choices[0]` is captured. Multi-choice
  sampling is rare and out of the matrix; documented as a known limit.
- **Anthropic `cache_creation_input_tokens`** (cache *write* cost) still not
  surfaced — deliberately not part of canonical `cached_tokens` (would break
  cross-provider parity); would be an Anthropic-only extra. Unchanged from Step 2.
- **Responses streaming interleave ordering** — assembled output groups text →
  tool calls → refusal; original interleave is lost. No consumer needs ordered
  assembly until exact-replay exists. Unchanged from Step 2.
- **Async wrappers** do not exist; sync↔async parity stays out of scope until
  they are introduced (separate workstream).
- **Web render tests** — no React/DOM runner in the repo. UI detection/format
  rules are covered by `bun test` (Step 3); rendering is verified via
  `next build` + manual inspection. A jsdom/RTL harness remains intentionally
  deferred.

---

## 5. Deliverables produced by Step 4

- **QA report** — this document.
- **Validation matrix + regression tests** —
  `apps/sdk-python/tests/test_provider_hardening_qa.py` (34 tests).
- **Fixes** — G1 (`normalize.py`), G2 (`streaming.py` + `openai.py`),
  G3 (comment in `openai.py`).
- **Updated docs** — spec + implementation-plan status (Step 4 complete).

Test totals: full SDK suite **669 passed** (635 pre-Step-4 baseline + 34 new),
0 failures, 0 regressions.

---

## 6. Support matrix (what is guaranteed today)

| Provider / API | Text | Tool calls | Refusal | Thinking | Streaming | Cached tokens | Media |
|---|---|---|---|---|---|---|---|
| OpenAI Chat Completions | ✅ | ✅ (function + custom) | ✅ `meta.refusal` | n/a | ✅¹ | ✅ `prompt_tokens_details` | input only |
| OpenAI Responses | ✅ | ✅ (function_call) | ✅ `meta.refusal` | ⚠️ reasoning → generic block | ✅ | ✅ `input_tokens_details` | ✅ images |
| Anthropic Messages | ✅ | ✅ (tool_use) | ✅ `meta.refusal` (Step 4) | ✅ thinking + redacted | ✅ | ✅ `cache_read_input_tokens` | ✅ images/docs |

¹ Streamed chat usage requires `stream_options={"include_usage": true}`.

**Canonical guarantees (all paths, sync + streaming):**
- Every captured call produces a normalized `metadata.llm`, an `llm_request`
  artifact, and a response artifact (`llm_response` or `llm_stream`).
- `usage` always exposes `prompt/completion/total/cached_tokens`
  (`null` = not reported; `0` = reported-as-zero).
- Refusal is a structured channel (`meta.refusal`) on **both** providers, with
  the `[refusal] ` text mirror for back-compat.
- Thinking is structurally separate from `output.text` and never enters compare
  summaries (Design Principle 7).
- Failures fail closed: a raised provider call → `status=failed` with
  `error_type` and the request preserved; an enrichment failure →
  `status=completed` + `capture="partial"` with raw payloads preserved.

**Known limits (documented, not bugs):** streamed chat usage opt-in; `n > 1`
first-choice-only; OpenAI reasoning content rendered generically; Anthropic
cache-write tokens not canonicalized; async wrappers absent.

---

## 7. Final readiness assessment

**OpenAI and Anthropic provider support is production-ready for the v1
observability scope.**

- Every scenario in the QA matrix captures correctly across sync and streaming,
  with consistent canonical shapes, usage, artifacts, summaries, and step
  status.
- The two real gaps found (Anthropic refusal channel; OpenAI streaming model
  fidelity) were parity/consistency issues, both fixed and regression-tested.
- Remaining items are documented limits or genuinely deferred feature work,
  none blocking.
- The full SDK suite is green (669 passed) with the validation matrix now part
  of CI, so the hardened behavior is protected against regression.

**Recommendation: close the Provider Hardening workstream** (Steps 0–4 complete)
and move to broader Leer roadmap work. Re-open only when introducing async
wrappers or a reasoning/thinking-parity step, both of which are out of this
pass's scope.

### Optional follow-up (not required)
A runnable UI demo (`examples/demo_provider_hardening.py`) emitting one run per
hardened edge case for visual run-detail/compare inspection was **not** added —
the offline validation matrix supersedes it for deterministic, CI-runnable
verification. Add it later only if a guided visual walkthrough is wanted.
