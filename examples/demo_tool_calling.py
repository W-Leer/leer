"""
Demo: First-class tool calling with Leer.

Shows the canonical LLM → tool → LLM flow using explicit tool_step tracing.
Uses fake clients so it runs without API keys or network.

Timeline produced:
  [code] prepare_prompt
  [llm]  gpt-4.1      → emits tool call get_weather(call_123)
  [tool] get_weather   → executes with city=Paris
  [llm]  gpt-4.1      → final response after tool result

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_tool_calling.py
"""

from __future__ import annotations

import json
from typing import Any

from leer import configure, step, tool_step, trace
from leer.integrations.openai import wrap_openai_client

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Fake OpenAI client
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data


class _FakeCompletions:
    def __init__(self) -> None:
        self._call_count = 0

    def create(self, **kwargs: Any) -> _FakeResponse:
        self._call_count += 1

        if self._call_count == 1:
            return _FakeResponse({
                "id": "chatcmpl-001",
                "model": "gpt-4.1",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Paris"}',
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            })

        return _FakeResponse({
            "id": "chatcmpl-002",
            "model": "gpt-4.1",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "The weather in Paris is 18°C and sunny.",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65},
        })


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


# ---------------------------------------------------------------------------
# Fake tool
# ---------------------------------------------------------------------------

def get_weather(city: str) -> dict[str, Any]:
    return {"temperature": 18, "condition": "sunny", "city": city}


# ---------------------------------------------------------------------------
# Demo workflow
# ---------------------------------------------------------------------------

client = wrap_openai_client(_FakeOpenAI())


@trace(workflow_name="tool-calling-demo")
def run_demo() -> dict[str, Any]:
    with step("prepare_prompt", step_type="code") as s:
        prompt = "What is the weather in Paris?"
        s.output = {"prompt": prompt}

    llm_response_1 = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
    )

    tool_call = {
        "id": "call_123",
        "name": "get_weather",
        "arguments": {"city": "Paris"},
    }

    with tool_step(
        "get_weather",
        tool_call_id=tool_call["id"],
        source_provider="openai",
        source_model="gpt-4.1",
    ) as s:
        s.input = tool_call["arguments"]
        result = get_weather(**tool_call["arguments"])
        s.output = result

    llm_response_2 = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "tool_calls": [tool_call]},
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": json.dumps(result),
            },
        ],
    )

    final = llm_response_2.model_dump()["choices"][0]["message"]["content"]
    return {"response": final}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: LLM → tool → LLM flow")
    print("=" * 60)
    output = run_demo()
    print(f"  Result: {json.dumps(output, indent=2)}")
    print()
    print("Done. Check the Leer UI for a run under 'demo-project'.")
    print("Expected timeline:")
    print("  [code] prepare_prompt")
    print("  [llm]  gpt-4.1 (tool call emitted)")
    print("  [tool] get_weather")
    print("  [llm]  gpt-4.1 (final answer)")


if __name__ == "__main__":
    main()
