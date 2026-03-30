"""Provider-agnostic normalized LLM call shape.

Every provider normalizer produces the same ``NormalizedLLMCall`` so the rest
of the system (artifacts, summaries, UI) never needs to know which provider
was used.

The normalizers accept plain dicts — the future wrappers will call
``.model_dump()`` (or equivalent) on SDK response objects before passing
them here.
"""

from __future__ import annotations

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
    status: str = "ok"


@dataclass
class NormalizedLLMCall:
    provider: str
    model: str
    input: LLMInput
    output: LLMOutput
    usage: LLMUsage
    meta: LLMMeta

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPENAI_PARAMS = frozenset({
    "temperature", "max_tokens", "max_completion_tokens", "top_p",
    "frequency_penalty", "presence_penalty", "stop", "seed",
    "response_format", "logprobs", "top_logprobs",
})

_ANTHROPIC_PARAMS = frozenset({
    "temperature", "max_tokens", "top_p", "top_k", "stop_sequences",
})


def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Traverse nested dicts safely."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


# ---------------------------------------------------------------------------
# OpenAI normalizer
# ---------------------------------------------------------------------------

def normalize_openai(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an OpenAI chat completion request + response.

    Handles the ``client.chat.completions.create()`` path.
    """
    messages = list(request.get("messages", []))

    system: str | None = None
    non_system: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            system = msg.get("content") or system
        else:
            non_system.append(msg)

    params = {k: v for k, v in request.items() if k in _OPENAI_PARAMS}

    # --- response ---
    choice = _safe_get(response, "choices", default=[{}])
    first = choice[0] if isinstance(choice, list) and choice else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}

    text = message.get("content") if isinstance(message, dict) else None

    raw_tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
    tool_calls = [
        {
            "id": tc.get("id"),
            "type": tc.get("type", "function"),
            "function": tc.get("function", {}),
        }
        for tc in (raw_tool_calls or [])
        if isinstance(tc, dict)
    ]

    usage_raw = response.get("usage") or {}
    usage = LLMUsage(
        prompt_tokens=usage_raw.get("prompt_tokens"),
        completion_tokens=usage_raw.get("completion_tokens"),
        total_tokens=usage_raw.get("total_tokens"),
    )

    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None

    return NormalizedLLMCall(
        provider="openai",
        model=response.get("model") or request.get("model", "unknown"),
        input=LLMInput(
            system=system,
            messages=non_system,
            tools=request.get("tools", []),
            params=params,
        ),
        output=LLMOutput(
            text=text,
            tool_calls=tool_calls,
        ),
        usage=usage,
        meta=LLMMeta(
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_id=response.get("id"),
            status="error" if finish_reason == "error" else "ok",
        ),
    )


# ---------------------------------------------------------------------------
# Anthropic normalizer
# ---------------------------------------------------------------------------

def normalize_anthropic(
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> NormalizedLLMCall:
    """Normalize an Anthropic messages API request + response.

    Handles the ``client.messages.create()`` path.
    """
    system = request.get("system")
    if isinstance(system, list):
        system = " ".join(
            block.get("text", "") for block in system
            if isinstance(block, dict) and block.get("type") == "text"
        ) or None

    messages = list(request.get("messages", []))
    params = {k: v for k, v in request.items() if k in _ANTHROPIC_PARAMS}

    tools_raw = request.get("tools", [])
    tools = [
        {"name": t.get("name"), "description": t.get("description"), "input_schema": t.get("input_schema")}
        for t in (tools_raw or [])
        if isinstance(t, dict)
    ]

    # --- response ---
    content_blocks = response.get("content", [])

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in (content_blocks if isinstance(content_blocks, list) else []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "id": block.get("id"),
                "type": "function",
                "function": {
                    "name": block.get("name"),
                    "arguments": block.get("input", {}),
                },
            })

    text = "\n\n".join(text_parts) if text_parts else None

    usage_raw = response.get("usage") or {}
    prompt_tokens = usage_raw.get("input_tokens")
    completion_tokens = usage_raw.get("output_tokens")
    total = (prompt_tokens or 0) + (completion_tokens or 0) if (prompt_tokens or completion_tokens) else None

    return NormalizedLLMCall(
        provider="anthropic",
        model=response.get("model") or request.get("model", "unknown"),
        input=LLMInput(
            system=system,
            messages=messages,
            tools=tools,
            params=params,
        ),
        output=LLMOutput(
            text=text,
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
            status="error" if response.get("type") == "error" else "ok",
        ),
    )
