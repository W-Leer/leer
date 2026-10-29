"""Streaming version-drift suite (workstream E, Step 2).

Each ``fixtures/provider_payloads/stream/<stem>.json`` is the SSE event list
for the non-streaming fixture ``raw/<stem>.json``. It is replayed with
``create(stream=True)`` through the real SDK and Leer's wrapper, then:

- the streamed record (minus wall-clock fields) must match
  ``golden_stream/<stem>.json``;
- it must equal the non-streamed record of the raw twin (streaming parity).

Regenerate goldens after an intentional change and review the diff:

    LEER_UPDATE_GOLDEN=1 uv run python -m pytest tests/test_provider_drift_streaming.py

Add a scenario: write ``raw/<stem>.json``, run
``uv run python tools/derive_stream_fixture.py tests/fixtures/provider_payloads/raw/<stem>.json``,
then regenerate. See ``docs/04-execution/version-drift-step-0-audit.md``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

pydantic = pytest.importorskip("pydantic")

from real_sdk_harness import (  # noqa: E402
    anthropic_client,
    json_response,
    only_llm_step,
    openai_client,
    sse_response,
    traced,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "provider_payloads"
RAW_DIR = FIXTURE_ROOT / "raw"
STREAM_DIR = FIXTURE_ROOT / "stream"
GOLDEN_DIR = FIXTURE_ROOT / "golden_stream"

_UPDATE = os.environ.get("LEER_UPDATE_GOLDEN") == "1"
_STREAM_FIXTURES = sorted(STREAM_DIR.glob("*.json"))
_IDS = [p.stem for p in _STREAM_FIXTURES]

# Wall-clock values; everything else in the record is deterministic.
# ``captured_chunk_bytes`` counts serialized events including their
# ``timestamp_offset_ms``, so it varies with timing digits.
_TIMING_KEYS = (
    "first_chunk_at", "last_chunk_at", "time_to_first_chunk_ms", "stream_duration_ms", "captured_chunk_bytes",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _call(kind: str, client_for: Any, request: dict[str, Any], *, stream: bool) -> Any:
    kwargs = {**request, "stream": True} if stream else dict(request)
    if kind == "openai_chat":
        result = client_for(openai_client).chat.completions.create(**kwargs)
    elif kind == "openai_responses":
        result = client_for(openai_client).responses.create(**kwargs)
    else:
        result = client_for(anthropic_client).messages.create(**kwargs)
    if stream:
        for _ in result:
            pass
    return result


def _streamed_step(stream_fixture: dict[str, Any], request: dict[str, Any]) -> Any:
    named = stream_fixture["kind"] != "openai_chat"
    events = stream_fixture["events"]
    run = traced(lambda: _call(
        stream_fixture["kind"], lambda make: make(lambda req: sse_response(events, named=named)), request, stream=True,
    ))
    return only_llm_step(run)


def _plain_llm(raw_fixture: dict[str, Any]) -> dict[str, Any]:
    body = raw_fixture["response"]
    run = traced(lambda: _call(
        raw_fixture["kind"], lambda make: make(lambda req: json_response(body)), raw_fixture["request"], stream=False,
    ))
    return only_llm_step(run).metadata["llm"]


def _without_latency(llm: dict[str, Any]) -> dict[str, Any]:
    return {**llm, "meta": {k: v for k, v in llm["meta"].items() if k != "latency_ms"}}


def _snapshot(step: Any) -> dict[str, Any]:
    stream = {k: v for k, v in step.metadata["stream"].items() if k not in _TIMING_KEYS}
    return {"llm": _without_latency(step.metadata["llm"]), "stream": stream}


def test_stream_corpus_present() -> None:
    assert len(_STREAM_FIXTURES) >= 10, f"expected a streaming fixture corpus, found {len(_STREAM_FIXTURES)}"


@pytest.mark.parametrize("stream_path", _STREAM_FIXTURES, ids=_IDS)
def test_stream_events_are_valid_for_the_current_sdk(stream_path: Path) -> None:
    """The SDKs parse stream events leniently, so validate each one strictly
    against the SDK's event type to keep the corpus to shapes providers send."""
    fixture = _load(stream_path)
    kind = fixture["kind"]
    if kind == "openai_chat":
        from openai.types.chat import ChatCompletionChunk
        adapter: Any = pydantic.TypeAdapter(ChatCompletionChunk)
    elif kind == "openai_responses":
        from openai.types.responses import ResponseStreamEvent
        adapter = pydantic.TypeAdapter(ResponseStreamEvent)
    else:
        from anthropic.types import RawMessageStreamEvent
        adapter = pydantic.TypeAdapter(RawMessageStreamEvent)
    for i, event in enumerate(fixture["events"]):
        try:
            adapter.validate_python(event)
        except pydantic.ValidationError as exc:
            raise AssertionError(f"event {i} ({event.get('type', 'chunk')}) is not SDK-valid:\n{exc}") from None


@pytest.mark.parametrize("stream_path", _STREAM_FIXTURES, ids=_IDS)
def test_stream_golden_snapshot(stream_path: Path) -> None:
    raw = _load(RAW_DIR / stream_path.name)
    step = _streamed_step(_load(stream_path), raw["request"])
    assert step.status == "completed"
    actual = _snapshot(step)

    golden_path = GOLDEN_DIR / stream_path.name
    if _UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip(f"updated golden: {golden_path.name}")
    assert golden_path.exists(), f"missing golden for {stream_path.name}; regenerate with LEER_UPDATE_GOLDEN=1"
    assert actual == _load(golden_path), (
        f"streaming drift for {stream_path.name}: canonical output changed. "
        "If intentional, regenerate with LEER_UPDATE_GOLDEN=1 and review the diff."
    )


@pytest.mark.parametrize("stream_path", _STREAM_FIXTURES, ids=_IDS)
def test_stream_matches_non_streaming_twin(stream_path: Path) -> None:
    raw_path = RAW_DIR / stream_path.name
    assert raw_path.exists(), f"stream fixture {stream_path.name} needs a non-streaming twin in raw/"
    raw = _load(raw_path)
    streamed = _without_latency(_streamed_step(_load(stream_path), raw["request"]).metadata["llm"])
    plain = _without_latency(_plain_llm(raw))
    assert streamed == plain
