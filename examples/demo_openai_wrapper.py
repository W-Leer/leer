"""
Demo: OpenAI wrapper with automatic LLM instrumentation.

This uses a *fake* OpenAI client so it runs without an API key or network.
It demonstrates exactly what happens when you use wrap_openai_client()
inside a trace — the wrapper auto-creates steps, metadata, artifacts,
and summaries for every LLM call.

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_openai_wrapper.py
"""

from __future__ import annotations

import json
from typing import Any

from leer import configure, step, trace
from leer.integrations.openai import wrap_openai_client

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Fake OpenAI client — simulates the real SDK without network calls
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data

    def __repr__(self) -> str:
        return f"FakeResponse({self._data.get('id', '?')})"


class _FakeCompletions:
    def create(self, **kwargs: Any) -> _FakeResponse:
        model = kwargs.get("model", "gpt-4.1")
        messages = kwargs.get("messages", [])
        user_msg = next(
            (m["content"] for m in messages if m.get("role") == "user"), ""
        )

        if "fail" in user_msg.lower():
            raise RuntimeError(f"Simulated API error for: {user_msg[:60]}")

        return _FakeResponse({
            "id": "chatcmpl-demo-001",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"Here is a summary of your request about: {user_msg[:80]}",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 25,
                "completion_tokens": 18,
                "total_tokens": 43,
            },
        })


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


# ---------------------------------------------------------------------------
# Demo workflows
# ---------------------------------------------------------------------------

client = wrap_openai_client(_FakeOpenAI())


@trace(workflow_name="openai-wrapper-success")
def demo_success() -> dict[str, Any]:
    """A normal wrapped LLM call — auto-produces step, artifacts, summaries."""

    with step("prepare_prompt", step_type="code") as s:
        prompt = "Explain how Leer traces LLM calls in three bullet points."
        s.output = {"prompt": prompt}

    result = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are a concise technical writer."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    response_text = result.model_dump()["choices"][0]["message"]["content"]
    return {"response": response_text}


@trace(workflow_name="openai-wrapper-failure")
def demo_failure() -> dict[str, Any]:
    """A failing LLM call — the wrapper records the error in the step."""

    result = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": "Please fail this request"},
        ],
    )

    return {"response": result.model_dump()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: OpenAI wrapper — successful call")
    print("=" * 60)
    output = demo_success()
    print(f"  Result: {json.dumps(output, indent=2)}")
    print()

    print("=" * 60)
    print("Demo: OpenAI wrapper — failing call")
    print("=" * 60)
    try:
        demo_failure()
    except RuntimeError as e:
        print(f"  Caught expected error: {e}")
    print()

    print("Done. Check the Leer UI for two runs under 'demo-project'.")


if __name__ == "__main__":
    main()
