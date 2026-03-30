"""Provider-agnostic normalized LLM call shape.

Every provider normalizer produces the same ``NormalizedLLMCall`` so the rest
of the system (artifacts, summaries, UI) never needs to know which provider
was used.

The normalizers accept plain dicts — the future wrappers will call
``.model_dump()`` (or equivalent) on SDK response objects before passing
them here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Normalized shape
# ---------------------------------------------------------------------------

@dataclass
class LLMInput:
    system: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMOutput:
    text: str | None = None
    content_blocks: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class LLMMeta:
    latency_ms: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None


@dataclass
class NormalizedLLMCall:
    provider: str
    model: str | None
    input: LLMInput
    output: LLMOutput
    usage: LLMUsage
    meta: LLMMeta

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Traverse nested dicts safely."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _extract_params(request: dict[str, Any], known: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in request.items() if k in known}


def _parse_arguments(raw: Any) -> Any:
    """Parse JSON-string arguments into structured data when possible."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _resolve_model(response: dict[str, Any], request: dict[str, Any]) -> str | None:
    return response.get("model") or request.get("model") or None


# ---------------------------------------------------------------------------
# OpenAI — parameter sets
# ---------------------------------------------------------------------------

_OPENAI_CHAT_PARAMS = frozenset({
    "temperature", "max_tokens", "max_completion_tokens", "top_p",
    "frequency_penalty", "presence_penalty", "stop", "seed",
    "response_format", "logprobs", "top_logprobs",
})

_OPENAI_RESPONSES_PARAMS = frozenset({
    "temperature", "max_output_tokens", "top_p",
    "truncation", "text", "store", "reasoning",
})


# ---------------------------------------------------------------------------
# OpenAI — public entry point
# ---------------------------------------------------------------------------

def normalize_openai(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an OpenAI request + response.

    Auto-detects the API shape (chat completions vs. responses) and
    dispatches to the appropriate helper.
    """
    if "output" in response and "choices" not in response:
        return _normalize_openai_responses(request, response, latency_ms=latency_ms)
    return _normalize_openai_chat(request, response, latency_ms=latency_ms)


# ---------------------------------------------------------------------------
# OpenAI — chat completions shape
# ---------------------------------------------------------------------------

def _normalize_openai_chat(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize ``client.chat.completions.create()``."""
    messages = list(request.get("messages", []))

    system: str | None = None
    non_system: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") in ("system", "developer"):
            system = msg.get("content") or system
        else:
            non_system.append(msg)

    params = _extract_params(request, _OPENAI_CHAT_PARAMS)

    choices = response.get("choices") or []
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}

    text = message.get("content") if isinstance(message, dict) else None

    raw_tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
    tool_calls: list[dict[str, Any]] = []
    for tc in (raw_tool_calls or []):
        if not isinstance(tc, dict):
            continue
        tc_type = tc.get("type", "function")
        if tc_type == "function":
            tool_calls.append({
                "id": tc.get("id"),
                "name": _safe_get(tc, "function", "name"),
                "arguments": _parse_arguments(_safe_get(tc, "function", "arguments")),
            })
        elif tc_type == "custom":
            tool_calls.append({
                "id": tc.get("id"),
                "name": _safe_get(tc, "custom", "name"),
                "arguments": _parse_arguments(_safe_get(tc, "custom", "input")),
            })

    content_blocks: list[dict[str, Any]] = []
    if text:
        content_blocks.append({"type": "text", "text": text})
    for tc in tool_calls:
        content_blocks.append({"type": "tool_call", **tc})

    usage_raw = response.get("usage") or {}

    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None

    return NormalizedLLMCall(
        provider="openai",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=non_system,
            tools=request.get("tools", []),
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
        ),
        usage=LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_id=response.get("id"),
        ),
    )


# ---------------------------------------------------------------------------
# OpenAI — responses shape
# ---------------------------------------------------------------------------

def _normalize_openai_responses(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize ``client.responses.create()``."""
    system = request.get("instructions")

    raw_input = request.get("input", [])
    if isinstance(raw_input, str):
        messages: list[dict[str, Any]] = [{"role": "user", "content": raw_input}]
    elif isinstance(raw_input, list):
        non_system: list[dict[str, Any]] = []
        for m in raw_input:
            if not isinstance(m, dict):
                continue
            if m.get("role") == "system":
                system = m.get("content") or system
            else:
                non_system.append(m)
        messages = non_system
    else:
        messages = []

    params = _extract_params(request, _OPENAI_RESPONSES_PARAMS)

    tools_raw = request.get("tools", [])
    tools: list[dict[str, Any]] = []
    for t in (tools_raw or []):
        if not isinstance(t, dict):
            continue
        if t.get("type") == "function":
            tools.append(t.get("function", t))
        else:
            tools.append(t)

    output_items = response.get("output", [])

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content_blocks: list[dict[str, Any]] = []

    for item in (output_items if isinstance(output_items, list) else []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "message":
            for block in (item.get("content") or []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text":
                    t = block.get("text", "")
                    text_parts.append(t)
                    content_blocks.append({"type": "text", "text": t})

        elif item_type == "function_call":
            tc = {
                "id": item.get("call_id") or item.get("id"),
                "name": item.get("name"),
                "arguments": _parse_arguments(item.get("arguments")),
            }
            tool_calls.append(tc)
            content_blocks.append({"type": "tool_call", **tc})

    text = "\n\n".join(text_parts) if text_parts else None

    usage_raw = response.get("usage") or {}

    return NormalizedLLMCall(
        provider="openai",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
        ),
        usage=LLMUsage(
            prompt_tokens=usage_raw.get("input_tokens"),
            completion_tokens=usage_raw.get("output_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=response.get("status"),
            request_id=response.get("id"),
        ),
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

_ANTHROPIC_PARAMS = frozenset({
    "temperature", "max_tokens", "top_p", "top_k", "stop_sequences",
    "thinking",
})


def normalize_anthropic(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an Anthropic messages API request + response."""
    system = request.get("system")
    if isinstance(system, list):
        system = " ".join(
            block.get("text", "") for block in system
            if isinstance(block, dict) and block.get("type") == "text"
        ) or None

    messages = list(request.get("messages", []))
    params = _extract_params(request, _ANTHROPIC_PARAMS)

    tools_raw = request.get("tools", [])
    tools = [
        {"name": t.get("name"), "description": t.get("description"), "input_schema": t.get("input_schema")}
        for t in (tools_raw or [])
        if isinstance(t, dict)
    ]

    raw_blocks = response.get("content", [])

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content_blocks: list[dict[str, Any]] = []

    for block in (raw_blocks if isinstance(raw_blocks, list) else []):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")

        if block_type == "text":
            t = block.get("text", "")
            text_parts.append(t)
            content_blocks.append({"type": "text", "text": t})
        elif block_type == "tool_use":
            tc = {
                "id": block.get("id"),
                "name": block.get("name"),
                "arguments": block.get("input", {}),
            }
            tool_calls.append(tc)
            content_blocks.append({"type": "tool_call", **tc})
        elif block_type == "thinking":
            content_blocks.append({
                "type": "thinking",
                "thinking": block.get("thinking", ""),
            })
        elif block_type == "redacted_thinking":
            content_blocks.append({"type": "redacted_thinking"})

    text = "\n\n".join(text_parts) if text_parts else None

    usage_raw = response.get("usage") or {}
    prompt_tokens = usage_raw.get("input_tokens")
    completion_tokens = usage_raw.get("output_tokens")
    total = (prompt_tokens or 0) + (completion_tokens or 0) if (prompt_tokens or completion_tokens) else None

    return NormalizedLLMCall(
        provider="anthropic",
        model=_resolve_model(response, request),
        input=LLMInput(
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ),
        output=LLMOutput(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
        ),
        usage=LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        ),
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=response.get("stop_reason"),
            request_id=response.get("id"),
        ),
    )
