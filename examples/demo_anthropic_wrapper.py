"""
Demo: Anthropic wrapper with automatic LLM instrumentation.

This uses a *fake* Anthropic client so it runs without an API key or network.
It demonstrates exactly what happens when you use wrap_anthropic_client()
inside a trace — the wrapper auto-creates steps, metadata, artifacts,
and summaries for every LLM call.

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_anthropic_wrapper.py
"""

from __future__ import annotations

import json
from typing import Any

from leer import configure, step, trace
from leer.integrations.anthropic import wrap_anthropic_client

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Fake Anthropic client — simulates the real SDK without network calls
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data

    def __repr__(self) -> str:
        return f"FakeResponse({self._data.get('id', '?')})"


class _FakeMessages:
    def create(self, **kwargs: Any) -> _FakeResponse:
        model = kwargs.get("model", "claude-sonnet-5-5")
        messages = kwargs.get("messages", [])
        user_msg = next(
            (m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)),
            "",
        )

        if "fail" in user_msg.lower():
            raise RuntimeError(f"Simulated API error for: {user_msg[:60]}")

        return _FakeResponse({
            "id": "msg_demo_001",
            "type": "message",
            "model": model,
            "role": "assistant",
            "content": [
                {"type": "text", "text": f"Here is a summary of your request about: {user_msg[:80]}"},
            ],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 20,
                "output_tokens": 15,
            },
        })


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


# ---------------------------------------------------------------------------
# Demo workflows
# ---------------------------------------------------------------------------

client = wrap_anthropic_client(_FakeAnthropic())


@trace(workflow_name="anthropic-wrapper-success")
def demo_success() -> dict[str, Any]:
    """A normal wrapped Anthropic call — auto-produces step, artifacts, summaries."""

    with step("prepare_prompt", step_type="code") as s:
        prompt = "Explain how Leer traces LLM calls in three bullet points."
        s.output = {"prompt": prompt}

    result = client.messages.create(
        model="claude-sonnet-5-5",
        system="You are a concise technical writer.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        service_tier="auto",
    )

    response_text = result.model_dump()["content"][0]["text"]
    return {"response": response_text}


@trace(workflow_name="anthropic-wrapper-failure")
def demo_failure() -> dict[str, Any]:
    """A failing Anthropic call — the wrapper records the error in the step."""

    result = client.messages.create(
        model="claude-sonnet-5-5",
        messages=[{"role": "user", "content": "Please fail this request"}],
        max_tokens=100,
    )

    return {"response": result.model_dump()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: Anthropic wrapper — successful call")
    print("=" * 60)
    output = demo_success()
    print(f"  Result: {json.dumps(output, indent=2)}")
    print()

    print("=" * 60)
    print("Demo: Anthropic wrapper — failing call")
    print("=" * 60)
    try:
        demo_failure()
    except RuntimeError as e:
        print(f"  Caught expected error: {e}")
    print()

    print("Done. Check the Leer UI for two runs under 'demo-project'.")


if __name__ == "__main__":
    main()
