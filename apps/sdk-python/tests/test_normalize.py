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


# ===================================================================
# Heuristic tool-call linkage (mirrors frontend buildToolCallLinkage)
# ===================================================================

def _make_step(
    *,
    id: str,
    step_type: str = "llm",
    name: str = "step",
    status: str = "completed",
    sequence_index: int = 0,
    parent_step_id: str | None = None,
    metadata: dict | None = None,
    tool_calls: list[dict] | None = None,
) -> dict:
    """Build a minimal timeline step dict matching the TimelineStep shape."""
    llm = None
    if step_type == "llm":
        llm = {
            "provider": "openai",
            "model": "gpt-4",
            "input": {"system": None, "messages": [], "tools": [], "params": {}},
            "output": {
                "text": None,
                "tool_calls": tool_calls or [],
                "content_blocks": [],
            },
            "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
            "meta": {"finish_reason": None, "request_id": None, "latency_ms": None},
        }
    return {
        "id": id,
        "parent_step_id": parent_step_id,
        "sequence_index": sequence_index,
        "name": name,
        "step_type": step_type,
        "status": status,
        "started_at": None,
        "ended_at": None,
        "input_summary": None,
        "output_summary": None,
        "error_summary": None,
        "metadata": metadata or {},
        "model_provider": None,
        "model_name": None,
        "duration_ms": None,
        "llm": llm,
        "artifacts": [],
    }


def _build_tool_call_linkage(steps: list[dict]) -> dict:
    """Python mirror of the TypeScript buildToolCallLinkage function.

    Faithfully replicates the exact same algorithm so tests validate
    the logic that runs in the frontend.
    """

    def _tool_step_name(step: dict) -> str:
        meta_name = (step.get("metadata") or {}).get("tool_name")
        if isinstance(meta_name, str) and meta_name:
            return meta_name
        return step["name"]

    def _derive_lifecycle(link: dict | None) -> str:
        if link is None:
            return "unmatched"
        s = link.get("toolStepStatus", "")
        if s == "completed":
            return "completed"
        if s == "failed":
            return "failed"
        return "unmatched"

    call_links: dict[str, dict] = {}
    tool_step_to_llm: dict[str, dict] = {}

    id_to_tool_step: dict[str, dict] = {}
    tool_steps: list[dict] = []

    for s in steps:
        if s["step_type"] == "tool":
            tool_steps.append(s)
            tc_id = (s.get("metadata") or {}).get("tool_call_id")
            if isinstance(tc_id, str) and tc_id:
                id_to_tool_step[tc_id] = s

    claimed: set[str] = set()

    # Phase 1: exact matches
    for llm_step in steps:
        calls = (llm_step.get("llm") or {}).get("output", {}).get("tool_calls") or []
        if not calls:
            continue
        for ci, tc in enumerate(calls):
            call_id = tc.get("id") if isinstance(tc.get("id"), str) else None
            key = f"{llm_step['id']}:{ci}"
            if call_id:
                matched = id_to_tool_step.get(call_id)
                if matched:
                    link = {
                        "toolStepId": matched["id"],
                        "toolStepName": matched["name"],
                        "toolStepIndex": matched["sequence_index"],
                        "toolStepStatus": matched["status"],
                        "confidence": "exact",
                    }
                    call_links[key] = {
                        "link": link,
                        "confidence": "exact",
                        "lifecycle": _derive_lifecycle(link),
                    }
                    tool_step_to_llm[matched["id"]] = {
                        "llmStep": llm_step,
                        "confidence": "exact",
                    }
                    claimed.add(matched["id"])

    # Phase 2: heuristic fallback
    for llm_step in steps:
        calls = (llm_step.get("llm") or {}).get("output", {}).get("tool_calls") or []
        if not calls:
            continue
        unresolved_indices: list[int] = []
        unresolved_names: list[str] = []
        for ci, tc in enumerate(calls):
            key = f"{llm_step['id']}:{ci}"
            if key in call_links:
                continue
            name = tc.get("name", "") if isinstance(tc.get("name"), str) else ""
            unresolved_indices.append(ci)
            unresolved_names.append(name)

        if not unresolved_indices:
            continue

        tier1: list[dict] = []
        tier2: list[dict] = []
        for ts in tool_steps:
            if ts["id"] in claimed:
                continue
            if ts.get("parent_step_id") == llm_step["id"]:
                tier1.append(ts)
            elif ts["sequence_index"] > llm_step["sequence_index"]:
                tier2.append(ts)

        tier1.sort(key=lambda s: s["sequence_index"])
        tier2.sort(key=lambda s: s["sequence_index"])
        candidates = tier1 if tier1 else tier2

        cand_claimed: set[str] = set()
        for ui in range(len(unresolved_indices)):
            call_name = unresolved_names[ui]
            if not call_name:
                continue
            best: dict | None = None
            for cand in candidates:
                if cand["id"] in cand_claimed:
                    continue
                if _tool_step_name(cand) != call_name:
                    continue
                best = cand
                break

            if best is None:
                continue

            ci = unresolved_indices[ui]
            key = f"{llm_step['id']}:{ci}"
            link = {
                "toolStepId": best["id"],
                "toolStepName": best["name"],
                "toolStepIndex": best["sequence_index"],
                "toolStepStatus": best["status"],
                "confidence": "heuristic",
            }
            call_links[key] = {
                "link": link,
                "confidence": "heuristic",
                "lifecycle": _derive_lifecycle(link),
            }
            tool_step_to_llm[best["id"]] = {
                "llmStep": llm_step,
                "confidence": "heuristic",
            }
            claimed.add(best["id"])
            cand_claimed.add(best["id"])

    # Phase 3: fill unlinked
    for llm_step in steps:
        calls = (llm_step.get("llm") or {}).get("output", {}).get("tool_calls") or []
        for ci in range(len(calls)):
            key = f"{llm_step['id']}:{ci}"
            if key not in call_links:
                call_links[key] = {
                    "link": None,
                    "confidence": "unlinked",
                    "lifecycle": "unmatched",
                }

    return {"callLinks": call_links, "toolStepToLlm": tool_step_to_llm}


class TestHeuristicLinkageExactMatch:
    """Exact match behavior tests."""

    def test_exact_id_match_wins_over_heuristic(self):
        """When a tool_call_id exists and matches a tool step, exact wins."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", sequence_index=1,
                parent_step_id="llm1",
                metadata={"tool_call_id": "tc1"},
            ),
            _make_step(
                id="tool2", step_type="tool", name="search", sequence_index=2,
                parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "exact"
        assert r["link"]["toolStepId"] == "tool1"

    def test_exact_linked_completed(self):
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "exact"
        assert r["lifecycle"] == "completed"

    def test_exact_linked_failed(self):
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="failed",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "exact"
        assert r["lifecycle"] == "failed"


class TestHeuristicLinkageFallback:
    """Heuristic fallback behavior tests."""

    def test_missing_id_same_parent_same_name(self):
        """Tool call without id heuristically matches a child tool step with same name."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "heuristic"
        assert r["link"]["toolStepId"] == "tool1"
        assert r["lifecycle"] == "completed"

    def test_multiple_calls_align_by_order(self):
        """Multiple tool calls of the same name align to same-name tool steps in order."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[
                    {"name": "search"},
                    {"name": "search"},
                ],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
            _make_step(
                id="tool2", step_type="tool", name="search", status="failed",
                sequence_index=2, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r0 = result["callLinks"]["llm1:0"]
        r1 = result["callLinks"]["llm1:1"]
        assert r0["confidence"] == "heuristic"
        assert r0["link"]["toolStepId"] == "tool1"
        assert r1["confidence"] == "heuristic"
        assert r1["link"]["toolStepId"] == "tool2"

    def test_tool_step_before_llm_not_preferred(self):
        """A tool step with lower sequence_index than the LLM step is not a valid heuristic candidate."""
        steps = [
            _make_step(
                id="tool_early", step_type="tool", name="search", status="completed",
                sequence_index=0,
            ),
            _make_step(
                id="llm1", step_type="llm", sequence_index=1,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool_late", step_type="tool", name="search", status="completed",
                sequence_index=2,
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "heuristic"
        assert r["link"]["toolStepId"] == "tool_late"

    def test_nearest_sequence_index_breaks_ties(self):
        """Among multiple valid candidates, the one with nearest sequence_index wins."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "fetch"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="fetch", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
            _make_step(
                id="tool2", step_type="tool", name="fetch", status="completed",
                sequence_index=5, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["link"]["toolStepId"] == "tool1"

    def test_ambiguous_candidates_remain_unlinked(self):
        """When there are no name-matching unclaimed candidates, call remains unlinked."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="other_tool", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "unlinked"
        assert r["link"] is None

    def test_metadata_tool_name_preferred_over_step_name(self):
        """metadata.tool_name takes priority over step.name for heuristic matching."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="tool_step_generic",
                status="completed", sequence_index=1, parent_step_id="llm1",
                metadata={"tool_name": "search"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "heuristic"
        assert r["link"]["toolStepId"] == "tool1"

    def test_tier1_preferred_over_tier2(self):
        """Child tool steps (same parent) are preferred over nearby non-child steps."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool_child", step_type="tool", name="search", status="completed",
                sequence_index=2, parent_step_id="llm1",
            ),
            _make_step(
                id="tool_nearby", step_type="tool", name="search", status="completed",
                sequence_index=1,
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "heuristic"
        assert r["link"]["toolStepId"] == "tool_child"


class TestHeuristicLinkageUnlinked:
    """Unlinked behavior tests."""

    def test_no_compatible_tool_step(self):
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "unlinked"
        assert r["lifecycle"] == "unmatched"

    def test_wrong_tool_name(self):
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="fetch_data", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "unlinked"

    def test_already_claimed_not_reused(self):
        """Once a tool step is claimed by exact match, it cannot be reused heuristically."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[
                    {"id": "tc1", "name": "search"},
                    {"name": "search"},
                ],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, parent_step_id="llm1",
                metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r0 = result["callLinks"]["llm1:0"]
        r1 = result["callLinks"]["llm1:1"]
        assert r0["confidence"] == "exact"
        assert r0["link"]["toolStepId"] == "tool1"
        assert r1["confidence"] == "unlinked"
        assert r1["link"] is None

    def test_empty_tool_call_name_stays_unlinked(self):
        """A tool call without a name cannot be heuristically matched."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": ""}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "unlinked"


class TestHeuristicLinkageRegression:
    """Regression tests."""

    def test_exact_linkage_still_works(self):
        """Standard exact linkage path remains functional."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "exact"
        assert r["link"]["toolStepId"] == "tool1"
        assert r["lifecycle"] == "completed"
        # back-link
        back = result["toolStepToLlm"]["tool1"]
        assert back["llmStep"]["id"] == "llm1"
        assert back["confidence"] == "exact"

    def test_lifecycle_strict_for_running(self):
        """Linked step with 'running' status → unmatched lifecycle."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="running",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "exact"
        assert r["lifecycle"] == "unmatched"

    def test_lifecycle_strict_for_pending(self):
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"id": "tc1", "name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="pending",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["lifecycle"] == "unmatched"

    def test_no_crash_when_metadata_missing(self):
        """Steps without metadata don't crash the linker."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1,
            ),
        ]
        result = _build_tool_call_linkage(steps)
        assert "llm1:0" in result["callLinks"]

    def test_no_crash_when_tool_name_missing(self):
        """Tool step with no name or metadata.tool_name doesn't crash."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r = result["callLinks"]["llm1:0"]
        assert r["confidence"] == "unlinked"

    def test_back_link_confidence_heuristic(self):
        """toolStepToLlm entry has heuristic confidence for heuristic matches."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[{"name": "search"}],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        back = result["toolStepToLlm"]["tool1"]
        assert back["confidence"] == "heuristic"

    def test_mixed_exact_and_heuristic(self):
        """One call with id (exact) and one without (heuristic) in same LLM step."""
        steps = [
            _make_step(
                id="llm1", step_type="llm", sequence_index=0,
                tool_calls=[
                    {"id": "tc1", "name": "search"},
                    {"name": "fetch"},
                ],
            ),
            _make_step(
                id="tool1", step_type="tool", name="search", status="completed",
                sequence_index=1, metadata={"tool_call_id": "tc1"},
            ),
            _make_step(
                id="tool2", step_type="tool", name="fetch", status="completed",
                sequence_index=2, parent_step_id="llm1",
            ),
        ]
        result = _build_tool_call_linkage(steps)
        r0 = result["callLinks"]["llm1:0"]
        r1 = result["callLinks"]["llm1:1"]
        assert r0["confidence"] == "exact"
        assert r0["link"]["toolStepId"] == "tool1"
        assert r1["confidence"] == "heuristic"
        assert r1["link"]["toolStepId"] == "tool2"


# ===================================================================
# tool_call artifact creation (mirrors create_tool_call_artifacts)
# ===================================================================

from pathlib import Path


class TestToolCallArtifactCreation:
    """Test that create_tool_call_artifacts produces correct artifacts."""

    def test_one_artifact_per_tool_call(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "search", "arguments": {"q": "hello"}},
                {"id": "tc2", "name": "fetch", "arguments": {"url": "https://x.com"}},
            ]),
        )
        arts = create_tool_call_artifacts(n, step_id="step-abc")
        assert len(arts) == 2

    def test_zero_artifacts_when_no_tool_calls(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[]),
        )
        arts = create_tool_call_artifacts(n, step_id="step-abc")
        assert len(arts) == 0

    def test_artifact_type_and_role(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "search", "arguments": {"q": "hi"}},
            ]),
        )
        art = create_tool_call_artifacts(n, step_id="s1")[0]
        assert art.artifact_type == "tool_call"
        assert art.role == "output"
        assert art.step_id == "s1"

    def test_artifact_payload_shape(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "search", "arguments": {"q": "hello"}},
            ]),
        )
        art = create_tool_call_artifacts(n, step_id="s1")[0]
        data = art.inline_data
        assert data["tool_name"] == "search"
        assert data["tool_call_id"] == "tc1"
        assert data["arguments"] == {"q": "hello"}
        assert "arguments_hash" in data
        assert data["call_index"] == 0

    def test_artifact_metadata_shape(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="anthropic", model="claude-sonnet",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "search", "arguments": {}},
            ]),
        )
        art = create_tool_call_artifacts(n, step_id="s1")[0]
        meta = art.metadata
        assert meta["tool_name"] == "search"
        assert meta["tool_call_id"] == "tc1"
        assert meta["provider"] == "anthropic"
        assert meta["model"] == "claude-sonnet"
        assert meta["call_index"] == 0

    def test_artifact_without_call_id(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"name": "search", "arguments": {"q": "hi"}},
            ]),
        )
        art = create_tool_call_artifacts(n, step_id="s1")[0]
        assert "tool_call_id" not in art.inline_data
        assert "tool_call_id" not in art.metadata

    def test_preview_text(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "get_weather", "arguments": {}},
            ]),
        )
        art = create_tool_call_artifacts(n, step_id="s1")[0]
        assert "get_weather" in art.preview_text
        assert "tc1" in art.preview_text

    def test_multiple_calls_preserve_order(self):
        from leer.integrations.normalize import NormalizedLLMCall, LLMInput, LLMOutput, LLMUsage, LLMMeta
        from leer.integrations.normalize import create_tool_call_artifacts

        n = NormalizedLLMCall(
            provider="openai", model="gpt-4",
            input=LLMInput(), usage=LLMUsage(), meta=LLMMeta(),
            output=LLMOutput(tool_calls=[
                {"id": "tc1", "name": "alpha", "arguments": {}},
                {"id": "tc2", "name": "beta", "arguments": {}},
                {"id": "tc3", "name": "gamma", "arguments": {}},
            ]),
        )
        arts = create_tool_call_artifacts(n, step_id="s1")
        assert [a.inline_data["tool_name"] for a in arts] == ["alpha", "beta", "gamma"]
        assert [a.inline_data["call_index"] for a in arts] == [0, 1, 2]


# ===================================================================
# Tool-step artifact linkage metadata alignment
# ===================================================================

class TestToolStepArtifactMetadata:
    """Test that tool_request/response/error artifacts carry linkage metadata."""

    def _run_tool_step(self, *, tool_name="search", tool_call_id="tc1",
                       succeed=True, has_input=True, has_output=True):
        from leer.context import set_current_run
        from leer.models import TraceRun
        from leer.tool import tool_step

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step(tool_name, tool_call_id=tool_call_id) as s:
                if has_input:
                    s.input = {"q": "hello"}
                if succeed:
                    if has_output:
                        s.output = {"result": "world"}
                else:
                    raise ValueError("tool failed")
        except ValueError:
            pass
        finally:
            set_current_run(None)
        return run

    def test_tool_request_has_linkage_metadata(self):
        run = self._run_tool_step()
        req_arts = [a for a in run.artifacts if a.artifact_type == "tool_request"]
        assert len(req_arts) == 1
        meta = req_arts[0].metadata
        assert meta["tool_name"] == "search"
        assert meta["tool_call_id"] == "tc1"

    def test_tool_response_has_linkage_metadata(self):
        run = self._run_tool_step()
        resp_arts = [a for a in run.artifacts if a.artifact_type == "tool_response"]
        assert len(resp_arts) == 1
        meta = resp_arts[0].metadata
        assert meta["tool_name"] == "search"
        assert meta["tool_call_id"] == "tc1"

    def test_tool_error_has_linkage_metadata(self):
        run = self._run_tool_step(succeed=False)
        err_arts = [a for a in run.artifacts if a.artifact_type == "tool_error"]
        assert len(err_arts) == 1
        meta = err_arts[0].metadata
        assert meta["tool_name"] == "search"
        assert meta["tool_call_id"] == "tc1"

    def test_metadata_without_tool_call_id(self):
        from leer.context import set_current_run
        from leer.models import TraceRun
        from leer.tool import tool_step

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            with tool_step("custom_tool") as s:
                s.input = {"x": 1}
                s.output = {"y": 2}
        finally:
            set_current_run(None)

        req_art = next(a for a in run.artifacts if a.artifact_type == "tool_request")
        assert req_art.metadata["tool_name"] == "custom_tool"
        assert "tool_call_id" not in req_art.metadata


# ===================================================================
# OpenAI/Anthropic tool_call artifact integration
# ===================================================================

class TestToolCallArtifactIntegration:
    """End-to-end: wrappers produce tool_call artifacts alongside llm_request/response."""

    def test_openai_tool_call_artifacts_created(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_openai_wrapper import _fake_openai_client, _make_tool_call_response
        from leer.context import set_current_run
        from leer.integrations.openai import wrap_openai_client
        from leer.models import TraceRun

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            client = wrap_openai_client(_fake_openai_client(chat_response=_make_tool_call_response()))
            client.chat.completions.create(model="gpt-4.1", messages=[])
        finally:
            set_current_run(None)

        tc_arts = [a for a in run.artifacts if a.artifact_type == "tool_call"]
        assert len(tc_arts) == 1
        assert tc_arts[0].inline_data["tool_name"] == "get_weather"
        assert tc_arts[0].metadata["provider"] == "openai"

    def test_anthropic_tool_call_artifacts_created(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_anthropic_wrapper import _fake_anthropic_client, _make_tool_use_response
        from leer.context import set_current_run
        from leer.integrations.anthropic import wrap_anthropic_client
        from leer.models import TraceRun

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            client = wrap_anthropic_client(_fake_anthropic_client(response=_make_tool_use_response()))
            client.messages.create(model="claude-sonnet-4-20250514", messages=[], max_tokens=100)
        finally:
            set_current_run(None)

        tc_arts = [a for a in run.artifacts if a.artifact_type == "tool_call"]
        assert len(tc_arts) == 1
        assert tc_arts[0].inline_data["tool_name"] == "get_weather"
        assert tc_arts[0].metadata["provider"] == "anthropic"

    def test_no_tool_call_artifacts_when_no_calls(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_openai_wrapper import _fake_openai_client
        from leer.context import set_current_run
        from leer.integrations.openai import wrap_openai_client
        from leer.models import TraceRun

        run = TraceRun(workflow_name="test")
        run.status = "running"
        set_current_run(run)
        try:
            client = wrap_openai_client(_fake_openai_client())
            client.chat.completions.create(model="gpt-4.1", messages=[])
        finally:
            set_current_run(None)

        tc_arts = [a for a in run.artifacts if a.artifact_type == "tool_call"]
        assert len(tc_arts) == 0


# ============================================================================
# Compare-side tool-call alignment and lifecycle derivation (Python mirrors)
# ============================================================================

# These mirror the TS functions in apps/web/src/app/compare/page.tsx to provide
# strong logic coverage for the alignment algorithm and lifecycle derivation.

class _ToolCallSummary:
    def __init__(self, name: str, id: str | None = None, arguments_hash: str | None = None):
        self.name = name
        self.id = id
        self.arguments_hash = arguments_hash


class _AlignedPair:
    def __init__(self, a: _ToolCallSummary | None, b: _ToolCallSummary | None):
        self.a = a
        self.b = b


def _align_tool_calls(calls_a: list[_ToolCallSummary], calls_b: list[_ToolCallSummary]) -> list[_AlignedPair]:
    """Python mirror of alignToolCalls() in compare/page.tsx."""
    used_b: set[int] = set()

    id_to_b: dict[str, int] = {}
    for bi, tc in enumerate(calls_b):
        if tc.id:
            id_to_b[tc.id] = bi

    resolved_a: list[int | None] = [None] * len(calls_a)
    for ai, tc in enumerate(calls_a):
        if tc.id:
            bi = id_to_b.get(tc.id)
            if bi is not None and bi not in used_b:
                resolved_a[ai] = bi
                used_b.add(bi)

    for ai, tc in enumerate(calls_a):
        if resolved_a[ai] is not None:
            continue
        if ai < len(calls_b) and ai not in used_b and tc.name == calls_b[ai].name:
            resolved_a[ai] = ai
            used_b.add(ai)

    pairs: list[_AlignedPair] = []
    for ai in range(len(calls_a)):
        bi = resolved_a[ai]
        pairs.append(_AlignedPair(a=calls_a[ai], b=calls_b[bi] if bi is not None else None))

    for bi in range(len(calls_b)):
        if bi not in used_b:
            pairs.append(_AlignedPair(a=None, b=calls_b[bi]))

    return pairs


class _CompareStep:
    def __init__(self, step_type: str, exists: bool, status: str | None = None,
                 tool_call_id: str | None = None, tool_name: str | None = None,
                 name: str | None = None):
        self.step_type = step_type
        self.exists = exists
        self.status = status
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.name = name


def _derive_compare_lifecycle(
    tc: _ToolCallSummary,
    steps: list[_CompareStep],
) -> str:
    """Python mirror of deriveCompareCallLifecycle() for one side."""
    for s in steps:
        if s.step_type != "tool" or not s.exists:
            continue
        if tc.id and s.tool_call_id and tc.id == s.tool_call_id:
            if s.status == "completed":
                return "completed"
            if s.status == "failed":
                return "failed"
            return "unmatched"
        if not tc.id and not s.tool_call_id and s.tool_name and s.tool_name == tc.name:
            if s.status == "completed":
                return "completed"
            if s.status == "failed":
                return "failed"
            return "unmatched"
    return "unmatched"


class TestAlignToolCalls:
    """Tests for the alignment algorithm (Python mirror of TS alignToolCalls)."""

    def test_identical_calls_align_positionally(self):
        a = [_ToolCallSummary("get_weather", "id1"), _ToolCallSummary("get_time", "id2")]
        b = [_ToolCallSummary("get_weather", "id1"), _ToolCallSummary("get_time", "id2")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a and pairs[0].b and pairs[0].a.id == pairs[0].b.id == "id1"
        assert pairs[1].a and pairs[1].b and pairs[1].a.id == pairs[1].b.id == "id2"

    def test_different_ids_same_name_aligns_positionally(self):
        """Same name at same position aligns even when ids differ."""
        a = [_ToolCallSummary("get_weather", "id_a")]
        b = [_ToolCallSummary("get_weather", "id_b")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 1
        assert pairs[0].a is not None and pairs[0].b is not None
        assert pairs[0].a.id == "id_a" and pairs[0].b.id == "id_b"

    def test_different_ids_different_names_unmatched(self):
        """Different name + different id → each side appears alone."""
        a = [_ToolCallSummary("get_weather", "id_a")]
        b = [_ToolCallSummary("get_time", "id_b")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a is not None and pairs[0].b is None
        assert pairs[1].a is None and pairs[1].b is not None

    def test_reordered_calls_aligned_by_id(self):
        a = [_ToolCallSummary("get_weather", "id1"), _ToolCallSummary("get_time", "id2")]
        b = [_ToolCallSummary("get_time", "id2"), _ToolCallSummary("get_weather", "id1")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a and pairs[0].b and pairs[0].a.name == "get_weather" and pairs[0].b.name == "get_weather"
        assert pairs[1].a and pairs[1].b and pairs[1].a.name == "get_time" and pairs[1].b.name == "get_time"

    def test_extra_call_in_b_shows_as_only_in_b(self):
        a = [_ToolCallSummary("get_weather", "id1")]
        b = [_ToolCallSummary("get_weather", "id1"), _ToolCallSummary("get_time", "id2")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a is not None and pairs[0].b is not None
        assert pairs[1].a is None and pairs[1].b is not None and pairs[1].b.name == "get_time"

    def test_extra_call_in_a_shows_as_only_in_a(self):
        a = [_ToolCallSummary("get_weather", "id1"), _ToolCallSummary("get_time", "id2")]
        b = [_ToolCallSummary("get_weather", "id1")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a is not None and pairs[0].b is not None
        assert pairs[1].a is not None and pairs[1].b is None and pairs[1].a.name == "get_time"

    def test_no_ids_falls_back_to_positional_name(self):
        a = [_ToolCallSummary("get_weather"), _ToolCallSummary("get_time")]
        b = [_ToolCallSummary("get_weather"), _ToolCallSummary("get_time")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a is not None and pairs[0].b is not None
        assert pairs[1].a is not None and pairs[1].b is not None

    def test_no_ids_different_names_remain_unmatched(self):
        a = [_ToolCallSummary("get_weather")]
        b = [_ToolCallSummary("get_time")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 2
        assert pairs[0].a is not None and pairs[0].b is None
        assert pairs[1].a is None and pairs[1].b is not None

    def test_empty_both_sides(self):
        pairs = _align_tool_calls([], [])
        assert pairs == []

    def test_empty_a_side(self):
        b = [_ToolCallSummary("get_weather", "id1")]
        pairs = _align_tool_calls([], b)
        assert len(pairs) == 1
        assert pairs[0].a is None and pairs[0].b is not None

    def test_empty_b_side(self):
        a = [_ToolCallSummary("get_weather", "id1")]
        pairs = _align_tool_calls(a, [])
        assert len(pairs) == 1
        assert pairs[0].a is not None and pairs[0].b is None

    def test_args_hash_preserved_in_alignment(self):
        a = [_ToolCallSummary("get_weather", "id1", "aaa")]
        b = [_ToolCallSummary("get_weather", "id1", "bbb")]
        pairs = _align_tool_calls(a, b)
        assert len(pairs) == 1
        assert pairs[0].a and pairs[0].b
        assert pairs[0].a.arguments_hash == "aaa"
        assert pairs[0].b.arguments_hash == "bbb"


class TestCompareCallLifecycle:
    """Tests for compare-side lifecycle derivation (Python mirror of TS deriveCompareCallLifecycle)."""

    def test_completed_via_exact_id_match(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("tool", True, "completed", "call_1", "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "completed"

    def test_failed_via_exact_id_match(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("tool", True, "failed", "call_1", "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "failed"

    def test_running_step_gives_unmatched(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("tool", True, "running", "call_1", "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "unmatched"

    def test_no_matching_step_gives_unmatched(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("tool", True, "completed", "call_2", "other_tool")]
        assert _derive_compare_lifecycle(tc, steps) == "unmatched"

    def test_name_fallback_when_no_ids(self):
        tc = _ToolCallSummary("get_weather")
        steps = [_CompareStep("tool", True, "completed", None, "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "completed"

    def test_name_fallback_failed(self):
        tc = _ToolCallSummary("get_weather")
        steps = [_CompareStep("tool", True, "failed", None, "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "failed"

    def test_step_not_exists_ignored(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("tool", False, "completed", "call_1", "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "unmatched"

    def test_non_tool_step_ignored(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        steps = [_CompareStep("llm", True, "completed", "call_1", "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "unmatched"

    def test_empty_steps_gives_unmatched(self):
        tc = _ToolCallSummary("get_weather", "call_1")
        assert _derive_compare_lifecycle(tc, []) == "unmatched"

    def test_missing_metadata_gives_unmatched(self):
        tc = _ToolCallSummary("get_weather")
        steps = [_CompareStep("tool", True, "completed", None, None, "get_weather")]
        assert _derive_compare_lifecycle(tc, steps) == "unmatched"
