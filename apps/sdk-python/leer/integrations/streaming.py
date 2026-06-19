"""In-memory stream collector for LLM streaming capture.

The collector is provider-agnostic: each provider wrapper translates its
native chunk format into the normalized ``push_*`` calls defined here.
The collector accumulates events, assembles final text/tool-call state,
and produces the metadata + artifact payloads that the wrapper attaches
to the step on stream completion.

Usage (inside a provider wrapper)::

    collector = StreamCollector(provider="openai", model="gpt-4.1")
    for chunk in provider_stream:
        collector.append_text_delta("Hello")
        yield chunk  # pass through unchanged
    meta = collector.stream_metadata()
    artifact = collector.stream_artifact_payload()
    assembled = collector.assembled_output()
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_CAPTURE_LIMIT_BYTES = 512 * 1024  # 512 KiB


# ---------------------------------------------------------------------------
# Normalized stream event
# ---------------------------------------------------------------------------

@dataclass
class StreamEvent:
    """Provider-agnostic representation of a single stream chunk."""

    index: int
    type: str  # text_delta | tool_call_delta | message_start | message_stop | usage | unknown
    timestamp_offset_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "type": self.type,
            "timestamp_offset_ms": self.timestamp_offset_ms,
        }
        d.update(self.payload)
        return d


# ---------------------------------------------------------------------------
# Tool-call assembly state
# ---------------------------------------------------------------------------

@dataclass
class _ToolCallAccumulator:
    """Tracks incremental assembly of a single tool call from deltas."""

    tool_call_id: str | None = None
    name_parts: list[str] = field(default_factory=list)
    arguments_parts: list[str] = field(default_factory=list)
    index: int = 0

    def assembled(self) -> dict[str, Any]:
        name = "".join(self.name_parts) or None
        raw_args = "".join(self.arguments_parts)
        arguments: Any = None
        if raw_args:
            try:
                arguments = json.loads(raw_args)
            except (json.JSONDecodeError, ValueError):
                arguments = raw_args
        return {
            "id": self.tool_call_id,
            "name": name,
            "arguments": arguments,
        }


# ---------------------------------------------------------------------------
# Thinking-block assembly state (Anthropic extended thinking)
# ---------------------------------------------------------------------------

@dataclass
class _ThinkingAccumulator:
    """Tracks incremental assembly of a single thinking block from deltas.

    Anthropic streams extended-thinking content as:
      - ``content_block_start`` with ``content_block.type == "thinking"`` or
        ``"redacted_thinking"``
      - zero or more ``content_block_delta`` events with ``delta.type ==
        "thinking_delta"`` (text increments) or ``"signature_delta"``
        (verification signature for the completed block)
      - ``content_block_stop``

    Redacted-thinking blocks carry no text deltas; the block itself is a
    placeholder ``{"type": "redacted_thinking"}`` indistinguishable from a
    standard one in canonical output.
    """

    index: int
    redacted: bool = False
    text_parts: list[str] = field(default_factory=list)
    signature_parts: list[str] = field(default_factory=list)

    def assembled(self) -> dict[str, Any]:
        if self.redacted:
            return {"type": "redacted_thinking"}
        block: dict[str, Any] = {
            "type": "thinking",
            "thinking": "".join(self.text_parts),
        }
        if self.signature_parts:
            block["signature"] = "".join(self.signature_parts)
        return block


# ---------------------------------------------------------------------------
# StreamCollector
# ---------------------------------------------------------------------------

class StreamCollector:
    """Accumulates normalized stream events and assembles final output."""

    def __init__(
        self,
        provider: str,
        model: str | None = None,
        capture_limit_bytes: int = DEFAULT_CAPTURE_LIMIT_BYTES,
    ) -> None:
        self.provider = provider
        self.model = model
        self._capture_limit = capture_limit_bytes

        # Timing
        self._start_mono: float = time.monotonic()
        self._start_wall: datetime = datetime.now(timezone.utc)
        self._first_chunk_mono: float | None = None
        self._last_chunk_mono: float | None = None

        # Event log
        self._events: list[StreamEvent] = []
        self._observed_count: int = 0
        self._captured_bytes: int = 0
        self._truncated: bool = False

        # Assembly state
        self._text_parts: list[str] = []
        self._tool_calls: dict[int, _ToolCallAccumulator] = {}
        # Thinking blocks (Anthropic extended thinking). Keyed by content-block
        # index so deltas land on the right block. Used only when a provider
        # actively streams thinking content; absent otherwise.
        self._thinking_blocks: dict[int, _ThinkingAccumulator] = {}
        # Refusal text streamed by the provider (OpenAI chat-completions
        # ``delta.refusal`` and OpenAI Responses ``response.refusal.delta``).
        # Tracked separately from ``_text_parts`` so the assembled response
        # can preserve the canonical refusal shape (chat completions
        # ``message.refusal`` / Responses ``refusal`` content block), which
        # is what the normalizers and Step 1's ``meta.refusal`` rule expect.
        self._refusal_parts: list[str] = []
        self._usage: dict[str, int | None] = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
        }
        self._finish_reason: str | None = None
        self._request_id: str | None = None
        # Model the provider reports on the wire (resolved snapshot). When set
        # it wins over the requested model in the assembled response, matching
        # the non-streaming path where ``response.model`` is authoritative.
        self._response_model: str | None = None

        # Termination
        self._termination: str = "completed"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _offset_ms(self) -> int:
        return int((time.monotonic() - self._start_mono) * 1000)

    def _record_chunk_timing(self) -> None:
        now = time.monotonic()
        if self._first_chunk_mono is None:
            self._first_chunk_mono = now
        self._last_chunk_mono = now

    def _next_index(self) -> int:
        """Return the next monotonic observed-event index."""
        idx = self._observed_count
        self._observed_count += 1
        return idx

    def _append_event(self, event: StreamEvent) -> None:
        """Store an event if within the capture budget.

        The event's ``index`` is the truthful observed position regardless
        of whether the event is stored.  After truncation, events stop being
        stored but the observed counter keeps incrementing.
        """
        event_bytes = len(json.dumps(event.to_dict()).encode())
        if not self._truncated:
            if self._captured_bytes + event_bytes > self._capture_limit:
                self._truncated = True
            else:
                self._events.append(event)
                self._captured_bytes += event_bytes

    # ------------------------------------------------------------------
    # Public push API — called by provider wrappers
    # ------------------------------------------------------------------

    def append_text_delta(self, text: str) -> None:
        self._record_chunk_timing()
        self._text_parts.append(text)
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="text_delta",
            timestamp_offset_ms=self._offset_ms(),
            payload={"text": text},
        ))

    def append_refusal_delta(self, text: str) -> None:
        """Append a streamed refusal-text delta.

        Refusal text is intentionally tracked separately from regular text
        parts so the assembled response preserves the canonical refusal
        shape that ``normalize_openai`` (and Step 1's ``meta.refusal``) rely
        on. Empty deltas are ignored.
        """
        if not text:
            return
        self._record_chunk_timing()
        self._refusal_parts.append(text)
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="refusal_delta",
            timestamp_offset_ms=self._offset_ms(),
            payload={"text": text},
        ))

    def append_tool_call_delta(
        self,
        tool_index: int = 0,
        *,
        tool_call_id: str | None = None,
        name_delta: str | None = None,
        arguments_delta: str | None = None,
    ) -> None:
        self._record_chunk_timing()
        acc = self._tool_calls.setdefault(
            tool_index,
            _ToolCallAccumulator(index=tool_index),
        )
        if tool_call_id is not None:
            acc.tool_call_id = tool_call_id
        if name_delta:
            acc.name_parts.append(name_delta)
        if arguments_delta:
            acc.arguments_parts.append(arguments_delta)

        payload: dict[str, Any] = {"tool_index": tool_index}
        if tool_call_id is not None:
            payload["tool_call_id"] = tool_call_id
        if name_delta:
            payload["name_delta"] = name_delta
        if arguments_delta:
            payload["arguments_delta"] = arguments_delta

        self._append_event(StreamEvent(
            index=self._next_index(),
            type="tool_call_delta",
            timestamp_offset_ms=self._offset_ms(),
            payload=payload,
        ))

    def append_usage(
        self,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cached_tokens: int | None = None,
    ) -> None:
        self._record_chunk_timing()
        if prompt_tokens is not None:
            self._usage["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            self._usage["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            self._usage["total_tokens"] = total_tokens
        if cached_tokens is not None:
            self._usage["cached_tokens"] = cached_tokens

        payload: dict[str, Any] = {}
        if prompt_tokens is not None:
            payload["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            payload["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        if cached_tokens is not None:
            payload["cached_tokens"] = cached_tokens

        self._append_event(StreamEvent(
            index=self._next_index(),
            type="usage",
            timestamp_offset_ms=self._offset_ms(),
            payload=payload,
        ))

    def begin_thinking_block(self, *, block_index: int, redacted: bool = False) -> None:
        """Open a thinking block at the given content-block index.

        Subsequent ``append_thinking_delta`` / ``append_thinking_signature``
        calls land on this block until another ``begin_thinking_block`` is
        opened. Redacted-thinking blocks emit no text deltas; the block is
        recorded as a placeholder so canonical output mirrors non-streaming.
        """
        self._record_chunk_timing()
        self._thinking_blocks[block_index] = _ThinkingAccumulator(
            index=block_index,
            redacted=redacted,
        )
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="thinking_start",
            timestamp_offset_ms=self._offset_ms(),
            payload={"block_index": block_index, "redacted": redacted},
        ))

    def append_thinking_delta(self, *, block_index: int, text: str) -> None:
        self._record_chunk_timing()
        acc = self._thinking_blocks.get(block_index)
        if acc is None:
            # Tolerate out-of-order events: implicitly open a non-redacted block.
            acc = _ThinkingAccumulator(index=block_index)
            self._thinking_blocks[block_index] = acc
        acc.text_parts.append(text)
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="thinking_delta",
            timestamp_offset_ms=self._offset_ms(),
            payload={"block_index": block_index, "text": text},
        ))

    def append_thinking_signature(self, *, block_index: int, signature: str) -> None:
        self._record_chunk_timing()
        acc = self._thinking_blocks.get(block_index)
        if acc is None:
            acc = _ThinkingAccumulator(index=block_index)
            self._thinking_blocks[block_index] = acc
        acc.signature_parts.append(signature)
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="thinking_signature",
            timestamp_offset_ms=self._offset_ms(),
            payload={"block_index": block_index, "signature": signature},
        ))

    def mark_message_start(self, payload: dict[str, Any] | None = None) -> None:
        self._record_chunk_timing()
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="message_start",
            timestamp_offset_ms=self._offset_ms(),
            payload=payload or {},
        ))

    def mark_message_stop(
        self,
        *,
        finish_reason: str | None = None,
        request_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._record_chunk_timing()
        if finish_reason is not None:
            self._finish_reason = finish_reason
        if request_id is not None:
            self._request_id = request_id
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="message_stop",
            timestamp_offset_ms=self._offset_ms(),
            payload=payload or {},
        ))

    def mark_unknown(self, payload: dict[str, Any] | None = None) -> None:
        self._record_chunk_timing()
        self._append_event(StreamEvent(
            index=self._next_index(),
            type="unknown",
            timestamp_offset_ms=self._offset_ms(),
            payload=payload or {},
        ))

    def set_finish_reason(self, reason: str) -> None:
        self._finish_reason = reason

    def set_request_id(self, request_id: str) -> None:
        self._request_id = request_id

    def set_response_model(self, model: str | None) -> None:
        """Record the provider-reported (resolved) model. Empty values ignored."""
        if model:
            self._response_model = model

    def mark_failed(self) -> None:
        self._termination = "failed"

    def mark_interrupted(self) -> None:
        self._termination = "interrupted"

    def mark_cancelled(self) -> None:
        self._termination = "cancelled"

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    @property
    def chunk_count(self) -> int:
        """Total observed events, including those dropped by truncation."""
        return self._observed_count

    @property
    def assembled_text(self) -> str | None:
        text = "".join(self._text_parts)
        return text if text else None

    @property
    def assembled_refusal(self) -> str | None:
        text = "".join(self._refusal_parts)
        return text if text else None

    @property
    def assembled_tool_calls(self) -> list[dict[str, Any]]:
        return [
            self._tool_calls[idx].assembled()
            for idx in sorted(self._tool_calls)
        ]

    @property
    def assembled_thinking_blocks(self) -> list[dict[str, Any]]:
        """Thinking blocks in content-block order (Anthropic streams only).

        Empty list when no thinking blocks were observed. Order matches the
        non-streaming ``content_blocks`` ordering used by ``normalize_anthropic``.
        """
        return [
            self._thinking_blocks[idx].assembled()
            for idx in sorted(self._thinking_blocks)
        ]

    def stream_metadata(self) -> dict[str, Any]:
        """Produce the ``step.metadata["stream"]`` dict per the streaming spec."""
        first_at: str | None = None
        last_at: str | None = None
        ttfc_ms: int | None = None
        stream_dur_ms: int | None = None

        if self._first_chunk_mono is not None:
            first_wall = datetime.fromtimestamp(
                self._start_wall.timestamp() + (self._first_chunk_mono - self._start_mono),
                tz=timezone.utc,
            )
            first_at = first_wall.isoformat()
            ttfc_ms = int((self._first_chunk_mono - self._start_mono) * 1000)

        if self._last_chunk_mono is not None:
            last_wall = datetime.fromtimestamp(
                self._start_wall.timestamp() + (self._last_chunk_mono - self._start_mono),
                tz=timezone.utc,
            )
            last_at = last_wall.isoformat()
            stream_dur_ms = int((self._last_chunk_mono - self._start_mono) * 1000)

        text = self.assembled_text
        return {
            "is_stream": True,
            "provider": self.provider,
            "chunk_count": self.chunk_count,
            "first_chunk_at": first_at,
            "last_chunk_at": last_at,
            "time_to_first_chunk_ms": ttfc_ms,
            "stream_duration_ms": stream_dur_ms,
            "termination": self._termination,
            "assembled_text_chars": len(text) if text else 0,
            "assembled_tool_calls": len(self._tool_calls),
            "captured_chunk_bytes": self._captured_bytes,
            "truncated_chunks": self._truncated,
        }

    def stream_artifact_payload(self) -> dict[str, Any]:
        """Produce the ``llm_stream`` artifact inline_data dict."""
        return {
            "provider": self.provider,
            "model": self.model,
            "events": [e.to_dict() for e in self._events],
        }

    def assembled_output(self) -> dict[str, Any]:
        """Provider-agnostic assembled output for normalizer consumption.

        Wrappers can use this to build a response dict compatible with
        ``normalize_openai`` / ``normalize_anthropic``, or consume it
        directly for summary generation.
        """
        tool_calls = self.assembled_tool_calls
        return {
            "text": self.assembled_text,
            "refusal": self.assembled_refusal,
            "tool_calls": tool_calls,
            "thinking_blocks": self.assembled_thinking_blocks,
            "usage": dict(self._usage),
            "finish_reason": self._finish_reason,
            "request_id": self._request_id,
            "model": self._response_model,
        }
