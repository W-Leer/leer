"""OpenAI wrapper for Leer SDK.

Usage::

    from openai import OpenAI
    from leer.integrations.openai import wrap_openai_client

    client = wrap_openai_client(OpenAI())

    # Inside a @trace, every create() call automatically produces
    # an LLM step with metadata, artifacts, and summaries.
    result = client.chat.completions.create(model="gpt-4.1", messages=[...])

    # Streaming is also supported transparently:
    stream = client.chat.completions.create(
        model="gpt-4.1", messages=[...], stream=True,
    )
    for chunk in stream:
        print(chunk)  # original chunks, unchanged
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Iterator

from leer.artifacts import attach_artifact, create_json_artifact
from leer.context import current_step, get_current_run, pop_step, push_step
from leer.integrations.normalize import NormalizedLLMCall, normalize_openai
from leer.integrations.streaming import StreamCollector
from leer.models import TraceStep, _now
from leer.step import _duration_ms, _emit_step_event, step as leer_step


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wrap_openai_client(client: Any) -> Any:
    """Wrap an OpenAI client for automatic LLM instrumentation.

    Returns a proxy that transparently intercepts ``chat.completions.create()``
    and ``responses.create()`` when inside an active trace. All other attributes
    and methods are forwarded to the original client unchanged.

    The original provider return value is always preserved — including stream
    iterators when ``stream=True``.
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

    When ``stream=True`` is detected the call is handled by the streaming
    path which wraps the returned iterator.
    """
    run = get_current_run()
    if run is None:
        return original_fn(*args, **kwargs)

    request_dict = dict(kwargs)

    if request_dict.get("stream"):
        return _instrumented_streaming_create(original_fn, args, request_dict)

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
# Streaming instrumented call
# ---------------------------------------------------------------------------

def _instrumented_streaming_create(
    original_fn: Any,
    args: tuple[Any, ...],
    request_dict: dict[str, Any],
) -> Any:
    """Handle a streaming create() call.

    Creates the LLM step eagerly, then returns a wrapping iterator that
    captures chunks into a StreamCollector and finalizes the step when
    iteration completes or fails.
    """
    run = get_current_run()
    if run is None:
        return original_fn(*args, **request_dict)

    model_hint = request_dict.get("model") or "openai"
    step_name = str(model_hint)

    parent = current_step()
    parent_step_id = parent.id if parent else None

    s = TraceStep(
        name=step_name,
        step_type="llm",
        sequence_index=len(run.steps),
        parent_step_id=parent_step_id,
        status="running",
        started_at=_now(),
    )
    run.steps.append(s)
    push_step(s)
    _emit_step_event("step.created", s.id)
    _emit_step_event("step.started", s.id)

    t0 = time.perf_counter()

    try:
        raw_stream = original_fn(*args, **request_dict)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        collector = StreamCollector(provider="openai", model=request_dict.get("model"))
        collector.mark_failed()

        s.status = "failed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        s.error_summary = {"traceback": traceback.format_exc()}
        s.metadata.update({
            "provider": "openai",
            "model": request_dict.get("model"),
            "latency_ms": latency_ms,
        })
        s.metadata["stream"] = collector.stream_metadata()
        _safe_attach_request_artifact(s, request_dict)
        _emit_step_event("step.failed", s.id)
        pop_step()
        raise

    collector = StreamCollector(provider="openai", model=request_dict.get("model"))
    return _StreamingIterator(raw_stream, collector, s, request_dict, t0)


# ---------------------------------------------------------------------------
# Streaming iterator wrapper
# ---------------------------------------------------------------------------

class _StreamingIterator:
    """Wraps an OpenAI stream, captures chunks, and finalizes the step."""

    def __init__(
        self,
        raw_stream: Any,
        collector: StreamCollector,
        step: TraceStep,
        request_dict: dict[str, Any],
        t0: float,
    ) -> None:
        self._raw_stream = raw_stream
        self._collector = collector
        self._step = step
        self._request_dict = request_dict
        self._t0 = t0
        self._finalized = False

    def __iter__(self) -> Iterator[Any]:
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._raw_stream)
        except StopIteration:
            self._finalize_success()
            raise
        except Exception:
            self._finalize_failure()
            raise

        try:
            _process_openai_chunk(self._collector, chunk)
        except Exception:
            pass

        return chunk

    def __enter__(self) -> _StreamingIterator:
        if hasattr(self._raw_stream, "__enter__"):
            self._raw_stream.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if hasattr(self._raw_stream, "__exit__"):
            self._raw_stream.__exit__(exc_type, exc_val, exc_tb)
        if not self._finalized:
            if exc_type is not None:
                self._finalize_failure()
            else:
                self._finalize_success()

    def _finalize_success(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        s = self._step
        collector = self._collector

        s.metadata["stream"] = collector.stream_metadata()

        assembled = collector.assembled_output()
        response_dict = _assembled_to_chat_response(assembled, self._request_dict)

        try:
            _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
        except Exception:
            s.metadata.update({
                "provider": "openai",
                "model": self._request_dict.get("model"),
                "latency_ms": latency_ms,
            })
            _safe_attach_request_artifact(s, self._request_dict)

        attach_artifact(create_json_artifact(
            artifact_type="llm_stream",
            role="output",
            data=collector.stream_artifact_payload(),
            preview_text=f"{collector.chunk_count} chunks, {collector.stream_metadata()['termination']}",
            step_id=s.id,
        ))

        s.status = "completed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        _emit_step_event("step.completed", s.id)
        pop_step()

    def _finalize_failure(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        s = self._step
        collector = self._collector
        collector.mark_failed()

        s.status = "failed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        s.error_summary = {"traceback": traceback.format_exc()}

        s.metadata["stream"] = collector.stream_metadata()

        assembled = collector.assembled_output()
        has_output = bool(assembled.get("text") or assembled.get("tool_calls"))

        if has_output:
            response_dict = _assembled_to_chat_response(assembled, self._request_dict)
            try:
                _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
            except Exception:
                s.metadata.update({
                    "provider": "openai",
                    "model": self._request_dict.get("model"),
                    "latency_ms": latency_ms,
                })
                _safe_attach_request_artifact(s, self._request_dict)
        else:
            s.metadata.update({
                "provider": "openai",
                "model": self._request_dict.get("model"),
                "latency_ms": latency_ms,
            })
            _safe_attach_request_artifact(s, self._request_dict)

        try:
            attach_artifact(create_json_artifact(
                artifact_type="llm_stream",
                role="output",
                data=collector.stream_artifact_payload(),
                preview_text=f"{collector.chunk_count} chunks, {collector.stream_metadata()['termination']}",
                step_id=s.id,
            ))
        except Exception:
            pass

        _emit_step_event("step.failed", s.id)
        pop_step()


# ---------------------------------------------------------------------------
# OpenAI chunk parsing
# ---------------------------------------------------------------------------

def _process_openai_chunk(collector: StreamCollector, chunk: Any) -> None:
    """Translate a single OpenAI streaming chunk into collector updates."""
    chunk_dict = _to_dict(chunk) if not isinstance(chunk, dict) else chunk

    if chunk_dict.get("id"):
        collector.set_request_id(chunk_dict["id"])

    choices = chunk_dict.get("choices") or []
    if not choices:
        usage = chunk_dict.get("usage")
        if usage and isinstance(usage, dict):
            collector.append_usage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
        return

    choice = choices[0] if isinstance(choices, list) else {}
    if not isinstance(choice, dict):
        return

    delta = choice.get("delta") or {}
    finish_reason = choice.get("finish_reason")

    if isinstance(delta, dict):
        content = delta.get("content")
        if content:
            collector.append_text_delta(content)

        tool_calls = delta.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                tc_index = tc.get("index", 0)
                func = tc.get("function") or {}
                collector.append_tool_call_delta(
                    tc_index,
                    tool_call_id=tc.get("id"),
                    name_delta=func.get("name") if isinstance(func, dict) else None,
                    arguments_delta=func.get("arguments") if isinstance(func, dict) else None,
                )

    if finish_reason:
        collector.mark_message_stop(
            finish_reason=finish_reason,
            request_id=chunk_dict.get("id"),
        )

    usage = chunk_dict.get("usage")
    if usage and isinstance(usage, dict):
        collector.append_usage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )


# ---------------------------------------------------------------------------
# Assembled output → OpenAI chat response dict
# ---------------------------------------------------------------------------

def _assembled_to_chat_response(
    assembled: dict[str, Any],
    request_dict: dict[str, Any],
) -> dict[str, Any]:
    """Convert collector assembled output to a dict matching the OpenAI
    chat completions response shape, suitable for ``normalize_openai``."""
    tool_calls_raw: list[dict[str, Any]] = []
    for tc in assembled.get("tool_calls") or []:
        args = tc.get("arguments")
        if not isinstance(args, str):
            import json
            try:
                args = json.dumps(args)
            except (TypeError, ValueError):
                args = str(args) if args is not None else ""
        tool_calls_raw.append({
            "id": tc.get("id"),
            "type": "function",
            "function": {
                "name": tc.get("name"),
                "arguments": args,
            },
        })

    message: dict[str, Any] = {"role": "assistant", "content": assembled.get("text")}
    if tool_calls_raw:
        message["tool_calls"] = tool_calls_raw

    usage = assembled.get("usage") or {}
    usage_dict: dict[str, Any] = {}
    if usage.get("prompt_tokens") is not None:
        usage_dict["prompt_tokens"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        usage_dict["completion_tokens"] = usage["completion_tokens"]
    if usage.get("total_tokens") is not None:
        usage_dict["total_tokens"] = usage["total_tokens"]

    return {
        "id": assembled.get("request_id") or "",
        "model": request_dict.get("model"),
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": assembled.get("finish_reason"),
        }],
        "usage": usage_dict,
    }


def _assembled_response_preview(assembled: dict[str, Any]) -> str:
    text = assembled.get("text")
    if text:
        return text[:200]
    tool_calls = assembled.get("tool_calls") or []
    if tool_calls:
        names = [tc.get("name", "?") for tc in tool_calls]
        return f"tool_calls: {', '.join(names)}"
    return "OpenAI streamed response"


def _safe_attach_request_artifact(s: Any, request_dict: dict[str, Any]) -> None:
    """Attach the llm_request artifact best-effort. Never raises."""
    try:
        attach_artifact(create_json_artifact(
            artifact_type="llm_request",
            role="input",
            data=request_dict,
            preview_text=f"model: {request_dict.get('model', '?')} (streamed)",
            step_id=s.id,
        ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Step enrichment
# ---------------------------------------------------------------------------

def _enrich_step(
    s: Any,
    request_dict: dict[str, Any],
    result: Any,
    latency_ms: int,
    *,
    _is_dict: bool = False,
) -> None:
    """Populate the step with metadata, summaries, and artifacts."""
    response_dict = result if _is_dict else _to_dict(result)
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
