"""
Demo: Compare-page blob-backed stream validation.

Creates TWO streaming LLM runs whose llm_stream artifacts are large
enough to exceed the default blob threshold (256 KB), so the compare
page can validate per-side blob lazy loading of stream events.

Runs produced:
  stream-blob-fast  — low startup delay, fast chunk pace
  stream-blob-slow  — higher startup delay, slower chunk pace

Each run generates ~1,200 content_block_delta events with realistic
text, producing an llm_stream artifact of roughly 400–500 KB — well
above the 256 KB default threshold.

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_blob_stream_compare.py
"""

from __future__ import annotations

import json
import time
from typing import Any

from leer import configure, trace
from leer.integrations.anthropic import wrap_anthropic_client

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


CHUNK_COUNT = 1200
CHUNK_TEMPLATE = (
    "Token {i}: Large language models generate text by predicting the next "
    "token in a sequence. Each chunk in a streaming response represents one "
    "or more decoded tokens sent to the client incrementally. "
    "Chunk {i} of {total}."
)


# ---------------------------------------------------------------------------
# Fake Anthropic streaming client (large payload variant)
# ---------------------------------------------------------------------------


class _FakeEvent:
    """Mimics an Anthropic SSE event object with attribute access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        val = self._data.get(name)
        if isinstance(val, dict):
            return _FakeEvent(val)
        return val

    def model_dump(self) -> dict[str, Any]:
        return self._data


class _FakeStreamIterator:
    """Yields a large sequence of Anthropic streaming events."""

    def __init__(
        self,
        chunk_count: int,
        model: str,
        startup_delay: float = 0.0,
        chunk_delay: float = 0.0,
    ) -> None:
        events: list[dict[str, Any]] = []

        events.append({
            "type": "message_start",
            "message": {
                "id": "msg_blob_compare_demo",
                "model": model,
                "usage": {"input_tokens": 45},
            },
        })

        events.append({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        })

        for i in range(chunk_count):
            events.append({
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "text_delta",
                    "text": CHUNK_TEMPLATE.format(i=i, total=chunk_count),
                },
            })

        events.append({"type": "content_block_stop", "index": 0})

        events.append({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": chunk_count * 8},
        })

        events.append({"type": "message_stop"})

        self._events = [_FakeEvent(e) for e in events]
        self._idx = 0
        self._startup_delay = startup_delay
        self._chunk_delay = chunk_delay

    def __iter__(self) -> _FakeStreamIterator:
        return self

    def __next__(self) -> _FakeEvent:
        if self._idx >= len(self._events):
            raise StopIteration
        ev = self._events[self._idx]
        if self._idx == 0 and self._startup_delay > 0:
            time.sleep(self._startup_delay)
        elif self._chunk_delay > 0:
            time.sleep(self._chunk_delay)
        self._idx += 1
        return ev

    def __enter__(self) -> _FakeStreamIterator:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FakeMessages:
    def __init__(
        self,
        chunk_count: int,
        startup_delay: float = 0.0,
        chunk_delay: float = 0.0,
    ) -> None:
        self._chunk_count = chunk_count
        self._startup_delay = startup_delay
        self._chunk_delay = chunk_delay

    def create(self, **kwargs: Any) -> Any:
        model = kwargs.get("model", "claude-sonnet-4-20250514")
        if kwargs.get("stream"):
            return _FakeStreamIterator(
                chunk_count=self._chunk_count,
                model=model,
                startup_delay=self._startup_delay,
                chunk_delay=self._chunk_delay,
            )
        return _FakeEvent({
            "id": "msg_blob_nonstream",
            "type": "message",
            "model": model,
            "role": "assistant",
            "content": [{"type": "text", "text": "Fallback."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })


class _FakeAnthropic:
    def __init__(
        self,
        chunk_count: int,
        startup_delay: float = 0.0,
        chunk_delay: float = 0.0,
    ) -> None:
        self.messages = _FakeMessages(
            chunk_count=chunk_count,
            startup_delay=startup_delay,
            chunk_delay=chunk_delay,
        )


# ---------------------------------------------------------------------------
# Demo workflows
# ---------------------------------------------------------------------------


def _run_stream(label: str, client_obj: Any) -> int:
    """Run a streaming call, count chunks, suppress per-chunk printing."""
    wrapped = wrap_anthropic_client(client_obj)
    stream = wrapped.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[
            {
                "role": "user",
                "content": (
                    "Write a detailed technical explanation of how streaming "
                    "LLM responses work, covering tokenization, buffering, "
                    "and incremental decoding. Be thorough."
                ),
            }
        ],
        max_tokens=8000,
        stream=True,
    )

    chunks = 0
    for event in stream:
        if getattr(event, "type", None) == "content_block_delta":
            chunks += 1

    print(f"  [{label}] {chunks} chunks streamed")
    return chunks


@trace(workflow_name="stream-blob-fast")
def demo_fast() -> dict:
    """Fast stream: low TTFC, fast chunk pace."""
    chunks = _run_stream(
        "fast",
        _FakeAnthropic(chunk_count=CHUNK_COUNT, startup_delay=0.01, chunk_delay=0.001),
    )
    return {"chunks": chunks}


@trace(workflow_name="stream-blob-slow")
def demo_slow() -> dict:
    """Slow stream: higher TTFC, slower chunks."""
    chunks = _run_stream(
        "slow",
        _FakeAnthropic(chunk_count=CHUNK_COUNT, startup_delay=0.15, chunk_delay=0.003),
    )
    return {"chunks": chunks}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    sample_event = json.dumps({
        "index": 0,
        "type": "content_block_delta",
        "timestamp_offset_ms": 0,
        "text_delta": CHUNK_TEMPLATE.format(i=0, total=CHUNK_COUNT),
    }, separators=(",", ":")).encode()
    estimated_bytes = len(sample_event) * CHUNK_COUNT
    threshold = 256 * 1024

    print("=" * 60)
    print("Demo: Compare-page blob-backed stream validation")
    print("=" * 60)
    print()
    print(f"  Chunks per run:     {CHUNK_COUNT:>8,}")
    print(f"  Est. event payload: {estimated_bytes:>8,} bytes")
    print(f"  Blob threshold:     {threshold:>8,} bytes")
    print(f"  Above threshold:    {'yes' if estimated_bytes > threshold else 'NO — may stay inline'}")
    print()

    print("  Creating stream-blob-fast...")
    demo_fast()
    print("  Creating stream-blob-slow...")
    demo_slow()

    print()
    print("=" * 60)
    print("What to inspect in the UI (compare page):")
    print("=" * 60)
    print()
    print("  1. Open http://localhost:3000 → demo-project")
    print("  2. Select 'stream-blob-fast' and 'stream-blob-slow'")
    print("  3. Open the Compare page for these two runs")
    print()
    print("  Verify:")
    print("    → Stream latency / chunk count sections render from metadata")
    print("    → Open stream playback → click Run A")
    print("    →   Events should lazy-load (blob-backed llm_stream)")
    print("    →   Playback, grouping, raw view should work after load")
    print("    → Switch to Run B → events lazy-load independently")
    print("    → Loading indicator is per-side (A does not affect B)")
    print("    → If a fetch fails, error + Retry button appear for that side only")
    print()
    print("  See docs/04-execution/blob-storage-qa.md for the full checklist.")


if __name__ == "__main__":
    main()
