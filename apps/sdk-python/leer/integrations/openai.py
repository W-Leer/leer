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
from leer.integrations.normalize import NormalizedLLMCall, create_tool_call_artifacts, materialize_media_artifacts, normalize_openai
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
        # ``beta.chat.completions.parse`` is the original structured-output
        # entry point; wrap the ``beta`` namespace so it is instrumented too.
        if hasattr(client, "beta") and hasattr(client.beta, "chat"):
            self.beta = _WrappedBeta(client.beta)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _WrappedBeta:
    def __init__(self, beta: Any) -> None:
        self._beta = beta
        self.chat = _WrappedChat(beta.chat)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._beta, name)


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

    def parse(self, *args: Any, **kwargs: Any) -> Any:
        # Structured-output helper (returns ``message.parsed``); instrument it
        # exactly like ``create`` so schema-constrained calls are captured.
        return _instrumented_create(self._completions.parse, args, kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _WrappedResponses:
    def __init__(self, responses: Any) -> None:
        self._responses = responses

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return _instrumented_create(self._responses.create, args, kwargs)

    def parse(self, *args: Any, **kwargs: Any) -> Any:
        # Responses-API structured-output helper (returns ``output_parsed``).
        return _instrumented_create(self._responses.parse, args, kwargs)

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

def _is_responses_request(request_dict: dict[str, Any]) -> bool:
    """Detect an OpenAI Responses-API call by request shape.

    The Responses API uses ``input`` (string or list of items); chat
    completions uses ``messages`` (list of role/content dicts). When both
    are present we treat the call as Responses (Responses can mix),
    matching the dispatch rule used by ``normalize_openai``. When neither
    is present we default to chat completions for back-compat.
    """
    return "input" in request_dict and "messages" not in request_dict


def _instrumented_streaming_create(
    original_fn: Any,
    args: tuple[Any, ...],
    request_dict: dict[str, Any],
) -> Any:
    """Handle a streaming create() call.

    Creates the LLM step eagerly, then returns a wrapping iterator that
    captures chunks into a StreamCollector and finalizes the step when
    iteration completes or fails. The iterator dispatches per-chunk
    parsing based on the request's API style (chat completions vs
    Responses) so streaming captures stay in canonical parity with
    non-streaming captures.
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
    api_style = "responses" if _is_responses_request(request_dict) else "chat"
    return _StreamingIterator(raw_stream, collector, s, request_dict, t0, api_style)


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
        api_style: str = "chat",
    ) -> None:
        self._raw_stream = raw_stream
        self._collector = collector
        self._step = step
        self._request_dict = request_dict
        self._t0 = t0
        self._finalized = False
        # ``api_style`` is "chat" (chat completions chunks) or "responses"
        # (Responses-API events). Selects the chunk parser and the
        # assembled-to-response-dict converter so streaming captures
        # round-trip into the matching normalizer.
        self._api_style = api_style

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
            if self._api_style == "responses":
                _process_openai_responses_event(self._collector, chunk)
            else:
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

    def _build_response_dict(self, assembled: dict[str, Any]) -> dict[str, Any]:
        """Convert assembled stream state into the matching API-shape dict.

        Dispatched on ``self._api_style`` so the result is normalizer-ready:
        chat-completions calls produce a ``{"choices": [...]}`` shape;
        Responses-API calls produce a ``{"output": [...]}`` shape.
        """
        if self._api_style == "responses":
            return _assembled_to_responses_dict(assembled, self._request_dict)
        return _assembled_to_chat_response(assembled, self._request_dict)

    def _finalize_success(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        s = self._step
        collector = self._collector

        s.metadata["stream"] = collector.stream_metadata()

        assembled = collector.assembled_output()
        response_dict = self._build_response_dict(assembled)

        try:
            _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
        except Exception:
            _safe_partial_enrich(s, self._request_dict, response_dict, latency_ms)

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
        has_output = bool(
            assembled.get("text")
            or assembled.get("tool_calls")
            or assembled.get("refusal")
        )

        if has_output:
            response_dict = self._build_response_dict(assembled)
            try:
                _enrich_step(s, self._request_dict, response_dict, latency_ms, _is_dict=True)
            except Exception:
                _safe_partial_enrich(s, self._request_dict, response_dict, latency_ms)
        else:
            _safe_partial_enrich(s, self._request_dict, None, latency_ms)

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

def _extract_chat_cached_tokens(usage: dict[str, Any]) -> int | None:
    """Pull ``cached_tokens`` from a chat-completions chunk usage dict."""
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        value = details.get("cached_tokens")
        if isinstance(value, int):
            return value
    return None


def _push_chat_usage(collector: StreamCollector, usage: dict[str, Any]) -> None:
    collector.append_usage(
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        cached_tokens=_extract_chat_cached_tokens(usage),
    )


def _process_openai_chunk(collector: StreamCollector, chunk: Any) -> None:
    """Translate a single OpenAI streaming chunk into collector updates."""
    chunk_dict = _to_dict(chunk) if not isinstance(chunk, dict) else chunk

    if chunk_dict.get("id"):
        collector.set_request_id(chunk_dict["id"])
    if chunk_dict.get("model"):
        collector.set_response_model(chunk_dict["model"])

    choices = chunk_dict.get("choices") or []
    if not choices:
        usage = chunk_dict.get("usage")
        if isinstance(usage, dict):
            _push_chat_usage(collector, usage)
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

        # Refusal text streamed via ``delta.refusal`` (chat-completions
        # streaming surface). Routed to the dedicated refusal accumulator
        # so the assembled response emits ``message.refusal`` and Step 1's
        # refusal handling kicks in canonically.
        refusal_delta = delta.get("refusal")
        if isinstance(refusal_delta, str) and refusal_delta:
            collector.append_refusal_delta(refusal_delta)

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
    if isinstance(usage, dict):
        _push_chat_usage(collector, usage)


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
    refusal = assembled.get("refusal")
    if refusal:
        # Round-trip into the canonical chat-completions ``message.refusal``
        # field so ``_normalize_openai_chat`` produces ``meta.refusal`` and
        # the ``[refusal] ...`` text contract from Step 1 applies uniformly
        # for streaming captures.
        message["refusal"] = refusal

    usage = assembled.get("usage") or {}
    usage_dict: dict[str, Any] = {}
    if usage.get("prompt_tokens") is not None:
        usage_dict["prompt_tokens"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        usage_dict["completion_tokens"] = usage["completion_tokens"]
    if usage.get("total_tokens") is not None:
        usage_dict["total_tokens"] = usage["total_tokens"]
    if usage.get("cached_tokens") is not None:
        usage_dict["prompt_tokens_details"] = {"cached_tokens": usage["cached_tokens"]}

    return {
        "id": assembled.get("request_id") or "",
        "model": assembled.get("model") or request_dict.get("model"),
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": assembled.get("finish_reason"),
        }],
        "usage": usage_dict,
    }


# ---------------------------------------------------------------------------
# OpenAI Responses-API event parsing and assembly
# ---------------------------------------------------------------------------

def _process_openai_responses_event(collector: StreamCollector, event: Any) -> None:
    """Translate a single OpenAI Responses-API stream event into collector calls.

    Handles the load-bearing event types only: anything else is recorded as
    an ``unknown`` event so it shows up in the ``llm_stream`` artifact for
    debugging without breaking canonical assembly.

    Tool-call deltas are keyed by the event's ``output_index`` so the
    collector aggregates argument deltas onto the right function-call item
    when the model emits multiple in one response.
    """
    event_dict = _to_dict(event) if not isinstance(event, dict) else event
    event_type = event_dict.get("type")

    if event_type == "response.created":
        response = event_dict.get("response") or {}
        rid = response.get("id") if isinstance(response, dict) else None
        if rid:
            collector.set_request_id(rid)
        if isinstance(response, dict) and response.get("model"):
            collector.set_response_model(response["model"])
        collector.mark_message_start(payload={"response_id": rid})

    elif event_type == "response.output_item.added":
        item = event_dict.get("item") or {}
        if isinstance(item, dict) and item.get("type") == "function_call":
            output_index = event_dict.get("output_index", 0)
            collector.append_tool_call_delta(
                output_index,
                tool_call_id=item.get("call_id") or item.get("id"),
                name_delta=item.get("name"),
                arguments_delta=item.get("arguments") or None,
            )

    elif event_type == "response.output_text.delta":
        delta = event_dict.get("delta")
        if isinstance(delta, str) and delta:
            collector.append_text_delta(delta)

    elif event_type == "response.refusal.delta":
        delta = event_dict.get("delta")
        if isinstance(delta, str) and delta:
            collector.append_refusal_delta(delta)

    elif event_type == "response.function_call_arguments.delta":
        output_index = event_dict.get("output_index", 0)
        delta = event_dict.get("delta")
        if isinstance(delta, str) and delta:
            collector.append_tool_call_delta(output_index, arguments_delta=delta)

    elif event_type == "response.completed":
        response = event_dict.get("response") or {}
        if isinstance(response, dict):
            if response.get("model"):
                collector.set_response_model(response["model"])
            usage = response.get("usage")
            if isinstance(usage, dict):
                cached = None
                details = usage.get("input_tokens_details")
                if isinstance(details, dict) and isinstance(details.get("cached_tokens"), int):
                    cached = details["cached_tokens"]
                collector.append_usage(
                    prompt_tokens=usage.get("input_tokens"),
                    completion_tokens=usage.get("output_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    cached_tokens=cached,
                )
            status = response.get("status")
            collector.mark_message_stop(
                finish_reason=status,
                request_id=response.get("id"),
            )

    elif event_type in ("response.failed", "response.incomplete"):
        response = event_dict.get("response") or {}
        status = response.get("status") if isinstance(response, dict) else None
        if status:
            collector.set_finish_reason(status)
        collector.mark_message_stop(payload={"original_type": event_type})

    elif event_type and event_type.startswith("response."):
        # Recognized-but-unmodeled Responses event (e.g.
        # ``response.in_progress``, ``response.output_item.done``,
        # ``response.content_part.added``, ``response.output_text.done``).
        # These carry no canonical payload we assemble from, and the
        # load-bearing data they summarize is already captured via the
        # delta/usage events above, so they are intentionally dropped rather
        # than stored — keeping the ``llm_stream`` artifact focused. Unknown
        # *non*-``response.`` events still fall through to ``mark_unknown``.
        pass

    else:
        collector.mark_unknown(payload={"original_type": event_type})


def _assembled_to_responses_dict(
    assembled: dict[str, Any],
    request_dict: dict[str, Any],
) -> dict[str, Any]:
    """Convert collector assembled state to a Responses-API response dict.

    The shape mirrors what ``client.responses.create()`` returns for
    non-streaming calls (with ``output``, ``usage.input_tokens``, etc.) so
    ``normalize_openai`` dispatches to ``_normalize_openai_responses`` and
    streaming captures land in the same canonical shape as non-streaming
    captures.

    Output-array ordering: an ``assistant`` message with text content (when
    text was streamed), then any ``function_call`` items in tool-index
    order, then a ``refusal`` message (when refusal text was streamed).
    The actual interleave the model produced is lost in the streamed
    representation, but each load-bearing piece round-trips intact.
    """
    output: list[dict[str, Any]] = []

    text = assembled.get("text")
    if text:
        output.append({
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        })

    for tc in assembled.get("tool_calls") or []:
        args = tc.get("arguments")
        if args is None:
            args_str = ""
        elif isinstance(args, str):
            args_str = args
        else:
            import json as _json
            try:
                args_str = _json.dumps(args)
            except (TypeError, ValueError):
                args_str = str(args)
        output.append({
            "type": "function_call",
            "call_id": tc.get("id"),
            "name": tc.get("name"),
            "arguments": args_str,
        })

    refusal = assembled.get("refusal")
    if refusal:
        output.append({
            "type": "message",
            "role": "assistant",
            "content": [{"type": "refusal", "refusal": refusal}],
        })

    usage = assembled.get("usage") or {}
    usage_dict: dict[str, Any] = {}
    if usage.get("prompt_tokens") is not None:
        usage_dict["input_tokens"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        usage_dict["output_tokens"] = usage["completion_tokens"]
    if usage.get("total_tokens") is not None:
        usage_dict["total_tokens"] = usage["total_tokens"]
    if usage.get("cached_tokens") is not None:
        usage_dict["input_tokens_details"] = {"cached_tokens": usage["cached_tokens"]}

    return {
        "id": assembled.get("request_id") or "",
        "object": "response",
        "model": assembled.get("model") or request_dict.get("model"),
        "status": assembled.get("finish_reason"),
        "output": output,
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


def _safe_partial_enrich(
    s: Any,
    request_dict: dict[str, Any],
    response_dict: dict[str, Any] | None,
    latency_ms: int,
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
            "provider": "openai",
            "model": request_dict.get("model"),
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
    normalized = normalize_openai(request_dict, response_dict, latency_ms=latency_ms)

    media_artifacts = materialize_media_artifacts(
        normalized, response_dict, step_id=s.id,
    )
    for art in media_artifacts:
        attach_artifact(art)

    for art in create_tool_call_artifacts(normalized, step_id=s.id):
        attach_artifact(art)

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
        summary["tools"] = [
            t.get("name") or t.get("function", {}).get("name", "?")
            for t in n.input.tools
        ]
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
    return " | ".join(parts) if parts else "OpenAI request"


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
