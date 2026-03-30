from leer.integrations.normalize import (
    normalize_anthropic,
    normalize_openai,
    NormalizedLLMCall,
)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _openai_request() -> dict:
    return {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0.7,
        "max_tokens": 200,
    }


def _openai_response() -> dict:
    return {
        "id": "chatcmpl-abc123",
        "model": "gpt-4.1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hi there! How can I help?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "total_tokens": 28,
        },
    }


def test_openai_basic():
    n = normalize_openai(_openai_request(), _openai_response(), latency_ms=350)

    assert n.provider == "openai"
    assert n.model == "gpt-4.1"

    assert n.input.system == "You are a helpful assistant."
    assert len(n.input.messages) == 1
    assert n.input.messages[0]["role"] == "user"
    assert n.input.params == {"temperature": 0.7, "max_tokens": 200}

    assert n.output.text == "Hi there! How can I help?"
    assert n.output.tool_calls == []

    assert n.usage.prompt_tokens == 20
    assert n.usage.completion_tokens == 8
    assert n.usage.total_tokens == 28

    assert n.meta.latency_ms == 350
    assert n.meta.finish_reason == "stop"
    assert n.meta.request_id == "chatcmpl-abc123"
    assert n.meta.status == "ok"


def test_openai_with_tool_calls():
    resp = _openai_response()
    resp["choices"][0]["message"]["content"] = None
    resp["choices"][0]["message"]["tool_calls"] = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
        }
    ]
    resp["choices"][0]["finish_reason"] = "tool_calls"

    n = normalize_openai(_openai_request(), resp)

    assert n.output.text is None
    assert len(n.output.tool_calls) == 1
    assert n.output.tool_calls[0]["function"]["name"] == "get_weather"
    assert n.meta.finish_reason == "tool_calls"


def test_openai_empty_response():
    n = normalize_openai({"model": "gpt-4.1"}, {})

    assert n.provider == "openai"
    assert n.model == "gpt-4.1"
    assert n.input.system is None
    assert n.input.messages == []
    assert n.output.text is None
    assert n.usage.prompt_tokens is None
    assert n.meta.finish_reason is None
    assert n.meta.status == "ok"


def test_openai_model_falls_back_to_request():
    n = normalize_openai({"model": "gpt-4.1", "messages": []}, {"choices": []})
    assert n.model == "gpt-4.1"


def test_openai_to_dict_shape():
    n = normalize_openai(_openai_request(), _openai_response(), latency_ms=100)
    d = n.to_dict()

    assert d["provider"] == "openai"
    assert d["model"] == "gpt-4.1"
    assert isinstance(d["input"], dict)
    assert isinstance(d["output"], dict)
    assert isinstance(d["usage"], dict)
    assert isinstance(d["meta"], dict)
    assert d["input"]["system"] == "You are a helpful assistant."
    assert d["usage"]["total_tokens"] == 28
    assert d["meta"]["latency_ms"] == 100


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _anthropic_request() -> dict:
    return {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": "You are a helpful assistant.",
        "messages": [
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0.5,
    }


def _anthropic_response() -> dict:
    return {
        "id": "msg_abc123",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-20250514",
        "content": [
            {"type": "text", "text": "Hi! How can I help you today?"}
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 15,
            "output_tokens": 10,
        },
    }


def test_anthropic_basic():
    n = normalize_anthropic(_anthropic_request(), _anthropic_response(), latency_ms=600)

    assert n.provider == "anthropic"
    assert n.model == "claude-sonnet-4-20250514"

    assert n.input.system == "You are a helpful assistant."
    assert len(n.input.messages) == 1
    assert n.input.messages[0]["role"] == "user"
    assert n.input.params == {"max_tokens": 1024, "temperature": 0.5}

    assert n.output.text == "Hi! How can I help you today?"
    assert n.output.tool_calls == []

    assert n.usage.prompt_tokens == 15
    assert n.usage.completion_tokens == 10
    assert n.usage.total_tokens == 25

    assert n.meta.latency_ms == 600
    assert n.meta.finish_reason == "end_turn"
    assert n.meta.request_id == "msg_abc123"
    assert n.meta.status == "ok"


def test_anthropic_with_tool_use():
    resp = _anthropic_response()
    resp["content"] = [
        {"type": "text", "text": "Let me check the weather."},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "get_weather",
            "input": {"city": "Paris"},
        },
    ]
    resp["stop_reason"] = "tool_use"

    n = normalize_anthropic(_anthropic_request(), resp)

    assert n.output.text == "Let me check the weather."
    assert len(n.output.tool_calls) == 1
    assert n.output.tool_calls[0]["function"]["name"] == "get_weather"
    assert n.output.tool_calls[0]["function"]["arguments"] == {"city": "Paris"}
    assert n.meta.finish_reason == "tool_use"


def test_anthropic_system_as_list():
    req = _anthropic_request()
    req["system"] = [
        {"type": "text", "text": "You are helpful."},
        {"type": "text", "text": "Be concise."},
    ]

    n = normalize_anthropic(req, _anthropic_response())
    assert n.input.system == "You are helpful. Be concise."


def test_anthropic_empty_response():
    n = normalize_anthropic({"model": "claude-sonnet-4-20250514"}, {})

    assert n.provider == "anthropic"
    assert n.model == "claude-sonnet-4-20250514"
    assert n.input.system is None
    assert n.input.messages == []
    assert n.output.text is None
    assert n.usage.prompt_tokens is None
    assert n.usage.total_tokens is None
    assert n.meta.status == "ok"


def test_anthropic_to_dict_shape():
    n = normalize_anthropic(_anthropic_request(), _anthropic_response(), latency_ms=200)
    d = n.to_dict()

    assert d["provider"] == "anthropic"
    assert d["model"] == "claude-sonnet-4-20250514"
    assert d["input"]["system"] == "You are a helpful assistant."
    assert d["output"]["text"] == "Hi! How can I help you today?"
    assert d["usage"]["total_tokens"] == 25
    assert d["meta"]["latency_ms"] == 200


# ---------------------------------------------------------------------------
# Cross-provider consistency
# ---------------------------------------------------------------------------

def test_both_normalizers_produce_same_type():
    a = normalize_openai(_openai_request(), _openai_response())
    b = normalize_anthropic(_anthropic_request(), _anthropic_response())

    assert type(a) is type(b) is NormalizedLLMCall

    da = a.to_dict()
    db = b.to_dict()
    assert set(da.keys()) == set(db.keys())
    assert set(da["input"].keys()) == set(db["input"].keys())
    assert set(da["output"].keys()) == set(db["output"].keys())
    assert set(da["usage"].keys()) == set(db["usage"].keys())
    assert set(da["meta"].keys()) == set(db["meta"].keys())
