"""G-A2 — instrument OpenAI's `.stream()` context-manager helpers.

Before this, only `create(stream=True)` was captured; `client.chat.completions.
stream(...)` and `client.responses.stream(...)` fell through uninstrumented
(no step). These tests pin that `.stream()` produces the *same* canonical
record as `create(stream=True)`, reusing the StreamCollector assembly.

The chat `.stream()` helper emits higher-level events; each underlying chunk
arrives as a `chunk`-type event wrapping the raw ChatCompletionChunk. The
responses `.stream()` helper emits the same event types as
`responses.create(stream=True)`.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from leer.context import reset_context, set_current_run
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun


def _traced(fn: Any) -> TraceRun:
    run = TraceRun(workflow_name="stream-helpers")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


class _FakeStreamObj:
    """Entered stream: iterable + exposes get_final_* like the real helper."""

    def __init__(self, events: list[Any], final: Any = None) -> None:
        self._events = list(events)
        self._i = 0
        self._final = final

    def __iter__(self) -> "_FakeStreamObj":
        return self

    def __next__(self) -> Any:
        if self._i >= len(self._events):
            raise StopIteration
        ev = self._events[self._i]
        self._i += 1
        if isinstance(ev, Exception):
            raise ev
        return ev

    def get_final_completion(self) -> Any:
        return self._final

    def get_final_response(self) -> Any:
        return self._final


class _FakeStreamManager:
    """Context manager returned by `.stream()`; enter yields the stream."""

    def __init__(self, stream: _FakeStreamObj) -> None:
        self._stream = stream
        self.entered = False
        self.exited = False

    def __enter__(self) -> _FakeStreamObj:
        self.entered = True
        return self._stream

    def __exit__(self, *a: Any) -> bool:
        self.exited = True
        return False


def _chunk_event(**chunk: Any) -> dict[str, Any]:
    return {"type": "chunk", "chunk": chunk}


def _step(run: TraceRun):
    assert len(run.steps) == 1, f"expected exactly one step, got {len(run.steps)}"
    return run.steps[0]


def _artifact_types(run: TraceRun, step) -> list[str]:
    return [a.artifact_type for a in run.artifacts if a.step_id == step.id]


# ---------------------------------------------------------------------------
# Chat completions .stream()
# ---------------------------------------------------------------------------

class TestChatStreamHelper:

    def test_creates_step_with_assembled_text_and_stream_artifact(self):
        events = [
            _chunk_event(id="s1", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": "Hello "}}]),
            # Non-chunk semantic events duplicate chunk data; must be ignored.
            {"type": "content.delta", "delta": "Hello "},
            _chunk_event(id="s1", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": "world"}}]),
            {"type": "content.done", "content": "Hello world"},
            _chunk_event(id="s1", model="gpt-4.1", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
            _chunk_event(usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}),
        ]

        def go(run):
            client = MagicMock()
            client.chat.completions.stream.return_value = _FakeStreamManager(_FakeStreamObj(events))
            with wrap_openai_client(client).chat.completions.stream(
                model="gpt-4.1", messages=[{"role": "user", "content": "hi"}],
            ) as stream:
                for _ in stream:
                    pass
        run = _traced(go)
        s = _step(run)
        assert s.step_type == "llm"
        assert s.status == "completed"
        assert s.metadata.get("capture") != "partial"
        assert s.metadata.get("stream", {}).get("is_stream") is True
        llm = s.metadata.get("llm")
        assert isinstance(llm, dict)
        # Only chunk events drive assembly — no double counting.
        assert llm["output"]["text"] == "Hello world"
        assert s.metadata["usage"]["total_tokens"] == 8
        assert "llm_stream" in _artifact_types(run, s)

    def test_structured_output_parity(self):
        obj = {"intent": "q", "confidence": 0.9}
        text = json.dumps(obj)
        events = [
            _chunk_event(id="s2", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": text[:10]}}]),
            _chunk_event(id="s2", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": text[10:]}}]),
            _chunk_event(id="s2", model="gpt-4.1", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
        ]

        def go(run):
            client = MagicMock()
            client.chat.completions.stream.return_value = _FakeStreamManager(_FakeStreamObj(events))
            with wrap_openai_client(client).chat.completions.stream(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
                response_format={"type": "json_object"},
            ) as stream:
                for _ in stream:
                    pass
        llm = _step(_traced(go)).metadata["llm"]
        assert llm["output"]["text"] == text
        assert llm["output"].get("parsed") == obj
        assert llm["meta"].get("output_is_json") is True

    def test_get_final_completion_delegates_to_underlying(self):
        sentinel = {"id": "final", "choices": []}
        events = [_chunk_event(id="s3", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": "hi"}}])]

        captured: dict[str, Any] = {}

        def go(run):
            client = MagicMock()
            client.chat.completions.stream.return_value = _FakeStreamManager(_FakeStreamObj(events, final=sentinel))
            with wrap_openai_client(client).chat.completions.stream(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
            ) as stream:
                for _ in stream:
                    pass
                captured["final"] = stream.get_final_completion()
        run = _traced(go)
        # Instrumentation must not break the user's access to the helper API.
        assert len(run.steps) == 1
        assert captured["final"] is sentinel

    def test_midstream_failure_marks_step_failed(self):
        events = [
            _chunk_event(id="s4", model="gpt-4.1", choices=[{"index": 0, "delta": {"content": "partial"}}]),
            RuntimeError("stream broke"),
        ]

        def go(run):
            client = MagicMock()
            client.chat.completions.stream.return_value = _FakeStreamManager(_FakeStreamObj(events))
            try:
                with wrap_openai_client(client).chat.completions.stream(
                    model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
                ) as stream:
                    for _ in stream:
                        pass
            except RuntimeError:
                pass
        s = _step(_traced(go))
        assert s.status == "failed"

    def test_no_active_trace_is_passthrough(self):
        mgr = _FakeStreamManager(_FakeStreamObj([_chunk_event(id="s5", choices=[])]))
        client = MagicMock()
        client.chat.completions.stream.return_value = mgr
        # Outside a trace: returns the raw manager, creates no step.
        result = wrap_openai_client(client).chat.completions.stream(
            model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
        )
        assert result is mgr


# ---------------------------------------------------------------------------
# Responses .stream()
# ---------------------------------------------------------------------------

class TestResponsesStreamHelper:

    def test_creates_step_with_assembled_text(self):
        events = [
            {"type": "response.created", "response": {"id": "resp_1", "model": "gpt-4.1"}},
            {"type": "response.output_text.delta", "delta": "Hel"},
            {"type": "response.output_text.delta", "delta": "lo"},
            {"type": "response.completed", "response": {
                "id": "resp_1", "model": "gpt-4.1", "status": "completed",
                "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
            }},
        ]

        def go(run):
            client = MagicMock()
            client.responses.stream.return_value = _FakeStreamManager(_FakeStreamObj(events))
            with wrap_openai_client(client).responses.stream(
                model="gpt-4.1", input="hi",
            ) as stream:
                for _ in stream:
                    pass
        run = _traced(go)
        s = _step(run)
        assert s.status == "completed"
        assert s.metadata.get("stream", {}).get("is_stream") is True
        llm = s.metadata["llm"]
        assert llm["provider"] == "openai"
        assert llm["output"]["text"] == "Hello"
        assert s.metadata["usage"]["total_tokens"] == 6
        assert "llm_stream" in _artifact_types(run, s)
