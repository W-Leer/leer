"""OpenAI wrapper for Leer SDK.

Usage::

    from openai import OpenAI
    from leer.integrations.openai import wrap_openai_client

    client = wrap_openai_client(OpenAI())

    # Inside a @trace, every create() call automatically produces
    # an LLM step with metadata, artifacts, and summaries.
    result = client.chat.completions.create(model="gpt-4.1", messages=[...])
"""

from __future__ import annotations

import time
from typing import Any

from leer.artifacts import attach_artifact, create_json_artifact
from leer.context import get_current_run
from leer.integrations.normalize import NormalizedLLMCall, normalize_openai
from leer.step import step as leer_step


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wrap_openai_client(client: Any) -> Any:
    """Wrap an OpenAI client for automatic LLM instrumentation.

    Returns a proxy that transparently intercepts ``chat.completions.create()``
    and ``responses.create()`` when inside an active trace. All other attributes
    and methods are forwarded to the original client unchanged.

    The original provider return value is always preserved.
    """
    return _WrappedOpenAI(client)


# ---------------------------------------------------------------------------
# Proxy classes — delegate everything except the create() methods
# ---------------------------------------------------------------------------

class _WrappedOpenAI:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.chat = _WrappedChat(client.chat)
        if hasattr(client, "responses"):
            self.responses = _WrappedResponses(client.responses)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _WrappedChat:
    def __init__(self, chat: Any) -> None:
        self._chat = chat
        self.completions = _WrappedCompletions(chat.completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class _WrappedCompletions:
    def __init__(self, completions: Any) -> None:
        self._completions = completions

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return _instrumented_create(self._completions.create, args, kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _WrappedResponses:
    def __init__(self, responses: Any) -> None:
        self._responses = responses

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return _instrumented_create(self._responses.create, args, kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._responses, name)


# ---------------------------------------------------------------------------
# Instrumented call — shared between both API styles
# ---------------------------------------------------------------------------

def _instrumented_create(
    original_fn: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Call the original create() and instrument it when inside a trace.

    Request capture relies on ``**kwargs`` — the OpenAI SDK's ``create()``
    methods accept keyword arguments (model, messages, input, etc.).
    Positional args are forwarded to the provider but not recorded.
    """
    run = get_current_run()
    if run is None:
        return original_fn(*args, **kwargs)

    request_dict = dict(kwargs)
    model_hint = request_dict.get("model") or "openai"
    step_name = str(model_hint)

    with leer_step(step_name, step_type="llm") as s:
        t0 = time.perf_counter()

        try:
            result = original_fn(*args, **kwargs)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _safe_enrich_error(s, request_dict, latency_ms, exc)
            raise

        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            _enrich_step(s, request_dict, result, latency_ms)
        except Exception:
            pass

        return result


# ---------------------------------------------------------------------------
# Step enrichment
# ---------------------------------------------------------------------------

def _enrich_step(
    s: Any,
    request_dict: dict[str, Any],
    result: Any,
    latency_ms: int,
) -> None:
    """Populate the step with metadata, summaries, and artifacts."""
    response_dict = _to_dict(result)
    normalized = normalize_openai(request_dict, response_dict, latency_ms=latency_ms)

    s.metadata.update({
        "provider": "openai",
        "model": normalized.model,
        "latency_ms": latency_ms,
        "finish_reason": normalized.meta.finish_reason,
        "request_id": normalized.meta.request_id,
        "usage": {
            "prompt_tokens": normalized.usage.prompt_tokens,
            "completion_tokens": normalized.usage.completion_tokens,
            "total_tokens": normalized.usage.total_tokens,
        },
        "llm": normalized.to_dict(),
    })

    s.input_summary = _input_summary(normalized)
    s.output_summary = _output_summary(normalized)

    attach_artifact(create_json_artifact(
        artifact_type="llm_request",
        role="input",
        data=request_dict,
        preview_text=_request_preview(normalized),
        step_id=s.id,
    ))

    attach_artifact(create_json_artifact(
        artifact_type="llm_response",
        role="output",
        data=response_dict,
        preview_text=_response_preview(normalized),
        step_id=s.id,
    ))


def _safe_enrich_error(
    s: Any,
    request_dict: dict[str, Any],
    latency_ms: int,
    exc: BaseException,
) -> None:
    """Best-effort metadata on a failed LLM call. Never raises."""
    try:
        s.metadata.update({
            "provider": "openai",
            "model": request_dict.get("model"),
            "latency_ms": latency_ms,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        })

        attach_artifact(create_json_artifact(
            artifact_type="llm_request",
            role="input",
            data=request_dict,
            preview_text=f"model: {request_dict.get('model', '?')} (failed)",
            step_id=s.id,
        ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Summaries — concise, human-readable for list views
# ---------------------------------------------------------------------------

def _input_summary(n: NormalizedLLMCall) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if n.model:
        summary["model"] = n.model
    if n.input.system:
        summary["system"] = n.input.system[:200]
    for m in reversed(n.input.messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                summary["user"] = content[:200]
            elif isinstance(content, list):
                texts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") in ("text", "input_text")
                ]
                if texts:
                    summary["user"] = " ".join(texts)[:200]
            break
    if n.input.tools:
        summary["tools"] = [
            t.get("name") or t.get("function", {}).get("name", "?")
            for t in n.input.tools
        ]
    return summary


def _output_summary(n: NormalizedLLMCall) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if n.output.text:
        summary["text"] = n.output.text[:500]
    if n.output.tool_calls:
        summary["tool_calls"] = [
            {"name": tc.get("name", "?")} for tc in n.output.tool_calls
        ]
    if n.usage.total_tokens is not None:
        summary["tokens"] = n.usage.total_tokens
    return summary


# ---------------------------------------------------------------------------
# Artifact previews — short strings for quick scanning
# ---------------------------------------------------------------------------

def _request_preview(n: NormalizedLLMCall) -> str:
    parts: list[str] = []
    if n.model:
        parts.append(f"model: {n.model}")
    if n.input.system:
        parts.append(f"system: {n.input.system[:80]}")
    for m in n.input.messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                parts.append(f"user: {content[:80]}")
            break
    return " | ".join(parts) if parts else "OpenAI request"


def _response_preview(n: NormalizedLLMCall) -> str:
    if n.output.text:
        return n.output.text[:200]
    if n.output.tool_calls:
        names = [tc.get("name", "?") for tc in n.output.tool_calls]
        return f"tool_calls: {', '.join(names)}"
    return "OpenAI response"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert a provider SDK response object to a plain dict."""
    if isinstance(obj, dict):
        return obj
    for method in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                result = fn()
                if isinstance(result, dict):
                    return result
            except Exception:
                continue
    return {}
