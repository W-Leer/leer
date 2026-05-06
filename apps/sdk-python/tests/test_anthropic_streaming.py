"""Tests for Anthropic streaming wrapper integration — fully mock-based."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from leer.context import get_current_run, set_current_run, reset_context
from leer.integrations.anthropic import wrap_anthropic_client
from leer.models import TraceRun
from leer.step import step as leer_step


# ---------------------------------------------------------------------------
# Helpers — fake Anthropic streaming events
# ---------------------------------------------------------------------------

def _msg_start(
    *,
    msg_id: str = "msg_stream_1",
    model: str = "claude-sonnet-4-20250514",
    input_tokens: int = 10,
) -> dict[str, Any]:
    return {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {"input_tokens": input_tokens},
        },
    }


def _content_block_start_text(index: int = 0) -> dict[str, Any]:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "text", "text": ""},
    }


def _content_block_start_tool(
    index: int,
    tool_id: str = "toolu_abc",
    name: str = "get_weather",
) -> dict[str, Any]:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}},
    }


def _text_delta(text: str, index: int = 0) -> dict[str, Any]:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text},
    }


def _input_json_delta(partial_json: str, index: int = 0) -> dict[str, Any]:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "input_json_delta", "partial_json": partial_json},
    }


def _content_block_stop(index: int = 0) -> dict[str, Any]:
    return {"type": "content_block_stop", "index": index}


def _msg_delta(
    stop_reason: str = "end_turn",
    output_tokens: int = 5,
) -> dict[str, Any]:
    return {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason},
        "usage": {"output_tokens": output_tokens},
    }


def _msg_stop() -> dict[str, Any]:
    return {"type": "message_stop"}


def _text_events(
    *parts: str,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> list[dict[str, Any]]:
    """Build a complete text-only Anthropic stream event sequence."""
    events: list[dict[str, Any]] = [_msg_start(input_tokens=input_tokens)]
    events.append(_content_block_start_text(0))
    for p in parts:
        events.append(_text_delta(p, 0))
    events.append(_content_block_stop(0))
    events.append(_msg_delta(stop_reason=stop_reason, output_tokens=output_tokens))
    events.append(_msg_stop())
    return events


def _tool_use_events(
    tool_id: str = "toolu_abc",
    name: str = "get_weather",
    arguments: str = '{"city":"Paris"}',
) -> list[dict[str, Any]]:
    """Build a complete tool-use Anthropic stream event sequence."""
    events: list[dict[str, Any]] = [_msg_start()]
    events.append(_content_block_start_tool(0, tool_id=tool_id, name=name))
    step = max(1, len(arguments) // 3)
    for i in range(0, len(arguments), step):
        events.append(_input_json_delta(arguments[i:i + step], 0))
    events.append(_content_block_stop(0))
    events.append(_msg_delta(stop_reason="tool_use", output_tokens=15))
    events.append(_msg_stop())
    return events


class _FakeStream:
    """Iterable that yields events in order, supporting both for-loop and
    context-manager patterns."""

    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)
        self._index = 0

    def __iter__(self) -> _FakeStream:
        return self

    def __next__(self) -> Any:
        if self._index >= len(self._events):
            raise StopIteration
        event = self._events[self._index]
        if isinstance(event, Exception):
            self._index += 1
            raise event
        self._index += 1
        return event

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FailingStream:
    """Yields some events then raises."""

    def __init__(self, events: list[Any], error: Exception) -> None:
        self._events = list(events)
        self._error = error
        self._index = 0

    def __iter__(self) -> _FailingStream:
        return self

    def __next__(self) -> Any:
        if self._index >= len(self._events):
            raise self._error
        event = self._events[self._index]
        self._index += 1
        return event


def _fake_streaming_client(stream: Any) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = stream
    return client


def _traced(fn):
    run = TraceRun(workflow_name="test-anthropic-streaming")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


# ---------------------------------------------------------------------------
# 1. Streaming text success
# ---------------------------------------------------------------------------

class TestStreamingTextSuccess:

    def test_text_stream_produces_completed_step(self):
        events = _text_events("Hello", " world", "!")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            result = wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            )
            collected = list(result)
            assert len(collected) == len(events)

        run = _traced(go)
        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.status == "completed"

    def test_text_stream_has_correct_output_summary(self):
        events = _text_events("Hello", " world")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        assert s.output_summary is not None
        assert s.output_summary.get("text") == "Hello world"

    def test_text_stream_has_llm_metadata(self):
        events = _text_events("Hi")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        assert s.metadata.get("provider") == "anthropic"
        assert s.metadata.get("model") == "claude-sonnet-4-20250514"
        assert "llm" in s.metadata

    def test_text_stream_has_usage(self):
        events = _text_events("Hi", input_tokens=20, output_tokens=8)
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        usage = run.steps[0].metadata.get("usage", {})
        assert usage.get("prompt_tokens") == 20
        assert usage.get("completion_tokens") == 8
        assert usage.get("total_tokens") == 28


# ---------------------------------------------------------------------------
# 2. Streaming tool-use success
# ---------------------------------------------------------------------------

class TestStreamingToolUseSuccess:

    def test_tool_use_stream_assembles_correctly(self):
        events = _tool_use_events(
            tool_id="toolu_123", name="get_weather", arguments='{"city":"Paris"}',
        )
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        llm = s.metadata.get("llm", {})
        tool_calls = llm.get("output", {}).get("tool_calls", [])
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "get_weather"
        assert tool_calls[0]["id"] == "toolu_123"
        assert tool_calls[0]["arguments"] == {"city": "Paris"}


# ---------------------------------------------------------------------------
# 3. Partial failure after some events
# ---------------------------------------------------------------------------

class TestStreamingPartialFailure:

    def test_partial_stream_failure_preserves_text(self):
        good_events = [
            _msg_start(),
            _content_block_start_text(),
            _text_delta("partial "),
            _text_delta("text"),
        ]
        stream = _FailingStream(good_events, ConnectionError("stream died"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        stream_meta = s.metadata.get("stream", {})
        assert stream_meta.get("termination") == "failed"

    def test_partial_failure_populates_llm_metadata(self):
        good_events = [
            _msg_start(),
            _content_block_start_text(),
            _text_delta("partial output"),
        ]
        stream = _FailingStream(good_events, RuntimeError("broken"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except RuntimeError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        llm = s.metadata.get("llm")
        assert llm is not None
        assert llm["provider"] == "anthropic"
        assert "partial output" in llm["output"]["text"]

    def test_partial_failure_populates_output_summary(self):
        good_events = [
            _msg_start(),
            _content_block_start_text(),
            _text_delta("hello "),
            _text_delta("world"),
        ]
        stream = _FailingStream(good_events, RuntimeError("err"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except RuntimeError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.output_summary is not None
        assert s.output_summary.get("text") == "hello world"

    def test_partial_failure_has_stream_artifact(self):
        good_events = [_msg_start(), _content_block_start_text(), _text_delta("hi")]
        stream = _FailingStream(good_events, RuntimeError("oops"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except RuntimeError:
                pass

        run = _traced(go)
        stream_arts = [a for a in run.artifacts if a.artifact_type == "llm_stream"]
        assert len(stream_arts) == 1


# ---------------------------------------------------------------------------
# 4. Zero-chunk failure
# ---------------------------------------------------------------------------

class TestZeroChunkFailure:

    def test_zero_events_before_failure(self):
        stream = _FailingStream([], TimeoutError("timeout"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except TimeoutError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        sm = s.metadata.get("stream", {})
        assert sm["chunk_count"] == 0
        assert sm["termination"] == "failed"

    def test_zero_events_no_fake_llm_metadata(self):
        stream = _FailingStream([], TimeoutError("immediate"))

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            try:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))
            except TimeoutError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.metadata.get("provider") == "anthropic"
        assert "llm" not in s.metadata

    def test_create_call_itself_fails(self):
        client = MagicMock()
        client.messages.create.side_effect = ConnectionError("refused")

        def go(run):
            wrapped = wrap_anthropic_client(client)
            try:
                wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                )
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        sm = s.metadata.get("stream", {})
        assert sm["is_stream"] is True
        assert sm["provider"] == "anthropic"
        assert sm["chunk_count"] == 0
        assert sm["termination"] == "failed"
        assert "time_to_first_chunk_ms" in sm
        assert "truncated_chunks" in sm


# ---------------------------------------------------------------------------
# 5. Yielded events are unchanged
# ---------------------------------------------------------------------------

class TestEventsUnchanged:

    def test_yielded_events_are_identical(self):
        original_events = _text_events("a", "b", "c")
        stream = _FakeStream(original_events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            result = wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            )
            collected = list(result)
            for orig, yielded in zip(original_events, collected):
                assert orig is yielded

        _traced(go)


# ---------------------------------------------------------------------------
# 6. Stream metadata added to step
# ---------------------------------------------------------------------------

class TestStreamMetadata:

    def test_stream_metadata_shape(self):
        events = _text_events("Hello", " world")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        sm = s.metadata.get("stream")
        assert sm is not None
        assert sm["is_stream"] is True
        assert sm["provider"] == "anthropic"
        assert sm["termination"] == "completed"
        assert sm["truncated_chunks"] is False
        assert isinstance(sm["chunk_count"], int)
        assert sm["chunk_count"] > 0


# ---------------------------------------------------------------------------
# 7. llm_stream artifact attached
# ---------------------------------------------------------------------------

class TestStreamArtifact:

    def test_stream_artifact_attached_on_success(self):
        events = _text_events("test")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        stream_arts = [a for a in run.artifacts if a.artifact_type == "llm_stream"]
        assert len(stream_arts) == 1
        art = stream_arts[0]
        assert art.role == "output"
        assert art.step_id == run.steps[0].id
        assert art.inline_data is not None
        assert "events" in art.inline_data
        assert art.preview_text is not None
        assert "chunks" in art.preview_text

    def test_request_and_response_artifacts_also_attached(self):
        events = _text_events("hello")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        types = [a.artifact_type for a in run.artifacts]
        assert "llm_request" in types
        assert "llm_response" in types
        assert "llm_stream" in types


# ---------------------------------------------------------------------------
# 8. Final LLM metadata shape after successful stream
# ---------------------------------------------------------------------------

class TestFinalLlmShape:

    def test_llm_metadata_matches_non_streaming_shape(self):
        events = _text_events("Hello world", input_tokens=10, output_tokens=5)
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        llm = s.metadata.get("llm")
        assert llm is not None
        assert llm["provider"] == "anthropic"
        assert llm["model"] == "claude-sonnet-4-20250514"
        assert llm["output"]["text"] == "Hello world"
        assert llm["meta"]["finish_reason"] == "end_turn"
        assert llm["usage"]["prompt_tokens"] == 10
        assert llm["usage"]["completion_tokens"] == 5

    def test_finish_reason_preserved(self):
        events = _text_events("x", stop_reason="max_tokens")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        assert run.steps[0].metadata["llm"]["meta"]["finish_reason"] == "max_tokens"

    def test_message_id_preserved_as_request_id(self):
        events = _text_events("Hi")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        assert run.steps[0].metadata["llm"]["meta"]["request_id"] == "msg_stream_1"


# ---------------------------------------------------------------------------
# 9. Non-streaming behavior unchanged
# ---------------------------------------------------------------------------

class TestNonStreamingUnchanged:

    def test_non_streaming_still_works(self):

        class _FakeMessage:
            def model_dump(self) -> dict[str, Any]:
                return {
                    "id": "msg_test123",
                    "model": "claude-sonnet-4-20250514",
                    "content": [{"type": "text", "text": "hello"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                }

        client = MagicMock()
        client.messages.create.return_value = _FakeMessage()

        def go(run):
            wrapped = wrap_anthropic_client(client)
            result = wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100,
            )
            assert result.model_dump()["model"] == "claude-sonnet-4-20250514"

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        assert s.metadata.get("provider") == "anthropic"
        assert "stream" not in s.metadata
        assert s.output_summary.get("text") == "hello"

    def test_non_streaming_with_explicit_stream_false(self):

        class _FakeMessage:
            def model_dump(self) -> dict[str, Any]:
                return {
                    "id": "msg_test",
                    "model": "claude-sonnet-4-20250514",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                }

        client = MagicMock()
        client.messages.create.return_value = _FakeMessage()

        def go(run):
            wrapped = wrap_anthropic_client(client)
            wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=False,
            )

        run = _traced(go)
        assert run.steps[0].status == "completed"
        assert "stream" not in run.steps[0].metadata


# ---------------------------------------------------------------------------
# 10. Parent step semantics
# ---------------------------------------------------------------------------

class TestStreamingParentStep:

    def test_root_stream_has_no_parent(self):
        events = _text_events("hello")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        assert run.steps[0].parent_step_id is None

    def test_stream_inside_step_inherits_parent(self):
        events = _text_events("nested")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            with leer_step("outer", step_type="code") as outer:
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
                ))

        run = _traced(go)
        assert len(run.steps) == 2
        outer = run.steps[0]
        inner = run.steps[1]
        assert outer.parent_step_id is None
        assert inner.parent_step_id == outer.id


# ---------------------------------------------------------------------------
# Context manager streaming pattern
# ---------------------------------------------------------------------------

class TestContextManagerStream:

    def test_context_manager_pattern(self):
        events = _text_events("ctx", " mgr")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            result = wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100, stream=True,
            )
            with result as s:
                collected = list(s)
            assert len(collected) == len(events)

        run = _traced(go)
        assert run.steps[0].status == "completed"
        stream_arts = [a for a in run.artifacts if a.artifact_type == "llm_stream"]
        assert len(stream_arts) == 1


# ---------------------------------------------------------------------------
# Step 1 hardening — provider-reported model wins in streaming
# ---------------------------------------------------------------------------

class TestStep1ProviderReportedModel:
    """Anthropic's `message_start` event reports the actual model the
    provider served. Previously the streaming-assembled response only
    used `request.model`, which can disagree (e.g. when an alias is
    requested). The fix matches the non-streaming path, where
    `response.model` is authoritative."""

    def test_provider_model_overrides_request_model(self):
        events: list[dict[str, Any]] = [
            _msg_start(model="claude-sonnet-4-20250514-canary"),
            _content_block_start_text(),
            _text_delta("hi"),
            _content_block_stop(0),
            _msg_delta(),
            _msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-latest",  # alias requested
                messages=[], max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        # `metadata.model` is set from the normalized LLM call, which
        # uses _resolve_model(response, request) — provider model wins.
        assert s.metadata.get("model") == "claude-sonnet-4-20250514-canary"
        assert s.metadata["llm"]["model"] == "claude-sonnet-4-20250514-canary"

    def test_request_model_used_when_provider_omits(self):
        """No `message_start.message.model` → request model is the fallback."""
        msg_start_no_model = {
            "type": "message_start",
            "message": {
                "id": "msg_x",
                "usage": {"input_tokens": 5},
            },
        }
        events: list[dict[str, Any]] = [
            msg_start_no_model,
            _content_block_start_text(),
            _text_delta("hi"),
            _content_block_stop(0),
            _msg_delta(),
            _msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=100, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        assert s.metadata.get("model") == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Step 1 hardening — partial-capture fallback when enrich_step fails
# ---------------------------------------------------------------------------

class TestStep1AnthropicStreamingPartialCapture:
    """When `_enrich_step` raises during streaming finalization, the step
    must still get baseline metadata, a `capture: partial` flag, and
    both `llm_request` and `llm_response` artifacts so debugging
    context is preserved."""

    def test_streaming_enrich_failure_marks_partial(self):
        from unittest.mock import patch

        events = _text_events("hello")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            with patch(
                "leer.integrations.anthropic._enrich_step",
                side_effect=RuntimeError("boom"),
            ):
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[],
                    max_tokens=100, stream=True,
                ))

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        assert s.metadata.get("capture") == "partial"
        assert s.metadata.get("provider") == "anthropic"
        assert s.metadata.get("model") == "claude-sonnet-4-20250514"

    def test_streaming_enrich_failure_attaches_request_and_response(self):
        from unittest.mock import patch

        events = _text_events("hello")
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_streaming_client(stream))
            with patch(
                "leer.integrations.anthropic._enrich_step",
                side_effect=RuntimeError("boom"),
            ):
                list(wrapped.messages.create(
                    model="claude-sonnet-4-20250514", messages=[],
                    max_tokens=100, stream=True,
                ))

        run = _traced(go)
        req_arts = [a for a in run.artifacts if a.artifact_type == "llm_request"]
        resp_arts = [a for a in run.artifacts if a.artifact_type == "llm_response"]
        assert len(req_arts) == 1
        assert len(resp_arts) == 1
        # The assembled response_dict carries text from the stream.
        resp_data = resp_arts[0].inline_data
        assert isinstance(resp_data, dict)
        text_blocks = [b for b in resp_data.get("content", []) if b.get("type") == "text"]
        assert any("hello" in b.get("text", "") for b in text_blocks)
