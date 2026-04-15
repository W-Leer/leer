"""
Demo: MCP tracing — protocol metadata, capability identity, and tool linkage coexistence.

Creates two deterministic runs (A and B) that exercise MCP tracing across
run-detail and compare.  No real provider or MCP server calls required.

Run A — "mcp-tracing-demo-a":
  [llm] planner     → emits 2 tool calls:
        1. read_file(call_mcp_a1)    — exact linked to MCP tool step
        2. list_dir(call_mcp_a2)     — exact linked to MCP tool step
  [tool] read_file   — MCP-backed via filesystem-server (stdio)
                       has both MCP metadata AND tool_call_id linkage
                       mcp_request + mcp_response artifacts
  [tool] list_dir    — MCP-backed via filesystem-server (stdio)
                       mcp_request + mcp_response artifacts

Run B — "mcp-tracing-demo-b":
  [llm] planner     → emits 2 tool calls:
        1. query_schema(call_mcp_b1) — exact linked to MCP tool step
        2. run_query(call_mcp_b2)    — exact linked to MCP tool step
  [tool] query_schema — MCP-backed via database-server (http)
                        different server_name and transport from Run A
                        mcp_request + mcp_response artifacts
  [tool] run_query    — MCP-backed via database-server (http)
                        mcp_request + mcp_error artifact (simulated failure)

Compare A vs B should surface:
  - MCP badge on all tool steps
  - capability badge (mcp_tool) on all tool steps
  - MCP compare section: server divergence (filesystem-server → database-server)
  - MCP compare section: transport divergence (stdio → http)
  - tool lifecycle: completed on A, mixed on B (run_query fails)
  - tool linkage: exact confidence on all steps
  - insight: MCP server divergence

Prerequisites:
  - API running at http://127.0.0.1:8000
  - Postgres running with migrations applied

Run (from repo root):
  cd apps/sdk-python && uv run python ../../examples/demo_mcp_tracing.py
"""

from __future__ import annotations

import json
from typing import Any

from leer import (
    attach_artifact,
    capability_metadata,
    configure,
    create_json_artifact,
    create_mcp_request_artifact,
    create_mcp_response_artifact,
    create_mcp_error_artifact,
    mcp_metadata,
    step,
    tool_step,
    trace,
)
from leer.context import get_current_run
from leer.integrations.normalize import _arguments_hash

configure(
    api_base_url="http://127.0.0.1:8000",
    project_slug="demo-project",
)


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as demo_tool_lifecycle.py)
# ---------------------------------------------------------------------------

def _tool_call_summary(name: str, *, call_id: str | None = None, args: Any = None) -> dict[str, Any]:
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
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "input": {
            "system": "You are an AI assistant with MCP server access.",
            "messages": messages or [{"role": "user", "content": "Read the project files."}],
            "tools": [],
        },
        "output": {
            "text": None,
            "tool_calls": tool_calls,
            "content_blocks": [],
        },
        "usage": {"prompt_tokens": 45, "completion_tokens": 25, "total_tokens": 70},
        "meta": {"latency_ms": 280, "finish_reason": "tool_calls"},
    }


def _emit_tool_call_artifacts(step_obj: Any, tool_calls: list[dict[str, Any]], provider: str, model: str) -> None:
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
# MCP metadata builder — merges mcp_metadata + capability_metadata + tool fields
# ---------------------------------------------------------------------------

def _mcp_tool_meta(
    *,
    tool_name: str,
    tool_call_id: str,
    operation_kind: str = "tool_call",
    server_name: str,
    server_id: str,
    transport_kind: str,
    parent_llm_step_id: str | None = None,
) -> dict[str, Any]:
    """Build combined metadata for an MCP-backed tool step.

    Merges:
      - standard tool fields (tool_name, tool_call_id)
      - MCP protocol metadata (protocol_kind, operation_kind, server_name, ...)
      - capability identity (capability_kind=mcp_tool, capability_name, server_name)
    """
    meta = mcp_metadata(
        operation_kind=operation_kind,
        target_name=tool_name,
        server_name=server_name,
        server_id=server_id,
        transport_kind=transport_kind,
        tool_call_id=tool_call_id,
        parent_llm_step_id=parent_llm_step_id,
    )
    meta.update(capability_metadata(
        capability_kind="mcp_tool",
        capability_name=tool_name,
        capability_label=tool_name.replace("_", " ").title(),
        server_name=server_name,
        server_id=server_id,
    ))
    return meta


# ---------------------------------------------------------------------------
# Run A — filesystem-server, stdio transport, two successful MCP calls
# ---------------------------------------------------------------------------

TOOL_CALLS_A = [
    {"id": "call_mcp_a1", "name": "read_file", "arguments": {"path": "/src/main.py"}},
    {"id": "call_mcp_a2", "name": "list_dir", "arguments": {"path": "/src"}},
]


@trace(workflow_name="mcp-tracing-demo-a")
def run_a() -> dict[str, Any]:
    run_id = get_current_run().id  # type: ignore[union-attr]

    # LLM planner step
    with step("planner", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as llm:
        llm.metadata["llm"] = _make_llm_metadata("fake", "demo-v1", TOOL_CALLS_A)
        llm.output_summary = {
            "text": None,
            "tool_calls": [
                _tool_call_summary("read_file", call_id="call_mcp_a1", args={"path": "/src/main.py"}),
                _tool_call_summary("list_dir", call_id="call_mcp_a2", args={"path": "/src"}),
            ],
        }
        _emit_tool_call_artifacts(llm, TOOL_CALLS_A, "fake", "demo-v1")
        llm_id = llm.id

    # MCP tool step 1: read_file — exact linkage + MCP metadata + MCP artifacts
    mcp_common_a = dict(
        server_name="filesystem-server",
        server_id="fs-001",
        transport_kind="stdio",
    )

    with tool_step(
        "read_file",
        tool_call_id="call_mcp_a1",
        source_provider="fake",
        source_model="demo-v1",
        metadata=_mcp_tool_meta(
            tool_name="read_file",
            tool_call_id="call_mcp_a1",
            parent_llm_step_id=llm_id,
            **mcp_common_a,
        ),
    ) as s:
        s.input = {"path": "/src/main.py"}
        s.output = {"content": "import leer\n\ndef main():\n    pass\n", "size": 42}

        attach_artifact(create_mcp_request_artifact(
            {"method": "tools/call", "params": {"name": "read_file", "arguments": {"path": "/src/main.py"}}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="read_file",
            **mcp_common_a,
        ))
        attach_artifact(create_mcp_response_artifact(
            {"result": {"content": [{"type": "text", "text": "import leer\n\ndef main():\n    pass\n"}]}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="read_file",
            **mcp_common_a,
        ))

    # MCP tool step 2: list_dir — exact linkage + MCP metadata + MCP artifacts
    with tool_step(
        "list_dir",
        tool_call_id="call_mcp_a2",
        source_provider="fake",
        source_model="demo-v1",
        metadata=_mcp_tool_meta(
            tool_name="list_dir",
            tool_call_id="call_mcp_a2",
            parent_llm_step_id=llm_id,
            **mcp_common_a,
        ),
    ) as s:
        s.input = {"path": "/src"}
        s.output = {"entries": ["main.py", "utils.py", "config.py"]}

        attach_artifact(create_mcp_request_artifact(
            {"method": "tools/call", "params": {"name": "list_dir", "arguments": {"path": "/src"}}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="list_dir",
            **mcp_common_a,
        ))
        attach_artifact(create_mcp_response_artifact(
            {"result": {"content": [{"type": "text", "text": "main.py\nutils.py\nconfig.py"}]}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="list_dir",
            **mcp_common_a,
        ))

    return {"status": "completed", "mcp_calls": 2, "server": "filesystem-server", "run_id": run_id}


# ---------------------------------------------------------------------------
# Run B — database-server, http transport, one success + one error
# ---------------------------------------------------------------------------

TOOL_CALLS_B = [
    {"id": "call_mcp_b1", "name": "query_schema", "arguments": {"table": "users"}},
    {"id": "call_mcp_b2", "name": "run_query", "arguments": {"sql": "SELECT * FROM users LIMIT 10"}},
]


@trace(workflow_name="mcp-tracing-demo-b")
def run_b() -> dict[str, Any]:
    run_id = get_current_run().id  # type: ignore[union-attr]

    # LLM planner step
    with step("planner", step_type="llm", metadata={"provider": "fake", "model": "demo-v1"}) as llm:
        llm.metadata["llm"] = _make_llm_metadata(
            "fake", "demo-v1", TOOL_CALLS_B,
            messages=[{"role": "user", "content": "Query the users table."}],
        )
        llm.output_summary = {
            "text": None,
            "tool_calls": [
                _tool_call_summary("query_schema", call_id="call_mcp_b1", args={"table": "users"}),
                _tool_call_summary("run_query", call_id="call_mcp_b2", args={"sql": "SELECT * FROM users LIMIT 10"}),
            ],
        }
        _emit_tool_call_artifacts(llm, TOOL_CALLS_B, "fake", "demo-v1")
        llm_id = llm.id

    mcp_common_b = dict(
        server_name="database-server",
        server_id="db-001",
        transport_kind="http",
    )

    # MCP tool step 1: query_schema — succeeds
    with tool_step(
        "query_schema",
        tool_call_id="call_mcp_b1",
        source_provider="fake",
        source_model="demo-v1",
        metadata=_mcp_tool_meta(
            tool_name="query_schema",
            tool_call_id="call_mcp_b1",
            parent_llm_step_id=llm_id,
            **mcp_common_b,
        ),
    ) as s:
        s.input = {"table": "users"}
        s.output = {"columns": ["id", "name", "email", "created_at"], "primary_key": "id"}

        attach_artifact(create_mcp_request_artifact(
            {"method": "tools/call", "params": {"name": "query_schema", "arguments": {"table": "users"}}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="query_schema",
            **mcp_common_b,
        ))
        attach_artifact(create_mcp_response_artifact(
            {"result": {"content": [{"type": "text", "text": "id INT, name TEXT, email TEXT, created_at TIMESTAMP"}]}},
            step_id=s.id,
            operation_kind="tool_call",
            target_name="query_schema",
            **mcp_common_b,
        ))

    # MCP tool step 2: run_query — FAILS with MCP error
    try:
        with tool_step(
            "run_query",
            tool_call_id="call_mcp_b2",
            source_provider="fake",
            source_model="demo-v1",
            metadata=_mcp_tool_meta(
                tool_name="run_query",
                tool_call_id="call_mcp_b2",
                parent_llm_step_id=llm_id,
                **mcp_common_b,
            ),
        ) as s:
            s.input = {"sql": "SELECT * FROM users LIMIT 10"}

            attach_artifact(create_mcp_request_artifact(
                {"method": "tools/call", "params": {"name": "run_query", "arguments": {"sql": "SELECT * FROM users LIMIT 10"}}},
                step_id=s.id,
                operation_kind="tool_call",
                target_name="run_query",
                **mcp_common_b,
            ))
            attach_artifact(create_mcp_error_artifact(
                error_type="PermissionDenied",
                message="User does not have SELECT permission on table 'users'",
                error_code=-32001,
                step_id=s.id,
                operation_kind="tool_call",
                target_name="run_query",
                **mcp_common_b,
            ))
            raise PermissionError("SELECT permission denied")
    except PermissionError:
        pass

    return {"status": "completed", "mcp_calls": 2, "mcp_errors": 1, "server": "database-server", "run_id": run_id}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 70

    print(sep)
    print("Demo: MCP Tracing — Protocol Metadata + Tool Linkage Coexistence")
    print(sep)
    print()

    print("Creating Run A (mcp-tracing-demo-a) — filesystem-server / stdio ...")
    out_a = run_a()
    id_a = out_a.get("run_id", "?")
    print(f"  Run ID: {id_a}")
    print(f"  Result: {json.dumps(out_a)}")
    print()

    print("Creating Run B (mcp-tracing-demo-b) — database-server / http ...")
    out_b = run_b()
    id_b = out_b.get("run_id", "?")
    print(f"  Run ID: {id_b}")
    print(f"  Result: {json.dumps(out_b)}")
    print()

    print(sep)
    print("INSPECTION GUIDE")
    print(sep)
    print()

    print(f"Run A — mcp-tracing-demo-a  (id: {id_a})")
    print("  Steps: [llm] planner → [tool] read_file → [tool] list_dir")
    print("  Server: filesystem-server (fs-001), transport: stdio")
    print("  Both tool steps carry:")
    print("    - tool_call_id  (exact linkage to LLM)")
    print("    - MCP metadata  (protocol_kind=mcp, server_name, transport_kind)")
    print("    - Capability    (capability_kind=mcp_tool)")
    print("    - mcp_request + mcp_response artifacts")
    print("    - tool_request + tool_response artifacts (auto-generated)")
    print()

    print(f"Run B — mcp-tracing-demo-b  (id: {id_b})")
    print("  Steps: [llm] planner → [tool] query_schema → [tool] run_query")
    print("  Server: database-server (db-001), transport: http")
    print("  query_schema: completed, mcp_request + mcp_response")
    print("  run_query:    failed,    mcp_request + mcp_error")
    print()

    print(f"Quick links:")
    print(f"  Run A detail:  http://localhost:3000/runs/{id_a}")
    print(f"  Run B detail:  http://localhost:3000/runs/{id_b}")
    print(f"  Compare A / B: http://localhost:3000/compare?a={id_a}&b={id_b}")
    print()

    print("RUN-DETAIL CHECKS:")
    print("  - MCP badge (violet) visible on all tool steps")
    print("  - Capability badge (mcp_tool, violet) visible")
    print("  - MCP metadata rows: server, operation, target, transport, server_id")
    print("  - Capability rows: kind=mcp_tool, name, label")
    print("  - mcp_request / mcp_response / mcp_error in artifact list")
    print("  - tool_request / tool_response in artifact list (auto-generated)")
    print("  - Tool lifecycle: exact linkage confidence badge")
    print("  - Click tool call → jump to tool step (bidirectional)")
    print("  - run_query (Run B): failed status + mcp_error artifact")
    print()

    print("COMPARE CHECKS (compare Run A vs Run B):")
    print("  NOTE: Tool step names differ across runs (read_file/list_dir vs")
    print("  query_schema/run_query), so compare alignment is fallback-based")
    print("  (by position), not by semantic name matching.  Expect positional")
    print("  pairing, not name-based pairing.")
    print()
    print("  - MCP compare section: server filesystem-server → database-server")
    print("  - MCP compare section: transport stdio → http")
    print("  - MCP badge shown on both sides")
    print("  - Capability badge (mcp_tool) shown on both sides")
    print("  - Tool linkage section: provider, model, exact confidence")
    print("  - Tool call names differ: read_file/list_dir vs query_schema/run_query")
    print("  - Insight: MCP server divergence message")
    print("  - Fallback-aligned tool row containing run_query on B shows failed")
    print("    status on B and non-failed counterpart on A")
    print()

    print("REGRESSION CHECKS:")
    print("  - Tool lifecycle badges still appear for MCP tool steps")
    print("  - Exact linkage confidence still works (tool_call_id present)")
    print("  - LLM → tool jump navigation still works")
    print("  - tool_request / tool_response artifacts auto-generated alongside MCP artifacts")
    print("  - No console errors")
    print()

    print("Open http://localhost:3000 to inspect.")
    print(sep)


if __name__ == "__main__":
    main()
