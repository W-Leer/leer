"""
Demo: Async-style fan-out tracing with Leer.

Simulates an LLM step that emits multiple tool calls, each traced as a
child step pointing back to the LLM step via parent_step_id.  No real
concurrency — this validates data shape and timeline semantics only.

Timeline produced:
  #0 [code] prepare_prompt
  #1 [llm]  gpt-4.1           → emits 3 tool calls
    ├─ #2 [tool] get_weather   (Paris)   parent=#1
    ├─ #3 [tool] get_weather   (London)  parent=#1
    └─ #4 [tool] get_weather   (NYC)     parent=#1
  #5 [llm]  gpt-4.1           → aggregation

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_async_tool_fanout.py
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
                "id": "chatcmpl-fanout-001",
                "model": "gpt-4.1",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_paris",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "Paris"}',
                                },
                            },
                            {
                                "id": "call_london",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "London"}',
                                },
                            },
                            {
                                "id": "call_nyc",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "New York"}',
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 40, "completion_tokens": 25, "total_tokens": 65},
            })

        return _FakeResponse({
            "id": "chatcmpl-fanout-002",
            "model": "gpt-4.1",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        "Paris is 18°C and sunny, London is 12°C and cloudy, "
                        "New York is 22°C and clear."
                    ),
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120},
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

WEATHER_DB: dict[str, dict[str, Any]] = {
    "Paris":    {"temperature": 18, "condition": "sunny"},
    "London":   {"temperature": 12, "condition": "cloudy"},
    "New York": {"temperature": 22, "condition": "clear"},
}


def get_weather(city: str) -> dict[str, Any]:
    data = WEATHER_DB.get(city, {"temperature": 0, "condition": "unknown"})
    return {**data, "city": city}


# ---------------------------------------------------------------------------
# Demo workflow
# ---------------------------------------------------------------------------

client = wrap_openai_client(_FakeOpenAI())

TOOL_CALLS = [
    {"id": "call_paris",  "name": "get_weather", "arguments": {"city": "Paris"}},
    {"id": "call_london", "name": "get_weather", "arguments": {"city": "London"}},
    {"id": "call_nyc",    "name": "get_weather", "arguments": {"city": "New York"}},
]


@trace(workflow_name="async-fanout-demo")
def run_fanout_demo() -> dict[str, Any]:
    # --- root code step: build prompt ---
    with step("prepare_prompt", step_type="code") as s:
        prompt = "What is the weather in Paris, London, and New York?"
        s.output = {"prompt": prompt}

    # --- LLM step: emits 3 tool calls ---
    llm_response = client.chat.completions.create(
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

    # The LLM step was auto-created by the wrapper.  Grab its id so child
    # tool steps can reference it as parent — this is the fan-out pattern.
    llm_step = [
        st for st in _current_run_steps()
        if st.step_type == "llm"
    ][-1]

    # --- fan-out: 3 child tool steps, all parented to the LLM step ---
    results: list[dict[str, Any]] = []
    for tc in TOOL_CALLS:
        with tool_step(
            tc["name"],
            tool_call_id=tc["id"],
            source_provider="openai",
            source_model="gpt-4.1",
            parent_step_id=llm_step.id,
        ) as ts:
            ts.input = tc["arguments"]
            result = get_weather(**tc["arguments"])
            ts.output = result
            results.append(result)

    # --- aggregation LLM step ---
    tool_messages = [
        {"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(r)}
        for tc, r in zip(TOOL_CALLS, results)
    ]
    agg_response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "tool_calls": TOOL_CALLS},
            *tool_messages,
        ],
    )

    final = agg_response.model_dump()["choices"][0]["message"]["content"]
    return {"response": final}


def _current_run_steps():
    from leer.context import get_current_run
    run = get_current_run()
    return run.steps if run else []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(run_fn):
    """Run the demo and print structural assertions."""
    from unittest.mock import patch
    from leer.models import TraceRun

    captured: list[TraceRun] = []

    def mock_submit(run: TraceRun) -> None:
        captured.append(run)

    with patch("leer.decorators.submit", mock_submit):
        output = run_fn()

    run = captured[0]
    steps = run.steps

    print(f"\n  Steps: {len(steps)}")
    for s in steps:
        parent_tag = f"  parent=#{s.parent_step_id[:8]}..." if s.parent_step_id else ""
        indent = "    " if s.parent_step_id else "  "
        print(f"{indent}#{s.sequence_index} [{s.step_type:4s}] {s.name}{parent_tag}")

    # Structural checks
    llm_steps = [s for s in steps if s.step_type == "llm"]
    tool_steps = [s for s in steps if s.step_type == "tool"]
    code_steps = [s for s in steps if s.step_type == "code"]

    assert len(code_steps) >= 1, "expected at least 1 code step"
    assert len(llm_steps) >= 2, "expected at least 2 llm steps"
    assert len(tool_steps) == 3, "expected exactly 3 tool steps"

    parent_llm = llm_steps[0]
    for ts in tool_steps:
        assert ts.parent_step_id == parent_llm.id, (
            f"tool step '{ts.name}' should have parent_step_id == LLM step id"
        )

    parent_ids = {ts.parent_step_id for ts in tool_steps}
    assert len(parent_ids) == 1, "all tool steps should share the same parent"

    indices = [s.sequence_index for s in steps]
    assert indices == sorted(indices), "sequence_index must be globally ordered"
    assert len(set(indices)) == len(indices), "sequence_index must be unique"

    assert code_steps[0].parent_step_id is None, "root code step should have no parent"
    assert llm_steps[0].parent_step_id is None, "root LLM step should have no parent"

    print("\n  All assertions passed.")
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Demo: Async-style fan-out (LLM → 3 child tool steps)")
    print("=" * 60)

    output = validate(run_fanout_demo)
    print(f"\n  Result: {json.dumps(output, indent=2)}")
    print()
    print("Expected timeline:")
    print("  #0 [code] prepare_prompt")
    print("  #1 [llm]  gpt-4.1 (emits 3 tool calls)")
    print("    ├─ #2 [tool] get_weather (Paris)")
    print("    ├─ #3 [tool] get_weather (London)")
    print("    └─ #4 [tool] get_weather (NYC)")
    print("  #5 [llm]  gpt-4.1 (aggregation)")


if __name__ == "__main__":
    main()
