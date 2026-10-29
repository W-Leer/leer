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

    # So are the SDK helpers, on both ``client.messages`` and
    # ``client.beta.messages``:
    with client.messages.stream(model=..., messages=[...]) as stream:
        message = stream.get_final_message()
    parsed = client.messages.parse(model=..., messages=[...], output_format=MyModel)
"""

from __future__ import annotations

import copy
import json
import time
import traceback
from typing import Any, Iterator

from leer.artifacts import attach_artifact, create_json_artifact
from leer.context import current_step, get_current_run, pop_step, push_step
from leer.integrations.normalize import NormalizedLLMCall, create_tool_call_artifacts, materialize_media_artifacts, normalize_anthropic
from leer.integrations.streaming import StreamCollector
from leer.models import TraceStep, _now
from leer.step import _duration_ms, _emit_step_event, step as leer_step


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def wrap_anthropic_client(client: Any) -> Any:
    """Wrap an Anthropic client for automatic LLM instrumentation.

    Returns a proxy that transparently intercepts ``messages.create()``,
    ``messages.parse()`` and ``messages.stream()`` (and the same methods on
    ``beta.messages``) when inside an active trace. All other attributes and
    methods are forwarded to the original client unchanged.

    The original provider return value is always preserved — including stream
    iterators when ``stream=True``.
    """
    return _WrappedAnthropic(client)


# ---------------------------------------------------------------------------
# Proxy classes — delegate everything except the model-calling methods
# ---------------------------------------------------------------------------

class _WrappedAnthropic:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.messages = _WrappedMessages(client.messages)
        if hasattr(client, "beta") and hasattr(client.beta, "messages"):
            self.beta = _WrappedBeta(client.beta)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _WrappedBeta:
    """Proxy for ``client.beta`` that instruments ``beta.messages``."""

    def __init__(self, beta: Any) -> None:
        self._beta = beta
        self.messages = _WrappedMessages(beta.messages)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._beta, name)


class _WrappedMessages:
    """Proxy for ``client.messages`` / ``client.beta.messages``.

    Intercepts ``create()``, ``parse()`` and ``stream()``; everything else
    (``count_tokens``, ``batches``, ``tool_runner``, ...) is forwarded as-is.
    """

    def __init__(self, messages: Any) -> None:
        self._messages = messages

    def create(self, **kwargs: Any) -> Any:
        """Intercept messages.create(); Anthropic SDK uses keyword-only args."""
        return _instrumented_create(self._messages.create, kwargs)

    def parse(self, **kwargs: Any) -> Any:
        return _instrumented_create(self._messages.parse, kwargs)

    def stream(self, **kwargs: Any) -> Any:
        return _instrumented_stream(self._messages.stream, kwargs)

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
            # If full enrichment fails, fall back to a partial-capture record
            # so the step is not silently empty. We pass the best
            # representation of the response we can produce — provider SDK
            # objects are converted via ``_to_dict`` (returning ``{}`` when
            # conversion itself fails), so callers always see *something*.
            try:
                response_dict = _to_dict(result) if not isinstance(result, dict) else result
            except Exception:
                response_dict = None
            _safe_partial_enrich(s, request_dict, response_dict, latency_ms)

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
# Streaming context-manager helper (messages.stream())
# ---------------------------------------------------------------------------

class _WrappedStreamManager:
    """Instruments ``messages.stream()``.

    The manager issues the request on ``__enter__``. We create the step there,
    feed events through the same ``StreamCollector`` assembly as
    ``create(stream=True)``, and finalize when the stream ends or on
    ``__exit__``.
    """

    def __init__(self, manager: Any, request_dict: dict[str, Any]) -> None:
        self._manager = manager
        self._request_dict = request_dict
        self._iterator: _StreamingIterator | None = None

    def __enter__(self) -> Any:
        run = get_current_run()
        if run is None:
            return self._manager.__enter__()

        parent = current_step()
        s = TraceStep(
            name=str(self._request_dict.get("model") or "anthropic"),
            step_type="llm",
            sequence_index=len(run.steps),
            parent_step_id=parent.id if parent else None,
            status="running",
            started_at=_now(),
        )
        run.steps.append(s)
        push_step(s)
        _emit_step_event("step.created", s.id)
        _emit_step_event("step.started", s.id)

        t0 = time.perf_counter()
        try:
            raw_stream = self._manager.__enter__()
        except Exception:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            collector = StreamCollector(provider="anthropic", model=self._request_dict.get("model"))
            collector.mark_failed()
            s.status = "failed"
            s.ended_at = _now()
            s.duration_ms = _duration_ms(s)
            s.error_summary = {"traceback": traceback.format_exc()}
            s.metadata.update({
                "provider": "anthropic",
                "model": self._request_dict.get("model"),
                "latency_ms": latency_ms,
            })
            s.metadata["stream"] = collector.stream_metadata()
            _safe_attach_request_artifact(s, self._request_dict)
            _emit_step_event("step.failed", s.id)
            pop_step()
            raise

        collector = StreamCollector(provider="anthropic", model=self._request_dict.get("model"))
        ctx: dict[str, Any] = {}

        # ``MessageStream`` reads every event through a private ``_iterator``,
        # including for ``text_stream``, ``until_done()`` and
        # ``get_final_message()``. Routing it through the collector is the only
        # way to see those paths, and lets us hand back the genuine SDK stream.
        # Fall back to proxying if it's missing.
        inner = getattr(raw_stream, "_iterator", None)
        if inner is not None and hasattr(inner, "__next__"):
            self._iterator = _StreamingIterator(inner, collector, s, self._request_dict, t0, ctx)
            raw_stream._iterator = self._iterator
            return raw_stream

        self._iterator = _StreamingIterator(raw_stream, collector, s, self._request_dict, t0, ctx)
        return self._iterator

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        if self._iterator is not None and not self._iterator._finalized:
            if exc_type is not None:
                self._iterator._finalize_failure()
            else:
                self._iterator._finalize_success()
        return self._manager.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._manager, name)


def _instrumented_stream(stream_fn: Any, kwargs: dict[str, Any]) -> Any:
    """Wrap a ``messages.stream()`` call. Outside a trace, returns the raw manager."""
    manager = stream_fn(**kwargs)
    if get_current_run() is None:
        return manager
    return _WrappedStreamManager(manager, dict(kwargs))


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

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._raw_stream, name)

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
            assembled,
            self._request_dict,
            msg_id=self._ctx.get("msg_id"),
            response_model=self._ctx.get("model"),
            streamed_blocks=_streamed_content_blocks(self._ctx),
            stop_details=self._ctx.get("stop_details"),
        )

        try:
            _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
        except Exception:
            _safe_partial_enrich(
                s, self._request_dict, response_dict, latency_ms,
                response_model=self._ctx.get("model"),
            )

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
        streamed_blocks = _streamed_content_blocks(self._ctx)
        has_output = bool(assembled.get("text") or assembled.get("tool_calls") or streamed_blocks)

        if has_output:
            response_dict = _assembled_to_anthropic_response(
                assembled,
                self._request_dict,
                msg_id=self._ctx.get("msg_id"),
                response_model=self._ctx.get("model"),
                streamed_blocks=streamed_blocks,
                stop_details=self._ctx.get("stop_details"),
            )
            try:
                _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
            except Exception:
                _safe_partial_enrich(
                    s, self._request_dict, response_dict, latency_ms,
                    response_model=self._ctx.get("model"),
                )
        else:
            _safe_partial_enrich(
                s, self._request_dict, None, latency_ms,
                response_model=self._ctx.get("model"),
            )

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
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
        kwargs: dict[str, Any] = {}
        if usage.get("input_tokens") is not None:
            kwargs["prompt_tokens"] = usage["input_tokens"]
        # Anthropic reports cache-read tokens at ``cache_read_input_tokens``
        # on both ``message_start`` and ``message_delta``. Capture whatever
        # arrives first; ``message_delta`` may overwrite with a final value.
        if usage.get("cache_read_input_tokens") is not None:
            kwargs["cached_tokens"] = usage["cache_read_input_tokens"]
        if kwargs:
            collector.append_usage(**kwargs)

    elif event_type == "content_block_start":
        block = event_dict.get("content_block") or {}
        block_index = event_dict.get("index", 0)
        block_type = block.get("type")
        ctx.setdefault("blocks", {})[block_index] = copy.deepcopy(block)
        if block_type == "tool_use":
            collector.append_tool_call_delta(
                block_index,
                tool_call_id=block.get("id"),
                name_delta=block.get("name"),
            )
        elif block_type == "thinking":
            collector.begin_thinking_block(block_index=block_index, redacted=False)
        elif block_type == "redacted_thinking":
            collector.begin_thinking_block(block_index=block_index, redacted=True)

    elif event_type == "content_block_delta":
        delta = event_dict.get("delta") or {}
        delta_type = delta.get("type")
        block_index = event_dict.get("index", 0)
        _accumulate_block_delta(ctx, block_index, delta)

        if delta_type == "text_delta":
            text = delta.get("text", "")
            if text:
                collector.append_text_delta(text)
        elif delta_type == "input_json_delta":
            partial = delta.get("partial_json", "")
            if partial:
                collector.append_tool_call_delta(block_index, arguments_delta=partial)
        elif delta_type == "thinking_delta":
            text = delta.get("thinking", "")
            if text:
                collector.append_thinking_delta(block_index=block_index, text=text)
        elif delta_type == "signature_delta":
            sig = delta.get("signature", "")
            if sig:
                collector.append_thinking_signature(block_index=block_index, signature=sig)

    elif event_type == "message_delta":
        delta = event_dict.get("delta") or {}
        stop_reason = delta.get("stop_reason")
        if stop_reason:
            collector.set_finish_reason(stop_reason)
        if delta.get("stop_details") is not None:
            ctx["stop_details"] = delta["stop_details"]
        usage = event_dict.get("usage") if isinstance(event_dict.get("usage"), dict) else {}
        kwargs = {}
        if usage.get("output_tokens") is not None:
            kwargs["completion_tokens"] = usage["output_tokens"]
        if usage.get("cache_read_input_tokens") is not None:
            kwargs["cached_tokens"] = usage["cache_read_input_tokens"]
        if kwargs:
            collector.append_usage(**kwargs)

    elif event_type == "message_stop":
        collector.mark_message_stop(request_id=ctx.get("msg_id"))

    elif event_type not in ("content_block_stop", "ping", *_HELPER_EVENT_TYPES):
        collector.mark_unknown(payload={"original_type": event_type})


# Convenience events ``MessageStream`` synthesizes alongside the raw events it
# was built from (e.g. ``text`` next to each ``text_delta``). The raw events
# already carry the data, so these are skipped rather than logged as unknown.
_HELPER_EVENT_TYPES = ("text", "thinking", "signature", "input_json", "citation")


def _accumulate_block_delta(ctx: dict[str, Any], index: int, delta: dict[str, Any]) -> None:
    """Apply a delta to the block it belongs to, the way the SDK's
    ``accumulate_event`` does, so the streamed message keeps every block type,
    each text block, and the original order."""
    block = ctx.get("blocks", {}).get(index)
    if block is None:
        return
    delta_type = delta.get("type")
    if delta_type == "text_delta":
        block["text"] = (block.get("text") or "") + (delta.get("text") or "")
    elif delta_type == "input_json_delta":
        partial = ctx.setdefault("partial_json", {})
        partial[index] = partial.get(index, "") + (delta.get("partial_json") or "")
    elif delta_type == "thinking_delta":
        block["thinking"] = (block.get("thinking") or "") + (delta.get("thinking") or "")
    elif delta_type == "signature_delta":
        block["signature"] = delta.get("signature")
    elif delta_type == "citations_delta":
        block.setdefault("citations", []).append(delta.get("citation"))


def _streamed_content_blocks(ctx: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Blocks rebuilt from stream events, in index order; ``None`` when no
    ``content_block_start`` arrived (callers fall back to the collector)."""
    blocks = ctx.get("blocks")
    if not blocks:
        return None
    partial = ctx.get("partial_json", {})
    content: list[dict[str, Any]] = []
    for index in sorted(blocks):
        block = dict(blocks[index])
        raw = partial.get(index)
        if raw:
            try:
                block["input"] = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                block["input"] = raw
        content.append(block)
    return content


# ---------------------------------------------------------------------------
# Assembled output → Anthropic response dict
# ---------------------------------------------------------------------------

def _assembled_to_anthropic_response(
    assembled: dict[str, Any],
    request_dict: dict[str, Any],
    *,
    msg_id: str | None = None,
    response_model: str | None = None,
    streamed_blocks: list[dict[str, Any]] | None = None,
    stop_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert collector assembled output to a dict matching the Anthropic
    messages response shape, suitable for ``normalize_anthropic``.

    ``response_model`` (when present) is the model reported by the provider
    in the ``message_start`` event — that wins over the request model so
    streaming behavior matches the non-streaming path, where
    ``response.model`` is authoritative.

    ``streamed_blocks`` (from ``_streamed_content_blocks``) are used as the
    content when present; the collector's text/thinking/tool_use assembly is
    the fallback.
    """
    response: dict[str, Any] = {
        "id": msg_id or assembled.get("request_id") or "",
        "model": response_model or request_dict.get("model"),
        "content": streamed_blocks if streamed_blocks is not None else _collector_content(assembled),
        "stop_reason": assembled.get("finish_reason"),
        "usage": _collector_usage(assembled),
    }
    if stop_details is not None:
        response["stop_details"] = stop_details
    return response


def _collector_content(assembled: dict[str, Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []

    # Thinking blocks come first to match Anthropic's non-streaming ordering
    # (extended-thinking blocks are emitted before the final assistant text).
    for block in assembled.get("thinking_blocks") or []:
        content.append(block)

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
    return content


def _collector_usage(assembled: dict[str, Any]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    raw_usage = assembled.get("usage") or {}
    if raw_usage.get("prompt_tokens") is not None:
        usage["input_tokens"] = raw_usage["prompt_tokens"]
    if raw_usage.get("completion_tokens") is not None:
        usage["output_tokens"] = raw_usage["completion_tokens"]
    if raw_usage.get("cached_tokens") is not None:
        # Round-trip into the canonical Anthropic key so the normalizer
        # (which reads ``cache_read_input_tokens``) sees the streamed value.
        usage["cache_read_input_tokens"] = raw_usage["cached_tokens"]
    return usage


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


def _safe_partial_enrich(
    s: Any,
    request_dict: dict[str, Any],
    response_dict: dict[str, Any] | None,
    latency_ms: int,
    *,
    response_model: str | None = None,
) -> None:
    """Best-effort metadata + artifacts for cases where ``_enrich_step``
    cannot run (raised, or was never reachable because no output was
    captured). Never raises.

    Guarantees:
    - ``metadata.provider`` / ``metadata.model`` / ``metadata.latency_ms``
      are populated.
    - ``metadata["capture"] == "partial"`` so consumers can distinguish
      partial captures from fully-enriched steps without false positives.
    - The ``llm_request`` artifact is always attached.
    - The ``llm_response`` artifact is attached when a ``response_dict``
      is available, so debugging context is preserved even when
      normalization fails.
    """
    try:
        s.metadata.update({
            "provider": "anthropic",
            "model": response_model or request_dict.get("model"),
            "latency_ms": latency_ms,
            "capture": "partial",
        })
    except Exception:
        pass

    try:
        attach_artifact(create_json_artifact(
            artifact_type="llm_request",
            role="input",
            data=request_dict,
            preview_text=f"model: {request_dict.get('model', '?')} (partial capture)",
            step_id=s.id,
        ))
    except Exception:
        pass

    if response_dict is not None:
        try:
            attach_artifact(create_json_artifact(
                artifact_type="llm_response",
                role="output",
                data=response_dict,
                preview_text="partial capture (raw response preserved)",
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

    for art in create_tool_call_artifacts(normalized, step_id=s.id):
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
            "cached_tokens": normalized.usage.cached_tokens,
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
    from leer.integrations.normalize import summarize_tool_call

    summary: dict[str, Any] = {}
    if n.output.text:
        summary["text"] = n.output.text[:500]
    if n.output.tool_calls:
        summary["tool_calls"] = [
            summarize_tool_call(tc) for tc in n.output.tool_calls
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
    # Walk reversed so the *last* user message wins — that is the message
    # the model actually saw, and matches `_input_summary` so preview and
    # summary do not disagree on multi-turn chats.
    for m in reversed(n.input.messages):
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
                result = _call_dump(fn) if method == "model_dump" else fn()
                if isinstance(result, dict):
                    return result
            except Exception:
                continue
    return {}


def _call_dump(model_dump: Any) -> Any:
    # SDK generic models (e.g. ``ParsedMessage``) emit Pydantic serializer
    # warnings when dumped, which would surface in the caller's logs.
    try:
        return model_dump(warnings=False)
    except TypeError:
        return model_dump()
