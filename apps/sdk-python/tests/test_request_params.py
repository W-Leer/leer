"""Which request parameters reach ``input.params`` (drift D-M6).

Recorded: anything that changes what the model sees, how it generates, which
tools it may use, or which model / capacity serves it. Left out: identity,
billing, storage, caching hints, diagnostics, transport. Everything stays in
the ``llm_request`` artifact either way.
"""

from __future__ import annotations

from typing import Any

import pytest

from leer.integrations.normalize import normalize_anthropic, normalize_openai

_CHAT_RESPONSE = {"id": "c1", "object": "chat.completion", "model": "gpt-test",
                  "choices": [{"index": 0, "finish_reason": "stop",
                               "message": {"role": "assistant", "content": "ok"}}]}
_RESPONSES_RESPONSE = {"id": "r1", "object": "response", "model": "gpt-test", "status": "completed",
                       "output": [{"id": "m1", "type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": "ok"}]}]}
_ANTHROPIC_RESPONSE = {"id": "m1", "type": "message", "model": "claude-test", "stop_reason": "end_turn",
                       "content": [{"type": "text", "text": "ok"}]}


def _params(provider: str, extra: dict[str, Any]) -> dict[str, Any]:
    if provider == "chat":
        request = {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}], **extra}
        return normalize_openai(request, _CHAT_RESPONSE).input.params
    if provider == "responses":
        return normalize_openai({"model": "gpt-test", "input": "hi", **extra}, _RESPONSES_RESPONSE).input.params
    request = {"model": "claude-test", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}], **extra}
    return normalize_anthropic(request, _ANTHROPIC_RESPONSE).input.params


RECORDED = {
    "chat": {
        "reasoning_effort": "high", "verbosity": "low", "tool_choice": "required", "parallel_tool_calls": False,
        "function_call": "auto", "n": 2, "logit_bias": {"50256": -100}, "modalities": ["text", "audio"],
        "audio": {"voice": "alloy", "format": "mp3"}, "prediction": {"type": "content", "content": "x"},
        "web_search_options": {"search_context_size": "low"}, "service_tier": "priority",
        "moderation": {"type": "auto"},
    },
    "responses": {
        "tool_choice": {"type": "function", "name": "lookup"}, "parallel_tool_calls": False, "max_tool_calls": 3,
        "top_logprobs": 2, "previous_response_id": "resp_prev", "conversation": "conv_1",
        "prompt": {"id": "pmpt_1", "variables": {"city": "Paris"}}, "include": ["reasoning.encrypted_content"],
        "background": True, "service_tier": "flex", "context_management": [{"type": "compaction"}],
        "moderation": {"type": "auto"},
    },
    "anthropic": {
        "tool_choice": {"type": "any"}, "service_tier": "auto", "speed": "fast", "container": "cntr_1",
        "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]}, "compaction": {"type": "summarize"},
        "thread": {"type": "continue", "previous_message_id": "msg_prev"},
        "fallbacks": [{"model": "claude-sonnet-5"}], "mcp_servers": [{"type": "url", "url": "https://mcp.example", "name": "ex"}],
        "betas": ["fast-mode-2026-02-01"],
    },
}

LEFT_OUT = {
    "chat": {"metadata": {"k": "v"}, "user": "u1", "safety_identifier": "s1", "store": True,
             "stream_options": {"include_usage": True}, "prompt_cache_key": "k", "prompt_cache_retention": "24h"},
    "responses": {"metadata": {"k": "v"}, "user": "u1", "safety_identifier": "s1",
                  "stream_options": {"include_obfuscation": False}, "prompt_cache_key": "k",
                  "access_programs": ["x"]},
    "anthropic": {"metadata": {"user_id": "u1"}, "cache_control": {"type": "ephemeral"},
                  "diagnostics": {"previous_message_id": "m0"}, "inference_geo": "us",
                  "fallback_credit_token": "tok", "user_profile_id": "p1", "workspace_id": "w1"},
}


@pytest.mark.parametrize("provider", list(RECORDED))
def test_behavior_changing_params_are_recorded(provider: str) -> None:
    assert _params(provider, RECORDED[provider]) == {
        **({"max_tokens": 16} if provider == "anthropic" else {}),
        **RECORDED[provider],
    }


@pytest.mark.parametrize("provider", list(LEFT_OUT))
def test_identity_billing_and_transport_params_are_left_out(provider: str) -> None:
    params = _params(provider, LEFT_OUT[provider])
    assert not set(params) & set(LEFT_OUT[provider])


@pytest.mark.parametrize("provider", ["chat", "anthropic"])
def test_older_sampling_params_still_recorded(provider: str) -> None:
    """anthropic 2.3 dropped these, but older SDKs and the raw API still send them."""
    params = _params(provider, {"temperature": 0.2, "top_p": 0.9})
    assert params["temperature"] == 0.2
    assert params["top_p"] == 0.9


def test_anthropic_builtin_tools_keep_their_type_and_settings() -> None:
    request = {"model": "claude-test", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}], "tools": [
        {"name": "lookup", "description": "Find a thing", "input_schema": {"type": "object"}},
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
        {"type": "custom", "name": "run", "description": "Run", "input_schema": {"type": "object"}},
    ]}
    tools = normalize_anthropic(request, _ANTHROPIC_RESPONSE).input.tools
    assert tools == [
        {"name": "lookup", "description": "Find a thing", "input_schema": {"type": "object"}},
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
        {"name": "run", "description": "Run", "input_schema": {"type": "object"}},
    ]
