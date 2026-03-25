"""
Minimal demo showing how to use the Leer SDK.

Prerequisites:
  - API running at http://127.0.0.1:8000  (cd apps/api && uv run uvicorn app.main:app --reload)
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_agent.py
"""

from leer import configure, step, trace

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


@trace(workflow_name="demo-agent")
def run_agent() -> dict:
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


if __name__ == "__main__":
    output = run_agent()
    print("Agent output:", output)
