# Provider payload fixtures — version-drift regression corpus

This corpus protects Leer's normalization against OpenAI / Anthropic API shape
changes. Driven by `tests/test_provider_drift.py`.

- `raw/` — representative provider request + response payloads (hand-authored).
- `golden/` — the canonical `NormalizedLLMCall.to_dict()` each raw payload
  normalizes to. **Committed.** A change here means normalization drifted.
- `stream/` — the SSE event list for the raw fixture with the same name,
  replayed through the real SDK by `tests/test_provider_drift_streaming.py`.
- `golden_stream/` — the streamed `llm` record and `stream` metadata, minus
  wall-clock fields. The streamed record must also equal the non-streamed one.

## Raw fixture format

```jsonc
{
  "kind": "openai_chat" | "openai_responses" | "anthropic",
  "provenance": {
    "provider": "openai",
    "surface": "client.chat.completions.create",
    "source": "hand-authored",      // or "recorded:<model>@<date>"
    "api_reference_date": "2026-06",
    "notes": "..."
  },
  "latency_ms": 842,                  // pinned so the golden stays deterministic
  "request":  { ... },                // what the caller passed
  "response": { ... }                 // provider response (as `.model_dump()` shape)
}
```

`kind` selects the normalizer: `openai_*` → `normalize_openai` (which
auto-detects chat vs. responses), `anthropic` → `normalize_anthropic`.

## How drift is detected

Each raw fixture is normalized and its `to_dict()` compared to the matching
`golden/<name>.json`. Any difference fails `test_golden_snapshot`. A separate
`test_canonical_invariants` asserts scenario properties (refusal sets
`meta.refusal`, tool scenarios capture a tool call, etc.) independently of the
snapshot, so a regressed golden cannot be committed unnoticed.

## Accepting an intentional normalization change

When you intentionally change normalization, regenerate and **review the diff**
before committing:

```bash
cd apps/sdk-python
LEER_UPDATE_GOLDEN=1 uv run python -m pytest tests/test_provider_drift.py
git diff tests/fixtures/provider_payloads/golden/   # confirm every change is expected
```

## Adding a scenario

1. Drop a new `raw/<provider>__<scenario>.json` (follow an existing one).
   Stem names trigger invariants: `tool`, `refusal`, `provider_run`, … (see
   `test_canonical_invariants`).
2. Derive its streamed twin:
   `uv run python tools/derive_stream_fixture.py tests/fixtures/provider_payloads/raw/<stem>.json`
3. Regenerate goldens for both suites:
   `LEER_UPDATE_GOLDEN=1 uv run python -m pytest tests/test_provider_drift.py tests/test_provider_drift_streaming.py`
4. Review the new goldens for correctness; commit raw, stream and goldens together.

## Refreshing against real provider payloads

The committed fixtures are hand-authored for deterministic, offline CI. An
opt-in recorder that refreshes them from the live APIs is **planned but not
built yet** (workstream E step 3; see
`docs/04-execution/provider-drift-assessment-2026-10.md`). It will write `raw/`
fixtures with `provenance.source = "recorded:<model>@<date>"`; review that diff
(especially new or renamed fields) before regenerating goldens.

Every `response` must validate against the real SDK type (`ChatCompletion`,
`Response`, or Anthropic `Message`); `test_fixture_is_valid_for_the_current_sdk`
enforces it. Every stream event must validate against the SDK's event type
(`test_stream_events_are_valid_for_the_current_sdk`), and every `request` must
be accepted by the SDK's `create()` (the replay calls it). When an SDK upgrade makes a field required, add it to the
fixture first, then regenerate goldens and review the diff.
