"""Drive the real OpenAI / Anthropic SDKs (dev dependencies) through Leer's
wrappers over an in-memory HTTP transport. No network, no API keys.

Importing this module skips the importing test module when an SDK is missing.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest

openai = pytest.importorskip("openai")
anthropic = pytest.importorskip("anthropic")
httpx2 = pytest.importorskip("httpx2")

from leer.context import reset_context, set_current_run  # noqa: E402
from leer.integrations.anthropic import wrap_anthropic_client  # noqa: E402
from leer.integrations.openai import wrap_openai_client  # noqa: E402
from leer.models import TraceRun  # noqa: E402


def traced(fn: Callable[[], Any]) -> TraceRun:
    run = TraceRun(workflow_name="real-sdk-contract")
    run.status = "running"
    set_current_run(run)
    reset_context()
    try:
        fn()
    finally:
        set_current_run(None)
    return run


def llm_steps(run: TraceRun) -> list[Any]:
    return [s for s in run.steps if s.step_type == "llm"]


def only_llm_step(run: TraceRun) -> Any:
    steps = llm_steps(run)
    assert len(steps) == 1, f"expected exactly one LLM step, got {len(steps)}"
    return steps[0]


def artifact_types(run: TraceRun, step: Any) -> set[str]:
    return {a.artifact_type for a in run.artifacts if a.step_id == step.id}


def sse_response(events: list[dict[str, Any]], *, named: bool) -> Any:
    """``named``: Responses / Anthropic send ``event:`` lines; chat completions
    sends bare ``data:`` lines ending in ``[DONE]``."""
    chunks = []
    for e in events:
        prefix = f"event: {e['type']}\n" if named else ""
        chunks.append(f"{prefix}data: {json.dumps(e)}\n\n")
    if not named:
        chunks.append("data: [DONE]\n\n")
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content="".join(chunks).encode()
    )


def json_response(body: dict[str, Any]) -> Any:
    return httpx2.Response(200, json=body)


def openai_client(handler: Callable[[Any], Any]) -> Any:
    return wrap_openai_client(openai.OpenAI(
        api_key="sk-test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    ))


def anthropic_client(handler: Callable[[Any], Any]) -> Any:
    return wrap_anthropic_client(anthropic.Anthropic(
        api_key="sk-test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    ))
