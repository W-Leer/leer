"""Tests for the OpenAI wrapper — fully mock-based, no real API calls."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from leer.context import get_current_run, set_current_run
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun


# ---------------------------------------------------------------------------
# Helpers — fake OpenAI client and response objects
# ---------------------------------------------------------------------------

class _FakeChatCompletion:
    """Mimics an OpenAI ChatCompletion response object."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)


def _make_chat_response(
    *,
    text: str = "Hello!",
    model: str = "gpt-4.1",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> _FakeChatCompletion:
    return _FakeChatCompletion({
        "id": "chatcmpl-test123",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    })


def _make_responses_response(
    *,
    text: str = "Hi there!",
    model: str = "gpt-4.1",
) -> _FakeChatCompletion:
    return _FakeChatCompletion({
        "id": "resp_test456",
        "object": "response",
        "status": "completed",
        "model": model,
        "output": [
            {
                "type": "message",
                "id": "msg_001",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 6,
            "total_tokens": 18,
        },
    })


def _make_tool_call_response() -> _FakeChatCompletion:
    return _FakeChatCompletion({
        "id": "chatcmpl-tools",
        "model": "gpt-4.1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Paris"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
    })


def _fake_openai_client(chat_response: Any = None, responses_response: Any = None) -> MagicMock:
    """Build a mock OpenAI client with nested .chat.completions.create() / .responses.create()."""
    client = MagicMock()

    if chat_response is None:
        chat_response = _make_chat_response()
    client.chat.completions.create.return_value = chat_response

    if responses_response is None:
        responses_response = _make_responses_response()
    client.responses.create.return_value = responses_response

    return client


# ---------------------------------------------------------------------------
# Test: outside a trace — pass-through
# ---------------------------------------------------------------------------

class TestOutsideTrace:

    def test_chat_completions_passes_through(self):
        mock_client = _fake_openai_client()
        wrapped = wrap_openai_client(mock_client)

        result = wrapped.chat.completions.create(model="gpt-4.1", messages=[])

        mock_client.chat.completions.create.assert_called_once_with(model="gpt-4.1", messages=[])
        assert result.model_dump()["model"] == "gpt-4.1"

    def test_responses_passes_through(self):
        mock_client = _fake_openai_client()
        wrapped = wrap_openai_client(mock_client)

        result = wrapped.responses.create(model="gpt-4.1", input="Hello")

        mock_client.responses.create.assert_called_once_with(model="gpt-4.1", input="Hello")
        assert result.model_dump()["id"] == "resp_test456"

    def test_other_attributes_proxied(self):
        mock_client = _fake_openai_client()
        mock_client.api_key = "sk-test"
        wrapped = wrap_openai_client(mock_client)

        assert wrapped.api_key == "sk-test"

    def test_no_step_created_outside_trace(self):
        mock_client = _fake_openai_client()
        wrapped = wrap_openai_client(mock_client)

        wrapped.chat.completions.create(model="gpt-4.1", messages=[])

        assert get_current_run() is None

    def test_error_propagates_outside_trace(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = ConnectionError("network down")
        wrapped = wrap_openai_client(mock_client)

        raised = False
        try:
            wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        except ConnectionError:
            raised = True
        assert raised

    def test_no_side_effects_outside_trace(self):
        """Outside a trace, the wrapper must not create runs, steps, or artifacts anywhere."""
        mock_client = _fake_openai_client()
        wrapped = wrap_openai_client(mock_client)

        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        wrapped.responses.create(model="gpt-4.1", input="Hi")

        assert get_current_run() is None


# ---------------------------------------------------------------------------
# Test: inside a trace — chat completions
# ---------------------------------------------------------------------------

class TestChatCompletionsInsideTrace:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> tuple[Any, TraceRun]:
        """Helper: call wrapped.chat.completions.create inside a fake trace, return (result, run)."""
        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        try:
            result = wrapped.chat.completions.create(**kwargs)
        finally:
            set_current_run(None)

        return result, run

    def test_creates_llm_step(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        result, run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[{"role": "user", "content": "Hi"}]
        )

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.name == "gpt-4.1"
        assert s.status == "completed"

    def test_preserves_original_return_value(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        result, _ = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[]
        )

        assert result.model_dump()["id"] == "chatcmpl-test123"

    def test_step_metadata(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[{"role": "user", "content": "Hi"}]
        )

        meta = run.steps[0].metadata
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4.1"
        assert meta["finish_reason"] == "stop"
        assert meta["request_id"] == "chatcmpl-test123"
        assert isinstance(meta["latency_ms"], int)
        assert meta["usage"]["prompt_tokens"] == 10
        assert meta["usage"]["completion_tokens"] == 5
        assert meta["usage"]["total_tokens"] == 15

    def test_normalized_llm_shape_in_metadata(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[{"role": "user", "content": "Hi"}]
        )

        llm = run.steps[0].metadata["llm"]
        assert llm["provider"] == "openai"
        assert llm["model"] == "gpt-4.1"
        assert llm["output"]["text"] == "Hello!"
        assert isinstance(llm["input"], dict)
        assert isinstance(llm["usage"], dict)
        assert isinstance(llm["meta"], dict)

    def test_input_summary(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped,
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "What is 2+2?"},
            ],
        )

        inp = run.steps[0].input_summary
        assert inp["model"] == "gpt-4.1"
        assert inp["system"] == "You are helpful."
        assert inp["user"] == "What is 2+2?"

    def test_output_summary(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        out = run.steps[0].output_summary
        assert out["text"] == "Hello!"
        assert out["tokens"] == 15

    def test_creates_request_and_response_artifacts(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[{"role": "user", "content": "Hi"}]
        )

        assert len(run.artifacts) == 2

        req_art = run.artifacts[0]
        assert req_art.artifact_type == "llm_request"
        assert req_art.role == "input"
        assert req_art.format == "json"
        assert req_art.inline_data["model"] == "gpt-4.1"
        assert req_art.step_id == run.steps[0].id

        resp_art = run.artifacts[1]
        assert resp_art.artifact_type == "llm_response"
        assert resp_art.role == "output"
        assert resp_art.inline_data["model"] == "gpt-4.1"

    def test_artifact_preview_text(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped,
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "What is AI?"},
            ],
        )

        req_preview = run.artifacts[0].preview_text
        assert "gpt-4.1" in req_preview
        assert "Be concise" in req_preview

        resp_preview = run.artifacts[1].preview_text
        assert resp_preview == "Hello!"

    def test_tool_call_response(self):
        mock_client = _fake_openai_client(chat_response=_make_tool_call_response())
        wrapped = wrap_openai_client(mock_client)

        _, run = self._run_in_trace(
            wrapped,
            model="gpt-4.1",
            messages=[{"role": "user", "content": "Weather in Paris?"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )

        out = run.steps[0].output_summary
        assert len(out["tool_calls"]) == 1
        tc = out["tool_calls"][0]
        assert tc["name"] == "get_weather"
        assert tc["id"] == "call_abc"
        assert "arguments_hash" in tc
        assert out["tokens"] == 45

        inp = run.steps[0].input_summary
        assert "get_weather" in inp.get("tools", [])

    def test_sequence_index_on_artifacts(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        assert run.artifacts[0].sequence_index == 0
        assert run.artifacts[1].sequence_index == 1


# ---------------------------------------------------------------------------
# Test: inside a trace — responses API
# ---------------------------------------------------------------------------

class TestResponsesAPIInsideTrace:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> tuple[Any, TraceRun]:
        run = TraceRun(workflow_name="test-responses")
        run.status = "running"
        set_current_run(run)

        try:
            result = wrapped.responses.create(**kwargs)
        finally:
            set_current_run(None)

        return result, run

    def test_creates_llm_step(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", input="Hello!", instructions="Be helpful."
        )

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.step_type == "llm"
        assert s.name == "gpt-4.1"
        assert s.status == "completed"

    def test_preserves_original_return_value(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        result, _ = self._run_in_trace(wrapped, model="gpt-4.1", input="Hi")

        assert result.model_dump()["id"] == "resp_test456"

    def test_step_metadata_uses_responses_shape(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(wrapped, model="gpt-4.1", input="Hello!")

        meta = run.steps[0].metadata
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4.1"
        assert meta["finish_reason"] == "completed"
        assert meta["request_id"] == "resp_test456"
        assert meta["usage"]["prompt_tokens"] == 12
        assert meta["usage"]["completion_tokens"] == 6

    def test_normalized_llm_shape_in_metadata(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", input="Hello!", instructions="Be helpful."
        )

        llm = run.steps[0].metadata["llm"]
        assert llm["provider"] == "openai"
        assert llm["model"] == "gpt-4.1"
        assert llm["output"]["text"] == "Hi there!"
        assert llm["input"]["system"] == "Be helpful."
        assert isinstance(llm["output"]["content_blocks"], list)

    def test_input_summary_with_instructions(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped,
            model="gpt-4.1",
            instructions="You are concise.",
            input="Explain gravity.",
        )

        inp = run.steps[0].input_summary
        assert inp["model"] == "gpt-4.1"
        assert inp["system"] == "You are concise."
        assert inp["user"] == "Explain gravity."

    def test_output_summary_from_responses(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(wrapped, model="gpt-4.1", input="Hi")

        out = run.steps[0].output_summary
        assert out["text"] == "Hi there!"
        assert out["tokens"] == 18

    def test_creates_artifacts_with_correct_content(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        _, run = self._run_in_trace(
            wrapped, model="gpt-4.1", input="Hi", temperature=0.5
        )

        assert len(run.artifacts) == 2

        req_art = run.artifacts[0]
        assert req_art.artifact_type == "llm_request"
        assert req_art.role == "input"
        assert req_art.inline_data["model"] == "gpt-4.1"
        assert req_art.inline_data["input"] == "Hi"
        assert req_art.step_id == run.steps[0].id

        resp_art = run.artifacts[1]
        assert resp_art.artifact_type == "llm_response"
        assert resp_art.role == "output"
        assert "output" in resp_art.inline_data

    def test_responses_with_function_call(self):
        resp = _FakeChatCompletion({
            "id": "resp_fc",
            "object": "response",
            "status": "completed",
            "model": "gpt-4.1",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_xyz",
                    "name": "search",
                    "arguments": '{"q": "test"}',
                },
            ],
            "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        })
        mock_client = _fake_openai_client(responses_response=resp)
        wrapped = wrap_openai_client(mock_client)

        _, run = self._run_in_trace(wrapped, model="gpt-4.1", input="Search for test")

        out = run.steps[0].output_summary
        assert len(out["tool_calls"]) == 1
        tc = out["tool_calls"][0]
        assert tc["name"] == "search"
        assert tc["id"] == "call_xyz"
        assert "arguments_hash" in tc
        assert out.get("text") is None


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def _run_in_trace(self, wrapped: Any, method: str = "chat", **kwargs: Any) -> TraceRun:
        run = TraceRun(workflow_name="test-error")
        run.status = "running"
        set_current_run(run)

        try:
            if method == "chat":
                wrapped.chat.completions.create(**kwargs)
            else:
                wrapped.responses.create(**kwargs)
        except Exception:
            pass
        finally:
            set_current_run(None)

        return run

    def test_provider_error_propagates(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = RuntimeError("API rate limit")
        wrapped = wrap_openai_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        raised = False
        try:
            wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        except RuntimeError as e:
            raised = True
            assert "rate limit" in str(e)
        finally:
            set_current_run(None)

        assert raised, "Provider exception must propagate"

    def test_failed_call_creates_step_with_error(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = RuntimeError("timeout")
        wrapped = wrap_openai_client(mock_client)

        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.status == "failed"
        assert s.error_summary is not None
        assert "timeout" in str(s.error_summary)

    def test_failed_call_still_has_metadata(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")
        wrapped = wrap_openai_client(mock_client)

        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        meta = run.steps[0].metadata
        assert meta["provider"] == "openai"
        assert meta["model"] == "gpt-4.1"
        assert isinstance(meta["latency_ms"], int)
        assert meta["error_type"] == "RuntimeError"
        assert meta["error_message"] == "boom"

    def test_failed_call_creates_only_request_artifact(self):
        """On failure, only the request artifact should exist — no response artifact."""
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = RuntimeError("fail")
        wrapped = wrap_openai_client(mock_client)

        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        assert len(run.artifacts) == 1
        assert run.artifacts[0].artifact_type == "llm_request"
        assert "(failed)" in run.artifacts[0].preview_text

    def test_failed_step_has_traceback_in_error_summary(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = ValueError("bad input")
        wrapped = wrap_openai_client(mock_client)

        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        s = run.steps[0]
        assert s.status == "failed"
        assert "ValueError" in str(s.error_summary.get("traceback", ""))
        assert s.metadata["error_type"] == "ValueError"
        assert s.metadata["error_message"] == "bad input"

    def test_responses_api_failure(self):
        mock_client = _fake_openai_client()
        mock_client.responses.create.side_effect = TimeoutError("request timed out")
        wrapped = wrap_openai_client(mock_client)

        run = self._run_in_trace(wrapped, method="responses", model="gpt-4.1", input="Hi")

        assert len(run.steps) == 1
        s = run.steps[0]
        assert s.status == "failed"
        assert s.metadata["error_type"] == "TimeoutError"
        assert s.metadata["error_message"] == "request timed out"
        assert len(run.artifacts) == 1

    def test_instrumentation_failure_does_not_break_call(self):
        """If normalization or artifact creation throws, the result is still returned."""
        mock_client = _fake_openai_client()
        wrapped = wrap_openai_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        with patch(
            "leer.integrations.openai.normalize_openai",
            side_effect=Exception("normalization bug"),
        ):
            result = wrapped.chat.completions.create(model="gpt-4.1", messages=[])

        set_current_run(None)

        assert result.model_dump()["id"] == "chatcmpl-test123"


# ---------------------------------------------------------------------------
# Test: wrapper transparency
# ---------------------------------------------------------------------------

class TestWrapperTransparency:

    def test_chat_completions_other_methods_proxied(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.list.return_value = ["item"]
        wrapped = wrap_openai_client(mock_client)

        assert wrapped.chat.completions.list() == ["item"]

    def test_client_without_responses(self):
        """Older OpenAI SDK versions may not have .responses — should not crash."""
        mock_client = MagicMock(spec=["chat", "api_key"])
        mock_client.chat.completions.create.return_value = _make_chat_response()
        wrapped = wrap_openai_client(mock_client)

        result = wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        assert result.model_dump()["model"] == "gpt-4.1"

    def test_multiple_calls_create_separate_steps(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        wrapped.chat.completions.create(model="gpt-4.1", messages=[])

        set_current_run(None)

        assert len(run.steps) == 2
        assert len(run.artifacts) == 4


# ---------------------------------------------------------------------------
# Test: artifact details
# ---------------------------------------------------------------------------

class TestArtifactDetails:

    def _run_in_trace(self, wrapped: Any, **kwargs: Any) -> TraceRun:
        run = TraceRun(workflow_name="test-artifacts")
        run.status = "running"
        set_current_run(run)
        try:
            wrapped.chat.completions.create(**kwargs)
        finally:
            set_current_run(None)
        return run

    def test_artifact_storage_and_format(self):
        wrapped = wrap_openai_client(_fake_openai_client())
        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        for art in run.artifacts:
            assert art.storage_kind == "inline"
            assert art.format == "json"
            assert art.mime_type == "application/json"

    def test_request_artifact_contains_full_kwargs(self):
        wrapped = wrap_openai_client(_fake_openai_client())
        messages = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Explain AI."},
        ]
        run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=messages, temperature=0.3
        )

        req = run.artifacts[0].inline_data
        assert req["model"] == "gpt-4.1"
        assert req["messages"] == messages
        assert req["temperature"] == 0.3

    def test_response_artifact_contains_provider_payload(self):
        wrapped = wrap_openai_client(_fake_openai_client())
        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        resp = run.artifacts[1].inline_data
        assert resp["id"] == "chatcmpl-test123"
        assert resp["choices"][0]["message"]["content"] == "Hello!"
        assert resp["usage"]["total_tokens"] == 15

    def test_response_artifact_preview_for_tool_call(self):
        mock_client = _fake_openai_client(chat_response=_make_tool_call_response())
        wrapped = wrap_openai_client(mock_client)
        run = self._run_in_trace(
            wrapped, model="gpt-4.1", messages=[{"role": "user", "content": "weather"}]
        )

        resp_preview = run.artifacts[1].preview_text
        assert "get_weather" in resp_preview

    def test_artifacts_linked_to_step(self):
        wrapped = wrap_openai_client(_fake_openai_client())
        run = self._run_in_trace(wrapped, model="gpt-4.1", messages=[])

        step_id = run.steps[0].id
        for art in run.artifacts:
            assert art.step_id == step_id

    def test_artifact_sequence_indices_across_calls(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)

        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        wrapped.chat.completions.create(model="gpt-4.1", messages=[])

        set_current_run(None)

        indices = [a.sequence_index for a in run.artifacts]
        assert indices == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Test: step lifecycle
# ---------------------------------------------------------------------------

class TestStepLifecycle:

    def test_step_has_timing_fields(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        set_current_run(None)

        s = run.steps[0]
        assert s.started_at is not None
        assert s.ended_at is not None
        assert s.ended_at >= s.started_at

    def test_step_events_emitted(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        set_current_run(None)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.completed" in event_types

    def test_failed_step_events(self):
        mock_client = _fake_openai_client()
        mock_client.chat.completions.create.side_effect = RuntimeError("err")
        wrapped = wrap_openai_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        except RuntimeError:
            pass
        set_current_run(None)

        event_types = [e.event_type for e in run.events]
        assert "step.created" in event_types
        assert "step.started" in event_types
        assert "step.failed" in event_types
        assert "step.completed" not in event_types

    def test_empty_output_summary(self):
        """A response with no text and no tool_calls still produces a summary."""
        empty_resp = _FakeChatCompletion({
            "id": "chatcmpl-empty",
            "model": "gpt-4.1",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
        })
        mock_client = _fake_openai_client(chat_response=empty_resp)
        wrapped = wrap_openai_client(mock_client)

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.chat.completions.create(model="gpt-4.1", messages=[])
        set_current_run(None)

        out = run.steps[0].output_summary
        assert isinstance(out, dict)
        assert out.get("text") is None
        assert out.get("tool_calls") is None
        assert out["tokens"] == 5

    def test_input_summary_no_user_message(self):
        wrapped = wrap_openai_client(_fake_openai_client())

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        wrapped.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "system", "content": "You are helpful."}],
        )
        set_current_run(None)

        inp = run.steps[0].input_summary
        assert inp["model"] == "gpt-4.1"
        assert inp["system"] == "You are helpful."
        assert "user" not in inp
