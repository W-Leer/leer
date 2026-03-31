"""Tests for the Anthropic wrapper — fully mock-based, no real API calls."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from leer.context import get_current_run, set_current_run
from leer.integrations.anthropic import wrap_anthropic_client
from leer.models import TraceRun


# ---------------------------------------------------------------------------
# Helpers — fake Anthropic client and response objects
# ---------------------------------------------------------------------------

class _FakeMessage:
    """Mimics an Anthropic Message response object."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)


def _make_text_response(
    *,
    text: str = "Hello!",
    model: str = "claude-sonnet-4-20250514",
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> _FakeMessage:
    return _FakeMessage({
        "id": "msg_test123",
        "type": "message",
        "model": model,
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    })


def _make_tool_use_response() -> _FakeMessage:
    return _FakeMessage({
        "id": "msg_tools",
        "type": "message",
        "model": "claude-sonnet-4-20250514",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_abc",
                "name": "get_weather",
                "input": {"city": "Paris"},
            }
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 30, "output_tokens": 15},
    })


def _make_mixed_response() -> _FakeMessage:
    """Response with both text and tool_use blocks."""
    return _FakeMessage({
        "id": "msg_mixed",
        "type": "message",
        "model": "claude-sonnet-4-20250514",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me check the weather for you."},
            {
                "type": "tool_use",
                "id": "toolu_xyz",
                "name": "get_weather",
                "input": {"city": "London"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 25, "output_tokens": 20},
    })


def _fake_anthropic_client(response: Any = None) -> MagicMock:
    """Build a mock Anthropic client with .messages.create()."""
    client = MagicMock()

    if response is None:
        response = _make_text_response()
    client.messages.create.return_value = response

    return client


# ---------------------------------------------------------------------------
# Test: outside a trace — pass-through
# ---------------------------------------------------------------------------

class TestOutsideTrace:

    def test_messages_passes_through(self):
        mock_client = _fake_anthropic_client()
        wrapped = wrap_anthropic_client(mock_client)

        result = wrapped.messages.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        mock_client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )
        assert result.model_dump()["model"] == "claude-sonnet-4-20250514"

    def test_other_attributes_proxied(self):
        mock_client = _fake_anthropic_client()
        mock_client.api_key = "sk-ant-test"
        wrapped = wrap_anthropic_client(mock_client)

        assert wrapped.api_key == "sk-ant-test"

    def test_no_step_created_outside_trace(self):
        mock_client = _fake_anthropic_client()
        wrapped = wrap_anthropic_client(mock_client)

        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        assert get_current_run() is None

    def test_error_propagates_outside_trace(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = ConnectionError("network down")
        wrapped = wrap_anthropic_client(mock_client)

        raised = False
        try:
            wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        except ConnectionError:
            raised = True
        assert raised

    def test_no_side_effects_outside_trace(self):
        mock_client = _fake_anthropic_client()
        wrapped = wrap_anthropic_client(mock_client)

        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        assert get_current_run() is None

    def test_messages_other_methods_proxied(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.count_tokens.return_value = {"count": 42}
        wrapped = wrap_anthropic_client(mock_client)

        assert wrapped.messages.count_tokens() == {"count": 42}


# ---------------------------------------------------------------------------
# Test: inside a trace — messages.create
# ---------------------------------------------------------------------------

class TestMessagesInsideTrace:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> tuple[Any, TraceRun]:
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        try:
            result = wrapped.messages.create(**kwargs)
        finally:
            set_current_run(None)

        return result, run

    def test_creates_llm_step(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.name == "claude-sonnet-4-20250514"
        assert s.status == "completed"

    def test_preserves_original_return_value(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        result, _ = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[],
            max_tokens=100,
        )

        assert result.model_dump()["id"] == "msg_test123"

    def test_step_metadata(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        meta = run.steps[0].metadata
        assert meta["provider"] == "anthropic"
        assert meta["model"] == "claude-sonnet-4-20250514"
        assert meta["finish_reason"] == "end_turn"
        assert meta["request_id"] == "msg_test123"
        assert isinstance(meta["latency_ms"], int)
        assert meta["usage"]["prompt_tokens"] == 10
        assert meta["usage"]["completion_tokens"] == 5
        assert meta["usage"]["total_tokens"] == 15

    def test_normalized_llm_shape_in_metadata(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        llm = run.steps[0].metadata["llm"]
        assert llm["provider"] == "anthropic"
        assert llm["model"] == "claude-sonnet-4-20250514"
        assert llm["output"]["text"] == "Hello!"
        assert isinstance(llm["input"], dict)
        assert isinstance(llm["usage"], dict)
        assert isinstance(llm["meta"], dict)

    def test_input_summary(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            system="You are helpful.",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_tokens=100,
        )

        inp = run.steps[0].input_summary
        assert inp["model"] == "claude-sonnet-4-20250514"
        assert inp["system"] == "You are helpful."
        assert inp["user"] == "What is 2+2?"

    def test_input_summary_with_content_blocks(self):
        """Anthropic user messages can be arrays of content blocks."""
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this"},
                    {"type": "text", "text": "in detail"},
                ],
            }],
            max_tokens=100,
        )

        inp = run.steps[0].input_summary
        assert inp["user"] == "Describe this in detail"

    def test_output_summary(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[],
            max_tokens=100,
        )

        out = run.steps[0].output_summary
        assert out["text"] == "Hello!"
        assert out["tokens"] == 15

    def test_creates_request_and_response_artifacts(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert len(run.artifacts) == 2

        req_art = run.artifacts[0]
        assert req_art.artifact_type == "llm_request"
        assert req_art.role == "input"
        assert req_art.format == "json"
        assert req_art.inline_data["model"] == "claude-sonnet-4-20250514"
        assert req_art.step_id == run.steps[0].id

        resp_art = run.artifacts[1]
        assert resp_art.artifact_type == "llm_response"
        assert resp_art.role == "output"
        assert resp_art.inline_data["model"] == "claude-sonnet-4-20250514"

    def test_artifact_preview_text(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            system="Be concise.",
            messages=[{"role": "user", "content": "What is AI?"}],
            max_tokens=100,
        )

        req_preview = run.artifacts[0].preview_text
        assert "claude-sonnet-4-20250514" in req_preview
        assert "Be concise" in req_preview

        resp_preview = run.artifacts[1].preview_text
        assert resp_preview == "Hello!"

    def test_tool_use_response(self):
        mock_client = _fake_anthropic_client(response=_make_tool_use_response())
        wrapped = wrap_anthropic_client(mock_client)

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Weather in Paris?"}],
            tools=[{"name": "get_weather", "description": "Get weather", "input_schema": {}}],
            max_tokens=100,
        )

        out = run.steps[0].output_summary
        assert out["tool_calls"] == [{"name": "get_weather"}]
        assert out["tokens"] == 45

        inp = run.steps[0].input_summary
        assert "get_weather" in inp.get("tools", [])

    def test_mixed_text_and_tool_use(self):
        mock_client = _fake_anthropic_client(response=_make_mixed_response())
        wrapped = wrap_anthropic_client(mock_client)

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Weather?"}],
            max_tokens=100,
        )

        out = run.steps[0].output_summary
        assert out["text"] == "Let me check the weather for you."
        assert out["tool_calls"] == [{"name": "get_weather"}]

        llm = run.steps[0].metadata["llm"]
        assert len(llm["output"]["content_blocks"]) == 2

    def test_sequence_index_on_artifacts(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        _, run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[],
            max_tokens=100,
        )

        assert run.artifacts[0].sequence_index == 0
        assert run.artifacts[1].sequence_index == 1


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> TraceRun:
        run = TraceRun(workflow_name="test-error")
        run.status = "running"
        set_current_run(run)

        try:
            wrapped.messages.create(**kwargs)
        except Exception:
            pass
        finally:
            set_current_run(None)

        return run

    def test_provider_error_propagates(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = RuntimeError("API rate limit")
        wrapped = wrap_anthropic_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        raised = False
        try:
            wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        except RuntimeError as e:
            raised = True
            assert "rate limit" in str(e)
        finally:
            set_current_run(None)

        assert raised, "Provider exception must propagate"

    def test_failed_call_creates_step_with_error(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = RuntimeError("timeout")
        wrapped = wrap_anthropic_client(mock_client)

        run = self._run_in_trace(wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.status == "failed"
        assert s.error_summary is not None
        assert "timeout" in str(s.error_summary)

    def test_failed_call_still_has_metadata(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = RuntimeError("boom")
        wrapped = wrap_anthropic_client(mock_client)

        run = self._run_in_trace(wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        meta = run.steps[0].metadata
        assert meta["provider"] == "anthropic"
        assert meta["model"] == "claude-sonnet-4-20250514"
        assert isinstance(meta["latency_ms"], int)
        assert meta["error_type"] == "RuntimeError"
        assert meta["error_message"] == "boom"

    def test_failed_call_creates_only_request_artifact(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = RuntimeError("fail")
        wrapped = wrap_anthropic_client(mock_client)

        run = self._run_in_trace(wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        assert len(run.artifacts) == 1
        assert run.artifacts[0].artifact_type == "llm_request"
        assert "(failed)" in run.artifacts[0].preview_text

    def test_failed_step_has_traceback_in_error_summary(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = ValueError("bad input")
        wrapped = wrap_anthropic_client(mock_client)

        run = self._run_in_trace(wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        s = run.steps[0]
        assert s.status == "failed"
        assert "ValueError" in str(s.error_summary.get("traceback", ""))
        assert s.metadata["error_type"] == "ValueError"
        assert s.metadata["error_message"] == "bad input"

    def test_instrumentation_failure_does_not_break_call(self):
        mock_client = _fake_anthropic_client()
        wrapped = wrap_anthropic_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        with patch(
            "leer.integrations.anthropic.normalize_anthropic",
            side_effect=Exception("normalization bug"),
        ):
            result = wrapped.messages.create(
                model="claude-sonnet-4-20250514", messages=[], max_tokens=100
            )

        set_current_run(None)

        assert result.model_dump()["id"] == "msg_test123"


# ---------------------------------------------------------------------------
# Test: artifact details
# ---------------------------------------------------------------------------

class TestArtifactDetails:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> TraceRun:
        run = TraceRun(workflow_name="test-artifacts")
        run.status = "running"
        set_current_run(run)
        try:
            wrapped.messages.create(**kwargs)
        finally:
            set_current_run(None)
        return run

    def test_artifact_storage_and_format(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())
        run = self._run_in_trace(
            wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100
        )

        for art in run.artifacts:
            assert art.storage_kind == "inline"
            assert art.format == "json"
            assert art.mime_type == "application/json"

    def test_request_artifact_contains_full_kwargs(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())
        messages = [
            {"role": "user", "content": "Explain AI."},
        ]
        run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            system="Be brief.",
            messages=messages,
            max_tokens=200,
            temperature=0.3,
        )

        req = run.artifacts[0].inline_data
        assert req["model"] == "claude-sonnet-4-20250514"
        assert req["system"] == "Be brief."
        assert req["messages"] == messages
        assert req["max_tokens"] == 200
        assert req["temperature"] == 0.3

    def test_response_artifact_contains_provider_payload(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())
        run = self._run_in_trace(
            wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100
        )

        resp = run.artifacts[1].inline_data
        assert resp["id"] == "msg_test123"
        assert resp["content"][0]["text"] == "Hello!"
        assert resp["usage"]["input_tokens"] == 10

    def test_response_artifact_preview_for_tool_use(self):
        mock_client = _fake_anthropic_client(response=_make_tool_use_response())
        wrapped = wrap_anthropic_client(mock_client)
        run = self._run_in_trace(
            wrapped,
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "weather"}],
            max_tokens=100,
        )

        resp_preview = run.artifacts[1].preview_text
        assert "get_weather" in resp_preview

    def test_artifacts_linked_to_step(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())
        run = self._run_in_trace(
            wrapped, model="claude-sonnet-4-20250514", messages=[], max_tokens=100
        )

        step_id = run.steps[0].id
        for art in run.artifacts:
            assert art.step_id == step_id

    def test_artifact_sequence_indices_across_calls(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        set_current_run(None)

        indices = [a.sequence_index for a in run.artifacts]
        assert indices == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Test: step lifecycle
# ---------------------------------------------------------------------------

class TestStepLifecycle:

    def test_step_has_timing_fields(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        set_current_run(None)

        s = run.steps[0]
        assert s.started_at is not None
        assert s.ended_at is not None
        assert s.ended_at >= s.started_at

    def test_step_events_emitted(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        set_current_run(None)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.completed" in event_types

    def test_failed_step_events(self):
        mock_client = _fake_anthropic_client()
        mock_client.messages.create.side_effect = RuntimeError("err")
        wrapped = wrap_anthropic_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        except RuntimeError:
            pass
        set_current_run(None)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.failed" in event_types
        assert "step.completed" not in event_types

    def test_multiple_calls_create_separate_steps(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)

        set_current_run(None)

        assert len(run.steps) == 2
        assert len(run.artifacts) == 4

    def test_empty_output_summary(self):
        empty_resp = _FakeMessage({
            "id": "msg_empty",
            "type": "message",
            "model": "claude-sonnet-4-20250514",
            "role": "assistant",
            "content": [],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 0},
        })
        mock_client = _fake_anthropic_client(response=empty_resp)
        wrapped = wrap_anthropic_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        set_current_run(None)

        out = run.steps[0].output_summary
        assert isinstance(out, dict)
        assert out.get("text") is None
        assert out.get("tool_calls") is None
        assert out["tokens"] == 5

    def test_input_summary_no_user_message(self):
        wrapped = wrap_anthropic_client(_fake_anthropic_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.messages.create(
            model="claude-sonnet-4-20250514",
            system="You are helpful.",
            messages=[],
            max_tokens=100,
        )
        set_current_run(None)

        inp = run.steps[0].input_summary
        assert inp["model"] == "claude-sonnet-4-20250514"
        assert inp["system"] == "You are helpful."
        assert "user" not in inp
