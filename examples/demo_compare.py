"""
Generate three runs for comparison testing.

  Run A: completes successfully (baseline)
  Run B: fails on the llm_call step
  Run C: completes with different output

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_compare.py
"""

import sys

from leer import configure, trace, step

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


@trace(workflow_name="demo-agent")
def run_success() -> dict:
    with step("draft_prompt", step_type="code"):
        prompt = "Summarize the following text into three bullet points."

    with step("llm_call", step_type="llm", metadata={"provider": "openai"}):
        result = {
            "summary": [
                "AI agents are non-deterministic",
                "Leer provides execution traces",
                "Replay enables debugging",
            ]
        }

    return result


@trace(workflow_name="demo-agent")
def run_failure() -> dict:
    with step("draft_prompt", step_type="code"):
        prompt = "Summarize the following text into three bullet points."

    with step("llm_call", step_type="llm", metadata={"provider": "openai"}):
        raise TimeoutError("LLM provider timed out after 30s")

    return {}


@trace(workflow_name="demo-agent")
def run_different_output() -> dict:
    with step("draft_prompt", step_type="code"):
        prompt = "Summarize the following text into five bullet points."

    with step("llm_call", step_type="llm", metadata={"provider": "openai"}):
        result = {
            "summary": [
                "AI agents require careful orchestration",
                "Observability is essential for production",
                "Leer captures full execution traces",
                "Comparison reveals regressions",
                "Replay enables rapid iteration",
            ]
        }

    return result


if __name__ == "__main__":
    print("=== Run A: success (baseline) ===")
    out_a = run_success()
    print("  Output:", out_a)

    print("\n=== Run B: failure on llm_call ===")
    try:
        run_failure()
    except TimeoutError:
        print("  Caught expected TimeoutError")

    print("\n=== Run C: different output ===")
    out_c = run_different_output()
    print("  Output:", out_c)

    print("\nDone. Open http://localhost:3000 to see all three runs.")
    print("Copy two run IDs and use Compare to diff them.")
