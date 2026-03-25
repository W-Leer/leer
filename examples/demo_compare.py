"""
Generate three runs for comparison testing.

  1. baseline_success  — completes with a 3-line summary
  2. changed_success   — completes with a 5-line summary
  3. timeout_failure   — draft_prompt succeeds, llm_call raises TimeoutError

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_compare.py
"""

from leer import configure, step, trace

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


@trace(workflow_name="demo-agent")
def baseline_success() -> dict:
    with step("draft_prompt", step_type="code") as s:
        s.output = {"prompt": "Summarize the following text into three bullet points."}

    with step(
        "llm_call",
        step_type="llm",
        metadata={"provider": "openai"},
        input={"prompt": "Summarize the following text into three bullet points."},
    ) as s:
        s.output = {
            "summary": [
                "AI agents are non-deterministic",
                "Leer provides execution traces",
                "Replay enables debugging",
            ]
        }

    return s.output


@trace(workflow_name="demo-agent")
def changed_success() -> dict:
    with step("draft_prompt", step_type="code") as s:
        s.output = {"prompt": "Summarize the following text into five bullet points."}

    with step(
        "llm_call",
        step_type="llm",
        metadata={"provider": "openai"},
        input={"prompt": "Summarize the following text into five bullet points."},
    ) as s:
        s.output = {
            "summary": [
                "AI agents require careful orchestration",
                "Observability is essential for production",
                "Leer captures full execution traces",
                "Comparison reveals regressions",
                "Replay enables rapid iteration",
            ]
        }

    return s.output


@trace(workflow_name="demo-agent")
def timeout_failure() -> dict:
    with step("draft_prompt", step_type="code") as s:
        s.output = {"prompt": "Summarize the following text into three bullet points."}

    with step(
        "llm_call",
        step_type="llm",
        metadata={"provider": "openai"},
        input={"prompt": "Summarize the following text into three bullet points."},
    ):
        raise TimeoutError("LLM provider timed out after 30s")

    return {}


def main() -> None:
    print("1/3  baseline_success")
    out = baseline_success()
    print(f"     status=completed  output={out}\n")

    print("2/3  changed_success")
    out = changed_success()
    print(f"     status=completed  output={out}\n")

    print("3/3  timeout_failure")
    try:
        timeout_failure()
    except TimeoutError:
        print("     status=failed     (TimeoutError caught)\n")

    print("Done. Open http://localhost:3000 to see all three runs.")
    print("Copy two run IDs and use Compare to diff them.")


if __name__ == "__main__":
    main()
