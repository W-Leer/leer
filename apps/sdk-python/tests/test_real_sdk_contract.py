"""Contract tests against the real OpenAI / Anthropic SDKs.

The wrappers duck-type provider clients and the rest of the suite uses fakes.
These tests drive the *real* SDK objects (dev dependencies) over an in-memory
HTTP transport, so they catch what fakes can't: helper methods that consume a
stream internally (``get_final_*``, ``until_done``, ``text_stream``), SDK
surfaces the wrappers don't intercept, and renamed internals. No network, no
API keys.

See ``docs/04-execution/provider-drift-assessment-2026-10.md`` (D-H1).
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest

openai = pytest.importorskip("openai")
anthropic = pytest.importorskip("anthropic")
httpx2 = pytest.importorskip("httpx2")
pydantic = pytest.importorskip("pydantic")

from anthropic.lib.streaming import MessageStream, MessageStreamManager  # noqa: E402
from openai.lib.streaming.chat import ChatCompletionStream  # noqa: E402
from real_sdk_harness import (  # noqa: E402
    anthropic_client as _anthropic,
    artifact_types as _artifact_types,
    json_response as _json_response,
    only_llm_step as _only_llm_step,
    openai_client as _openai,
    sse_response as _sse_response,
    traced as _traced,
)

MESSAGES = [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# Provider payloads
# ---------------------------------------------------------------------------

OPENAI_CHAT_CHUNKS = [
    {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": "gpt-test",
     "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hel"}, "finish_reason": None}]},
    {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": "gpt-test",
     "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]},
]


def _openai_response_obj(status: str, output: list[dict[str, Any]], usage: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": "resp_1", "object": "response", "created_at": 1, "model": "gpt-test",
        "status": status, "output": output, "parallel_tool_calls": True,
        "tool_choice": "auto", "tools": [], "usage": usage,
    }


_RESP_MSG_DONE = {
    "id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
    "content": [{"type": "output_text", "text": "Hello", "annotations": []}],
}
_RESP_USAGE = {
    "input_tokens": 5, "output_tokens": 2, "total_tokens": 7,
    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
    "output_tokens_details": {"reasoning_tokens": 0},
}
OPENAI_RESPONSES_EVENTS = [
    {"type": "response.created", "sequence_number": 0,
     "response": _openai_response_obj("in_progress", [], None)},
    {"type": "response.output_item.added", "sequence_number": 1, "output_index": 0,
     "item": {"id": "msg_1", "type": "message", "role": "assistant", "status": "in_progress", "content": []}},
    {"type": "response.content_part.added", "sequence_number": 2, "item_id": "msg_1",
     "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
    {"type": "response.output_text.delta", "sequence_number": 3, "item_id": "msg_1",
     "output_index": 0, "content_index": 0, "delta": "Hel", "logprobs": []},
    {"type": "response.output_text.delta", "sequence_number": 4, "item_id": "msg_1",
     "output_index": 0, "content_index": 0, "delta": "lo", "logprobs": []},
    {"type": "response.output_text.done", "sequence_number": 5, "item_id": "msg_1",
     "output_index": 0, "content_index": 0, "text": "Hello", "logprobs": []},
    {"type": "response.output_item.done", "sequence_number": 6, "output_index": 0, "item": _RESP_MSG_DONE},
    {"type": "response.completed", "sequence_number": 7,
     "response": _openai_response_obj("completed", [_RESP_MSG_DONE], _RESP_USAGE)},
]


def _anthropic_events(text_parts: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    for part in text_parts:
        events.append({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "text_delta", "text": part}})
    events += [
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 2}},
        {"type": "message_stop"},
    ]
    return events


def _anthropic_message(text: str) -> dict[str, Any]:
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }


# ---------------------------------------------------------------------------
# OpenAI .stream() helpers — every consumption style must be captured
# ---------------------------------------------------------------------------

_CHAT_CONSUMERS: dict[str, Callable[[Any], Any]] = {
    "iterate": lambda s: [e for e in s],
    "get_final_completion": lambda s: s.get_final_completion(),
    "until_done": lambda s: s.until_done(),
}


@pytest.mark.parametrize("consume", list(_CHAT_CONSUMERS), ids=list(_CHAT_CONSUMERS))
def test_openai_chat_stream_captures_every_consumption_style(consume: str) -> None:
    client = _openai(lambda req: _sse_response(OPENAI_CHAT_CHUNKS, named=False))
    seen: dict[str, Any] = {}

    def go() -> None:
        with client.chat.completions.stream(model="gpt-test", messages=MESSAGES) as stream:
            seen["stream"] = stream
            _CHAT_CONSUMERS[consume](stream)

    run = _traced(go)
    s = _only_llm_step(run)
    assert s.status == "completed"
    assert s.metadata["llm"]["output"]["text"] == "Hello"
    assert s.metadata["llm"]["meta"]["finish_reason"] == "stop"
    assert "llm_stream" in _artifact_types(run, s)
    # The caller keeps the genuine SDK stream object (full API, isinstance works).
    assert isinstance(seen["stream"], ChatCompletionStream)


_RESPONSES_CONSUMERS: dict[str, Callable[[Any], Any]] = {
    "iterate": lambda s: [e for e in s],
    "get_final_response": lambda s: s.get_final_response(),
}


@pytest.mark.parametrize("consume", list(_RESPONSES_CONSUMERS), ids=list(_RESPONSES_CONSUMERS))
def test_openai_responses_stream_captures_every_consumption_style(consume: str) -> None:
    client = _openai(lambda req: _sse_response(OPENAI_RESPONSES_EVENTS, named=True))

    def go() -> None:
        with client.responses.stream(model="gpt-test", input="hi") as stream:
            _RESPONSES_CONSUMERS[consume](stream)

    run = _traced(go)
    s = _only_llm_step(run)
    assert s.status == "completed"
    assert s.metadata["llm"]["output"]["text"] == "Hello"


def _responses_events_from(final: dict[str, Any]) -> list[dict[str, Any]]:
    """A realistic Responses event sequence that ends in ``final``."""
    seq = iter(range(1000))
    events: list[dict[str, Any]] = [{
        "type": "response.created", "sequence_number": next(seq),
        "response": {**final, "status": "in_progress", "output": [], "usage": None},
    }]
    for i, item in enumerate(final["output"]):
        base = {"output_index": i, "item_id": item["id"]}
        if item["type"] == "message":
            text = item["content"][0]["text"]
            events.append({"type": "response.output_item.added", "sequence_number": next(seq), "output_index": i,
                           "item": {**item, "status": "in_progress", "content": []}})
            events.append({"type": "response.content_part.added", "sequence_number": next(seq), **base,
                           "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}})
            events.append({"type": "response.output_text.delta", "sequence_number": next(seq), **base,
                           "content_index": 0, "delta": text, "logprobs": []})
            events.append({"type": "response.output_text.done", "sequence_number": next(seq), **base,
                           "content_index": 0, "text": text, "logprobs": []})
        elif item["type"] == "function_call":
            events.append({"type": "response.output_item.added", "sequence_number": next(seq), "output_index": i,
                           "item": {**item, "status": "in_progress", "arguments": ""}})
            events.append({"type": "response.function_call_arguments.delta", "sequence_number": next(seq), **base,
                           "delta": item["arguments"]})
            events.append({"type": "response.function_call_arguments.done", "sequence_number": next(seq), **base,
                           "name": item["name"], "arguments": item["arguments"]})
        events.append({"type": "response.output_item.done", "sequence_number": next(seq), "output_index": i,
                       "item": item})
    events.append({"type": "response.completed", "sequence_number": next(seq), "response": final})
    return events


_PHASED_FINAL = _openai_response_obj("completed", [
    {"id": "msg_c", "type": "message", "role": "assistant", "status": "completed", "phase": "commentary",
     "content": [{"type": "output_text", "text": "Let me look that up.", "annotations": []}]},
    {"id": "fc_1", "type": "function_call", "call_id": "call_1", "name": "search", "namespace": "github",
     "arguments": "{\"q\": \"login\"}", "status": "completed"},
    {"id": "msg_f", "type": "message", "role": "assistant", "status": "completed", "phase": "final_answer",
     "content": [{"type": "output_text", "text": "{\"answer\": 42}", "annotations": []}]},
], _RESP_USAGE)


@pytest.mark.parametrize("surface", ["stream_helper", "create_stream_true"])
def test_openai_responses_streaming_matches_non_streaming(surface: str) -> None:
    """Phase, namespace and item order survive streaming exactly as in create()."""
    events = _responses_events_from(_PHASED_FINAL)
    streaming_client = _openai(lambda req: _sse_response(events, named=True))

    def go_stream() -> None:
        if surface == "stream_helper":
            with streaming_client.responses.stream(model="gpt-test", input="hi") as stream:
                stream.get_final_response()
        else:
            for _ in streaming_client.responses.create(model="gpt-test", input="hi", stream=True):
                pass

    streamed = _only_llm_step(_traced(go_stream)).metadata["llm"]
    plain = _only_llm_step(_traced(lambda: _openai(lambda req: _json_response(_PHASED_FINAL)).responses.create(
        model="gpt-test", input="hi",
    ))).metadata["llm"]

    assert streamed["output"] == plain["output"]
    assert streamed["usage"] == plain["usage"]
    assert streamed["model"] == plain["model"]
    assert streamed["meta"]["finish_reason"] == plain["meta"]["finish_reason"]
    assert streamed["output"]["text"] == '{"answer": 42}'
    assert streamed["output"]["tool_calls"][0]["namespace"] == "github"


# ---------------------------------------------------------------------------
# Anthropic messages.stream()
# ---------------------------------------------------------------------------

_ANTHROPIC_CONSUMERS: dict[str, Callable[[Any], Any]] = {
    "iterate": lambda s: [e for e in s],
    "text_stream": lambda s: [t for t in s.text_stream],
    "until_done": lambda s: s.until_done(),
    "get_final_message": lambda s: s.get_final_message(),
    "get_final_text": lambda s: s.get_final_text(),
}


@pytest.mark.parametrize("consume", list(_ANTHROPIC_CONSUMERS), ids=list(_ANTHROPIC_CONSUMERS))
def test_anthropic_messages_stream_captures_every_consumption_style(consume: str) -> None:
    client = _anthropic(lambda req: _sse_response(_anthropic_events(["Hel", "lo"]), named=True))
    seen: dict[str, Any] = {}

    def go() -> None:
        with client.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES) as stream:
            seen["stream"] = stream
            _ANTHROPIC_CONSUMERS[consume](stream)

    run = _traced(go)
    s = _only_llm_step(run)
    assert s.status == "completed"
    llm = s.metadata["llm"]
    assert llm["output"]["text"] == "Hello"
    assert llm["meta"]["finish_reason"] == "end_turn"
    assert llm["usage"]["prompt_tokens"] == 5
    assert llm["usage"]["completion_tokens"] == 2
    assert "llm_stream" in _artifact_types(run, s)
    assert isinstance(seen["stream"], MessageStream)


def test_anthropic_messages_stream_matches_non_streaming_canonical_output() -> None:
    """Streaming <-> non-streaming parity for the stream() helper."""
    streamed = _traced(lambda: _anthropic(
        lambda req: _sse_response(_anthropic_events(["Hel", "lo"]), named=True)
    ).messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES).__enter__().until_done())
    plain = _traced(lambda: _anthropic(
        lambda req: _json_response(_anthropic_message("Hello"))
    ).messages.create(model="claude-test", max_tokens=16, messages=MESSAGES))

    a = _only_llm_step(streamed).metadata["llm"]
    b = _only_llm_step(plain).metadata["llm"]
    for key in ("output", "usage"):
        assert a[key] == b[key], key
    assert a["meta"]["finish_reason"] == b["meta"]["finish_reason"]


def _anthropic_events_from(message: dict[str, Any]) -> list[dict[str, Any]]:
    """A realistic Anthropic event sequence that streams ``message``."""
    events: list[dict[str, Any]] = [{"type": "message_start", "message": {
        **message, "content": [], "stop_reason": None, "stop_details": None,
        "usage": {"input_tokens": message["usage"]["input_tokens"], "output_tokens": 0},
    }}]
    for i, block in enumerate(message["content"]):
        kind = block["type"]
        if kind == "text":
            events.append({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            events.append({"type": "content_block_delta", "index": i,
                           "delta": {"type": "text_delta", "text": block["text"]}})
        elif kind in ("tool_use", "server_tool_use"):
            events.append({"type": "content_block_start", "index": i, "content_block": {**block, "input": {}}})
            events.append({"type": "content_block_delta", "index": i,
                           "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        elif kind == "compaction":
            events.append({"type": "content_block_start", "index": i,
                           "content_block": {"type": "compaction", "content": None, "encrypted_content": None}})
            events.append({"type": "content_block_delta", "index": i, "delta": {
                "type": "compaction_delta", "content": block["content"],
                "encrypted_content": block.get("encrypted_content"),
            }})
        else:
            events.append({"type": "content_block_start", "index": i, "content_block": block})
        events.append({"type": "content_block_stop", "index": i})
    events += [
        {"type": "message_delta",
         "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None,
                   "stop_details": message.get("stop_details")},
         "usage": {"output_tokens": message["usage"]["output_tokens"]}},
        {"type": "message_stop"},
    ]
    return events


_SERVER_TOOL_MESSAGE = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [
        {"type": "text", "text": "Let me search."},
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "leer"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
            {"type": "web_search_result", "url": "https://leer.dev", "title": "Leer",
             "encrypted_content": "Eq…", "page_age": None}]},
        {"type": "text", "text": "Leer records agent runs."},
        {"type": "tool_use", "id": "toolu_1", "name": "save_note", "input": {"note": "done"}},
    ],
    "stop_reason": "tool_use", "stop_sequence": None,
    "usage": {"input_tokens": 5, "output_tokens": 9},
}

_REFUSAL_MESSAGE = {
    "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [], "stop_reason": "refusal", "stop_sequence": None,
    "stop_details": {"type": "refusal", "category": "cyber", "explanation": "Looks like malware."},
    "usage": {"input_tokens": 5, "output_tokens": 0},
}


@pytest.mark.parametrize("message", [_SERVER_TOOL_MESSAGE, _REFUSAL_MESSAGE], ids=["server_tool", "refusal"])
@pytest.mark.parametrize("surface", ["stream_helper", "create_stream_true"])
def test_anthropic_streaming_matches_non_streaming_block_by_block(surface: str, message: dict[str, Any]) -> None:
    """Server-tool blocks, separate text blocks, order and stop_details survive streaming."""
    events = _anthropic_events_from(message)
    client = _anthropic(lambda req: _sse_response(events, named=True))

    def go_stream() -> None:
        if surface == "stream_helper":
            with client.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES) as stream:
                stream.get_final_message()
        else:
            for _ in client.messages.create(model="claude-test", max_tokens=16, messages=MESSAGES, stream=True):
                pass

    streamed = _only_llm_step(_traced(go_stream)).metadata["llm"]
    plain = _only_llm_step(_traced(lambda: _anthropic(lambda req: _json_response(message)).messages.create(
        model="claude-test", max_tokens=16, messages=MESSAGES,
    ))).metadata["llm"]

    assert streamed["output"] == plain["output"]
    assert streamed["usage"] == plain["usage"]
    assert streamed["meta"]["finish_reason"] == plain["meta"]["finish_reason"]
    assert streamed["meta"]["refusal"] == plain["meta"]["refusal"]
    assert streamed["meta"]["refusal_category"] == plain["meta"]["refusal_category"]


def test_anthropic_server_tool_stream_shape() -> None:
    client = _anthropic(lambda req: _sse_response(_anthropic_events_from(_SERVER_TOOL_MESSAGE), named=True))
    run = _traced(lambda: client.messages.stream(
        model="claude-test", max_tokens=16, messages=MESSAGES).__enter__().until_done())
    out = _only_llm_step(run).metadata["llm"]["output"]
    assert [b["type"] for b in out["content_blocks"]] == ["text", "provider_tool", "text", "tool_call"]
    assert out["text"] == "Let me search.\n\nLeer records agent runs."
    assert [tc["name"] for tc in out["tool_calls"]] == ["save_note"]


_OPENAI_TOOLS_FINAL = _openai_response_obj("completed", [
    {"id": "rs_1", "type": "reasoning", "summary": [{"type": "summary_text", "text": "Search first."}]},
    {"id": "ws_1", "type": "web_search_call", "status": "completed",
     "action": {"type": "search", "query": "leer"}},
    {"id": "mcp_1", "type": "mcp_call", "name": "read_wiki", "server_label": "deepwiki",
     "arguments": "{\"repo\": \"leer\"}", "output": "page", "status": "completed"},
    {"id": "msg_f", "type": "message", "role": "assistant", "status": "completed",
     "content": [{"type": "output_text", "text": "Done.", "annotations": []}]},
], _RESP_USAGE)


def test_openai_responses_provider_tools_stream_like_create() -> None:
    events = _responses_events_from(_OPENAI_TOOLS_FINAL)
    streamed = _only_llm_step(_traced(lambda: _openai(lambda req: _sse_response(events, named=True))
                                      .responses.stream(model="gpt-test", input="hi")
                                      .__enter__().get_final_response())).metadata["llm"]
    plain = _only_llm_step(_traced(lambda: _openai(lambda req: _json_response(_OPENAI_TOOLS_FINAL))
                                   .responses.create(model="gpt-test", input="hi"))).metadata["llm"]
    assert streamed["output"] == plain["output"]
    assert [b["type"] for b in plain["output"]["content_blocks"]] == [
        "thinking", "provider_tool", "provider_tool", "text"]


def test_anthropic_messages_stream_outside_trace_is_passthrough() -> None:
    client = _anthropic(lambda req: _sse_response(_anthropic_events(["Hi"]), named=True))
    manager = client.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES)
    assert isinstance(manager, MessageStreamManager)
    with manager as stream:
        assert stream.get_final_text() == "Hi"


def test_anthropic_messages_stream_error_event_marks_step_failed() -> None:
    events = _anthropic_events(["Hel"])[:3] + [
        {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
    ]
    client = _anthropic(lambda req: _sse_response(events, named=True))

    def go() -> None:
        with pytest.raises(anthropic.APIStatusError):
            with client.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES) as stream:
                stream.until_done()

    run = _traced(go)
    s = _only_llm_step(run)
    assert s.status == "failed"


def test_anthropic_create_stream_true_still_captured() -> None:
    client = _anthropic(lambda req: _sse_response(_anthropic_events(["Hel", "lo"]), named=True))
    run = _traced(lambda: list(client.messages.create(
        model="claude-test", max_tokens=16, messages=MESSAGES, stream=True,
    )))
    assert _only_llm_step(run).metadata["llm"]["output"]["text"] == "Hello"


# ---------------------------------------------------------------------------
# Anthropic messages.parse() — native structured outputs
# ---------------------------------------------------------------------------

class _Sentiment(pydantic.BaseModel):
    sentiment: str
    score: float


def test_anthropic_messages_parse_captures_parsed_output() -> None:
    body = _anthropic_message(json.dumps({"sentiment": "positive", "score": 0.9}))
    client = _anthropic(lambda req: _json_response(body))
    seen: dict[str, Any] = {}

    def go() -> None:
        seen["result"] = client.messages.parse(
            model="claude-test", max_tokens=64, messages=MESSAGES, output_format=_Sentiment,
        )

    run = _traced(go)
    s = _only_llm_step(run)
    llm = s.metadata["llm"]
    assert llm["output"]["parsed"] == {"sentiment": "positive", "score": 0.9}
    assert llm["meta"]["output_is_json"] is True
    assert "output_format" in llm["input"]["params"], "requested schema must be recorded"
    # The caller still gets the SDK's typed result.
    assert seen["result"].parsed_output == _Sentiment(sentiment="positive", score=0.9)


# ---------------------------------------------------------------------------
# Anthropic client.beta.messages.*
# ---------------------------------------------------------------------------

def test_anthropic_beta_messages_create_is_captured() -> None:
    client = _anthropic(lambda req: _json_response(_anthropic_message("Hello")))
    run = _traced(lambda: client.beta.messages.create(
        model="claude-test", max_tokens=16, messages=MESSAGES,
    ))
    assert _only_llm_step(run).metadata["llm"]["output"]["text"] == "Hello"


def test_anthropic_beta_messages_stream_is_captured() -> None:
    client = _anthropic(lambda req: _sse_response(_anthropic_events(["Hel", "lo"]), named=True))

    def go() -> None:
        with client.beta.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES) as stream:
            stream.get_final_message()

    run = _traced(go)
    assert _only_llm_step(run).metadata["llm"]["output"]["text"] == "Hello"


def test_anthropic_other_beta_surfaces_still_reachable() -> None:
    client = _anthropic(lambda req: _json_response({}))
    assert hasattr(client.beta, "files")
    assert hasattr(client.beta.messages, "count_tokens")


# ---------------------------------------------------------------------------
# Anthropic client.beta.messages.tool_runner / thread (D-H5)
# ---------------------------------------------------------------------------

from anthropic import beta_tool  # noqa: E402
from anthropic.lib.tools import BetaStreamingToolRunner, BetaToolRunner  # noqa: E402
from real_sdk_harness import llm_steps as _llm_steps  # noqa: E402

_TOOL_USE_REPLY = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [{"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"city": "Paris"}}],
    "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 2},
}
_FINAL_REPLY = {
    "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [{"type": "text", "text": "It is 18C in Paris."}],
    "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 9, "output_tokens": 6},
}


@beta_tool
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"18C in {city}"


def _replying(*replies: dict[str, Any]) -> tuple[Callable[[Any], Any], list[dict[str, Any]]]:
    """Answer each request with the next reply, streamed when the request asks."""
    bodies: list[dict[str, Any]] = []

    def handler(req: Any) -> Any:
        body = json.loads(req.content)
        bodies.append(body)
        reply = replies[len(bodies) - 1]
        if body.get("stream"):
            return _sse_response(_anthropic_events_from(reply), named=True)
        return _json_response(reply)

    return handler, bodies


_RUNNER_MODES: dict[str, dict[str, Any]] = {
    "create": {},
    "stream": {"stream": True},
    "stream_eager": {"stream": True, "run_tools_eagerly": True},
}


@pytest.mark.parametrize("mode", list(_RUNNER_MODES), ids=list(_RUNNER_MODES))
def test_anthropic_tool_runner_records_every_turn(mode: str) -> None:
    options = _RUNNER_MODES[mode]
    streaming = bool(options.get("stream"))
    handler, bodies = _replying(_TOOL_USE_REPLY, _FINAL_REPLY)
    client = _anthropic(handler)
    replies: list[Any] = []

    def go() -> None:
        runner = client.beta.messages.tool_runner(
            model="claude-test", max_tokens=64, tools=[get_weather],
            messages=[{"role": "user", "content": "Weather in Paris?"}], **options,
        )
        assert isinstance(runner, BetaStreamingToolRunner if streaming else BetaToolRunner)
        for item in runner:
            replies.append(item.get_final_message() if streaming else item)

    run = _traced(go)

    assert [m.stop_reason for m in replies] == ["tool_use", "end_turn"]
    steps = _llm_steps(run)
    assert len(bodies) == 2
    assert len(steps) == 2
    first, second = (s.metadata["llm"] for s in steps)
    assert [tc["id"] for tc in first["output"]["tool_calls"]] == ["toolu_1"]
    assert first["input"]["params"]["thread"] == {"type": "create"}
    assert second["output"]["text"] == "It is 18C in Paris."
    assert second["input"]["params"]["thread"] == {"type": "continue", "previous_message_id": "msg_1"}
    assert second["input"]["messages"][0]["content"][0]["tool_use_id"] == "toolu_1"
    response_artifact = "llm_stream" if streaming else "llm_response"
    assert all(response_artifact in _artifact_types(run, s) for s in steps)
    assert all(s.status == "completed" for s in steps)
    assert all(s.parent_step_id is None for s in steps), "a turn must not nest under the previous turn"


def test_anthropic_tool_runner_streaming_matches_non_streaming() -> None:
    def canonical(mode: str) -> list[dict[str, Any]]:
        handler, _ = _replying(_TOOL_USE_REPLY, _FINAL_REPLY)
        client = _anthropic(handler)
        options = _RUNNER_MODES[mode]

        def go() -> None:
            for item in client.beta.messages.tool_runner(
                model="claude-test", max_tokens=64, tools=[get_weather],
                messages=[{"role": "user", "content": "Weather in Paris?"}], **options,
            ):
                if options:
                    item.get_final_message()

        return [s.metadata["llm"]["output"] for s in _llm_steps(_traced(go))]

    assert canonical("stream") == canonical("create")


def test_anthropic_thread_turns_are_recorded() -> None:
    handler, bodies = _replying(_anthropic_message("Hi"), {**_anthropic_message("Again"), "id": "msg_2"})
    client = _anthropic(handler)

    def go() -> None:
        thread = client.beta.messages.thread(model="claude-test", max_tokens=16)
        thread.send({"role": "user", "content": "hi"})
        with thread.stream({"role": "user", "content": "again"}) as stream:
            stream.get_final_message()

    run = _traced(go)

    steps = _llm_steps(run)
    assert len(bodies) == 2
    assert [s.metadata["llm"]["output"]["text"] for s in steps] == ["Hi", "Again"]
    assert "llm_response" in _artifact_types(run, steps[0])
    assert "llm_stream" in _artifact_types(run, steps[1])
    assert steps[1].metadata["llm"]["input"]["params"]["thread"]["previous_message_id"] == "msg_1"


def test_anthropic_tool_runner_outside_trace_is_passthrough() -> None:
    handler, bodies = _replying(_TOOL_USE_REPLY, _FINAL_REPLY)
    client = _anthropic(handler)
    runner = client.beta.messages.tool_runner(
        model="claude-test", max_tokens=64, tools=[get_weather],
        messages=[{"role": "user", "content": "Weather in Paris?"}],
    )
    assert isinstance(runner, BetaToolRunner)
    assert [m.stop_reason for m in runner] == ["tool_use", "end_turn"]
    assert len(bodies) == 2


# ---------------------------------------------------------------------------
# Compaction (ADR-003): OpenAI responses.compact() and compaction parts
# ---------------------------------------------------------------------------

from openai.types.responses import CompactedResponse  # noqa: E402

_COMPACTED = {
    "id": "cmp_resp_1", "object": "response.compaction", "created_at": 1,
    "output": [
        {"id": "msg_u1", "type": "message", "role": "user", "status": "completed",
         "content": [{"type": "input_text", "text": "Plan my trip"}]},
        {"id": "msg_u2", "type": "message", "role": "user", "status": "completed",
         "content": [{"type": "input_text", "text": "Make it cheaper"}]},
        {"id": "cmp_1", "type": "compaction", "encrypted_content": "gAAA…", "created_by": "user"},
    ],
    "usage": _RESP_USAGE,
}

_OPENAI_COMPACTION_PART = {
    "type": "compaction", "id": "cmp_1", "summary": None, "retained_messages": 2,
    "provider": "openai", "provider_part_type": "compaction",
    "preview_text": "context compacted (encrypted)",
}


def test_openai_responses_compact_is_recorded() -> None:
    paths: list[str] = []

    def handler(req: Any) -> Any:
        paths.append(req.url.path)
        return _json_response(_COMPACTED)

    client = _openai(handler)
    run = _traced(lambda: client.responses.compact(model="gpt-test", previous_response_id="resp_9"))

    step = _only_llm_step(run)
    llm = step.metadata["llm"]
    assert paths == ["/v1/responses/compact"]
    assert step.name == "gpt-test"
    assert llm["model"] == "gpt-test"
    assert llm["output"]["content_blocks"] == [_OPENAI_COMPACTION_PART]
    assert llm["output"]["text"] is None
    assert llm["usage"]["total_tokens"] == 7
    assert llm["meta"]["request_id"] == "cmp_resp_1"
    assert llm["input"]["params"]["previous_response_id"] == "resp_9"
    assert step.output_summary["compaction"] == "context compacted (encrypted)"
    assert {"llm_request", "llm_response"} <= _artifact_types(run, step)


def test_openai_responses_compact_outside_trace_is_passthrough() -> None:
    client = _openai(lambda req: _json_response(_COMPACTED))
    assert isinstance(client.responses.compact(model="gpt-test", input="hi"), CompactedResponse)


_AUTO_COMPACTED_FINAL = _openai_response_obj("completed", [
    {"id": "cmp_2", "type": "compaction", "encrypted_content": "gAAA…"},
    _RESP_MSG_DONE,
], _RESP_USAGE)


def test_openai_compaction_item_in_create_matches_stream() -> None:
    plain = _only_llm_step(_traced(lambda: _openai(lambda req: _json_response(_AUTO_COMPACTED_FINAL))
                                   .responses.create(model="gpt-test", input="hi"))).metadata["llm"]
    events = _responses_events_from(_AUTO_COMPACTED_FINAL)
    streamed = _only_llm_step(_traced(lambda: _openai(lambda req: _sse_response(events, named=True))
                                      .responses.stream(model="gpt-test", input="hi")
                                      .__enter__().get_final_response())).metadata["llm"]
    assert plain["output"]["content_blocks"] == [
        {"type": "compaction", "id": "cmp_2", "summary": None, "provider": "openai",
         "provider_part_type": "compaction", "preview_text": "context compacted (encrypted)"},
        {"type": "text", "text": "Hello"},
    ]
    assert plain["output"]["text"] == "Hello"
    assert streamed["output"] == plain["output"]


_COMPACTION_MESSAGE = {
    "id": "msg_c", "type": "message", "role": "assistant", "model": "claude-test",
    "content": [
        {"type": "compaction", "content": "User is planning a cheap trip.", "encrypted_content": "Eq…"},
        {"type": "text", "text": "Here is a cheaper plan."},
    ],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 5, "output_tokens": 9},
}


@pytest.mark.parametrize("surface", ["stream_helper", "create_stream_true"])
def test_anthropic_compaction_block_streams_like_create(surface: str) -> None:
    def go_stream() -> None:
        client = _anthropic(lambda req: _sse_response(_anthropic_events_from(_COMPACTION_MESSAGE), named=True))
        if surface == "stream_helper":
            with client.beta.messages.stream(model="claude-test", max_tokens=16, messages=MESSAGES) as stream:
                stream.get_final_message()
        else:
            for _ in client.beta.messages.create(model="claude-test", max_tokens=16, messages=MESSAGES, stream=True):
                pass

    streamed = _only_llm_step(_traced(go_stream)).metadata["llm"]
    plain = _only_llm_step(_traced(lambda: _anthropic(lambda req: _json_response(_COMPACTION_MESSAGE))
                                   .beta.messages.create(model="claude-test", max_tokens=16, messages=MESSAGES)
                                   )).metadata["llm"]

    assert plain["output"]["content_blocks"] == [
        {"type": "compaction", "summary": "User is planning a cheap trip.", "provider": "anthropic",
         "provider_part_type": "compaction", "preview_text": "User is planning a cheap trip."},
        {"type": "text", "text": "Here is a cheaper plan."},
    ]
    assert plain["output"]["text"] == "Here is a cheaper plan."
    assert streamed["output"] == plain["output"]


def test_anthropic_failed_compaction_has_no_summary() -> None:
    message = {**_COMPACTION_MESSAGE, "content": [{"type": "compaction", "content": None}]}
    run = _traced(lambda: _anthropic(lambda req: _json_response(message)).beta.messages.create(
        model="claude-test", max_tokens=16, messages=MESSAGES,
    ))
    step = _only_llm_step(run)
    assert step.metadata["llm"]["output"]["content_blocks"] == [
        {"type": "compaction", "summary": None, "provider": "anthropic",
         "provider_part_type": "compaction", "preview_text": "compaction produced no summary"},
    ]
    assert step.output_summary["compaction"] == "compaction produced no summary"
