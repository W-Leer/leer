"""Structured-output capture validation matrix (roadmap item A, Step 1).

Drives the *real* OpenAI / Anthropic wrappers (offline, fixture-based) to
assert that schema-constrained / JSON outputs are captured as a first-class
canonical signal, equivalently across providers and streaming:

  - ``output.parsed``        — the structured object the model returned
  - ``meta.output_is_json``  — whether the canonical text output is a JSON
                               object/array (content-derived, schema-agnostic)

It also pins the G-A1 gap from the Step-0 audit: the ``.parse()`` structured-
output helpers (``chat.completions.parse``, ``responses.parse``,
``beta.chat.completions.parse``) must be instrumented like ``create``.

Offline fakes mirror ``test_provider_hardening_qa.py``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from leer.context import reset_context, set_current_run
from leer.integrations.anthropic import wrap_anthropic_client
from leer.integrations.openai import wrap_openai_client
from leer.models import TraceRun


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _traced(fn: Any) -> TraceRun:
    run = TraceRun(workflow_name="structured-outputs")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn(run)
    finally:
        set_current_run(None)
    return run


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


def _step(run: TraceRun):
    assert len(run.steps) == 1, f"expected exactly one step, got {len(run.steps)}"
    return run.steps[0]


def _llm(step) -> dict[str, Any]:
    llm = step.metadata.get("llm")
    assert isinstance(llm, dict), f"no canonical llm metadata: {step.metadata!r}"
    return llm


# ---------------------------------------------------------------------------
# Canonical structured-output detection (non-streaming)
# ---------------------------------------------------------------------------

class TestCanonicalStructuredFields:

    def _chat(self, response: dict[str, Any], **req: Any) -> TraceRun:
        def go(run):
            client = MagicMock()
            client.chat.completions.create.return_value = response
            wrap_openai_client(client).chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": "classify"}],
                **req,
            )
        return _traced(go)

    def test_chat_json_object_output_sets_parsed_and_flag(self):
        obj = {"intent": "question", "confidence": 0.94, "entities": ["Leer"]}
        resp = {
            "id": "c1", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(obj)},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
        }
        llm = _llm(_step(self._chat(resp, response_format={"type": "json_object"})))
        assert llm["output"].get("parsed") == obj
        assert llm["meta"].get("output_is_json") is True

    def test_plain_text_output_is_not_structured(self):
        resp = {
            "id": "c2", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello there!"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        llm = _llm(_step(self._chat(resp)))
        assert llm["output"].get("parsed") is None
        assert llm["meta"].get("output_is_json") is False

    def test_refusal_text_is_not_structured(self):
        resp = {
            "id": "c3", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None,
                                                 "refusal": "I can't help with that."},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        llm = _llm(_step(self._chat(resp)))
        assert llm["output"].get("parsed") is None
        assert llm["meta"].get("output_is_json") is False

    def test_responses_json_output_sets_parsed(self):
        obj = {"answer": 42, "unit": "meaning"}
        resp = {
            "id": "r1", "object": "response", "model": "gpt-4.1", "status": "completed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(obj)}]}],
            "usage": {"input_tokens": 6, "output_tokens": 5, "total_tokens": 11},
        }

        def go(run):
            client = MagicMock()
            client.responses.create.return_value = resp
            wrap_openai_client(client).responses.create(
                model="gpt-4.1", input="q",
                text={"format": {"type": "json_schema", "name": "ans", "schema": {}}},
            )
        llm = _llm(_step(_traced(go)))
        assert llm["output"].get("parsed") == obj
        assert llm["meta"].get("output_is_json") is True

    def test_anthropic_json_text_output_sets_parsed(self):
        arr = [{"k": 1}, {"k": 2}]
        resp = {
            "id": "a1", "model": "claude-sonnet-4", "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(arr)}],
            "usage": {"input_tokens": 7, "output_tokens": 9},
        }

        def go(run):
            client = MagicMock()
            client.messages.create.return_value = resp
            wrap_anthropic_client(client).messages.create(
                model="claude-sonnet-4", max_tokens=64,
                messages=[{"role": "user", "content": "list"}],
            )
        llm = _llm(_step(_traced(go)))
        assert llm["output"].get("parsed") == arr
        assert llm["meta"].get("output_is_json") is True

    def test_anthropic_tool_use_structured_stays_in_tool_calls(self):
        """Anthropic structured-via-forced-tool keeps its object in
        ``tool_calls[].arguments`` and is NOT mislabeled as a JSON text output."""
        struct = {"city": "Paris", "days": 3}
        resp = {
            "id": "a2", "model": "claude-sonnet-4", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "extract", "input": struct}],
            "usage": {"input_tokens": 7, "output_tokens": 9},
        }

        def go(run):
            client = MagicMock()
            client.messages.create.return_value = resp
            wrap_anthropic_client(client).messages.create(
                model="claude-sonnet-4", max_tokens=64,
                messages=[{"role": "user", "content": "extract"}],
            )
        llm = _llm(_step(_traced(go)))
        assert llm["output"].get("parsed") is None
        assert llm["meta"].get("output_is_json") is False
        assert llm["output"]["tool_calls"][0]["arguments"] == struct


# ---------------------------------------------------------------------------
# G-A1 — .parse() helpers must be instrumented
# ---------------------------------------------------------------------------

class TestParseHelperInstrumentation:

    def test_chat_parse_creates_step(self):
        obj = {"name": "Ada", "age": 36}
        resp = {
            "id": "p1", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant",
                                                 "content": json.dumps(obj), "parsed": obj},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
        }

        def go(run):
            client = MagicMock()
            client.chat.completions.parse.return_value = resp
            wrap_openai_client(client).chat.completions.parse(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
                response_format={"type": "json_object"},
            )
        s = _step(_traced(go))
        assert s.status == "completed"
        assert s.metadata.get("capture") != "partial"
        llm = _llm(s)
        assert llm["output"].get("parsed") == obj
        assert llm["meta"].get("output_is_json") is True

    def test_responses_parse_creates_step(self):
        obj = {"ok": True}
        resp = {
            "id": "p2", "object": "response", "model": "gpt-4.1", "status": "completed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(obj)}]}],
            "output_parsed": obj,
            "usage": {"input_tokens": 6, "output_tokens": 5, "total_tokens": 11},
        }

        def go(run):
            client = MagicMock()
            client.responses.parse.return_value = resp
            wrap_openai_client(client).responses.parse(
                model="gpt-4.1", input="x",
                text_format={"type": "json_schema"},
            )
        s = _step(_traced(go))
        assert s.status == "completed"
        llm = _llm(s)
        assert llm["output"].get("parsed") == obj

    def test_beta_chat_parse_creates_step(self):
        obj = {"label": "spam"}
        resp = {
            "id": "p3", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant",
                                                 "content": json.dumps(obj), "parsed": obj},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
        }

        def go(run):
            client = MagicMock()
            client.beta.chat.completions.parse.return_value = resp
            wrap_openai_client(client).beta.chat.completions.parse(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
                response_format={"type": "json_object"},
            )
        s = _step(_traced(go))
        assert s.status == "completed"
        assert _llm(s)["output"].get("parsed") == obj

    def test_parse_with_non_serializable_response_format_still_captures(self):
        """`.parse()` is normally called with a pydantic *class* as
        ``response_format``; a non-dict kwarg must not degrade capture."""
        class _SchemaModel:  # stand-in for a pydantic model class
            pass

        resp = {
            "id": "p4", "model": "gpt-4.1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}", "parsed": {}},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
        }

        def go(run):
            client = MagicMock()
            client.chat.completions.parse.return_value = resp
            wrap_openai_client(client).chat.completions.parse(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}],
                response_format=_SchemaModel,
            )
        s = _step(_traced(go))
        assert s.status == "completed"
        assert s.metadata.get("capture") != "partial"


# ---------------------------------------------------------------------------
# Streaming structured parity
# ---------------------------------------------------------------------------

class TestStreamingStructuredParity:

    def test_streaming_json_output_sets_parsed(self):
        obj = {"a": 1}
        chunks = [
            {"id": "s1", "model": "gpt-4.1", "choices": [{"index": 0, "delta": {"content": '{"a":'}}]},
            {"id": "s1", "model": "gpt-4.1", "choices": [{"index": 0, "delta": {"content": "1}"}}]},
            {"id": "s1", "model": "gpt-4.1", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}},
        ]

        def go(run):
            client = MagicMock()
            client.chat.completions.create.return_value = _FakeStream(chunks)
            stream = wrap_openai_client(client).chat.completions.create(
                model="gpt-4.1", messages=[{"role": "user", "content": "x"}], stream=True,
            )
            for _ in stream:
                pass
        llm = _llm(_step(_traced(go)))
        # Text reassembles from the literal deltas (no whitespace).
        assert llm["output"]["text"] == '{"a":1}'
        assert llm["output"].get("parsed") == obj
        assert llm["meta"].get("output_is_json") is True
