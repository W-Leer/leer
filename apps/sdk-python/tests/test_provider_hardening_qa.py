"""Step 4 — Provider Hardening QA validation matrix.

This module is the executable form of the Step 4 QA matrix. It drives the
*real* OpenAI / Anthropic wrappers (no network, fixture-based) across every
scenario in the QA plan and asserts execution-record quality for each:

  - request capture        (``llm_request`` artifact)
  - response capture       (``llm_response`` / ``llm_stream`` artifact)
  - normalized output      (``metadata.llm`` canonical shape)
  - metadata usage         (``metadata.usage`` triplet + cached_tokens)
  - tool-call capture      (``output.tool_calls`` + ``tool_call`` artifacts)
  - stream artifacts        (``llm_stream`` + stream metadata on streamed steps)
  - step status            (``completed`` / ``failed`` matching reality)
  - partial-capture behavior (``metadata.capture == "partial"`` fallback)

Two classes (``TestGapAnthropicRefusal`` and
``TestGapOpenAIStreamingModelFidelity``) assert the *desired* post-hardening
behavior for the two gaps discovered during the Step 4 code review. They are
the regression tests for the Step 4 fixes.

All scenarios run offline via fakes mirroring the patterns already used in
``test_openai_streaming.py`` / ``test_streaming_step2.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from leer.context import reset_context, set_current_run
from leer.integrations.anthropic import wrap_anthropic_client
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun


# ---------------------------------------------------------------------------
# Shared harness
# ---------------------------------------------------------------------------

def _traced(fn: Any) -> TraceRun:
    """Run ``fn(run)`` inside a fake active trace and return the captured run."""
    run = TraceRun(workflow_name="provider-hardening-qa")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


class _FakeStream:
    """Iterable yielding events in order; supports for-loop + context manager.

    An ``Exception`` instance in the sequence is raised when reached, to model
    a mid-stream provider failure.
    """

    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)
        self._index = 0

    def __iter__(self) -> "_FakeStream":
        return self

    def __next__(self) -> Any:
        if self._index >= len(self._events):
            raise StopIteration
        ev = self._events[self._index]
        self._index += 1
        if isinstance(ev, Exception):
            raise ev
        return ev

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def _openai_client(*, chat=None, responses=None, stream=None) -> MagicMock:
    client = MagicMock()
    if chat is not None:
        client.chat.completions.create.return_value = chat
    if responses is not None:
        client.responses.create.return_value = responses
    if stream is not None:
        # Caller decides which surface returns the stream.
        pass
    return client


def _anthropic_client(result: Any) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = result
    return client


def _step(run: TraceRun):
    assert len(run.steps) == 1, f"expected exactly one step, got {len(run.steps)}"
    return run.steps[0]


def _artifact_types(run: TraceRun, step) -> list[str]:
    return [a.artifact_type for a in run.artifacts if a.step_id == step.id]


def _assert_full_capture(step, *, provider: str, streamed: bool) -> dict[str, Any]:
    """Assert the universal execution-record-quality invariants for a
    fully-enriched (non-partial) LLM step. Returns the canonical ``llm`` dict.
    """
    assert step.step_type == "llm"
    assert step.status == "completed", f"status={step.status}"
    # Not a degraded capture.
    assert step.metadata.get("capture") != "partial"
    # Baseline metadata.
    assert step.metadata.get("provider") == provider
    assert step.metadata.get("model")
    # Canonical normalized output present.
    llm = step.metadata.get("llm")
    assert isinstance(llm, dict) and llm.get("provider") == provider
    # Usage triplet exists with the cross-provider cached_tokens key.
    usage = step.metadata.get("usage")
    assert isinstance(usage, dict)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"):
        assert key in usage, f"missing usage key {key}"
    # Streamed steps carry stream metadata; one-shot steps do not.
    if streamed:
        assert step.metadata.get("stream", {}).get("is_stream") is True
    return llm


# ===========================================================================
# A. OpenAI Chat Completions — non-streaming
# ===========================================================================

class TestOpenAIChatNonStreaming:

    def _run(self, response: dict[str, Any], **req: Any) -> TraceRun:
        def go(run):
            wrapped = wrap_openai_client(_openai_client(chat=response))
            wrapped.chat.completions.create(
                model="gpt-4.1",
                messages=req.get("messages", [{"role": "user", "content": "hi"}]),
                **{k: v for k, v in req.items() if k != "messages"},
            )
        return _traced(go)

    def test_simple_text(self):
        resp = {
            "id": "chatcmpl-1", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        assert llm["output"]["text"] == "Hello!"
        assert "llm_request" in _artifact_types(run, s)
        assert "llm_response" in _artifact_types(run, s)
        assert s.metadata["usage"]["total_tokens"] == 12

    def test_single_tool_call(self):
        resp = {
            "id": "chatcmpl-2", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_a", "type": "function",
                                "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}}],
            }, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["name"] == "get_weather"
        assert tcs[0]["arguments"] == {"city": "Paris"}
        assert "tool_call" in _artifact_types(run, s)

    def test_multiple_tool_calls(self):
        resp = {
            "id": "chatcmpl-3", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": None,
                "tool_calls": [
                    {"id": "call_a", "type": "function",
                     "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}},
                    {"id": "call_b", "type": "function",
                     "function": {"name": "get_time", "arguments": '{"tz":"UTC"}'}},
                ],
            }, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 25, "total_tokens": 55},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        names = [tc["name"] for tc in llm["output"]["tool_calls"]]
        assert names == ["get_weather", "get_time"]
        # One tool_call artifact per call.
        assert _artifact_types(run, s).count("tool_call") == 2

    def test_refusal(self):
        resp = {
            "id": "chatcmpl-4", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": None,
                "refusal": "I can't help with that.",
            }, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        # Step 1 dual-representation contract.
        assert llm["meta"]["refusal"] == "I can't help with that."
        assert llm["output"]["text"].startswith("[refusal]")

    def test_empty_output_with_usage_is_visible(self):
        resp = {
            "id": "chatcmpl-5", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 0, "total_tokens": 8},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        assert llm["output"]["text"] is None
        # Empty completion is still a real, inspectable record.
        assert s.metadata["usage"]["total_tokens"] == 8


# ===========================================================================
# B. OpenAI Chat Completions — streaming
# ===========================================================================

def _chat_chunk(*, content=None, refusal=None, tool_calls=None,
                finish_reason=None, usage=None, model="gpt-4.1",
                chunk_id="chatcmpl-stream") -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if refusal is not None:
        delta["refusal"] = refusal
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    d: dict[str, Any] = {
        "id": chunk_id, "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        d["usage"] = usage
    return d


def _run_chat_stream(chunks: list[Any], **req: Any) -> TraceRun:
    client = MagicMock()
    client.chat.completions.create.return_value = _FakeStream(chunks)
    del client.responses  # force chat-completions detection

    def go(run):
        wrapped = wrap_openai_client(client)
        list(wrapped.chat.completions.create(
            model=req.get("model", "gpt-4.1"),
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        ))
    return _traced(go)


class TestOpenAIChatStreaming:

    def test_text_stream(self):
        chunks = [
            _chat_chunk(content="Hel"),
            _chat_chunk(content="lo"),
            _chat_chunk(finish_reason="stop",
                        usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}),
        ]
        run = _run_chat_stream(chunks)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        assert llm["output"]["text"] == "Hello"
        assert "llm_stream" in _artifact_types(run, s)
        assert s.metadata["stream"]["chunk_count"] >= 3

    def test_tool_call_stream(self):
        chunks = [
            _chat_chunk(tool_calls=[{"index": 0, "id": "call_a",
                                     "function": {"name": "get_weather", "arguments": ""}}]),
            _chat_chunk(tool_calls=[{"index": 0, "function": {"arguments": '{"city":'}}]),
            _chat_chunk(tool_calls=[{"index": 0, "function": {"arguments": '"Paris"}'}}]),
            _chat_chunk(finish_reason="tool_calls"),
        ]
        run = _run_chat_stream(chunks)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["name"] == "get_weather"
        assert tcs[0]["arguments"] == {"city": "Paris"}
        assert "llm_stream" in _artifact_types(run, s)

    def test_refusal_stream(self):
        chunks = [
            _chat_chunk(refusal="I cannot "),
            _chat_chunk(refusal="help with that."),
            _chat_chunk(finish_reason="stop"),
        ]
        run = _run_chat_stream(chunks)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        assert llm["meta"]["refusal"] == "I cannot help with that."
        assert llm["output"]["text"].startswith("[refusal]")

    def test_mid_stream_failure_marks_failed_and_preserves_partial(self):
        chunks = [
            _chat_chunk(content="partial"),
            RuntimeError("connection reset"),
        ]
        run = _run_chat_stream_failing(chunks)
        s = _step(run)
        assert s.status == "failed"
        # Stream artifact still attached; partial text was captured.
        assert "llm_stream" in _artifact_types(run, s)
        assert s.error_summary is not None


def _run_chat_stream_failing(chunks: list[Any]) -> TraceRun:
    client = MagicMock()
    client.chat.completions.create.return_value = _FakeStream(chunks)
    del client.responses

    def go(run):
        wrapped = wrap_openai_client(client)
        try:
            list(wrapped.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": "hi"}],
                stream=True,
            ))
        except RuntimeError:
            pass
    return _traced(go)


# ===========================================================================
# C. OpenAI Responses — non-streaming
# ===========================================================================

class TestOpenAIResponsesNonStreaming:

    def _run(self, response: dict[str, Any]) -> TraceRun:
        def go(run):
            wrapped = wrap_openai_client(_openai_client(responses=response))
            wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "hi"}],
            )
        return _traced(go)

    def test_text_output(self):
        resp = {
            "id": "resp_1", "object": "response", "status": "completed", "model": "gpt-4.1",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Hi there!"}]}],
            "usage": {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        assert llm["output"]["text"] == "Hi there!"
        assert "llm_response" in _artifact_types(run, s)

    def test_tool_call(self):
        resp = {
            "id": "resp_2", "object": "response", "status": "completed", "model": "gpt-4.1",
            "output": [{"type": "function_call", "call_id": "call_x", "name": "get_weather",
                        "arguments": '{"city":"Paris"}'}],
            "usage": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["id"] == "call_x"
        assert "tool_call" in _artifact_types(run, s)

    def test_refusal(self):
        resp = {
            "id": "resp_3", "object": "response", "status": "completed", "model": "gpt-4.1",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "refusal", "refusal": "I won't do that."}]}],
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=False)
        assert llm["meta"]["refusal"] == "I won't do that."
        assert llm["output"]["text"].startswith("[refusal]")


# ===========================================================================
# D. OpenAI Responses — streaming
# ===========================================================================

def _resp_event(event_type: str, **kwargs: Any) -> dict[str, Any]:
    payload = {"type": event_type}
    payload.update(kwargs)
    return payload


def _run_responses_stream(events: list[Any], **req: Any) -> TraceRun:
    client = MagicMock()
    client.responses.create.return_value = _FakeStream(events)

    def go(run):
        wrapped = wrap_openai_client(client)
        list(wrapped.responses.create(
            model=req.get("model", "gpt-4.1"),
            input=[{"role": "user", "content": "hi"}],
            stream=True,
        ))
    return _traced(go)


class TestOpenAIResponsesStreaming:

    def test_text_stream(self):
        events = [
            _resp_event("response.created", response={"id": "resp_1", "model": "gpt-4.1"}),
            _resp_event("response.output_text.delta", output_index=0, delta="Hello"),
            _resp_event("response.output_text.delta", output_index=0, delta=" world"),
            _resp_event("response.completed", response={
                "id": "resp_1", "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12,
                          "input_tokens_details": {"cached_tokens": 4}},
            }),
        ]
        run = _run_responses_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        assert llm["output"]["text"] == "Hello world"
        assert s.metadata["usage"]["cached_tokens"] == 4
        assert "llm_stream" in _artifact_types(run, s)

    def test_tool_call_stream(self):
        events = [
            _resp_event("response.created", response={"id": "resp_2"}),
            _resp_event("response.output_item.added", output_index=0, item={
                "id": "fc_1", "type": "function_call", "name": "get_weather",
                "call_id": "call_xyz", "arguments": ""}),
            _resp_event("response.function_call_arguments.delta", output_index=0, delta='{"city":'),
            _resp_event("response.function_call_arguments.delta", output_index=0, delta='"Paris"}'),
            _resp_event("response.completed", response={
                "id": "resp_2", "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15}}),
        ]
        run = _run_responses_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["id"] == "call_xyz"
        assert tcs[0]["arguments"] == {"city": "Paris"}

    def test_refusal_stream(self):
        events = [
            _resp_event("response.created", response={"id": "resp_3"}),
            _resp_event("response.refusal.delta", output_index=0, delta="I cannot "),
            _resp_event("response.refusal.delta", output_index=0, delta="help with that."),
            _resp_event("response.completed", response={
                "id": "resp_3", "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}}),
        ]
        run = _run_responses_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="openai", streamed=True)
        assert llm["meta"]["refusal"] == "I cannot help with that."
        assert llm["output"]["text"].startswith("[refusal]")


# ===========================================================================
# E. Anthropic — non-streaming
# ===========================================================================

class TestAnthropicNonStreaming:

    def _run(self, response: dict[str, Any]) -> TraceRun:
        def go(run):
            wrapped = wrap_anthropic_client(_anthropic_client(response))
            wrapped.messages.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=200,
            )
        return _traced(go)

    def test_simple_text(self):
        resp = {
            "id": "msg_1", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 3},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=False)
        assert llm["output"]["text"] == "Hello!"
        # Anthropic total is computed (no provider-supplied total).
        assert s.metadata["usage"]["total_tokens"] == 13
        assert "llm_response" in _artifact_types(run, s)

    def test_tool_use(self):
        resp = {
            "id": "msg_2", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "get_weather",
                         "input": {"city": "Paris"}}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 8},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=False)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["arguments"] == {"city": "Paris"}
        assert "tool_call" in _artifact_types(run, s)

    def test_thinking(self):
        resp = {
            "id": "msg_3", "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "thinking", "thinking": "Let me reason about this.", "signature": "sig"},
                {"type": "text", "text": "The answer is 42."},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 15, "output_tokens": 12},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=False)
        blocks = llm["output"]["content_blocks"]
        thinking = [b for b in blocks if b.get("type") == "thinking"]
        assert len(thinking) == 1 and thinking[0]["thinking"] == "Let me reason about this."
        # Design Principle 7: thinking is NOT mirrored into output.text.
        assert llm["output"]["text"] == "The answer is 42."
        assert "Let me reason" not in (llm["output"]["text"] or "")

    def test_redacted_thinking(self):
        resp = {
            "id": "msg_4", "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "redacted_thinking", "data": "encrypted-blob"},
                {"type": "text", "text": "Done."},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 9, "output_tokens": 4},
        }
        run = self._run(resp)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=False)
        redacted = [b for b in llm["output"]["content_blocks"] if b.get("type") == "redacted_thinking"]
        assert len(redacted) == 1

    def test_cached_tokens(self):
        resp = {
            "id": "msg_5", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "cached"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 5, "cache_read_input_tokens": 80},
        }
        run = self._run(resp)
        s = _step(run)
        _assert_full_capture(s, provider="anthropic", streamed=False)
        assert s.metadata["usage"]["cached_tokens"] == 80


# ===========================================================================
# F. Anthropic — streaming
# ===========================================================================

def _anth_msg_start(*, msg_id="msg_s", model="claude-sonnet-4-20250514",
                    input_tokens=10, cache_read=None) -> dict[str, Any]:
    usage: dict[str, Any] = {"input_tokens": input_tokens}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
    return {"type": "message_start",
            "message": {"id": msg_id, "model": model, "usage": usage}}


def _anth_msg_delta(*, output_tokens=5, stop_reason="end_turn") -> dict[str, Any]:
    return {"type": "message_delta", "delta": {"stop_reason": stop_reason},
            "usage": {"output_tokens": output_tokens}}


def _anth_block_start(index: int, block: dict[str, Any]) -> dict[str, Any]:
    return {"type": "content_block_start", "index": index, "content_block": block}


def _anth_delta(index: int, delta: dict[str, Any]) -> dict[str, Any]:
    return {"type": "content_block_delta", "index": index, "delta": delta}


def _anth_block_stop(index: int) -> dict[str, Any]:
    return {"type": "content_block_stop", "index": index}


def _run_anth_stream(events: list[Any]) -> TraceRun:
    client = MagicMock()
    client.messages.create.return_value = _FakeStream(events)

    def go(run):
        wrapped = wrap_anthropic_client(client)
        list(wrapped.messages.create(
            model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}],
            max_tokens=200, stream=True,
        ))
    return _traced(go)


class TestAnthropicStreaming:

    def test_text_stream(self):
        events = [
            _anth_msg_start(),
            _anth_block_start(0, {"type": "text", "text": ""}),
            _anth_delta(0, {"type": "text_delta", "text": "Hello"}),
            _anth_delta(0, {"type": "text_delta", "text": " world"}),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=4),
            {"type": "message_stop"},
        ]
        run = _run_anth_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=True)
        assert llm["output"]["text"] == "Hello world"
        assert "llm_stream" in _artifact_types(run, s)

    def test_thinking_stream(self):
        events = [
            _anth_msg_start(),
            _anth_block_start(0, {"type": "thinking", "thinking": ""}),
            _anth_delta(0, {"type": "thinking_delta", "thinking": "Reasoning..."}),
            _anth_delta(0, {"type": "signature_delta", "signature": "sig"}),
            _anth_block_stop(0),
            _anth_block_start(1, {"type": "text", "text": ""}),
            _anth_delta(1, {"type": "text_delta", "text": "Answer"}),
            _anth_block_stop(1),
            _anth_msg_delta(output_tokens=8),
            {"type": "message_stop"},
        ]
        run = _run_anth_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=True)
        blocks = llm["output"]["content_blocks"]
        thinking = [b for b in blocks if b.get("type") == "thinking"]
        assert len(thinking) == 1 and thinking[0]["thinking"] == "Reasoning..."
        # Parity: thinking stays out of output.text on the streaming path too.
        assert llm["output"]["text"] == "Answer"

    def test_tool_use_stream(self):
        events = [
            _anth_msg_start(),
            _anth_block_start(0, {"type": "tool_use", "id": "toolu_1", "name": "get_weather"}),
            _anth_delta(0, {"type": "input_json_delta", "partial_json": '{"city":'}),
            _anth_delta(0, {"type": "input_json_delta", "partial_json": '"Paris"}'}),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=6, stop_reason="tool_use"),
            {"type": "message_stop"},
        ]
        run = _run_anth_stream(events)
        s = _step(run)
        llm = _assert_full_capture(s, provider="anthropic", streamed=True)
        tcs = llm["output"]["tool_calls"]
        assert len(tcs) == 1 and tcs[0]["name"] == "get_weather"
        assert tcs[0]["arguments"] == {"city": "Paris"}
        assert "tool_call" in _artifact_types(run, s)


# ===========================================================================
# G. Error handling + partial-capture behavior (both providers)
# ===========================================================================

class TestErrorAndPartialCapture:

    def test_openai_request_exception_marks_failed(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = ConnectionError("boom")
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            try:
                wrapped.chat.completions.create(
                    model="gpt-4.1", messages=[{"role": "user", "content": "hi"}])
            except ConnectionError:
                pass

        run = _traced(go)
        s = _step(run)
        assert s.status == "failed"
        assert s.metadata.get("error_type") == "ConnectionError"
        # Request preserved even on failure.
        assert "llm_request" in _artifact_types(run, s)
        # Failed calls are NOT tagged partial — they are real failures.
        assert s.metadata.get("capture") != "partial"

    def test_anthropic_request_exception_marks_failed(self):
        client = MagicMock()
        client.messages.create.side_effect = ConnectionError("boom")

        def go(run):
            wrapped = wrap_anthropic_client(client)
            try:
                wrapped.messages.create(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": "hi"}], max_tokens=10)
            except ConnectionError:
                pass

        run = _traced(go)
        s = _step(run)
        assert s.status == "failed"
        assert s.metadata.get("error_type") == "ConnectionError"
        assert "llm_request" in _artifact_types(run, s)

    def test_openai_enrich_failure_falls_back_to_partial(self):
        resp = {
            "id": "chatcmpl-p", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        def go(run):
            wrapped = wrap_openai_client(_openai_client(chat=resp))
            with patch("leer.integrations.openai.normalize_openai",
                       side_effect=ValueError("normalize blew up")):
                wrapped.chat.completions.create(
                    model="gpt-4.1", messages=[{"role": "user", "content": "hi"}])

        run = _traced(go)
        s = _step(run)
        # Step 1 contract: degraded observability, not failed execution.
        assert s.status == "completed"
        assert s.metadata.get("capture") == "partial"
        assert s.metadata.get("provider") == "openai"
        assert "llm_request" in _artifact_types(run, s)
        # Raw response preserved for debugging.
        assert "llm_response" in _artifact_types(run, s)

    def test_anthropic_enrich_failure_falls_back_to_partial(self):
        resp = {
            "id": "msg_p", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

        def go(run):
            wrapped = wrap_anthropic_client(_anthropic_client(resp))
            with patch("leer.integrations.anthropic.normalize_anthropic",
                       side_effect=ValueError("normalize blew up")):
                wrapped.messages.create(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": "hi"}], max_tokens=10)

        run = _traced(go)
        s = _step(run)
        assert s.status == "completed"
        assert s.metadata.get("capture") == "partial"
        assert s.metadata.get("provider") == "anthropic"
        assert "llm_request" in _artifact_types(run, s)
        assert "llm_response" in _artifact_types(run, s)


# ===========================================================================
# GAP G1 — Anthropic refusal (stop_reason == "refusal") -> meta.refusal
# ===========================================================================

class TestGapAnthropicRefusal:
    """Anthropic signals refusals via ``stop_reason == "refusal"`` rather than
    a content block. For cross-provider parity with OpenAI (and so the
    refusal badge / compare insight fire), the refusal must surface in
    ``meta.refusal``. Regression test for the Step 4 fix.
    """

    def test_non_streaming_refusal_populates_meta_refusal(self):
        resp = {
            "id": "msg_r", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "I can't help with that request."}],
            "stop_reason": "refusal",
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }

        def go(run):
            wrapped = wrap_anthropic_client(_anthropic_client(resp))
            wrapped.messages.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "..."}], max_tokens=100)

        run = _traced(go)
        s = _step(run)
        llm = s.metadata["llm"]
        assert llm["meta"]["refusal"] == "I can't help with that request."

    def test_non_streaming_refusal_without_text_inlines_marker(self):
        resp = {
            "id": "msg_r2", "model": "claude-sonnet-4-20250514",
            "content": [],
            "stop_reason": "refusal",
            "usage": {"input_tokens": 5, "output_tokens": 0},
        }

        def go(run):
            wrapped = wrap_anthropic_client(_anthropic_client(resp))
            wrapped.messages.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "..."}], max_tokens=100)

        run = _traced(go)
        s = _step(run)
        llm = s.metadata["llm"]
        # meta.refusal set even when the provider returned no explanation text.
        assert llm["meta"]["refusal"]
        # Dual-representation: inline marker when there is no other content.
        assert (llm["output"]["text"] or "").startswith("[refusal]")

    def test_streaming_refusal_populates_meta_refusal(self):
        events = [
            _anth_msg_start(),
            _anth_block_start(0, {"type": "text", "text": ""}),
            _anth_delta(0, {"type": "text_delta", "text": "I can't assist with that."}),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=7, stop_reason="refusal"),
            {"type": "message_stop"},
        ]
        run = _run_anth_stream(events)
        s = _step(run)
        llm = s.metadata["llm"]
        # The fix lives in normalize_anthropic keyed on stop_reason, so the
        # streaming path inherits it via the round-tripped response dict.
        assert llm["meta"]["refusal"] == "I can't assist with that."

    def test_end_turn_does_not_set_refusal(self):
        resp = {
            "id": "msg_ok", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "Sure, here you go."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }

        def go(run):
            wrapped = wrap_anthropic_client(_anthropic_client(resp))
            wrapped.messages.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}], max_tokens=100)

        run = _traced(go)
        s = _step(run)
        assert s.metadata["llm"]["meta"]["refusal"] is None


# ===========================================================================
# GAP G2 — OpenAI streaming preserves the provider-resolved model
# ===========================================================================

class TestGapOpenAIStreamingModelFidelity:
    """Non-streaming OpenAI uses ``response.model`` (the resolved snapshot);
    Anthropic streaming was fixed in Step 1 to do the same. OpenAI streaming
    must also record the model the provider reported on the wire, not the
    requested alias. Regression test for the Step 4 fix.
    """

    def test_chat_stream_uses_resolved_model(self):
        chunks = [
            _chat_chunk(content="hi", model="gpt-4.1-2025-04-14"),
            _chat_chunk(finish_reason="stop", model="gpt-4.1-2025-04-14"),
        ]
        run = _run_chat_stream(chunks, model="gpt-4.1")
        s = _step(run)
        assert s.metadata.get("model") == "gpt-4.1-2025-04-14"
        assert s.metadata["llm"]["model"] == "gpt-4.1-2025-04-14"

    def test_responses_stream_uses_resolved_model(self):
        events = [
            _resp_event("response.created",
                        response={"id": "resp_m", "model": "gpt-4.1-2025-04-14"}),
            _resp_event("response.output_text.delta", output_index=0, delta="hi"),
            _resp_event("response.completed", response={
                "id": "resp_m", "status": "completed", "model": "gpt-4.1-2025-04-14",
                "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}}),
        ]
        run = _run_responses_stream(events, model="gpt-4.1")
        s = _step(run)
        assert s.metadata.get("model") == "gpt-4.1-2025-04-14"
        assert s.metadata["llm"]["model"] == "gpt-4.1-2025-04-14"

    def test_chat_stream_falls_back_to_request_model_when_absent(self):
        # When the stream carries no model, the requested model is the
        # correct fallback (parity with the Anthropic ctx-less path).
        chunks = [
            {"id": "c1", "choices": [{"index": 0, "delta": {"content": "hi"},
                                      "finish_reason": None}]},
            {"id": "c1", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        run = _run_chat_stream(chunks, model="gpt-4.1")
        s = _step(run)
        assert s.metadata.get("model") == "gpt-4.1"
