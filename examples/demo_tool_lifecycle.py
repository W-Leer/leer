"""
Demo: Tool lifecycle — exact, heuristic, unmatched, and failed linkage.

Creates two deterministic runs (A and B) that exercise every lifecycle path
the UI and compare page must handle.  No real provider calls required.

Run A — "tool-lifecycle-demo-a":
  [llm] planner  → emits 3 tool calls:
        1. get_weather(call_exact_1)   — exact linked, completed
        2. lookup_city()               — heuristic linked, completed
        3. send_alert(call_orphan_1)   — unmatched (no tool step)
  [tool] get_weather   — exact linkage via tool_call_id, completes
  [tool] lookup_city   — heuristic linkage via tool_name only, completes

Run B — "tool-lifecycle-demo-b":
  [llm] planner  → emits 2 tool calls:
        1. get_weather(call_exact_2)   — exact linked, FAILS
        2. lookup_city()               — heuristic linked, completed (args changed)
  [tool] get_weather   — exact linkage, raises → failed
  [tool] lookup_city   — heuristic linkage, completes

Compare A vs B should surface:
  - tool call count difference (3 vs 2)
  - get_weather: lifecycle completed → failed
  - lookup_city: arguments_hash diff
  - send_alert: "only in A"
  - insight: tool failure divergence or tool-count divergence

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_tool_lifecycle.py
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from leer import configure, create_json_artifact, attach_artifact, step, tool_step, trace
from leer.integrations.normalize import _arguments_hash

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_call_summary(name: str, *, call_id: str | None = None, args: Any = None) -> dict[str, Any]:
    """Build an enriched tool call summary matching the SDK shape."""
    s: dict[str, Any] = {"name": name}
    if call_id is not None:
        s["id"] = call_id
    h = _arguments_hash(args)
    if h is not None:
        s["arguments_hash"] = h
    return s


def _make_llm_metadata(
    provider: str,
    model: str,
    tool_calls: list[dict[str, Any]],
    *,
    text: str | None = None,
) -> dict[str, Any]:
    """Build a minimal llm metadata shape the UI understands."""
    return {
        "provider": provider,
        "model": model,
        "input": {
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Plan the tasks."}],
            "tools": [],
        },
        "output": {
            "text": text,
            "tool_calls": tool_calls,
            "content_blocks": [],
        },
        "usage": {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
        "meta": {"latency_ms": 350, "finish_reason": "tool_calls"},
    }


def _emit_tool_call_artifacts(step_obj: Any, tool_calls: list[dict[str, Any]], provider: str, model: str) -> None:
    """Create tool_call artifacts on the LLM step, mirroring what the wrappers do."""
    for i, tc in enumerate(tool_calls):
        call_id = tc.get("id")
        name = tc.get("name", "?")
        args = tc.get("arguments")
        args_hash = _arguments_hash(args)

        data: dict[str, Any] = {"tool_name": name, "arguments": args, "call_index": i}
        if call_id is not None:
            data["tool_call_id"] = call_id
        if args_hash is not None:
            data["arguments_hash"] = args_hash

        meta: dict[str, Any] = {"tool_name": name, "call_index": i}
        if call_id is not None:
            meta["tool_call_id"] = call_id
        meta["provider"] = provider
        meta["model"] = model

        preview = f"{name}({call_id or ''})" if call_id else name
        attach_artifact(create_json_artifact(
            artifact_type="tool_call",
            role="output",
            data=data,
            preview_text=preview[:200],
            metadata=meta,
            step_id=step_obj.id,
        ))


# ---------------------------------------------------------------------------
# Run A — exact + heuristic + unmatched, all succeed
# ---------------------------------------------------------------------------

TOOL_CALLS_A = [
    {"id": "call_exact_1", "name": "get_weather", "arguments": {"city": "Paris"}},
    {"name": "lookup_city", "arguments": {"query": "nearest airport"}},
    {"id": "call_orphan_1", "name": "send_alert", "arguments": {"msg": "storm warning"}},
]


@trace(workflow_name="tool-lifecycle-demo-a")
def run_a() -> dict[str, Any]:
    with step("planner", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as s:
        s.metadata["llm"] = _make_llm_metadata("fake", "demo-v1", TOOL_CALLS_A)
        s.output_summary = {
            "text": None,
            "tool_calls": [
                _tool_call_summary("get_weather", call_id="call_exact_1", args={"city": "Paris"}),
                _tool_call_summary("lookup_city", args={"query": "nearest airport"}),
                _tool_call_summary("send_alert", call_id="call_orphan_1", args={"msg": "storm warning"}),
            ],
        }
        _emit_tool_call_artifacts(s, TOOL_CALLS_A, "fake", "demo-v1")

    # Exact linkage — completed
    with tool_step("get_weather", tool_call_id="call_exact_1", source_provider="fake", source_model="demo-v1") as s:
        s.input = {"city": "Paris"}
        s.output = {"temperature": 18, "condition": "sunny"}

    # Heuristic linkage — completed (no tool_call_id, name only)
    with tool_step("lookup_city", source_provider="fake", source_model="demo-v1") as s:
        s.input = {"query": "nearest airport"}
        s.output = {"city": "Paris", "airport": "CDG"}

    # send_alert: intentionally NO tool step → unmatched

    return {"status": "completed", "tools_executed": 2, "tools_unmatched": 1}


# ---------------------------------------------------------------------------
# Run B — exact fails, heuristic changes args, send_alert absent
# ---------------------------------------------------------------------------

TOOL_CALLS_B = [
    {"id": "call_exact_2", "name": "get_weather", "arguments": {"city": "London"}},
    {"name": "lookup_city", "arguments": {"query": "nearest train station"}},
]


@trace(workflow_name="tool-lifecycle-demo-b")
def run_b() -> dict[str, Any]:
    with step("planner", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as s:
        s.metadata["llm"] = _make_llm_metadata("fake", "demo-v1", TOOL_CALLS_B)
        s.output_summary = {
            "text": None,
            "tool_calls": [
                _tool_call_summary("get_weather", call_id="call_exact_2", args={"city": "London"}),
                _tool_call_summary("lookup_city", args={"query": "nearest train station"}),
            ],
        }
        _emit_tool_call_artifacts(s, TOOL_CALLS_B, "fake", "demo-v1")

    # Exact linkage — FAILS
    try:
        with tool_step("get_weather", tool_call_id="call_exact_2", source_provider="fake", source_model="demo-v1") as s:
            s.input = {"city": "London"}
            raise ConnectionError("Weather API unreachable")
    except ConnectionError:
        pass

    # Heuristic linkage — completed (different args than Run A)
    with tool_step("lookup_city", source_provider="fake", source_model="demo-v1") as s:
        s.input = {"query": "nearest train station"}
        s.output = {"city": "London", "station": "St Pancras"}

    return {"status": "completed", "tools_executed": 1, "tools_failed": 1}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    separator = "=" * 60

    print(separator)
    print("Demo: Tool Lifecycle — Exact / Heuristic / Unmatched / Failed")
    print(separator)
    print()

    print("Creating Run A (tool-lifecycle-demo-a)...")
    out_a = run_a()
    print(f"  Result: {json.dumps(out_a)}")
    print()

    print("Creating Run B (tool-lifecycle-demo-b)...")
    out_b = run_b()
    print(f"  Result: {json.dumps(out_b)}")
    print()

    print(separator)
    print("INSPECTION GUIDE")
    print(separator)
    print()
    print("Run A — tool-lifecycle-demo-a")
    print("  Steps: [llm] planner → [tool] get_weather → [tool] lookup_city")
    print("  Tool calls emitted: 3")
    print("    1. get_weather (call_exact_1)  → exact linkage   → completed")
    print("    2. lookup_city (no id)         → heuristic        → completed")
    print("    3. send_alert  (call_orphan_1) → unlinked         → unmatched")
    print()
    print("Run B — tool-lifecycle-demo-b")
    print("  Steps: [llm] planner → [tool] get_weather → [tool] lookup_city")
    print("  Tool calls emitted: 2")
    print("    1. get_weather (call_exact_2)  → exact linkage   → failed")
    print("    2. lookup_city (no id)         → heuristic        → completed")
    print()
    print("RUN DETAIL CHECKS:")
    print("  - Open Run A: verify exact/heuristic/unlinked badges")
    print("  - Open Run B: verify exact-failed and heuristic-completed badges")
    print("  - Click LLM tool call → jump to tool step works")
    print("  - Click tool step back-link → jump to source LLM step works")
    print("  - Heuristic-only tool step (lookup_city) shows linkage row")
    print("  - Unmatched call (send_alert) shows unmatched/unlinked badges")
    print()
    print("COMPARE CHECKS:")
    print("  - Open /compare?a=<run_a_id>&b=<run_b_id>")
    print("  - Tool calls section: 3 → 2 count badge visible")
    print("  - get_weather: aligned by name (different ids), args changed badge")
    print("  - lookup_city: aligned by name, args changed badge")
    print("  - send_alert: 'only in A' label")
    print("  - Lifecycle badges: completed vs failed for get_weather")
    print("  - Tool-step linkage: confidence badges visible")
    print("  - Insight: tool failure divergence or call-count divergence")
    print()
    print("Open http://localhost:3000 to inspect.")
    print(separator)


if __name__ == "__main__":
    main()
