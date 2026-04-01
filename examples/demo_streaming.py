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

    def __init__(self, text_parts: list[str], model: str) -> None:
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

    def __iter__(self) -> _FakeStreamIterator:
        return self

    def __next__(self) -> _FakeEvent:
        if self._idx >= len(self._events):
            raise StopIteration
        ev = self._events[self._idx]
        self._idx += 1
        time.sleep(0.03)
        return ev

    def __enter__(self) -> _FakeStreamIterator:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FakeMessages:
    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            model = kwargs.get("model", "claude-sonnet-4-20250514")
            return _FakeStreamIterator(
                text_parts=[
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
                ],
                model=model,
            )

        return _FakeEvent({
            "id": "msg_demo_nonstream",
            "type": "message",
            "model": kwargs.get("model", "claude-sonnet-4-20250514"),
            "role": "assistant",
            "content": [{"type": "text", "text": "Non-streaming fallback."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


# ---------------------------------------------------------------------------
# Demo workflow
# ---------------------------------------------------------------------------

client = wrap_anthropic_client(_FakeAnthropic())


@trace(workflow_name="streaming-anthropic")
def demo_streaming() -> str:
    """A streaming Anthropic call — produces a run with stream events."""

    stream = client.messages.create(
        model="claude-sonnet-4-20250514",
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
    return collected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: Anthropic streaming call")
    print("=" * 60)

    result = demo_streaming()

    print()
    print(f"Collected {len(result)} chars.")
    print("Done. Check the Leer UI for a run under 'demo-project'.")


if __name__ == "__main__":
    main()
