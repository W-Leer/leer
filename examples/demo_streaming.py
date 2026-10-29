"""
Demo: Anthropic streaming with automatic Leer instrumentation.

This uses a *fake* Anthropic client that yields realistic streaming
events, so it runs without an API key or network. The resulting run
will have:
  - an LLM step with stream metadata
  - an llm_stream artifact containing all captured events
  - full playback support in the frontend

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_streaming.py
"""

from __future__ import annotations

import time
from typing import Any

from leer import configure, trace
from leer.integrations.anthropic import wrap_anthropic_client

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Fake Anthropic streaming client
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
    """Yields a realistic sequence of Anthropic streaming events."""

    def __init__(
        self,
        text_parts: list[str],
        model: str,
        startup_delay: float = 0.0,
        chunk_delay: float = 0.03,
    ) -> None:
        events: list[dict[str, Any]] = []

        events.append({
            "type": "message_start",
            "message": {
                "id": "msg_stream_demo_001",
                "model": model,
                "usage": {"input_tokens": 22},
            },
        })

        events.append({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        })

        for part in text_parts:
            events.append({
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": part},
            })

        events.append({"type": "content_block_stop", "index": 0})

        events.append({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": len(text_parts) * 3},
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
        else:
            time.sleep(self._chunk_delay)
        self._idx += 1
        return ev

    def __enter__(self) -> _FakeStreamIterator:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


TEXT_PARTS = [
    "Streaming ",
    "LLM responses ",
    "work by ",
    "sending ",
    "partial ",
    "output tokens ",
    "incrementally ",
    "as they are ",
    "generated, ",
    "rather than ",
    "waiting for ",
    "the complete ",
    "response. ",
    "This allows ",
    "clients to ",
    "display text ",
    "progressively, ",
    "reducing ",
    "perceived ",
    "latency ",
    "and improving ",
    "user experience.",
]


class _FakeMessages:
    def __init__(self, startup_delay: float = 0.0, chunk_delay: float = 0.03) -> None:
        self._startup_delay = startup_delay
        self._chunk_delay = chunk_delay

    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            model = kwargs.get("model", "claude-sonnet-5-5")
            return _FakeStreamIterator(
                text_parts=TEXT_PARTS,
                model=model,
                startup_delay=self._startup_delay,
                chunk_delay=self._chunk_delay,
            )

        return _FakeEvent({
            "id": "msg_demo_nonstream",
            "type": "message",
            "model": kwargs.get("model", "claude-sonnet-5-5"),
            "role": "assistant",
            "content": [{"type": "text", "text": "Non-streaming fallback."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })


class _FakeAnthropic:
    def __init__(self, startup_delay: float = 0.0, chunk_delay: float = 0.03) -> None:
        self.messages = _FakeMessages(startup_delay=startup_delay, chunk_delay=chunk_delay)


# ---------------------------------------------------------------------------
# Demo workflow
# ---------------------------------------------------------------------------

def _run_stream(label: str, client_obj: Any) -> str:
    """Run a streaming call and print output progressively."""
    wrapped = wrap_anthropic_client(client_obj)
    stream = wrapped.messages.create(
        model="claude-sonnet-5-5",
        messages=[
            {
                "role": "user",
                "content": "Explain how streaming LLM responses work in 2 sentences.",
            }
        ],
        max_tokens=150,
        stream=True,
    )

    collected = ""
    for event in stream:
        if getattr(event, "type", None) == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta and getattr(delta, "type", None) == "text_delta":
                text = getattr(delta, "text", "")
                print(text, end="", flush=True)
                collected += text

    print()
    print(f"  [{label}] {len(collected)} chars collected")
    return collected


@trace(workflow_name="streaming-fast")
def demo_streaming_fast() -> str:
    """Fast stream: low TTFC, fast chunk pace."""
    return _run_stream("fast", _FakeAnthropic(startup_delay=0.02, chunk_delay=0.02))


@trace(workflow_name="streaming-slow")
def demo_streaming_slow() -> str:
    """Slow stream: high startup, slower chunks — for latency compare."""
    return _run_stream("slow", _FakeAnthropic(startup_delay=0.25, chunk_delay=0.06))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: Streaming latency variants")
    print("=" * 60)

    print("\n— Fast stream —")
    demo_streaming_fast()

    print("\n— Slow stream —")
    demo_streaming_slow()

    print()
    print("Done. Compare 'streaming-fast' vs 'streaming-slow' in the Leer UI.")


if __name__ == "__main__":
    main()
