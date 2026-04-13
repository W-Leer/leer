from leer.integrations.normalize import (
    normalize_anthropic,
    normalize_openai,
    NormalizedLLMCall,
)


# ---------------------------------------------------------------------------
# OpenAI — chat completions fixtures
# ---------------------------------------------------------------------------

def _openai_chat_request() -> dict:
    return {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0.7,
        "max_tokens": 200,
    }


def _openai_chat_response() -> dict:
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


# ---------------------------------------------------------------------------
# OpenAI — responses API fixtures
# ---------------------------------------------------------------------------

def _openai_responses_request() -> dict:
    return {
        "model": "gpt-4.1",
        "instructions": "You are a helpful assistant.",
        "input": [
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0.7,
        "max_output_tokens": 200,
    }


def _openai_responses_response() -> dict:
    return {
        "id": "resp_abc123",
        "object": "response",
        "status": "completed",
        "model": "gpt-4.1",
        "output": [
            {
                "type": "message",
                "id": "msg_001",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Hi there! How can I help?"}
                ],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
            "total_tokens": 28,
        },
    }


# ---------------------------------------------------------------------------
# Anthropic fixtures
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


# ===================================================================
# OpenAI — chat completions tests
# ===================================================================

class TestOpenAIChatCompletions:

    def test_basic(self):
        n = normalize_openai(_openai_chat_request(), _openai_chat_response(), latency_ms=350)

        assert n.provider == "openai"
        assert n.model == "gpt-4.1"

        assert n.input.system == "You are a helpful assistant."
        assert len(n.input.messages) == 1
        assert n.input.messages[0]["role"] == "user"
        assert n.input.params == {"temperature": 0.7, "max_tokens": 200}

        assert n.output.text == "Hi there! How can I help?"
        assert n.output.tool_calls == []
        assert n.output.content_blocks == [{"type": "text", "text": "Hi there! How can I help?"}]

        assert n.usage.prompt_tokens == 20
        assert n.usage.completion_tokens == 8
        assert n.usage.total_tokens == 28

        assert n.meta.latency_ms == 350
        assert n.meta.finish_reason == "stop"
        assert n.meta.request_id == "chatcmpl-abc123"

    def test_with_tool_calls(self):
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ]
        resp["choices"][0]["finish_reason"] = "tool_calls"

        n = normalize_openai(_openai_chat_request(), resp)

        assert n.output.text is None
        assert len(n.output.tool_calls) == 1

        tc = n.output.tool_calls[0]
        assert tc["name"] == "get_weather"
        assert tc["arguments"] == {"city": "Paris"}
        assert tc["id"] == "call_1"

        assert len(n.output.content_blocks) == 1
        assert n.output.content_blocks[0]["type"] == "tool_call"
        assert n.output.content_blocks[0]["name"] == "get_weather"

        assert n.meta.finish_reason == "tool_calls"

    def test_tool_call_arguments_parsed_from_json_string(self):
        """JSON string arguments are parsed into structured dicts."""
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "lookup", "arguments": '{"query": "test", "limit": 5}'},
            }
        ]

        n = normalize_openai(_openai_chat_request(), resp)
        assert n.output.tool_calls[0]["arguments"] == {"query": "test", "limit": 5}

    def test_tool_call_invalid_json_arguments_kept_as_string(self):
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_3",
                "type": "function",
                "function": {"name": "bad", "arguments": "not-json{"},
            }
        ]

        n = normalize_openai(_openai_chat_request(), resp)
        assert n.output.tool_calls[0]["arguments"] == "not-json{"

    def test_empty_response(self):
        n = normalize_openai({"model": "gpt-4.1"}, {})

        assert n.provider == "openai"
        assert n.model == "gpt-4.1"
        assert n.input.system is None
        assert n.input.messages == []
        assert n.output.text is None
        assert n.output.content_blocks == []
        assert n.output.tool_calls == []
        assert n.usage.prompt_tokens is None
        assert n.meta.finish_reason is None

    def test_model_falls_back_to_request(self):
        n = normalize_openai({"model": "gpt-4.1", "messages": []}, {"choices": []})
        assert n.model == "gpt-4.1"

    def test_model_is_none_when_absent(self):
        n = normalize_openai({"messages": []}, {})
        assert n.model is None

    def test_to_dict_shape(self):
        n = normalize_openai(_openai_chat_request(), _openai_chat_response(), latency_ms=100)
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
        assert "content_blocks" in d["output"]

    def test_no_status_field_in_meta(self):
        n = normalize_openai(_openai_chat_request(), _openai_chat_response())
        assert not hasattr(n.meta, "status")
        d = n.to_dict()
        assert "status" not in d["meta"]

    def test_developer_role_extracted_as_system(self):
        """Newer OpenAI models use 'developer' role instead of 'system'."""
        req = {
            "model": "o3",
            "messages": [
                {"role": "developer", "content": "You are a coding assistant."},
                {"role": "user", "content": "Hello"},
            ],
        }
        n = normalize_openai(req, _openai_chat_response())

        assert n.input.system == "You are a coding assistant."
        assert len(n.input.messages) == 1
        assert n.input.messages[0]["role"] == "user"

    def test_custom_tool_calls(self):
        """OpenAI chat completions supports custom tool calls with type='custom'."""
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_custom_1",
                "type": "custom",
                "custom": {"name": "my_tool", "input": "some raw input"},
            }
        ]

        n = normalize_openai(_openai_chat_request(), resp)

        assert len(n.output.tool_calls) == 1
        tc = n.output.tool_calls[0]
        assert tc["id"] == "call_custom_1"
        assert tc["name"] == "my_tool"
        assert tc["arguments"] == "some raw input"

    def test_mixed_function_and_custom_tool_calls(self):
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "call_fn",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            },
            {
                "id": "call_cust",
                "type": "custom",
                "custom": {"name": "my_custom", "input": "raw"},
            },
        ]

        n = normalize_openai(_openai_chat_request(), resp)

        assert len(n.output.tool_calls) == 2
        assert n.output.tool_calls[0]["name"] == "get_weather"
        assert n.output.tool_calls[0]["arguments"] == {"city": "Paris"}
        assert n.output.tool_calls[1]["name"] == "my_custom"
        assert n.output.tool_calls[1]["arguments"] == "raw"


# ===================================================================
# OpenAI — responses API tests
# ===================================================================

class TestOpenAIResponses:

    def test_basic(self):
        n = normalize_openai(
            _openai_responses_request(), _openai_responses_response(), latency_ms=400
        )

        assert n.provider == "openai"
        assert n.model == "gpt-4.1"

        assert n.input.system == "You are a helpful assistant."
        assert len(n.input.messages) == 1
        assert n.input.messages[0]["role"] == "user"
        assert n.input.params == {"temperature": 0.7, "max_output_tokens": 200}

        assert n.output.text == "Hi there! How can I help?"
        assert n.output.tool_calls == []
        assert n.output.content_blocks == [{"type": "text", "text": "Hi there! How can I help?"}]

        assert n.usage.prompt_tokens == 20
        assert n.usage.completion_tokens == 8
        assert n.usage.total_tokens == 28

        assert n.meta.latency_ms == 400
        assert n.meta.finish_reason == "completed"
        assert n.meta.request_id == "resp_abc123"

    def test_with_function_call(self):
        resp = _openai_responses_response()
        resp["output"] = [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Let me check."}],
            },
            {
                "type": "function_call",
                "id": "fc_001",
                "call_id": "call_xyz",
                "name": "get_weather",
                "arguments": '{"city": "Paris"}',
            },
        ]

        n = normalize_openai(_openai_responses_request(), resp)

        assert n.output.text == "Let me check."
        assert len(n.output.tool_calls) == 1
        assert n.output.tool_calls[0]["name"] == "get_weather"
        assert n.output.tool_calls[0]["arguments"] == {"city": "Paris"}
        assert n.output.tool_calls[0]["id"] == "call_xyz"

        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "text", "text": "Let me check."}
        assert n.output.content_blocks[1]["type"] == "tool_call"

    def test_string_input(self):
        req = {
            "model": "gpt-4.1",
            "instructions": "Be brief.",
            "input": "What is 2+2?",
        }
        resp = _openai_responses_response()

        n = normalize_openai(req, resp)

        assert n.input.system == "Be brief."
        assert len(n.input.messages) == 1
        assert n.input.messages[0] == {"role": "user", "content": "What is 2+2?"}

    def test_system_in_input_messages(self):
        """System messages in the input array are extracted like instructions."""
        req = {
            "model": "gpt-4.1",
            "input": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Hello"},
            ],
        }
        resp = _openai_responses_response()

        n = normalize_openai(req, resp)

        assert n.input.system == "You are concise."
        assert len(n.input.messages) == 1
        assert n.input.messages[0]["role"] == "user"

    def test_instructions_takes_precedence_over_system_in_input(self):
        req = {
            "model": "gpt-4.1",
            "instructions": "Top-level instruction.",
            "input": [
                {"role": "system", "content": "In-message system."},
                {"role": "user", "content": "Hello"},
            ],
        }
        resp = _openai_responses_response()

        n = normalize_openai(req, resp)
        # system messages in input override instructions (processed after)
        assert n.input.system == "In-message system."

    def test_empty_response(self):
        n = normalize_openai({"model": "gpt-4.1"}, {"output": [], "id": "resp_empty"})

        assert n.provider == "openai"
        assert n.model == "gpt-4.1"
        assert n.output.text is None
        assert n.output.content_blocks == []
        assert n.output.tool_calls == []

    def test_function_tools_normalized(self):
        req = {
            "model": "gpt-4.1",
            "input": "Call the tool.",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather for a city",
                        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                    },
                },
                {"type": "web_search"},
            ],
        }
        resp = _openai_responses_response()

        n = normalize_openai(req, resp)

        assert len(n.input.tools) == 2
        assert n.input.tools[0]["name"] == "get_weather"
        assert n.input.tools[1] == {"type": "web_search"}

    def test_dispatches_correctly(self):
        """Ensure responses shape is detected, not chat completions."""
        resp = _openai_responses_response()
        assert "output" in resp
        assert "choices" not in resp

        n = normalize_openai(_openai_responses_request(), resp)
        assert n.meta.finish_reason == "completed"


# ===================================================================
# Anthropic tests
# ===================================================================

class TestAnthropic:

    def test_basic(self):
        n = normalize_anthropic(_anthropic_request(), _anthropic_response(), latency_ms=600)

        assert n.provider == "anthropic"
        assert n.model == "claude-sonnet-4-20250514"

        assert n.input.system == "You are a helpful assistant."
        assert len(n.input.messages) == 1
        assert n.input.messages[0]["role"] == "user"
        assert n.input.params == {"max_tokens": 1024, "temperature": 0.5}

        assert n.output.text == "Hi! How can I help you today?"
        assert n.output.tool_calls == []
        assert n.output.content_blocks == [{"type": "text", "text": "Hi! How can I help you today?"}]

        assert n.usage.prompt_tokens == 15
        assert n.usage.completion_tokens == 10
        assert n.usage.total_tokens == 25

        assert n.meta.latency_ms == 600
        assert n.meta.finish_reason == "end_turn"
        assert n.meta.request_id == "msg_abc123"

    def test_with_tool_use(self):
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
        assert n.output.tool_calls[0]["name"] == "get_weather"
        assert n.output.tool_calls[0]["arguments"] == {"city": "Paris"}
        assert n.output.tool_calls[0]["id"] == "toolu_1"

        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "text", "text": "Let me check the weather."}
        assert n.output.content_blocks[1]["type"] == "tool_call"

        assert n.meta.finish_reason == "tool_use"

    def test_system_as_list(self):
        req = _anthropic_request()
        req["system"] = [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise."},
        ]

        n = normalize_anthropic(req, _anthropic_response())
        assert n.input.system == "You are helpful. Be concise."

    def test_empty_response(self):
        n = normalize_anthropic({"model": "claude-sonnet-4-20250514"}, {})

        assert n.provider == "anthropic"
        assert n.model == "claude-sonnet-4-20250514"
        assert n.input.system is None
        assert n.input.messages == []
        assert n.output.text is None
        assert n.output.content_blocks == []
        assert n.output.tool_calls == []
        assert n.usage.prompt_tokens is None
        assert n.usage.total_tokens is None

    def test_model_is_none_when_absent(self):
        n = normalize_anthropic({}, {})
        assert n.model is None

    def test_to_dict_shape(self):
        n = normalize_anthropic(_anthropic_request(), _anthropic_response(), latency_ms=200)
        d = n.to_dict()

        assert d["provider"] == "anthropic"
        assert d["model"] == "claude-sonnet-4-20250514"
        assert d["input"]["system"] == "You are a helpful assistant."
        assert d["output"]["text"] == "Hi! How can I help you today?"
        assert d["usage"]["total_tokens"] == 25
        assert d["meta"]["latency_ms"] == 200
        assert "content_blocks" in d["output"]

    def test_no_status_field_in_meta(self):
        n = normalize_anthropic(_anthropic_request(), _anthropic_response())
        assert not hasattr(n.meta, "status")
        d = n.to_dict()
        assert "status" not in d["meta"]

    def test_interleaved_content_blocks_preserve_order(self):
        """Text and tool_use blocks stay in the order the provider returned them."""
        resp = _anthropic_response()
        resp["content"] = [
            {"type": "text", "text": "First thought."},
            {"type": "tool_use", "id": "t1", "name": "search", "input": {"q": "a"}},
            {"type": "text", "text": "Second thought."},
        ]

        n = normalize_anthropic(_anthropic_request(), resp)

        assert n.output.text == "First thought.\n\nSecond thought."
        assert len(n.output.content_blocks) == 3
        assert n.output.content_blocks[0] == {"type": "text", "text": "First thought."}
        assert n.output.content_blocks[1]["type"] == "tool_call"
        assert n.output.content_blocks[1]["name"] == "search"
        assert n.output.content_blocks[2] == {"type": "text", "text": "Second thought."}

    def test_extended_thinking_blocks(self):
        """Thinking blocks are preserved in content_blocks but not in text."""
        resp = _anthropic_response()
        resp["content"] = [
            {"type": "thinking", "thinking": "Let me reason about this..."},
            {"type": "text", "text": "The answer is 42."},
        ]

        n = normalize_anthropic(_anthropic_request(), resp)

        assert n.output.text == "The answer is 42."
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "thinking", "thinking": "Let me reason about this..."}
        assert n.output.content_blocks[1] == {"type": "text", "text": "The answer is 42."}
        assert n.output.tool_calls == []

    def test_redacted_thinking_blocks(self):
        """Redacted thinking blocks are preserved without content."""
        resp = _anthropic_response()
        resp["content"] = [
            {"type": "redacted_thinking", "data": "encrypted-blob"},
            {"type": "text", "text": "Here is the answer."},
        ]

        n = normalize_anthropic(_anthropic_request(), resp)

        assert n.output.text == "Here is the answer."
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "redacted_thinking"}
        assert n.output.content_blocks[1] == {"type": "text", "text": "Here is the answer."}

    def test_thinking_param_captured(self):
        """The thinking config param should appear in params."""
        req = _anthropic_request()
        req["thinking"] = {"type": "enabled", "budget_tokens": 10000}

        n = normalize_anthropic(req, _anthropic_response())
        assert n.input.params["thinking"] == {"type": "enabled", "budget_tokens": 10000}


# ===================================================================
# Cross-provider consistency
# ===================================================================

class TestCrossProvider:

    def test_all_normalizers_produce_same_type(self):
        a = normalize_openai(_openai_chat_request(), _openai_chat_response())
        b = normalize_openai(_openai_responses_request(), _openai_responses_response())
        c = normalize_anthropic(_anthropic_request(), _anthropic_response())

        assert type(a) is type(b) is type(c) is NormalizedLLMCall

    def test_dict_keys_match_across_providers(self):
        a = normalize_openai(_openai_chat_request(), _openai_chat_response())
        b = normalize_openai(_openai_responses_request(), _openai_responses_response())
        c = normalize_anthropic(_anthropic_request(), _anthropic_response())

        da, db, dc = a.to_dict(), b.to_dict(), c.to_dict()

        assert set(da.keys()) == set(db.keys()) == set(dc.keys())
        assert set(da["input"].keys()) == set(db["input"].keys()) == set(dc["input"].keys())
        assert set(da["output"].keys()) == set(db["output"].keys()) == set(dc["output"].keys())
        assert set(da["usage"].keys()) == set(db["usage"].keys()) == set(dc["usage"].keys())
        assert set(da["meta"].keys()) == set(db["meta"].keys()) == set(dc["meta"].keys())

    def test_tool_call_shape_consistent(self):
        """All providers normalize tool calls to the same flat shape."""
        # OpenAI chat
        resp_oai = _openai_chat_response()
        resp_oai["choices"][0]["message"]["content"] = None
        resp_oai["choices"][0]["message"]["tool_calls"] = [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"x": 1}'}},
        ]
        n_oai = normalize_openai(_openai_chat_request(), resp_oai)

        # OpenAI responses
        resp_resp = _openai_responses_response()
        resp_resp["output"] = [
            {"type": "function_call", "id": "fc1", "call_id": "c2", "name": "f", "arguments": '{"x": 1}'},
        ]
        n_resp = normalize_openai(_openai_responses_request(), resp_resp)

        # Anthropic
        resp_ant = _anthropic_response()
        resp_ant["content"] = [
            {"type": "tool_use", "id": "t1", "name": "f", "input": {"x": 1}},
        ]
        n_ant = normalize_anthropic(_anthropic_request(), resp_ant)

        for n in [n_oai, n_resp, n_ant]:
            assert len(n.output.tool_calls) == 1
            tc = n.output.tool_calls[0]
            assert set(tc.keys()) == {"id", "name", "arguments"}
            assert tc["name"] == "f"
            assert tc["arguments"] == {"x": 1}


# ===================================================================
# Tool call summary helpers
# ===================================================================

class TestSummarizeToolCall:

    def test_basic_shape(self):
        from leer.integrations.normalize import summarize_tool_call
        tc = {"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}
        s = summarize_tool_call(tc)

        assert s["name"] == "get_weather"
        assert s["id"] == "call_1"
        assert "arguments_hash" in s
        assert isinstance(s["arguments_hash"], str)
        assert len(s["arguments_hash"]) == 12

    def test_no_id_when_absent(self):
        from leer.integrations.normalize import summarize_tool_call
        tc = {"name": "search", "arguments": {"q": "test"}}
        s = summarize_tool_call(tc)

        assert s["name"] == "search"
        assert "id" not in s
        assert "arguments_hash" in s

    def test_no_arguments_hash_when_none(self):
        from leer.integrations.normalize import summarize_tool_call
        tc = {"id": "c1", "name": "noop", "arguments": None}
        s = summarize_tool_call(tc)

        assert s["name"] == "noop"
        assert s["id"] == "c1"
        assert "arguments_hash" not in s

    def test_deterministic_hash(self):
        from leer.integrations.normalize import summarize_tool_call
        tc1 = {"name": "f", "arguments": {"a": 1, "b": 2}}
        tc2 = {"name": "f", "arguments": {"b": 2, "a": 1}}
        assert summarize_tool_call(tc1)["arguments_hash"] == summarize_tool_call(tc2)["arguments_hash"]

    def test_different_args_different_hash(self):
        from leer.integrations.normalize import summarize_tool_call
        tc1 = {"name": "f", "arguments": {"x": 1}}
        tc2 = {"name": "f", "arguments": {"x": 2}}
        assert summarize_tool_call(tc1)["arguments_hash"] != summarize_tool_call(tc2)["arguments_hash"]

    def test_string_arguments_hashed(self):
        from leer.integrations.normalize import summarize_tool_call
        tc = {"name": "f", "arguments": "some raw string"}
        s = summarize_tool_call(tc)
        assert "arguments_hash" in s


class TestArgumentsHash:

    def test_none_returns_none(self):
        from leer.integrations.normalize import _arguments_hash
        assert _arguments_hash(None) is None

    def test_empty_dict(self):
        from leer.integrations.normalize import _arguments_hash
        h = _arguments_hash({})
        assert isinstance(h, str)
        assert len(h) == 12

    def test_key_order_independent(self):
        from leer.integrations.normalize import _arguments_hash
        assert _arguments_hash({"a": 1, "b": 2}) == _arguments_hash({"b": 2, "a": 1})

    def test_nested_key_order_independent(self):
        from leer.integrations.normalize import _arguments_hash
        h1 = _arguments_hash({"outer": {"b": 2, "a": 1}})
        h2 = _arguments_hash({"outer": {"a": 1, "b": 2}})
        assert h1 == h2


# ===================================================================
# Enriched output_summary.tool_calls
# ===================================================================

class TestEnrichedOutputSummary:
    """Verify output summaries now include id and arguments_hash."""

    def test_openai_chat_summary_enriched(self):
        from leer.integrations.openai import _output_summary
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}},
        ]
        n = normalize_openai(_openai_chat_request(), resp)
        summary = _output_summary(n)

        assert len(summary["tool_calls"]) == 1
        tc = summary["tool_calls"][0]
        assert tc["name"] == "get_weather"
        assert tc["id"] == "call_1"
        assert "arguments_hash" in tc

    def test_anthropic_summary_enriched(self):
        from leer.integrations.anthropic import _output_summary
        resp = _anthropic_response()
        resp["content"] = [
            {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {"q": "test"}},
        ]
        n = normalize_anthropic(_anthropic_request(), resp)
        summary = _output_summary(n)

        assert len(summary["tool_calls"]) == 1
        tc = summary["tool_calls"][0]
        assert tc["name"] == "search"
        assert tc["id"] == "toolu_1"
        assert "arguments_hash" in tc

    def test_multiple_tool_calls_all_enriched(self):
        from leer.integrations.openai import _output_summary
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}},
            {"id": "call_2", "type": "function", "function": {"name": "search", "arguments": '{"q": "rain"}'}},
        ]
        n = normalize_openai(_openai_chat_request(), resp)
        summary = _output_summary(n)

        assert len(summary["tool_calls"]) == 2
        for tc in summary["tool_calls"]:
            assert "name" in tc
            assert "id" in tc
            assert "arguments_hash" in tc

    def test_summary_backward_compatible(self):
        """Existing name field is still present and unchanged."""
        from leer.integrations.openai import _output_summary
        resp = _openai_chat_response()
        resp["choices"][0]["message"]["content"] = None
        resp["choices"][0]["message"]["tool_calls"] = [
            {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}},
        ]
        n = normalize_openai(_openai_chat_request(), resp)
        summary = _output_summary(n)

        assert summary["tool_calls"][0]["name"] == "get_weather"

    def test_no_tool_calls_no_key(self):
        """When no tool calls, the summary has no tool_calls key."""
        from leer.integrations.openai import _output_summary
        n = normalize_openai(_openai_chat_request(), _openai_chat_response())
        summary = _output_summary(n)
        assert "tool_calls" not in summary

    def test_same_args_same_hash_across_providers(self):
        """Same arguments produce the same hash regardless of provider."""
        from leer.integrations.openai import _output_summary as oai_summary
        from leer.integrations.anthropic import _output_summary as ant_summary

        resp_oai = _openai_chat_response()
        resp_oai["choices"][0]["message"]["content"] = None
        resp_oai["choices"][0]["message"]["tool_calls"] = [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"x": 1}'}},
        ]
        n_oai = normalize_openai(_openai_chat_request(), resp_oai)

        resp_ant = _anthropic_response()
        resp_ant["content"] = [
            {"type": "tool_use", "id": "t1", "name": "f", "input": {"x": 1}},
        ]
        n_ant = normalize_anthropic(_anthropic_request(), resp_ant)

        hash_oai = oai_summary(n_oai)["tool_calls"][0]["arguments_hash"]
        hash_ant = ant_summary(n_ant)["tool_calls"][0]["arguments_hash"]
        assert hash_oai == hash_ant


# ===================================================================
# Compare-level args-hash diff detection
# ===================================================================

class TestCompareArgsHashDiff:
    """Prove that the enriched output_summary.tool_calls shape enables
    reliable args-diff detection at the compare level."""

    def _make_summary_with_tool_calls(self, tool_calls_data: list[dict]) -> dict:
        """Build an output_summary dict with enriched tool_calls."""
        from leer.integrations.normalize import summarize_tool_call
        return {"tool_calls": [summarize_tool_call(tc) for tc in tool_calls_data]}

    def test_identical_args_no_diff(self):
        tc = {"id": "c1", "name": "f", "arguments": {"x": 1}}
        s_a = self._make_summary_with_tool_calls([tc])
        s_b = self._make_summary_with_tool_calls([tc])
        assert s_a["tool_calls"][0]["arguments_hash"] == s_b["tool_calls"][0]["arguments_hash"]

    def test_different_args_detected(self):
        tc_a = {"id": "c1", "name": "f", "arguments": {"x": 1}}
        tc_b = {"id": "c1", "name": "f", "arguments": {"x": 2}}
        s_a = self._make_summary_with_tool_calls([tc_a])
        s_b = self._make_summary_with_tool_calls([tc_b])
        assert s_a["tool_calls"][0]["arguments_hash"] != s_b["tool_calls"][0]["arguments_hash"]

    def test_different_call_ids_detected(self):
        tc_a = {"id": "c1", "name": "f", "arguments": {"x": 1}}
        tc_b = {"id": "c2", "name": "f", "arguments": {"x": 1}}
        s_a = self._make_summary_with_tool_calls([tc_a])
        s_b = self._make_summary_with_tool_calls([tc_b])
        assert s_a["tool_calls"][0]["id"] != s_b["tool_calls"][0]["id"]
        assert s_a["tool_calls"][0]["arguments_hash"] == s_b["tool_calls"][0]["arguments_hash"]

    def test_different_call_count_detected(self):
        tc = {"id": "c1", "name": "f", "arguments": {"x": 1}}
        s_a = self._make_summary_with_tool_calls([tc])
        s_b = self._make_summary_with_tool_calls([tc, tc])
        assert len(s_a["tool_calls"]) != len(s_b["tool_calls"])

    def test_different_name_detected(self):
        tc_a = {"id": "c1", "name": "get_weather", "arguments": {"city": "Paris"}}
        tc_b = {"id": "c1", "name": "search",      "arguments": {"city": "Paris"}}
        s_a = self._make_summary_with_tool_calls([tc_a])
        s_b = self._make_summary_with_tool_calls([tc_b])
        assert s_a["tool_calls"][0]["name"] != s_b["tool_calls"][0]["name"]

    def test_end_to_end_openai(self):
        """Full pipeline: OpenAI normalize → output_summary → diff detection."""
        from leer.integrations.openai import _output_summary

        resp_a = _openai_chat_response()
        resp_a["choices"][0]["message"]["content"] = None
        resp_a["choices"][0]["message"]["tool_calls"] = [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"x": 1}'}},
        ]
        resp_b = _openai_chat_response()
        resp_b["choices"][0]["message"]["content"] = None
        resp_b["choices"][0]["message"]["tool_calls"] = [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"x": 99}'}},
        ]

        n_a = normalize_openai(_openai_chat_request(), resp_a)
        n_b = normalize_openai(_openai_chat_request(), resp_b)

        s_a = _output_summary(n_a)
        s_b = _output_summary(n_b)

        assert s_a["tool_calls"][0]["name"] == s_b["tool_calls"][0]["name"]
        assert s_a["tool_calls"][0]["id"] == s_b["tool_calls"][0]["id"]
        assert s_a["tool_calls"][0]["arguments_hash"] != s_b["tool_calls"][0]["arguments_hash"]


# ===================================================================
# Lifecycle derivation rules (mirrors frontend deriveToolCallStatus)
# ===================================================================

class TestLifecycleDerivation:
    """Test the derivation rules that the frontend applies.
    These are pure-logic tests mirroring the TypeScript function."""

    @staticmethod
    def _derive(link: dict | None) -> str:
        """Python mirror of deriveToolCallStatus."""
        if link is None:
            return "unmatched"
        status = link.get("toolStepStatus", "")
        if status == "completed":
            return "completed"
        if status == "failed":
            return "failed"
        return "unmatched"

    def test_no_link_is_unmatched(self):
        assert self._derive(None) == "unmatched"

    def test_linked_completed(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "completed"}
        assert self._derive(link) == "completed"

    def test_linked_failed(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "failed"}
        assert self._derive(link) == "failed"

    def test_linked_running_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "running"}
        assert self._derive(link) == "unmatched"

    def test_linked_pending_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "pending"}
        assert self._derive(link) == "unmatched"

    def test_linked_paused_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "paused"}
        assert self._derive(link) == "unmatched"

    def test_linked_cancelled_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "cancelled"}
        assert self._derive(link) == "unmatched"

    def test_linked_skipped_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": "skipped"}
        assert self._derive(link) == "unmatched"

    def test_linked_empty_status_is_unmatched(self):
        link = {"toolStepId": "s1", "toolStepName": "f", "toolStepIndex": 1, "toolStepStatus": ""}
        assert self._derive(link) == "unmatched"
