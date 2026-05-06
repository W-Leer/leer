"""Tests for OpenAI streaming wrapper integration — fully mock-based."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from leer.context import get_current_run, set_current_run, reset_context
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun
from leer.step import step as leer_step


# ---------------------------------------------------------------------------
# Helpers — fake streaming chunks
# ---------------------------------------------------------------------------

def _chunk(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
    chunk_id: str = "chatcmpl-stream-1",
    model: str = "gpt-4.1",
) -> dict[str, Any]:
    """Build a minimal OpenAI chat.completions streaming chunk as a dict."""
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls

    d: dict[str, Any] = {
        "id": chunk_id,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        d["usage"] = usage
    return d


def _text_chunks(*parts: str, finish_reason: str = "stop") -> list[dict[str, Any]]:
    """Produce a sequence of text-delta chunks followed by a stop chunk."""
    chunks = [_chunk(content=p) for p in parts]
    chunks.append(_chunk(finish_reason=finish_reason))
    return chunks


def _tool_call_chunks(
    call_id: str = "call_abc",
    name: str = "get_weather",
    arguments: str = '{"city":"Paris"}',
) -> list[dict[str, Any]]:
    """Produce a sequence of tool-call delta chunks."""
    chunks = [
        _chunk(tool_calls=[{
            "index": 0, "id": call_id,
            "function": {"name": name, "arguments": ""},
        }]),
    ]
    step = max(1, len(arguments) // 3)
    for i in range(0, len(arguments), step):
        chunks.append(_chunk(tool_calls=[{
            "index": 0,
            "function": {"arguments": arguments[i:i + step]},
        }]))
    chunks.append(_chunk(finish_reason="tool_calls"))
    return chunks


class _FakeStream:
    """Iterable that yields chunks in order, supporting both for-loop and
    context-manager patterns."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)
        self._index = 0

    def __iter__(self) -> _FakeStream:
        return self

    def __next__(self) -> Any:
        if self._index >= len(self._chunks):
            raise StopIteration
        chunk = self._chunks[self._index]
        if isinstance(chunk, Exception):
            self._index += 1
            raise chunk
        self._index += 1
        return chunk

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FailingStream:
    """Yields some chunks then raises."""

    def __init__(self, chunks: list[Any], error: Exception) -> None:
        self._chunks = list(chunks)
        self._error = error
        self._index = 0

    def __iter__(self) -> _FailingStream:
        return self

    def __next__(self) -> Any:
        if self._index >= len(self._chunks):
            raise self._error
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _fake_streaming_client(stream: Any) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = stream
    del client.responses
    return client


def _traced(fn):
    run = TraceRun(workflow_name="test-streaming")
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
        chunks = _text_chunks("Hello", " world", "!")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            result = wrapped.chat.completions.create(
                model="gpt-4.1", messages=[], stream=True,
            )
            collected = list(result)
            assert len(collected) == len(chunks)

        run = _traced(go)
        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.status == "completed"

    def test_text_stream_has_correct_output_summary(self):
        chunks = _text_chunks("Hello", " world")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        assert s.output_summary is not None
        assert s.output_summary.get("text") == "Hello world"

    def test_text_stream_has_llm_metadata(self):
        chunks = _text_chunks("Hi")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        assert s.metadata.get("provider") == "openai"
        assert s.metadata.get("model") == "gpt-4.1"
        assert "llm" in s.metadata


# ---------------------------------------------------------------------------
# 2. Streaming tool-call success
# ---------------------------------------------------------------------------

class TestStreamingToolCallSuccess:

    def test_tool_call_stream_assembles_correctly(self):
        chunks = _tool_call_chunks(call_id="call_123", name="get_weather", arguments='{"city":"Paris"}')
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        llm = s.metadata.get("llm", {})
        tool_calls = llm.get("output", {}).get("tool_calls", [])
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "get_weather"
        assert tool_calls[0]["id"] == "call_123"


# ---------------------------------------------------------------------------
# 3. Partial failure after some chunks
# ---------------------------------------------------------------------------

class TestStreamingPartialFailure:

    def test_partial_stream_failure_preserves_text(self):
        good_chunks = [_chunk(content="partial "), _chunk(content="text")]
        stream = _FailingStream(good_chunks, ConnectionError("stream died"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            result = wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True)
            try:
                list(result)
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        stream_meta = s.metadata.get("stream", {})
        assert stream_meta.get("termination") == "failed"
        assert stream_meta.get("chunk_count") == 2

    def test_partial_failure_has_stream_artifact(self):
        good_chunks = [_chunk(content="hi")]
        stream = _FailingStream(good_chunks, RuntimeError("oops"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))
            except RuntimeError:
                pass

        run = _traced(go)
        stream_arts = [a for a in run.artifacts if a.artifact_type == "llm_stream"]
        assert len(stream_arts) == 1


# ---------------------------------------------------------------------------
# 4. Zero-chunk failure
# ---------------------------------------------------------------------------

class TestZeroChunkFailure:

    def test_zero_chunks_before_failure(self):
        stream = _FailingStream([], TimeoutError("timeout"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))
            except TimeoutError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        stream_meta = s.metadata.get("stream", {})
        assert stream_meta["chunk_count"] == 0
        assert stream_meta["termination"] == "failed"

    def test_create_call_itself_fails(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = ConnectionError("refused")
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            try:
                wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True)
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        assert s.metadata.get("stream", {}).get("is_stream") is True
        assert s.metadata["stream"]["chunk_count"] == 0


# ---------------------------------------------------------------------------
# 5. Yielded chunks are unchanged
# ---------------------------------------------------------------------------

class TestChunksUnchanged:

    def test_yielded_chunks_are_identical(self):
        original_chunks = _text_chunks("a", "b", "c")
        stream = _FakeStream(original_chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            result = wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True)
            collected = list(result)
            for orig, yielded in zip(original_chunks, collected):
                assert orig is yielded

        _traced(go)


# ---------------------------------------------------------------------------
# 6. Stream metadata added to step
# ---------------------------------------------------------------------------

class TestStreamMetadata:

    def test_stream_metadata_shape(self):
        chunks = _text_chunks("Hello", " world")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        sm = s.metadata.get("stream")
        assert sm is not None
        assert sm["is_stream"] is True
        assert sm["provider"] == "openai"
        assert sm["chunk_count"] == 3
        assert sm["termination"] == "completed"
        assert sm["truncated_chunks"] is False

    def test_stream_metadata_includes_usage(self):
        chunks = [
            _chunk(content="hi"),
            _chunk(finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
        ]
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        usage = s.metadata.get("usage", {})
        assert usage.get("total_tokens") == 15


# ---------------------------------------------------------------------------
# 7. llm_stream artifact attached
# ---------------------------------------------------------------------------

class TestStreamArtifact:

    def test_stream_artifact_attached_on_success(self):
        chunks = _text_chunks("test")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

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
        chunks = _text_chunks("hello")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

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
        chunks = [
            _chunk(content="Hello world"),
            _chunk(finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
        ]
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        s = run.steps[0]
        llm = s.metadata.get("llm")
        assert llm is not None
        assert llm["provider"] == "openai"
        assert llm["model"] == "gpt-4.1"
        assert llm["output"]["text"] == "Hello world"
        assert llm["meta"]["finish_reason"] == "stop"
        assert llm["usage"]["prompt_tokens"] == 10
        assert llm["usage"]["completion_tokens"] == 5

    def test_finish_reason_preserved(self):
        chunks = [_chunk(content="x"), _chunk(finish_reason="length")]
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        assert run.steps[0].metadata["llm"]["meta"]["finish_reason"] == "length"


# ---------------------------------------------------------------------------
# 9. Non-streaming behavior unchanged
# ---------------------------------------------------------------------------

class TestNonStreamingUnchanged:

    def test_non_streaming_still_works(self):
        """Non-streaming calls must still produce the same step shape."""

        class _FakeResponse:
            def model_dump(self) -> dict[str, Any]:
                return {
                    "id": "chatcmpl-test",
                    "model": "gpt-4.1",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                }

        client = MagicMock()
        client.chat.completions.create.return_value = _FakeResponse()
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            result = wrapped.chat.completions.create(model="gpt-4.1", messages=[])
            assert result.model_dump()["model"] == "gpt-4.1"

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        assert s.metadata.get("provider") == "openai"
        assert "stream" not in s.metadata
        assert s.output_summary.get("text") == "hi"

    def test_non_streaming_with_explicit_stream_false(self):
        """stream=False must behave like non-streaming."""

        class _FakeResponse:
            def model_dump(self) -> dict[str, Any]:
                return {
                    "id": "chatcmpl-test",
                    "model": "gpt-4.1",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                }

        client = MagicMock()
        client.chat.completions.create.return_value = _FakeResponse()
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=False)

        run = _traced(go)
        assert run.steps[0].status == "completed"
        assert "stream" not in run.steps[0].metadata


# ---------------------------------------------------------------------------
# Context manager streaming pattern
# ---------------------------------------------------------------------------

class TestContextManagerStream:

    def test_context_manager_pattern(self):
        """Some users iterate streams with `with stream as s: for chunk in s:`"""
        chunks = _text_chunks("ctx", " mgr")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            result = wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True)
            with result as s:
                collected = list(s)
            assert len(collected) == len(chunks)

        run = _traced(go)
        assert run.steps[0].status == "completed"
        stream_arts = [a for a in run.artifacts if a.artifact_type == "llm_stream"]
        assert len(stream_arts) == 1


# ---------------------------------------------------------------------------
# 10. Partial failure populates normalized LLM state
# ---------------------------------------------------------------------------

class TestPartialFailureEnrichment:

    def test_partial_failure_populates_llm_metadata(self):
        """When partial text exists, failure path should run full enrichment."""
        good_chunks = [_chunk(content="partial output")]
        stream = _FailingStream(good_chunks, ConnectionError("stream died"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        llm = s.metadata.get("llm")
        assert llm is not None
        assert llm["provider"] == "openai"
        assert llm["model"] == "gpt-4.1"
        assert "partial output" in llm["output"]["text"]

    def test_partial_failure_populates_output_summary(self):
        """output_summary should contain partial text on failure."""
        good_chunks = [_chunk(content="hello "), _chunk(content="world")]
        stream = _FailingStream(good_chunks, RuntimeError("broken"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))
            except RuntimeError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        assert s.output_summary is not None
        assert s.output_summary.get("text") == "hello world"

    def test_partial_failure_populates_input_summary(self):
        """input_summary should be populated from request on failure."""
        good_chunks = [_chunk(content="hi")]
        stream = _FailingStream(good_chunks, RuntimeError("err"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(
                    model="gpt-4.1",
                    messages=[{"role": "user", "content": "test prompt"}],
                    stream=True,
                ))
            except RuntimeError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.input_summary is not None
        assert s.input_summary.get("model") == "gpt-4.1"

    def test_zero_output_failure_no_llm_metadata(self):
        """When no chunks observed, enrichment should not produce llm metadata."""
        stream = _FailingStream([], TimeoutError("immediate"))

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            try:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))
            except TimeoutError:
                pass

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "failed"
        assert s.metadata.get("provider") == "openai"
        assert "llm" not in s.metadata


# ---------------------------------------------------------------------------
# 11. Streaming steps preserve parent_step_id
# ---------------------------------------------------------------------------

class TestStreamingParentStep:

    def test_root_stream_has_no_parent(self):
        """A streaming call at root level has parent_step_id = None."""
        chunks = _text_chunks("hello")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        assert run.steps[0].parent_step_id is None

    def test_stream_inside_step_inherits_parent(self):
        """A streaming call inside a step context gets parent_step_id."""
        chunks = _text_chunks("nested")
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            with leer_step("outer", step_type="code") as outer:
                list(wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True))

        run = _traced(go)
        assert len(run.steps) == 2
        outer = run.steps[0]
        inner = run.steps[1]
        assert outer.parent_step_id is None
        assert inner.parent_step_id == outer.id


# ---------------------------------------------------------------------------
# 12. Create-call failure produces full stream metadata shape
# ---------------------------------------------------------------------------

class TestCreateCallFailureMetadata:

    def test_create_failure_has_full_stream_metadata(self):
        """If original_fn raises, stream metadata should have all standard keys."""
        client = MagicMock()
        client.chat.completions.create.side_effect = ConnectionError("refused")
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            try:
                wrapped.chat.completions.create(model="gpt-4.1", messages=[], stream=True)
            except ConnectionError:
                pass

        run = _traced(go)
        s = run.steps[0]
        sm = s.metadata.get("stream")
        assert sm is not None
        assert sm["is_stream"] is True
        assert sm["provider"] == "openai"
        assert sm["chunk_count"] == 0
        assert sm["termination"] == "failed"
        assert sm["truncated_chunks"] is False
        assert "time_to_first_chunk_ms" in sm
        assert "stream_duration_ms" in sm
        assert "captured_chunk_bytes" in sm
        assert "assembled_text_chars" in sm
        assert "assembled_tool_calls" in sm


# ---------------------------------------------------------------------------
# Step 1 hardening — partial-capture fallback when streaming enrich fails
# ---------------------------------------------------------------------------

class TestStep1OpenAIStreamingPartialCapture:
    """When `_enrich_step` raises during streaming finalization, the step
    must still get baseline metadata, a `capture: partial` flag, and
    both `llm_request` and `llm_response` artifacts so debugging
    context is preserved."""

    def test_streaming_enrich_failure_marks_partial(self):
        from unittest.mock import patch

        chunks = [_chunk(content="hello"), _chunk(content=" world", finish_reason="stop")]
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            with patch(
                "leer.integrations.openai._enrich_step",
                side_effect=RuntimeError("boom"),
            ):
                list(wrapped.chat.completions.create(
                    model="gpt-4.1", messages=[], stream=True,
                ))

        run = _traced(go)
        s = run.steps[0]
        assert s.status == "completed"
        assert s.metadata.get("capture") == "partial"
        assert s.metadata.get("provider") == "openai"
        assert s.metadata.get("model") == "gpt-4.1"

    def test_streaming_enrich_failure_attaches_request_and_response(self):
        from unittest.mock import patch

        chunks = [_chunk(content="hi"), _chunk(content="!", finish_reason="stop")]
        stream = _FakeStream(chunks)

        def go(run):
            wrapped = wrap_openai_client(_fake_streaming_client(stream))
            with patch(
                "leer.integrations.openai._enrich_step",
                side_effect=RuntimeError("boom"),
            ):
                list(wrapped.chat.completions.create(
                    model="gpt-4.1", messages=[], stream=True,
                ))

        run = _traced(go)
        req_arts = [a for a in run.artifacts if a.artifact_type == "llm_request"]
        resp_arts = [a for a in run.artifacts if a.artifact_type == "llm_response"]
        assert len(req_arts) == 1
        assert len(resp_arts) == 1
        # The assembled response_dict carries the streamed text in the chat shape.
        resp_data = resp_arts[0].inline_data
        assert resp_data["choices"][0]["message"]["content"] == "hi!"
