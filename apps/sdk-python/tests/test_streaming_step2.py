"""Step 2 streaming tests:

  - Fix #1: OpenAI Responses-API streaming canonical parity (request
    routed through ``responses.create(stream=True)`` now produces a
    canonically-normalized step instead of a silent empty assembled
    output). Bonus: chat-completions ``delta.refusal`` no longer dropped.
  - Fix #2: Anthropic ``thinking`` / ``redacted_thinking`` blocks are
    captured in streaming and round-trip through the assembled response.
  - Fix #5: Anthropic streaming captures ``cache_read_input_tokens`` from
    ``message_start.message.usage`` and ``message_delta.usage`` so the
    cached_tokens canonical field (Fix #3) lands on streamed steps too.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from leer.context import set_current_run, reset_context
from leer.integrations.anthropic import wrap_anthropic_client
from leer.integrations.openai import wrap_openai_client
from leer.integrations.streaming import StreamCollector
from leer.models import TraceRun


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

class _FakeStream:
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
        return ev

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def _traced(fn):
    run = TraceRun(workflow_name="step2-streaming")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


def _fake_openai_responses_client(stream: Any) -> MagicMock:
    """Fake OpenAI client that exposes both ``chat`` and ``responses``."""
    client = MagicMock()
    # ``responses.create`` returns the streaming iterable.
    client.responses.create.return_value = stream
    return client


def _fake_anthropic_client(stream: Any) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = stream
    return client


# ---------------------------------------------------------------------------
# Fix #1 — OpenAI Responses-API streaming canonical parity
# ---------------------------------------------------------------------------

def _resp_event(event_type: str, **kwargs: Any) -> dict[str, Any]:
    """Build a Responses-API streaming event as a plain dict."""
    payload = {"type": event_type}
    payload.update(kwargs)
    return payload


class TestOpenAIResponsesStreamingText:

    def _events(self) -> list[dict[str, Any]]:
        return [
            _resp_event("response.created", response={"id": "resp_1"}),
            _resp_event("response.output_item.added", output_index=0, item={
                "id": "msg_1", "type": "message", "role": "assistant", "content": [],
            }),
            _resp_event("response.output_text.delta", output_index=0, content_index=0, delta="Hello"),
            _resp_event("response.output_text.delta", output_index=0, content_index=0, delta=" world"),
            _resp_event("response.output_text.done", output_index=0, content_index=0, text="Hello world"),
            _resp_event("response.completed", response={
                "id": "resp_1",
                "status": "completed",
                "usage": {
                    "input_tokens": 10, "output_tokens": 2, "total_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 4},
                },
            }),
        ]

    def test_text_stream_assembles_into_completed_step(self):
        stream = _FakeStream(self._events())

        def go(run):
            wrapped = wrap_openai_client(_fake_openai_responses_client(stream))
            result = wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "hi"}],
                stream=True,
            )
            list(result)

        run = _traced(go)
        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.status == "completed"
        # Canonical text reaches the summary, proving the events were
        # processed by the Responses-shape parser (the chat parser would
        # have produced an empty step).
        assert s.output_summary.get("text") == "Hello world"

    def test_responses_streaming_metadata_provider_and_model(self):
        stream = _FakeStream(self._events())

        def go(run):
            wrapped = wrap_openai_client(_fake_openai_responses_client(stream))
            list(wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "hi"}],
                stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        assert s.metadata.get("provider") == "openai"
        assert s.metadata.get("model") == "gpt-4.1"
        # The ``llm`` block is the canonical normalized payload — its
        # presence proves _enrich_step ran (not the partial-capture path).
        assert "llm" in s.metadata
        assert s.metadata["llm"]["provider"] == "openai"

    def test_responses_streaming_picks_up_usage_and_cached_tokens(self):
        stream = _FakeStream(self._events())

        def go(run):
            wrapped = wrap_openai_client(_fake_openai_responses_client(stream))
            list(wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "hi"}],
                stream=True,
            ))

        run = _traced(go)
        usage = run.steps[0].metadata.get("usage", {})
        assert usage.get("prompt_tokens") == 10
        assert usage.get("completion_tokens") == 2
        assert usage.get("total_tokens") == 12
        # Fix #1 + Fix #3 together: cached tokens from the Responses-API
        # streaming event reach the canonical metadata.
        assert usage.get("cached_tokens") == 4


class TestOpenAIResponsesStreamingToolCall:

    def _events(self) -> list[dict[str, Any]]:
        return [
            _resp_event("response.created", response={"id": "resp_2"}),
            _resp_event("response.output_item.added", output_index=0, item={
                "id": "fc_1",
                "type": "function_call",
                "name": "get_weather",
                "call_id": "call_xyz",
                "arguments": "",
            }),
            _resp_event("response.function_call_arguments.delta", output_index=0, delta='{"city":'),
            _resp_event("response.function_call_arguments.delta", output_index=0, delta='"Paris"}'),
            _resp_event("response.function_call_arguments.done", output_index=0,
                        arguments='{"city":"Paris"}'),
            _resp_event("response.completed", response={
                "id": "resp_2",
                "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
            }),
        ]

    def test_function_call_streaming_assembles_and_normalizes(self):
        stream = _FakeStream(self._events())

        def go(run):
            wrapped = wrap_openai_client(_fake_openai_responses_client(stream))
            list(wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "weather?"}],
                stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        # Canonical normalized tool_calls land in metadata.llm.output.
        llm = s.metadata.get("llm") or {}
        output = llm.get("output") or {}
        tool_calls = output.get("tool_calls") or []
        assert len(tool_calls) == 1
        tc = tool_calls[0]
        assert tc["name"] == "get_weather"
        # call_id from output_item.added is preserved (Responses API).
        assert tc["id"] == "call_xyz"
        # Argument deltas are stitched together and parsed back into a dict.
        assert tc["arguments"] == {"city": "Paris"}


class TestOpenAIResponsesStreamingRefusal:

    def _events(self) -> list[dict[str, Any]]:
        return [
            _resp_event("response.created", response={"id": "resp_3"}),
            _resp_event("response.refusal.delta", output_index=0, content_index=0, delta="I cannot "),
            _resp_event("response.refusal.delta", output_index=0, content_index=0, delta="help with that."),
            _resp_event("response.completed", response={
                "id": "resp_3",
                "status": "completed",
                "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
            }),
        ]

    def test_refusal_streaming_populates_meta_refusal(self):
        stream = _FakeStream(self._events())

        def go(run):
            wrapped = wrap_openai_client(_fake_openai_responses_client(stream))
            list(wrapped.responses.create(
                model="gpt-4.1",
                input=[{"role": "user", "content": "..."}],
                stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        llm = s.metadata.get("llm") or {}
        meta = llm.get("meta") or {}
        # Step 1's contract: refusal text exposed in meta.refusal.
        assert meta.get("refusal") == "I cannot help with that."
        # Step 1's contract: refusal text also inlined into output.text.
        assert (llm.get("output") or {}).get("text", "").startswith("[refusal]")


class TestOpenAIChatStreamingRefusalDelta:
    """Bonus fix shipped alongside #1: chat-completions ``delta.refusal``
    no longer dropped during streaming."""

    def _chunk(self, *, content=None, refusal=None, finish_reason=None) -> dict:
        delta: dict = {}
        if content is not None:
            delta["content"] = content
        if refusal is not None:
            delta["refusal"] = refusal
        return {
            "id": "chatcmpl-ref",
            "model": "gpt-4.1",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }

    def test_streamed_refusal_lands_in_meta_refusal(self):
        chunks = [
            self._chunk(refusal="I cannot "),
            self._chunk(refusal="answer that."),
            self._chunk(finish_reason="stop"),
        ]
        stream = _FakeStream(chunks)

        client = MagicMock()
        client.chat.completions.create.return_value = stream
        del client.responses

        def go(run):
            wrapped = wrap_openai_client(client)
            list(wrapped.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": "..."}],
                stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        llm = s.metadata.get("llm") or {}
        meta = llm.get("meta") or {}
        assert meta.get("refusal") == "I cannot answer that."
        assert (llm.get("output") or {}).get("text", "").startswith("[refusal]")


# ---------------------------------------------------------------------------
# Fix #2 — Anthropic thinking blocks captured in streaming
# ---------------------------------------------------------------------------

def _anth_msg_start(*, msg_id="msg_th", model="claude-sonnet-4-20250514",
                    input_tokens=10, cache_read=None) -> dict:
    usage: dict = {"input_tokens": input_tokens}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
    return {
        "type": "message_start",
        "message": {"id": msg_id, "model": model, "usage": usage},
    }


def _anth_msg_delta(*, output_tokens=5, stop_reason="end_turn",
                    cache_read=None) -> dict:
    usage: dict = {"output_tokens": output_tokens}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
    return {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason},
        "usage": usage,
    }


def _anth_block_start_thinking(index: int, *, redacted: bool = False) -> dict:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "redacted_thinking" if redacted else "thinking",
            "thinking": "" if not redacted else None,
        },
    }


def _anth_thinking_delta(text: str, index: int = 0) -> dict:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "thinking_delta", "thinking": text},
    }


def _anth_signature_delta(sig: str, index: int = 0) -> dict:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "signature_delta", "signature": sig},
    }


def _anth_block_start_text(index: int) -> dict:
    return {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "text", "text": ""},
    }


def _anth_text_delta(text: str, index: int) -> dict:
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text},
    }


def _anth_block_stop(index: int) -> dict:
    return {"type": "content_block_stop", "index": index}


def _anth_msg_stop() -> dict:
    return {"type": "message_stop"}


class TestAnthropicStreamingThinking:

    def test_thinking_block_captured_in_assembled_output(self):
        events = [
            _anth_msg_start(),
            _anth_block_start_thinking(0),
            _anth_thinking_delta("Let me ", 0),
            _anth_thinking_delta("think about it.", 0),
            _anth_signature_delta("sig_payload", 0),
            _anth_block_stop(0),
            _anth_block_start_text(1),
            _anth_text_delta("Final answer.", 1),
            _anth_block_stop(1),
            _anth_msg_delta(stop_reason="end_turn", output_tokens=8),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        # The non-streaming canonical content_blocks include a "thinking"
        # block. Streaming must now match.
        llm = s.metadata.get("llm") or {}
        blocks = (llm.get("output") or {}).get("content_blocks") or []
        thinking_blocks = [b for b in blocks if b.get("type") == "thinking"]
        assert len(thinking_blocks) == 1
        assert thinking_blocks[0]["thinking"] == "Let me think about it."

    def test_redacted_thinking_block_preserved_as_placeholder(self):
        events = [
            _anth_msg_start(),
            _anth_block_start_thinking(0, redacted=True),
            _anth_block_stop(0),
            _anth_block_start_text(1),
            _anth_text_delta("ok", 1),
            _anth_block_stop(1),
            _anth_msg_delta(),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        blocks = ((s.metadata.get("llm") or {}).get("output") or {}).get("content_blocks") or []
        # Redacted-thinking maps to a typed placeholder, mirroring
        # non-streaming behavior.
        redacted = [b for b in blocks if b.get("type") == "redacted_thinking"]
        assert len(redacted) == 1

    def test_thinking_text_does_not_leak_into_output_text(self):
        # Output text should be the assistant text only — thinking content
        # is structurally separate. Compare/run-detail rely on this.
        events = [
            _anth_msg_start(),
            _anth_block_start_thinking(0),
            _anth_thinking_delta("internal reasoning", 0),
            _anth_block_stop(0),
            _anth_block_start_text(1),
            _anth_text_delta("public answer", 1),
            _anth_block_stop(1),
            _anth_msg_delta(),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        s = run.steps[0]
        text = (s.output_summary or {}).get("text", "")
        assert text == "public answer"
        assert "internal reasoning" not in text


# ---------------------------------------------------------------------------
# Fix #5 — Anthropic streaming captures cached tokens
# ---------------------------------------------------------------------------

class TestAnthropicStreamingCachedTokens:

    def test_cache_read_input_tokens_from_message_start(self):
        events = [
            _anth_msg_start(input_tokens=100, cache_read=42),
            _anth_block_start_text(0),
            _anth_text_delta("ok", 0),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=5),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        usage = run.steps[0].metadata.get("usage", {})
        assert usage.get("cached_tokens") == 42
        assert usage.get("prompt_tokens") == 100
        assert usage.get("completion_tokens") == 5

    def test_cache_read_input_tokens_from_message_delta_overrides_start(self):
        # When both message_start and message_delta report cache reads,
        # message_delta is the final value (matches non-streaming, where
        # the response.usage block wins).
        events = [
            _anth_msg_start(input_tokens=100, cache_read=10),
            _anth_block_start_text(0),
            _anth_text_delta("ok", 0),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=5, cache_read=99),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        usage = run.steps[0].metadata.get("usage", {})
        assert usage.get("cached_tokens") == 99

    def test_no_cache_tokens_when_provider_omits_them(self):
        events = [
            _anth_msg_start(input_tokens=10),
            _anth_block_start_text(0),
            _anth_text_delta("hi", 0),
            _anth_block_stop(0),
            _anth_msg_delta(output_tokens=2),
            _anth_msg_stop(),
        ]
        stream = _FakeStream(events)

        def go(run):
            wrapped = wrap_anthropic_client(_fake_anthropic_client(stream))
            list(wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[],
                max_tokens=200, stream=True,
            ))

        run = _traced(go)
        usage = run.steps[0].metadata.get("usage", {})
        assert usage.get("cached_tokens") is None


# ---------------------------------------------------------------------------
# Direct StreamCollector unit tests for the new push API
# ---------------------------------------------------------------------------

class TestStreamCollectorStep2API:
    """Targeted tests on StreamCollector's new push surface so failures
    point at the collector rather than provider-specific glue."""

    def test_append_usage_accepts_cached_tokens(self):
        c = StreamCollector(provider="x", model="m")
        c.append_usage(prompt_tokens=10, completion_tokens=2, cached_tokens=4)
        out = c.assembled_output()
        assert out["usage"]["cached_tokens"] == 4
        assert out["usage"]["prompt_tokens"] == 10
        assert out["usage"]["completion_tokens"] == 2

    def test_thinking_blocks_collected_in_index_order(self):
        c = StreamCollector(provider="x", model="m")
        # Open out of order; assembled output must still be index-sorted.
        c.begin_thinking_block(block_index=2)
        c.append_thinking_delta(block_index=2, text="second")
        c.begin_thinking_block(block_index=0)
        c.append_thinking_delta(block_index=0, text="first")
        out = c.assembled_output()
        thinks = out["thinking_blocks"]
        assert [b["thinking"] for b in thinks] == ["first", "second"]

    def test_redacted_thinking_block_has_placeholder_shape(self):
        c = StreamCollector(provider="x", model="m")
        c.begin_thinking_block(block_index=0, redacted=True)
        out = c.assembled_output()
        assert out["thinking_blocks"] == [{"type": "redacted_thinking"}]

    def test_refusal_accumulates_separately_from_text(self):
        c = StreamCollector(provider="x", model="m")
        c.append_text_delta("answer")
        c.append_refusal_delta("nope")
        out = c.assembled_output()
        assert out["text"] == "answer"
        assert out["refusal"] == "nope"

    def test_empty_refusal_ignored(self):
        c = StreamCollector(provider="x", model="m")
        c.append_refusal_delta("")
        out = c.assembled_output()
        assert out["refusal"] is None

    def test_thinking_signature_appended(self):
        c = StreamCollector(provider="x", model="m")
        c.begin_thinking_block(block_index=0)
        c.append_thinking_delta(block_index=0, text="reason")
        c.append_thinking_signature(block_index=0, signature="sig123")
        out = c.assembled_output()
        assert out["thinking_blocks"] == [{
            "type": "thinking",
            "thinking": "reason",
            "signature": "sig123",
        }]
