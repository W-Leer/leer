"""
Showcase: Structured output rendering across Leer surfaces.

Creates two runs (A and B) of the same workflow with deliberate
differences so you can inspect structured rendering in both the
run detail page and the compare page.

Rendering cases covered:
  #0 [code]  validate_input      — plain text output (no JSON detection)
  #1 [llm]   classify_intent     — JSON object as output.text (StructuredValue)
  #2 [llm]   plan_search         — tool calls with structured arguments
     └─ #3 [tool] search_docs    — nested structured output
  #4 [code]  compile_results     — array of objects (table rendering)

Compare diff targets (Run A vs Run B):
  • classify_intent  — intent, confidence, entities all change
  • search_docs      — different result count, different scores
  • compile_results  — extra row, different values

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_structured_outputs.py
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
# Fake OpenAI client — returns pre-defined responses in sequence
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def model_dump(self) -> dict[str, Any]:
        return self._data


class _FakeCompletions:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self._idx = 0

    def create(self, **kwargs: Any) -> _FakeResponse:
        resp = self._responses[self._idx]
        self._idx += 1
        return _FakeResponse(resp)


class _FakeChat:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.completions = _FakeCompletions(responses)


class _FakeOpenAI:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.chat = _FakeChat(responses)


# ---------------------------------------------------------------------------
# Response fixtures
# ---------------------------------------------------------------------------

# --- Run A responses ---

CLASSIFY_RESPONSE_A: dict[str, Any] = {
    "id": "chatcmpl-struct-001",
    "model": "gpt-4.1-mini",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            # Structured JSON output — rendered by StructuredValue in LLM detail
            "content": json.dumps({
                "intent": "question",
                "confidence": 0.94,
                "entities": ["Leer", "tracing"],
                "language": "en",
            }),
        },
        "finish_reason": "stop",
    }],
    "usage": {"prompt_tokens": 28, "completion_tokens": 15, "total_tokens": 43},
}

SEARCH_PLAN_RESPONSE_A: dict[str, Any] = {
    "id": "chatcmpl-struct-002",
    "model": "gpt-4.1",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": None,
            # Tool call with structured arguments — rendered by StructuredValue
            "tool_calls": [{
                "id": "call_search_a",
                "type": "function",
                "function": {
                    "name": "search_docs",
                    "arguments": json.dumps({
                        "query": "What is Leer",
                        "filters": {
                            "sections": ["overview", "vision"],
                            "max_results": 5,
                        },
                        "include_scores": True,
                    }),
                },
            }],
        },
        "finish_reason": "tool_calls",
    }],
    "usage": {"prompt_tokens": 55, "completion_tokens": 22, "total_tokens": 77},
}

# --- Run B responses (deliberately different for compare) ---

CLASSIFY_RESPONSE_B: dict[str, Any] = {
    "id": "chatcmpl-struct-003",
    "model": "gpt-4.1-mini",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": json.dumps({
                "intent": "comparison",
                "confidence": 0.87,
                "entities": ["Leer", "tracing", "debugging"],
                "language": "en",
            }),
        },
        "finish_reason": "stop",
    }],
    "usage": {"prompt_tokens": 32, "completion_tokens": 18, "total_tokens": 50},
}

SEARCH_PLAN_RESPONSE_B: dict[str, Any] = {
    "id": "chatcmpl-struct-004",
    "model": "gpt-4.1",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_search_b",
                "type": "function",
                "function": {
                    "name": "search_docs",
                    "arguments": json.dumps({
                        "query": "Leer tracing vs debugging",
                        "filters": {
                            "sections": ["overview", "vision", "debugging"],
                            "max_results": 10,
                        },
                        "include_scores": True,
                    }),
                },
            }],
        },
        "finish_reason": "tool_calls",
    }],
    "usage": {"prompt_tokens": 62, "completion_tokens": 25, "total_tokens": 87},
}


# ---------------------------------------------------------------------------
# Fake tool implementation
# ---------------------------------------------------------------------------

SEARCH_RESULTS_A = {
    "results": [
        {"title": "Product Vision", "path": "docs/vision.md", "score": 0.95, "section": "Purpose"},
        {"title": "Architecture Overview", "path": "docs/overview.md", "score": 0.87, "section": "Core Concepts"},
    ],
    "total_matches": 2,
    "query_time_ms": 45,
}

SEARCH_RESULTS_B = {
    "results": [
        {"title": "Product Vision", "path": "docs/vision.md", "score": 0.91, "section": "Purpose"},
        {"title": "Architecture Overview", "path": "docs/overview.md", "score": 0.85, "section": "Core Concepts"},
        {"title": "Debugging Guide", "path": "docs/debugging.md", "score": 0.78, "section": "Workflows"},
    ],
    "total_matches": 3,
    "query_time_ms": 62,
}


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

# Module-level client; replaced before each run
client: Any = None


def _current_run_steps():
    from leer.context import get_current_run
    run = get_current_run()
    return run.steps if run else []


def _make_client(responses: list[dict[str, Any]]):
    return wrap_openai_client(_FakeOpenAI(responses))


@trace(workflow_name="structured-output-demo")
def run_demo(variant: str, search_results: dict[str, Any]) -> dict[str, Any]:
    """
    Single workflow producing all structured-output rendering cases.
    Called twice (variant A and B) to create a compare pair.
    """
    global client

    # -- Step 0: plain text output (validates prose is NOT parsed as JSON) --
    with step("validate_input", step_type="code") as s:
        query = "What is Leer?" if variant == "A" else "How does Leer compare to logging?"
        s.input = {"query": query, "source": "api", "version": "v1"}
        s.output = f"Input validated: {len(query.split())} tokens, query is well-formed."

    # -- Step 1: LLM returning JSON object as text (StructuredValue in Output) --
    client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": f"Classify: {query}"}],
    )

    # -- Step 2: LLM emitting tool calls with structured arguments --
    client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": query},
            {"role": "system", "content": "Plan a document search to answer the query."},
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": "search_docs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "filters": {"type": "object"},
                        "include_scores": {"type": "boolean"},
                    },
                },
            },
        }],
    )

    llm_step = [s for s in _current_run_steps() if s.step_type == "llm"][-1]
    call_id = "call_search_a" if variant == "A" else "call_search_b"

    # -- Step 3: tool step with nested structured output --
    with tool_step(
        "search_docs",
        tool_call_id=call_id,
        source_provider="openai",
        source_model="gpt-4.1",
        parent_step_id=llm_step.id,
    ) as ts:
        ts.input = {
            "query": query,
            "filters": {"sections": ["overview", "vision"], "max_results": 5},
        }
        ts.output = search_results

    # -- Step 4: array of objects output (table rendering) --
    with step("compile_results", step_type="code") as s:
        s.input = {"result_count": search_results["total_matches"]}
        s.output = [
            {
                "source": r["path"],
                "title": r["title"],
                "relevance": r["score"],
                "section": r["section"],
            }
            for r in search_results["results"]
        ]

    return {
        "status": "completed",
        "answer": "Leer is an execution tracing platform for AI agents.",
        "sources_used": search_results["total_matches"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global client

    print("=" * 60)
    print("Demo: Structured Output Showcase")
    print("=" * 60)

    # --- Run A (baseline) ---
    print("\n  Submitting Run A (baseline)...")
    client = _make_client([CLASSIFY_RESPONSE_A, SEARCH_PLAN_RESPONSE_A])
    try:
        result_a = run_demo(variant="A", search_results=SEARCH_RESULTS_A)
        print(f"  Run A submitted. Output: {json.dumps(result_a)}")
    except Exception as e:
        print(f"  Run A failed: {e}")
        return

    # --- Run B (variant with diffs) ---
    print("\n  Submitting Run B (variant)...")
    client = _make_client([CLASSIFY_RESPONSE_B, SEARCH_PLAN_RESPONSE_B])
    try:
        result_b = run_demo(variant="B", search_results=SEARCH_RESULTS_B)
        print(f"  Run B submitted. Output: {json.dumps(result_b)}")
    except Exception as e:
        print(f"  Run B failed: {e}")
        return

    print()
    print("=" * 60)
    print("What to inspect in the UI:")
    print("=" * 60)
    print()
    print("  Run detail (either run):")
    print("    #0 validate_input  → plain text (no JSON detection)")
    print("    #1 classify_intent → JSON object rendered structurally")
    print("    #2 plan_search     → tool call args rendered structurally")
    print("    #3 search_docs     → nested object with array of results")
    print("    #4 compile_results → array of objects as table")
    print()
    print("  Compare (Run A vs Run B):")
    print("    classify_intent  → intent, confidence, entities differ")
    print("    search_docs      → different result count, different scores")
    print("    compile_results  → extra row in B, different relevance values")
    print()
    print("  Open http://localhost:3000 → find the two 'structured-output-demo' runs")
    print("  → click Compare on either and select the other")


if __name__ == "__main__":
    main()
