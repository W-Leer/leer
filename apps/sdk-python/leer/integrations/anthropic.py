"""Anthropic wrapper for Leer SDK.

Usage::

    from anthropic import Anthropic
    from leer.integrations.anthropic import wrap_anthropic_client

    client = wrap_anthropic_client(Anthropic())

    # Inside a @trace, every create() call automatically produces
    # an LLM step with metadata, artifacts, and summaries.
    result = client.messages.create(model="claude-sonnet-4-20250514", messages=[...])

    # Streaming is also supported transparently:
    stream = client.messages.create(
        model="claude-sonnet-4-20250514", messages=[...], stream=True,
    )
    for event in stream:
        print(event)  # original events, unchanged
"""

from __future__ import annotations

import json
import time
import traceback
from typing import Any, Iterator

from leer.artifacts import attach_artifact, create_json_artifact
from leer.context import current_step, get_current_run, pop_step, push_step
from leer.integrations.normalize import NormalizedLLMCall, materialize_media_artifacts, normalize_anthropic
from leer.integrations.streaming import StreamCollector
from leer.models import TraceStep, _now
from leer.step import _duration_ms, _emit_step_event, step as leer_step


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wrap_anthropic_client(client: Any) -> Any:
    """Wrap an Anthropic client for automatic LLM instrumentation.

    Returns a proxy that transparently intercepts ``messages.create()``
    when inside an active trace. All other attributes and methods are
    forwarded to the original client unchanged.

    The original provider return value is always preserved — including stream
    iterators when ``stream=True``.
    """
    return _WrappedAnthropic(client)


# ---------------------------------------------------------------------------
# Proxy classes — delegate everything except messages.create()
# ---------------------------------------------------------------------------

class _WrappedAnthropic:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.messages = _WrappedMessages(client.messages)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _WrappedMessages:
    """Proxy for ``client.messages`` that intercepts ``create()``."""

    def __init__(self, messages: Any) -> None:
        self._messages = messages

    def create(self, **kwargs: Any) -> Any:
        """Intercept messages.create(); Anthropic SDK uses keyword-only args."""
        return _instrumented_create(self._messages.create, kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._messages, name)


# ---------------------------------------------------------------------------
# Instrumented call
# ---------------------------------------------------------------------------

def _instrumented_create(
    original_fn: Any,
    kwargs: dict[str, Any],
) -> Any:
    """Call the original create() and instrument it when inside a trace.

    Anthropic's ``messages.create()`` uses keyword arguments exclusively
    (model, messages, system, max_tokens, etc.).

    When ``stream=True`` is detected the call is handled by the streaming
    path which wraps the returned iterator.
    """
    run = get_current_run()
    if run is None:
        return original_fn(**kwargs)

    request_dict = dict(kwargs)

    if request_dict.get("stream"):
        return _instrumented_streaming_create(original_fn, request_dict)

    model_hint = request_dict.get("model") or "anthropic"
    step_name = str(model_hint)

    with leer_step(step_name, step_type="llm") as s:
        t0 = time.perf_counter()

        try:
            result = original_fn(**kwargs)
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
    request_dict: dict[str, Any],
) -> Any:
    """Handle a streaming create() call.

    Creates the LLM step eagerly, then returns a wrapping iterator that
    captures events into a StreamCollector and finalizes the step when
    iteration completes or fails.
    """
    run = get_current_run()
    if run is None:
        return original_fn(**request_dict)

    model_hint = request_dict.get("model") or "anthropic"
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
        raw_stream = original_fn(**request_dict)
    except Exception:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        collector = StreamCollector(provider="anthropic", model=request_dict.get("model"))
        collector.mark_failed()

        s.status = "failed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        s.error_summary = {"traceback": traceback.format_exc()}
        s.metadata.update({
            "provider": "anthropic",
            "model": request_dict.get("model"),
            "latency_ms": latency_ms,
        })
        s.metadata["stream"] = collector.stream_metadata()
        _safe_attach_request_artifact(s, request_dict)
        _emit_step_event("step.failed", s.id)
        pop_step()
        raise

    collector = StreamCollector(provider="anthropic", model=request_dict.get("model"))
    ctx: dict[str, Any] = {}
    return _StreamingIterator(raw_stream, collector, s, request_dict, t0, ctx)


# ---------------------------------------------------------------------------
# Streaming iterator wrapper
# ---------------------------------------------------------------------------

class _StreamingIterator:
    """Wraps an Anthropic stream, captures events, and finalizes the step."""

    def __init__(
        self,
        raw_stream: Any,
        collector: StreamCollector,
        step: TraceStep,
        request_dict: dict[str, Any],
        t0: float,
        ctx: dict[str, Any],
    ) -> None:
        self._raw_stream = raw_stream
        self._collector = collector
        self._step = step
        self._request_dict = request_dict
        self._t0 = t0
        self._ctx = ctx
        self._finalized = False

    def __iter__(self) -> Iterator[Any]:
        return self

    def __next__(self) -> Any:
        try:
            event = next(self._raw_stream)
        except StopIteration:
            self._finalize_success()
            raise
        except Exception:
            self._finalize_failure()
            raise

        try:
            _process_anthropic_event(self._collector, event, self._ctx)
        except Exception:
            pass

        return event

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
        response_dict = _assembled_to_anthropic_response(
            assembled, self._request_dict, msg_id=self._ctx.get("msg_id"),
        )

        try:
            _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
        except Exception:
            s.metadata.update({
                "provider": "anthropic",
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
            response_dict = _assembled_to_anthropic_response(
                assembled, self._request_dict, msg_id=self._ctx.get("msg_id"),
            )
            try:
                _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
            except Exception:
                s.metadata.update({
                    "provider": "anthropic",
                    "model": self._request_dict.get("model"),
                    "latency_ms": latency_ms,
                })
                _safe_attach_request_artifact(s, self._request_dict)
        else:
            s.metadata.update({
                "provider": "anthropic",
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
# Anthropic event parsing
# ---------------------------------------------------------------------------

def _process_anthropic_event(
    collector: StreamCollector,
    event: Any,
    ctx: dict[str, Any],
) -> None:
    """Translate a single Anthropic stream event into collector updates."""
    event_dict = _to_dict(event) if not isinstance(event, dict) else event
    event_type = event_dict.get("type")

    if event_type == "message_start":
        msg = event_dict.get("message") or {}
        msg_id = msg.get("id")
        if msg_id:
            collector.set_request_id(msg_id)
            ctx["msg_id"] = msg_id
        if msg.get("model"):
            ctx["model"] = msg["model"]
        collector.mark_message_start(payload={"message_id": msg_id})
        usage = msg.get("usage") or {}
        if usage.get("input_tokens") is not None:
            collector.append_usage(prompt_tokens=usage["input_tokens"])

    elif event_type == "content_block_start":
        block = event_dict.get("content_block") or {}
        block_index = event_dict.get("index", 0)
        if block.get("type") == "tool_use":
            collector.append_tool_call_delta(
                block_index,
                tool_call_id=block.get("id"),
                name_delta=block.get("name"),
            )

    elif event_type == "content_block_delta":
        delta = event_dict.get("delta") or {}
        delta_type = delta.get("type")
        block_index = event_dict.get("index", 0)

        if delta_type == "text_delta":
            text = delta.get("text", "")
            if text:
                collector.append_text_delta(text)
        elif delta_type == "input_json_delta":
            partial = delta.get("partial_json", "")
            if partial:
                collector.append_tool_call_delta(block_index, arguments_delta=partial)

    elif event_type == "message_delta":
        delta = event_dict.get("delta") or {}
        stop_reason = delta.get("stop_reason")
        if stop_reason:
            collector.set_finish_reason(stop_reason)
        usage = event_dict.get("usage") or {}
        if usage.get("output_tokens") is not None:
            collector.append_usage(completion_tokens=usage["output_tokens"])

    elif event_type == "message_stop":
        collector.mark_message_stop(request_id=ctx.get("msg_id"))

    elif event_type not in ("content_block_stop", "ping"):
        collector.mark_unknown(payload={"original_type": event_type})


# ---------------------------------------------------------------------------
# Assembled output → Anthropic response dict
# ---------------------------------------------------------------------------

def _assembled_to_anthropic_response(
    assembled: dict[str, Any],
    request_dict: dict[str, Any],
    *,
    msg_id: str | None = None,
) -> dict[str, Any]:
    """Convert collector assembled output to a dict matching the Anthropic
    messages response shape, suitable for ``normalize_anthropic``."""
    content: list[dict[str, Any]] = []

    text = assembled.get("text")
    if text:
        content.append({"type": "text", "text": text})

    for tc in assembled.get("tool_calls") or []:
        args = tc.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                pass
        content.append({
            "type": "tool_use",
            "id": tc.get("id"),
            "name": tc.get("name"),
            "input": args if args is not None else {},
        })

    usage: dict[str, Any] = {}
    raw_usage = assembled.get("usage") or {}
    if raw_usage.get("prompt_tokens") is not None:
        usage["input_tokens"] = raw_usage["prompt_tokens"]
    if raw_usage.get("completion_tokens") is not None:
        usage["output_tokens"] = raw_usage["completion_tokens"]

    return {
        "id": msg_id or assembled.get("request_id") or "",
        "model": request_dict.get("model"),
        "content": content,
        "stop_reason": assembled.get("finish_reason"),
        "usage": usage,
    }


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
    normalized = normalize_anthropic(request_dict, response_dict, latency_ms=latency_ms)

    media_artifacts = materialize_media_artifacts(
        normalized, response_dict, step_id=s.id,
    )
    for art in media_artifacts:
        attach_artifact(art)

    s.metadata.update({
        "provider": "anthropic",
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
            "provider": "anthropic",
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
    from leer.integrations.normalize import _summarize_content_for_user

    summary: dict[str, Any] = {}
    if n.model:
        summary["model"] = n.model
    if n.input.system:
        summary["system"] = n.input.system[:200]
    for m in reversed(n.input.messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            summary["user"] = _summarize_content_for_user(content)
            break
    if n.input.tools:
        summary["tools"] = [t.get("name", "?") for t in n.input.tools]
    return summary


def _output_summary(n: NormalizedLLMCall) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if n.output.text:
        summary["text"] = n.output.text[:500]
    if n.output.tool_calls:
        summary["tool_calls"] = [
            {"name": tc.get("name", "?")} for tc in n.output.tool_calls
        ]
    media_parts = [
        b for b in n.output.content_blocks
        if b.get("type") in ("image", "document", "audio", "video", "file")
    ]
    if media_parts:
        summary["media"] = [
            f"[{b['type']}" + (f": {b['filename']}" if b.get("filename") else "") + "]"
            for b in media_parts
        ]
    if n.usage.total_tokens is not None:
        summary["tokens"] = n.usage.total_tokens
    return summary


# ---------------------------------------------------------------------------
# Artifact previews — short strings for quick scanning
# ---------------------------------------------------------------------------

def _request_preview(n: NormalizedLLMCall) -> str:
    from leer.integrations.normalize import _summarize_content_for_user

    parts: list[str] = []
    if n.model:
        parts.append(f"model: {n.model}")
    if n.input.system:
        parts.append(f"system: {n.input.system[:80]}")
    for m in n.input.messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            parts.append(f"user: {_summarize_content_for_user(content)[:80]}")
            break
    return " | ".join(parts) if parts else "Anthropic request"


def _response_preview(n: NormalizedLLMCall) -> str:
    if n.output.text:
        return n.output.text[:200]
    if n.output.tool_calls:
        names = [tc.get("name", "?") for tc in n.output.tool_calls]
        return f"tool_calls: {', '.join(names)}"
    media = [b for b in n.output.content_blocks if b.get("type") in ("image", "document", "audio", "video", "file")]
    if media:
        labels = [b.get("preview_text") or b.get("type", "media") for b in media]
        return ", ".join(labels)
    return "Anthropic response"


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
