"""Tests for the in-memory StreamCollector — stream capture foundation."""

from __future__ import annotations

import time

from leer.integrations.streaming import StreamCollector, StreamEvent


# ---------------------------------------------------------------------------
# 1. Text-only stream assembly
# ---------------------------------------------------------------------------

class TestTextAssembly:

    def test_assembles_text_deltas(self):
        c = StreamCollector(provider="openai", model="gpt-4.1")
        c.append_text_delta("Hello")
        c.append_text_delta(" world")
        c.append_text_delta("!")

        assert c.assembled_text == "Hello world!"
        assert c.assembled_tool_calls == []

    def test_empty_stream_returns_none_text(self):
        c = StreamCollector(provider="openai")
        assert c.assembled_text is None

    def test_single_delta(self):
        c = StreamCollector(provider="anthropic", model="claude-sonnet-4-20250514")
        c.append_text_delta("Hi")
        assert c.assembled_text == "Hi"


# ---------------------------------------------------------------------------
# 2. Tool-call delta assembly
# ---------------------------------------------------------------------------

class TestToolCallAssembly:

    def test_single_tool_call_assembled(self):
        c = StreamCollector(provider="openai", model="gpt-4.1")
        c.append_tool_call_delta(0, tool_call_id="call_abc", name_delta="get_weather")
        c.append_tool_call_delta(0, arguments_delta='{"ci')
        c.append_tool_call_delta(0, arguments_delta='ty":"Paris"}')

        calls = c.assembled_tool_calls
        assert len(calls) == 1
        assert calls[0]["id"] == "call_abc"
        assert calls[0]["name"] == "get_weather"
        assert calls[0]["arguments"] == {"city": "Paris"}

    def test_multiple_tool_calls_assembled(self):
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="call_1", name_delta="get_weather")
        c.append_tool_call_delta(0, arguments_delta='{"city":"Paris"}')
        c.append_tool_call_delta(1, tool_call_id="call_2", name_delta="get_time")
        c.append_tool_call_delta(1, arguments_delta='{"tz":"UTC"}')

        calls = c.assembled_tool_calls
        assert len(calls) == 2
        assert calls[0]["name"] == "get_weather"
        assert calls[1]["name"] == "get_time"
        assert calls[0]["arguments"] == {"city": "Paris"}
        assert calls[1]["arguments"] == {"tz": "UTC"}

    def test_invalid_json_arguments_kept_as_string(self):
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="call_x", name_delta="foo")
        c.append_tool_call_delta(0, arguments_delta="not json{")

        calls = c.assembled_tool_calls
        assert calls[0]["arguments"] == "not json{"

    def test_tool_call_id_preserved_across_deltas(self):
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="call_99")
        c.append_tool_call_delta(0, name_delta="search")
        c.append_tool_call_delta(0, arguments_delta="{}")

        assert c.assembled_tool_calls[0]["id"] == "call_99"

    def test_mixed_text_and_tool_calls(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("Thinking...")
        c.append_tool_call_delta(0, tool_call_id="call_1", name_delta="search")
        c.append_tool_call_delta(0, arguments_delta='{"q":"test"}')

        assert c.assembled_text == "Thinking..."
        assert len(c.assembled_tool_calls) == 1
        assert c.assembled_tool_calls[0]["name"] == "search"


# ---------------------------------------------------------------------------
# 3. Usage accumulation
# ---------------------------------------------------------------------------

class TestUsageAccumulation:

    def test_usage_from_single_event(self):
        c = StreamCollector(provider="openai")
        c.append_usage(prompt_tokens=50, completion_tokens=100, total_tokens=150)

        out = c.assembled_output()
        assert out["usage"]["prompt_tokens"] == 50
        assert out["usage"]["completion_tokens"] == 100
        assert out["usage"]["total_tokens"] == 150

    def test_partial_usage_updates(self):
        c = StreamCollector(provider="openai")
        c.append_usage(prompt_tokens=50)
        c.append_usage(completion_tokens=100)
        c.append_usage(total_tokens=150)

        out = c.assembled_output()
        assert out["usage"]["prompt_tokens"] == 50
        assert out["usage"]["completion_tokens"] == 100
        assert out["usage"]["total_tokens"] == 150

    def test_no_usage_defaults_to_none(self):
        c = StreamCollector(provider="openai")
        out = c.assembled_output()
        assert out["usage"]["prompt_tokens"] is None
        assert out["usage"]["completion_tokens"] is None
        assert out["usage"]["total_tokens"] is None

    def test_usage_contributes_to_observed_event_count(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("hi")
        c.append_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        assert c.chunk_count == 2
        assert len(c._events) == 2
        events = c.stream_artifact_payload()["events"]
        assert events[0]["type"] == "text_delta"
        assert events[0]["index"] == 0
        assert events[1]["type"] == "usage"
        assert events[1]["index"] == 1

    def test_usage_updates_timing(self):
        c = StreamCollector(provider="openai")
        c.append_usage(prompt_tokens=10)
        meta = c.stream_metadata()
        assert meta["first_chunk_at"] is not None
        assert meta["time_to_first_chunk_ms"] is not None


# ---------------------------------------------------------------------------
# 4. message_start / message_stop capture
# ---------------------------------------------------------------------------

class TestMessageLifecycle:

    def test_message_start_recorded(self):
        c = StreamCollector(provider="openai")
        c.mark_message_start({"model": "gpt-4.1"})
        c.append_text_delta("Hi")
        c.mark_message_stop(finish_reason="stop", request_id="req_123")

        events = [e.to_dict() for e in c._events]
        assert events[0]["type"] == "message_start"
        assert events[-1]["type"] == "message_stop"

    def test_finish_reason_and_request_id_captured(self):
        c = StreamCollector(provider="anthropic")
        c.mark_message_stop(finish_reason="end_turn", request_id="msg_abc")

        out = c.assembled_output()
        assert out["finish_reason"] == "end_turn"
        assert out["request_id"] == "msg_abc"

    def test_set_finish_reason_separately(self):
        c = StreamCollector(provider="openai")
        c.set_finish_reason("length")
        c.set_request_id("req_999")

        out = c.assembled_output()
        assert out["finish_reason"] == "length"
        assert out["request_id"] == "req_999"


# ---------------------------------------------------------------------------
# 5. Unknown events preserved
# ---------------------------------------------------------------------------

class TestUnknownEvents:

    def test_unknown_event_stored(self):
        c = StreamCollector(provider="openai")
        c.mark_unknown({"raw_type": "server_sent_event", "data": "ping"})

        assert c.chunk_count == 1
        events = [e.to_dict() for e in c._events]
        assert events[0]["type"] == "unknown"
        assert events[0]["raw_type"] == "server_sent_event"


# ---------------------------------------------------------------------------
# 6. chunk_count and timing metadata
# ---------------------------------------------------------------------------

class TestTimingMetadata:

    def test_chunk_count_matches_events(self):
        c = StreamCollector(provider="openai")
        c.mark_message_start()
        c.append_text_delta("a")
        c.append_text_delta("b")
        c.append_text_delta("c")
        c.mark_message_stop()

        assert c.chunk_count == 5

    def test_timing_fields_populated(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("token")
        time.sleep(0.01)
        c.append_text_delta("two")

        meta = c.stream_metadata()
        assert meta["chunk_count"] == 2
        assert meta["first_chunk_at"] is not None
        assert meta["last_chunk_at"] is not None
        assert meta["time_to_first_chunk_ms"] is not None
        assert isinstance(meta["time_to_first_chunk_ms"], int)
        assert meta["time_to_first_chunk_ms"] >= 0
        assert meta["stream_duration_ms"] is not None
        assert meta["stream_duration_ms"] >= meta["time_to_first_chunk_ms"]

    def test_empty_stream_timing_is_none(self):
        c = StreamCollector(provider="openai")
        meta = c.stream_metadata()
        assert meta["chunk_count"] == 0
        assert meta["first_chunk_at"] is None
        assert meta["last_chunk_at"] is None
        assert meta["time_to_first_chunk_ms"] is None
        assert meta["stream_duration_ms"] is None


# ---------------------------------------------------------------------------
# 7. Truncation flag behavior
# ---------------------------------------------------------------------------

class TestTruncation:

    def test_truncation_flag_set_when_limit_exceeded(self):
        c = StreamCollector(provider="openai", capture_limit_bytes=100)
        for i in range(200):
            c.append_text_delta(f"chunk_{i}_" * 5)

        meta = c.stream_metadata()
        assert meta["truncated_chunks"] is True
        assert c.chunk_count == 200
        stored = len(c._events)
        assert stored < 200
        assert c.assembled_text is not None
        assert "chunk_0_" in c.assembled_text

    def test_no_truncation_under_limit(self):
        c = StreamCollector(provider="openai", capture_limit_bytes=1_000_000)
        for i in range(5):
            c.append_text_delta("hi")

        meta = c.stream_metadata()
        assert meta["truncated_chunks"] is False
        assert c.chunk_count == 5
        assert len(c._events) == 5

    def test_assembly_continues_after_truncation(self):
        """Text/tool-call assembly must work even when event log is truncated."""
        c = StreamCollector(provider="openai", capture_limit_bytes=100)
        for i in range(100):
            c.append_text_delta(f"w{i} ")

        text = c.assembled_text
        assert text is not None
        assert "w0 " in text
        assert "w99 " in text
        assert c.chunk_count == 100
        assert c.stream_metadata()["truncated_chunks"] is True

    def test_stored_event_indices_truthful_under_truncation(self):
        """Stored events keep their original observed index, not storage position."""
        c = StreamCollector(provider="openai", capture_limit_bytes=200)
        for i in range(50):
            c.append_text_delta(f"t{i}")

        stored = c._events
        assert len(stored) < 50
        indices = [ev.index for ev in stored]
        assert indices == list(range(len(stored)))

    def test_chunk_count_includes_all_observed_after_truncation(self):
        """chunk_count must reflect total observed, not just stored events."""
        c = StreamCollector(provider="openai", capture_limit_bytes=50)
        c.append_text_delta("a" * 30)
        c.append_text_delta("b" * 30)
        c.append_text_delta("c" * 30)
        c.append_text_delta("d" * 30)

        assert c.chunk_count == 4
        assert len(c._events) < 4


# ---------------------------------------------------------------------------
# 8. Final metadata shape
# ---------------------------------------------------------------------------

class TestMetadataShape:

    def test_metadata_has_all_required_keys(self):
        c = StreamCollector(provider="openai", model="gpt-4.1")
        c.append_text_delta("Hello world")
        c.append_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        meta = c.stream_metadata()
        required_keys = {
            "is_stream", "provider", "chunk_count",
            "first_chunk_at", "last_chunk_at",
            "time_to_first_chunk_ms", "stream_duration_ms",
            "termination", "assembled_text_chars",
            "assembled_tool_calls", "captured_chunk_bytes",
            "truncated_chunks",
        }
        assert required_keys.issubset(meta.keys())
        assert meta["is_stream"] is True
        assert meta["provider"] == "openai"
        assert meta["termination"] == "completed"
        assert meta["assembled_text_chars"] == 11
        assert meta["assembled_tool_calls"] == 0
        assert meta["truncated_chunks"] is False

    def test_metadata_for_tool_call_stream(self):
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="call_1", name_delta="search")
        c.append_tool_call_delta(0, arguments_delta='{"q":"test"}')

        meta = c.stream_metadata()
        assert meta["assembled_text_chars"] == 0
        assert meta["assembled_tool_calls"] == 1


# ---------------------------------------------------------------------------
# 9. Artifact payload shape
# ---------------------------------------------------------------------------

class TestArtifactPayload:

    def test_artifact_payload_structure(self):
        c = StreamCollector(provider="openai", model="gpt-4.1")
        c.mark_message_start()
        c.append_text_delta("Hello")
        c.mark_message_stop(finish_reason="stop")

        payload = c.stream_artifact_payload()
        assert payload["provider"] == "openai"
        assert payload["model"] == "gpt-4.1"
        assert isinstance(payload["events"], list)
        assert len(payload["events"]) == 3
        assert payload["events"][0]["type"] == "message_start"
        assert payload["events"][1]["type"] == "text_delta"
        assert payload["events"][1]["text"] == "Hello"
        assert payload["events"][2]["type"] == "message_stop"

    def test_artifact_events_have_correct_indices(self):
        c = StreamCollector(provider="anthropic")
        c.append_text_delta("a")
        c.append_text_delta("b")
        c.append_text_delta("c")

        events = c.stream_artifact_payload()["events"]
        for i, ev in enumerate(events):
            assert ev["index"] == i

    def test_artifact_events_have_timestamp_offsets(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("token")

        events = c.stream_artifact_payload()["events"]
        assert "timestamp_offset_ms" in events[0]
        assert isinstance(events[0]["timestamp_offset_ms"], int)
        assert events[0]["timestamp_offset_ms"] >= 0


# ---------------------------------------------------------------------------
# 10. Partial stream / termination values
# ---------------------------------------------------------------------------

class TestTermination:

    def test_default_termination_is_completed(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("done")
        assert c.stream_metadata()["termination"] == "completed"

    def test_mark_failed(self):
        c = StreamCollector(provider="openai")
        c.append_text_delta("partial...")
        c.mark_failed()

        meta = c.stream_metadata()
        assert meta["termination"] == "failed"
        assert c.assembled_text == "partial..."

    def test_mark_interrupted(self):
        c = StreamCollector(provider="openai")
        c.mark_interrupted()
        assert c.stream_metadata()["termination"] == "interrupted"

    def test_mark_cancelled(self):
        c = StreamCollector(provider="openai")
        c.mark_cancelled()
        assert c.stream_metadata()["termination"] == "cancelled"

    def test_partial_tool_call_on_failure(self):
        """Even if stream fails mid-tool-call, partial assembly is preserved."""
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="call_1", name_delta="search")
        c.append_tool_call_delta(0, arguments_delta='{"q":"par')
        c.mark_failed()

        calls = c.assembled_tool_calls
        assert len(calls) == 1
        assert calls[0]["name"] == "search"
        assert calls[0]["arguments"] == '{"q":"par'

    def test_zero_chunk_failure(self):
        c = StreamCollector(provider="openai")
        c.mark_failed()

        meta = c.stream_metadata()
        assert meta["termination"] == "failed"
        assert meta["chunk_count"] == 0
        assert meta["assembled_text_chars"] == 0
        assert meta["first_chunk_at"] is None
        assert c.assembled_text is None


# ---------------------------------------------------------------------------
# StreamEvent serialization
# ---------------------------------------------------------------------------

class TestStreamEvent:

    def test_to_dict_minimal(self):
        ev = StreamEvent(index=0, type="text_delta", timestamp_offset_ms=100)
        d = ev.to_dict()
        assert d == {"index": 0, "type": "text_delta", "timestamp_offset_ms": 100}

    def test_to_dict_with_payload(self):
        ev = StreamEvent(
            index=1,
            type="text_delta",
            timestamp_offset_ms=150,
            payload={"text": "hi"},
        )
        d = ev.to_dict()
        assert d["text"] == "hi"
        assert d["index"] == 1

    def test_to_dict_tool_call_delta(self):
        ev = StreamEvent(
            index=2,
            type="tool_call_delta",
            timestamp_offset_ms=200,
            payload={
                "tool_call_id": "call_123",
                "name_delta": "get_weather",
                "arguments_delta": '{"city":',
            },
        )
        d = ev.to_dict()
        assert d["type"] == "tool_call_delta"
        assert d["tool_call_id"] == "call_123"
        assert d["name_delta"] == "get_weather"


# ---------------------------------------------------------------------------
# Assembled output shape
# ---------------------------------------------------------------------------

class TestAssembledOutput:

    def test_assembled_output_complete(self):
        c = StreamCollector(provider="openai", model="gpt-4.1")
        c.append_text_delta("Hello world")
        c.append_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        c.set_finish_reason("stop")
        c.set_request_id("req_abc")

        out = c.assembled_output()
        assert out["text"] == "Hello world"
        assert out["tool_calls"] == []
        assert out["usage"]["prompt_tokens"] == 10
        assert out["finish_reason"] == "stop"
        assert out["request_id"] == "req_abc"

    def test_assembled_output_with_tool_calls(self):
        c = StreamCollector(provider="openai")
        c.append_tool_call_delta(0, tool_call_id="c1", name_delta="search")
        c.append_tool_call_delta(0, arguments_delta='{"q":"hi"}')

        out = c.assembled_output()
        assert out["text"] is None
        assert len(out["tool_calls"]) == 1
        assert out["tool_calls"][0]["name"] == "search"

    def test_assembled_output_empty_stream(self):
        c = StreamCollector(provider="openai")
        out = c.assembled_output()
        assert out["text"] is None
        assert out["tool_calls"] == []
        assert out["finish_reason"] is None
        assert out["request_id"] is None
