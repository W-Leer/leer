# Provider payload fixtures — version-drift regression corpus

This corpus protects Leer's normalization against OpenAI / Anthropic API shape
changes. Driven by `tests/test_provider_drift.py`.

- `raw/` — representative provider request + response payloads (hand-authored).
- `golden/` — the canonical `NormalizedLLMCall.to_dict()` each raw payload
  normalizes to. **Committed.** A change here means normalization drifted.

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
2. Regenerate goldens with the command above.
3. Review the new golden for correctness; commit raw + golden together.

## Refreshing against real provider payloads

The committed fixtures are hand-authored for deterministic, offline CI. To
refresh them against live API shapes (requires API keys; never run in CI), use
the opt-in recorder:

```bash
OPENAI_API_KEY=... ANTHROPIC_API_KEY=... \
  uv run python tools/record_provider_fixtures.py
```

It writes new `raw/` fixtures with `provenance.source = "recorded:<model>@<date>"`.
Review the diff (especially any new/renamed fields) before regenerating goldens.
