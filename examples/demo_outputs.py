"""
Showcase different output types for the structured renderer.

Steps produce:
  1. plain string
  2. array of strings (bullet list)
  3. flat key-value object
  4. array of objects (table)
  5. nested object (collapsible tree)

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_outputs.py
"""

from leer import configure, step, trace

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


@trace(workflow_name="output-showcase")
def run_showcase() -> dict:

    # 1. Plain string output
    with step("validate_input", step_type="code", input={"query": "What is Leer?"}) as s:
        s.output = "Input validated successfully. Query has 3 tokens."

    # 2. Array of strings → bullet list
    with step(
        "generate_summary",
        step_type="llm",
        metadata={"provider": "openai", "model": "gpt-4"},
        input={"prompt": "Summarize Leer in 4 bullet points."},
    ) as s:
        s.output = {
            "summary": [
                "Leer traces AI agent execution end-to-end",
                "Every run, step, and event is captured",
                "Comparison reveals regressions between runs",
                "Replay enables deterministic debugging",
            ]
        }

    # 3. Flat key-value object
    with step("collect_metrics", step_type="code") as s:
        s.output = {
            "total_tokens": 142,
            "prompt_tokens": 98,
            "completion_tokens": 44,
            "latency_ms": 1230,
            "model": "gpt-4",
            "cached": False,
        }

    # 4. Array of objects → table
    with step(
        "rank_results",
        step_type="code",
        input={"candidates": 4},
    ) as s:
        s.output = {
            "result_preview": [
                {"rank": 1, "source": "docs/vision.md", "score": 0.95, "tokens": 38},
                {"rank": 2, "source": "docs/overview.md", "score": 0.87, "tokens": 52},
                {"rank": 3, "source": "README.md", "score": 0.72, "tokens": 41},
                {"rank": 4, "source": "AGENTS.md", "score": 0.65, "tokens": 29},
            ]
        }

    # 5. Nested object → collapsible tree
    with step("build_response", step_type="code") as s:
        s.output = {
            "response": {
                "answer": "Leer is an execution tracing platform for AI agents.",
                "sources": [
                    {"file": "docs/vision.md", "section": "Purpose"},
                    {"file": "docs/overview.md", "section": "Architecture"},
                ],
                "metadata": {
                    "confidence": 0.92,
                    "model": "gpt-4",
                    "latency_ms": 1230,
                },
            }
        }

    return {
        "summary": [
            "Leer is an execution tracing platform for AI agents",
            "It captures runs, steps, and events for debugging",
        ]
    }


def main() -> None:
    print("Running output showcase...")
    result = run_showcase()
    print(f"Done. Output: {result}")
    print("\nOpen http://localhost:3000 → click the 'output-showcase' run to see all renderer types.")


if __name__ == "__main__":
    main()
