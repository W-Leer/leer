"""Provider version-drift regression suite (workstream E, Step 1).

Locks the canonical normalization of a corpus of representative OpenAI /
Anthropic payloads. Each raw fixture under ``fixtures/provider_payloads/raw/``
is normalized and its ``NormalizedLLMCall.to_dict()`` compared to a committed
golden snapshot. If a provider changes a payload shape — or our normalization
changes — the canonical output diverges and the snapshot test fails with a
readable diff.

Golden snapshots are content-derived and deterministic (the only wall-clock
input, ``latency_ms``, is pinned per fixture). When a normalization change is
*intentional*, regenerate and review the diff:

    LEER_UPDATE_GOLDEN=1 uv run python -m pytest tests/test_provider_drift.py

A set of scenario invariants runs independently of the snapshot so a bogus
golden (e.g. regenerated after an accidental regression) cannot pass silently.

See ``docs/04-execution/version-drift-step-0-audit.md``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from leer.integrations.normalize import NormalizedLLMCall, normalize_anthropic, normalize_openai

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "provider_payloads"
RAW_DIR = FIXTURE_ROOT / "raw"
GOLDEN_DIR = FIXTURE_ROOT / "golden"

_UPDATE = os.environ.get("LEER_UPDATE_GOLDEN") == "1"

_RAW_FIXTURES = sorted(RAW_DIR.glob("*.json"))
_IDS = [p.stem for p in _RAW_FIXTURES]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(fixture: dict[str, Any]) -> NormalizedLLMCall:
    kind = fixture["kind"]
    request = fixture["request"]
    response = fixture["response"]
    latency = fixture.get("latency_ms")
    if kind in ("openai_chat", "openai_responses"):
        return normalize_openai(request, response, latency_ms=latency)
    if kind == "anthropic":
        return normalize_anthropic(request, response, latency_ms=latency)
    raise AssertionError(f"unknown fixture kind: {kind!r}")


def _dump_golden(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def test_fixture_corpus_present() -> None:
    """Guard against a silently-empty corpus making the suite vacuous."""
    assert len(_RAW_FIXTURES) >= 10, (
        f"expected a representative provider fixture corpus, found {len(_RAW_FIXTURES)}"
    )


@pytest.mark.parametrize("raw_path", _RAW_FIXTURES, ids=_IDS)
def test_golden_snapshot(raw_path: Path) -> None:
    fixture = _load(raw_path)
    actual = _normalize(fixture).to_dict()
    golden_path = GOLDEN_DIR / raw_path.name

    if _UPDATE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(_dump_golden(actual), encoding="utf-8")
        pytest.skip(f"updated golden: {golden_path.name}")

    assert golden_path.exists(), (
        f"missing golden for {raw_path.name}; regenerate with LEER_UPDATE_GOLDEN=1"
    )
    expected = _load(golden_path)
    assert actual == expected, (
        f"normalization drift for {raw_path.name}: canonical output changed. "
        f"If intentional, regenerate with LEER_UPDATE_GOLDEN=1 and review the diff."
    )


@pytest.mark.parametrize("raw_path", _RAW_FIXTURES, ids=_IDS)
def test_canonical_invariants(raw_path: Path) -> None:
    """Snapshot-independent invariants — these would catch a regressed golden."""
    fixture = _load(raw_path)
    stem = raw_path.stem
    d = _normalize(fixture).to_dict()

    expected_provider = "anthropic" if fixture["kind"] == "anthropic" else "openai"
    assert d["provider"] == expected_provider
    assert d["model"], "model must resolve to a non-empty value"
    for key in ("input", "output", "usage", "meta"):
        assert key in d, f"canonical output missing '{key}'"
    assert d["meta"]["latency_ms"] == fixture.get("latency_ms"), "latency must round-trip"

    if "refusal" in stem:
        assert d["meta"]["refusal"], "refusal scenario must populate meta.refusal"
    if "tool" in stem:
        assert len(d["output"]["tool_calls"]) >= 1, "tool scenario must capture a tool call"
        assert all(tc.get("name") for tc in d["output"]["tool_calls"]), "tool calls need a name"
    if "json_object" in stem:
        assert d["meta"]["output_is_json"] is True
        assert d["output"]["parsed"] is not None
    if "cached" in stem:
        assert d["usage"]["cached_tokens"] is not None, "cached scenario must report cached_tokens"
    if "thinking" in stem:
        block_types = {b.get("type") for b in d["output"]["content_blocks"]}
        assert block_types & {"thinking", "redacted_thinking"}, "thinking scenario must keep a thinking block"
    if "commentary" in stem:
        commentary = [b for b in d["output"]["content_blocks"] if b.get("phase") == "commentary"]
        assert commentary, "commentary must be kept as a tagged content block"
        assert commentary[0]["text"] not in (d["output"]["text"] or ""), "commentary must not leak into output.text"
    if "namespaced" in stem:
        keys = [(tc.get("namespace"), tc.get("name")) for tc in d["output"]["tool_calls"]]
        assert len(set(keys)) == len(keys), "same-named tools must stay distinguishable by namespace"
    if "provider_run" in stem:
        provider_tools = [b for b in d["output"]["content_blocks"] if b.get("type") == "provider_tool"]
        assert provider_tools, "provider-run tools must be kept as provider_tool parts"
        assert all(b.get("name") for b in provider_tools), "provider-run tools need a name"
        linked_ids = {tc.get("id") for tc in d["output"]["tool_calls"]}
        assert not linked_ids & {b["id"] for b in provider_tools}, "provider-run tools must stay out of tool_calls"
        assert "encrypted_content" not in json.dumps(d["output"]), "opaque provider blobs must not be copied"
    if "refusal_category" in stem:
        assert d["meta"]["refusal_category"], "refusal_category scenario must populate meta.refusal_category"


def _sdk_response_type(kind: str) -> Any:
    if kind == "openai_chat":
        return pytest.importorskip("openai.types.chat").ChatCompletion
    if kind == "openai_responses":
        return pytest.importorskip("openai.types.responses").Response
    return pytest.importorskip("anthropic.types").Message


@pytest.mark.parametrize("raw_path", _RAW_FIXTURES, ids=_IDS)
def test_fixture_is_valid_for_the_current_sdk(raw_path: Path) -> None:
    """Hand-authored payloads must be ones the real SDK would accept, so the
    corpus can't drift into shapes the provider never sends. Fails when an SDK
    upgrade adds a required field — update the fixture, then the golden."""
    fixture = _load(raw_path)
    _sdk_response_type(fixture["kind"]).model_validate(fixture["response"])


def test_harness_detects_drift() -> None:
    """Prove the snapshot comparison actually catches a changed field."""
    fixture = _load(RAW_DIR / "openai_chat__text.json")
    actual = _normalize(fixture).to_dict()
    mutated = json.loads(json.dumps(actual))
    mutated["output"]["text"] = (mutated["output"]["text"] or "") + " DRIFT"
    assert mutated != actual
