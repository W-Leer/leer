"""Tests for canonical metadata builders (MCP, capability, retrieval)."""

import copy
import json

from leer.metadata import (
    mcp_metadata,
    capability_metadata,
    retrieval_metadata,
    retrieval_output_summary,
)


# -- MCP metadata ----------------------------------------------------------


def test_mcp_minimal():
    m = mcp_metadata(operation_kind="tool_call")
    assert m == {"protocol_kind": "mcp", "operation_kind": "tool_call"}


def test_mcp_full():
    m = mcp_metadata(
        operation_kind="resource_read",
        target_name="file://readme.md",
        server_name="filesystem-server",
        server_id="fs-001",
        transport_kind="stdio",
        tool_call_id="call_abc",
        parent_llm_step_id="step_111",
        parent_tool_step_id="step_222",
        latency_ms=42,
        status="completed",
    )
    assert m["protocol_kind"] == "mcp"
    assert m["operation_kind"] == "resource_read"
    assert m["target_name"] == "file://readme.md"
    assert m["server_name"] == "filesystem-server"
    assert m["server_id"] == "fs-001"
    assert m["transport_kind"] == "stdio"
    assert m["tool_call_id"] == "call_abc"
    assert m["parent_llm_step_id"] == "step_111"
    assert m["parent_tool_step_id"] == "step_222"
    assert m["latency_ms"] == 42
    assert m["status"] == "completed"
    assert len(m) == 11


def test_mcp_omits_none_fields():
    m = mcp_metadata(
        operation_kind="tool_call",
        target_name="search",
        server_name=None,
        transport_kind=None,
    )
    assert "server_name" not in m
    assert "transport_kind" not in m
    assert set(m.keys()) == {"protocol_kind", "operation_kind", "target_name"}


def test_mcp_always_sets_protocol_kind():
    m = mcp_metadata(operation_kind="unknown")
    assert m["protocol_kind"] == "mcp"


def test_mcp_json_safe():
    m = mcp_metadata(operation_kind="tool_call", target_name="search", latency_ms=99)
    serialized = json.dumps(m)
    assert json.loads(serialized) == m


def test_mcp_independent_calls():
    """Verify the helper does not share state across calls."""
    m1 = mcp_metadata(operation_kind="tool_call")
    m2 = mcp_metadata(operation_kind="resource_read")
    assert m1["operation_kind"] == "tool_call"
    assert m2["operation_kind"] == "resource_read"


# -- Capability metadata ---------------------------------------------------


def test_capability_local_tool():
    m = capability_metadata(capability_kind="tool", capability_name="get_weather")
    assert m == {"capability_kind": "tool", "capability_name": "get_weather"}


def test_capability_mcp_tool():
    m = capability_metadata(
        capability_kind="mcp_tool",
        capability_name="read_file",
        server_name="filesystem-server",
        server_id="fs-001",
    )
    assert m["capability_kind"] == "mcp_tool"
    assert m["server_name"] == "filesystem-server"
    assert m["server_id"] == "fs-001"


def test_capability_retrieval():
    m = capability_metadata(
        capability_kind="retrieval",
        capability_name="vector_search",
        capability_namespace="knowledge-base",
    )
    assert m["capability_kind"] == "retrieval"
    assert m["capability_namespace"] == "knowledge-base"


def test_capability_skill():
    m = capability_metadata(
        capability_kind="skill",
        capability_name="answer_question",
        skill_name="qa-pipeline",
        skill_label="QA Pipeline",
    )
    assert m["capability_kind"] == "skill"
    assert m["skill_name"] == "qa-pipeline"
    assert m["skill_label"] == "QA Pipeline"


def test_capability_unknown():
    m = capability_metadata(capability_kind="unknown")
    assert m == {"capability_kind": "unknown"}


def test_capability_omits_none_fields():
    m = capability_metadata(
        capability_kind="tool",
        capability_name="calc",
        capability_label=None,
        server_name=None,
    )
    assert "capability_label" not in m
    assert "server_name" not in m


def test_capability_full():
    m = capability_metadata(
        capability_kind="mcp_tool",
        capability_name="read_file",
        capability_label="Read File",
        capability_namespace="fs",
        server_name="filesystem-server",
        server_id="fs-001",
        skill_name="file-ops",
        skill_label="File Operations",
    )
    assert len(m) == 8


def test_capability_json_safe():
    m = capability_metadata(capability_kind="mcp_tool", capability_name="search")
    assert json.loads(json.dumps(m)) == m


def test_capability_independent_calls():
    m1 = capability_metadata(capability_kind="tool")
    m2 = capability_metadata(capability_kind="mcp_tool", server_name="srv")
    assert "server_name" not in m1
    assert m2["server_name"] == "srv"


# -- Retrieval metadata ----------------------------------------------------


def test_retrieval_minimal():
    m = retrieval_metadata()
    assert m == {"capability_kind": "retrieval"}


def test_retrieval_full():
    m = retrieval_metadata(
        retrieval_stage="candidates",
        retrieval_backend="pgvector",
        index_name="docs_embeddings",
        query_text="how does auth work?",
        query_count=1,
        candidate_count=50,
        selected_count=5,
        context_token_estimate=2000,
        latency_ms=120,
        parent_llm_step_id="step_llm_1",
    )
    assert m["capability_kind"] == "retrieval"
    assert m["retrieval_stage"] == "candidates"
    assert m["retrieval_backend"] == "pgvector"
    assert m["index_name"] == "docs_embeddings"
    assert m["query_text"] == "how does auth work?"
    assert m["query_count"] == 1
    assert m["candidate_count"] == 50
    assert m["selected_count"] == 5
    assert m["context_token_estimate"] == 2000
    assert m["latency_ms"] == 120
    assert m["parent_llm_step_id"] == "step_llm_1"
    assert len(m) == 11


def test_retrieval_omits_none_fields():
    m = retrieval_metadata(
        retrieval_stage="request",
        retrieval_backend=None,
        candidate_count=None,
    )
    assert "retrieval_backend" not in m
    assert "candidate_count" not in m
    assert set(m.keys()) == {"capability_kind", "retrieval_stage"}


def test_retrieval_without_capability_kind():
    m = retrieval_metadata(
        retrieval_stage="context",
        include_capability_kind=False,
    )
    assert "capability_kind" not in m
    assert m == {"retrieval_stage": "context"}


def test_retrieval_json_safe():
    m = retrieval_metadata(
        retrieval_stage="candidates",
        candidate_count=100,
        latency_ms=55.7,
    )
    assert json.loads(json.dumps(m)) == m


def test_retrieval_independent_calls():
    m1 = retrieval_metadata(retrieval_stage="request")
    m2 = retrieval_metadata(retrieval_stage="candidates", candidate_count=10)
    assert "candidate_count" not in m1
    assert m2["candidate_count"] == 10


# -- Retrieval output summary ----------------------------------------------


def test_retrieval_summary_minimal():
    s = retrieval_output_summary()
    assert s == {"kind": "retrieval"}


def test_retrieval_summary_full():
    s = retrieval_output_summary(
        retrieval_stage="selected",
        retrieval_backend="elasticsearch",
        index_name="articles",
        query_text="latest news",
        candidate_count=200,
        selected_count=10,
        context_token_estimate=3000,
        latency_ms=85,
    )
    assert s["kind"] == "retrieval"
    assert s["retrieval_stage"] == "selected"
    assert s["retrieval_backend"] == "elasticsearch"
    assert s["selected_count"] == 10
    assert len(s) == 9


def test_retrieval_summary_omits_none():
    s = retrieval_output_summary(
        retrieval_stage="candidates",
        candidate_count=50,
        selected_count=None,
    )
    assert "selected_count" not in s


def test_retrieval_summary_json_safe():
    s = retrieval_output_summary(candidate_count=100)
    assert json.loads(json.dumps(s)) == s


def test_retrieval_summary_deterministic():
    a = retrieval_output_summary(candidate_count=10, selected_count=3)
    b = retrieval_output_summary(candidate_count=10, selected_count=3)
    assert a == b
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# -- Cross-cutting ---------------------------------------------------------


def test_metadata_dicts_are_independent():
    """Outputs from different helpers share no mutable state."""
    mcp = mcp_metadata(operation_kind="tool_call")
    cap = capability_metadata(capability_kind="mcp_tool")
    ret = retrieval_metadata(retrieval_stage="request")

    mcp["injected"] = True
    assert "injected" not in cap
    assert "injected" not in ret


def test_merge_mcp_and_capability():
    """Typical usage: merge MCP + capability metadata for a tool step."""
    merged = {
        **mcp_metadata(operation_kind="tool_call", server_name="search-srv"),
        **capability_metadata(capability_kind="mcp_tool", capability_name="search"),
    }
    assert merged["protocol_kind"] == "mcp"
    assert merged["capability_kind"] == "mcp_tool"
    assert merged["server_name"] == "search-srv"
    assert merged["capability_name"] == "search"


def test_deep_copy_safety():
    """Helpers return plain dicts that can be deep-copied safely."""
    m = mcp_metadata(operation_kind="tool_call", target_name="x")
    c = copy.deepcopy(m)
    c["target_name"] = "y"
    assert m["target_name"] == "x"
