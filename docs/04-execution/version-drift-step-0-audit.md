# Provider Version-Drift Monitoring — Step 0 Audit

Audit of how exposed Leer's **normalization** is to OpenAI / Anthropic API shape
changes, and how a recorded-fixture regression suite should be structured to
catch that drift before it silently corrupts execution records.

Related docs:
- `docs/04-execution/provider-hardening-qa.md` (the capture/normalization contracts this protects)
- `tasks/provider-hardening-implementation-plan.md` (Steps 0–4, now complete)
- `docs/04-growth/next-steps-roadmap.md` (workstream E)

Date: 2026-06-20

---

## 0. What this workstream protects against

A provider changes a payload shape — renames a field, re-nests a delta, adds a
content-block type, moves usage counters. Leer's normalization silently drifts:
it drops data or mis-maps it, and **no test fails**, because today's tests
assert against hand-authored dicts that reflect the *author's* mental model, not
the provider's *current* reality.

This is explicitly a **capture-correctness** safety net, consistent with
"capture over replay." We are not polling provider changelogs or hitting live
APIs in CI — we lock the canonical output of representative payloads so any
change in normalization (intended or not) is surfaced as a reviewable diff.

---

## 1. Normalization surface to protect

Three public entry points produce the canonical `NormalizedLLMCall`
(`leer/integrations/normalize.py`):

- `normalize_openai(request, response, *, latency_ms)` — auto-dispatches by
  response shape to:
  - `_normalize_openai_chat` (`choices[].message`)
  - `_normalize_openai_responses` (`output[]` items)
- `normalize_anthropic(request, response, *, latency_ms)` — `content[]` blocks.

The canonical output is `NormalizedLLMCall.to_dict()` — a fully JSON-serializable
dict over `provider / model / input / output / usage / meta`. It is
**deterministic** given a fixed `latency_ms` (the only wall-clock input;
`request_id` comes from the payload). This makes it an ideal golden-snapshot
target.

Drift-prone mappings worth locking specifically:
- chat: `message.refusal`, `tool_calls[].function`, `usage.prompt_tokens_details.cached_tokens`
- responses: `output[].type` switch (`message`/`function_call`/`refusal`/…),
  `usage.input_tokens_details.cached_tokens`, `status` → `finish_reason`
- anthropic: `content[].type` switch (`text`/`tool_use`/`thinking`/`redacted_thinking`),
  `stop_reason == "refusal"`, `usage.cache_read_input_tokens`

---

## 2. Drift-exposure gaps (current state)

- **G-E1 — No corpus of representative provider payloads.** Inline dicts are
  idealized, simplified, and scattered across 22 test files; there is no single
  source of truth for "what OpenAI/Anthropic actually return."
- **G-E2 — No full-shape lock.** Existing tests assert specific fields; a
  normalization change to an *unasserted* field passes silently. No `to_dict()`
  baseline exists.
- **G-E3 — Streaming shapes unprotected as a corpus.** Streaming is the most
  drift-prone (event-type names, delta nesting); events live inline per test.
- **G-E4 — No fixture provenance.** Without recording provider + API
  reference date, "drift" only means "vs our last snapshot," not "vs provider
  reality." Acceptable for v1 if documented.

---

## 3. Decisions (locked)

- **Fixture source:** hand-authored representative payloads, committed for
  deterministic/offline CI, plus an **optional, opt-in** recorder script to
  refresh fixtures from live APIs when keys are present (never run in CI).
- **Drift detection:** **golden snapshot** of `NormalizedLLMCall.to_dict()`
  (full-shape lock; regenerated via `LEER_UPDATE_GOLDEN=1`), backed by a set of
  scenario **invariants** decoupled from the snapshot so a bogus golden cannot
  be committed unnoticed.

---

## 4. Step plan

- **Step 1 (this step) — non-streaming golden suite.** Hand-authored raw
  fixtures for the chat / responses / anthropic entry points across the core
  scenarios (text, tool call, refusal, JSON object, cached, thinking),
  golden `to_dict()` snapshots, invariants, and a fixtures README documenting
  provenance + the refresh workflow.
- **Step 2 — streaming golden suite.** Drive `StreamCollector` with recorded
  event sequences (fixed timestamp offsets for determinism) → assemble →
  normalize → golden. Streaming is split out because its wall-clock timing
  needs careful pinning.
- **Step 3 — opt-in live recorder.** A script that, given API keys, calls the
  real providers and writes raw fixtures with provenance, so the corpus can be
  refreshed against provider reality on demand.

**Deferred:** live recording in CI, automated changelog/diff detection,
multimodal-specific fixtures (workstream B/C), async wrappers.

---

## 5. Status

- [x] Step 1 — non-streaming golden drift suite
- [ ] Step 2 — streaming golden suite
- [ ] Step 3 — opt-in live recorder

The October 2026 re-assessment
(`docs/04-execution/provider-drift-assessment-2026-10.md`) found that the
OpenAI fixtures aren't valid against the real SDK types (D-M4). Fix that before
step 3, so recorded and hand-authored fixtures share one shape.
