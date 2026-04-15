"""Canonical metadata builders for MCP, capability, and retrieval tracing.

These helpers produce normalized ``dict[str, Any]`` metadata payloads that
can be passed directly to ``step()``, ``tool_step()``, or
``create_json_artifact()`` metadata parameters.

All helpers are pure functions that omit ``None``-valued keys and never
mutate their inputs.

Usage::

    from leer.metadata import mcp_metadata, capability_metadata, retrieval_metadata

    with tool_step("read_file", metadata=mcp_metadata(
        operation_kind="tool_call",
        target_name="read_file",
        server_name="filesystem-server",
    )) as s:
        ...
"""

from __future__ import annotations

from typing import Any, Literal


# ---------------------------------------------------------------------------
# MCP metadata
# ---------------------------------------------------------------------------

def mcp_metadata(
    *,
    operation_kind: str,
    target_name: str | None = None,
    server_name: str | None = None,
    server_id: str | None = None,
    transport_kind: str | None = None,
    tool_call_id: str | None = None,
    parent_llm_step_id: str | None = None,
    parent_tool_step_id: str | None = None,
    latency_ms: int | float | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Build canonical MCP protocol metadata.

    Always sets ``protocol_kind="mcp"``.  All other keys are included
    only when their value is not ``None``.
    """
    d: dict[str, Any] = {"protocol_kind": "mcp", "operation_kind": operation_kind}
    _set(d, "target_name", target_name)
    _set(d, "server_name", server_name)
    _set(d, "server_id", server_id)
    _set(d, "transport_kind", transport_kind)
    _set(d, "tool_call_id", tool_call_id)
    _set(d, "parent_llm_step_id", parent_llm_step_id)
    _set(d, "parent_tool_step_id", parent_tool_step_id)
    _set(d, "latency_ms", latency_ms)
    _set(d, "status", status)
    return d


# ---------------------------------------------------------------------------
# Capability / skill metadata
# ---------------------------------------------------------------------------

CapabilityKind = Literal["tool", "mcp_tool", "retrieval", "skill", "unknown"]


def capability_metadata(
    *,
    capability_kind: CapabilityKind,
    capability_name: str | None = None,
    capability_label: str | None = None,
    capability_namespace: str | None = None,
    server_name: str | None = None,
    server_id: str | None = None,
    skill_name: str | None = None,
    skill_label: str | None = None,
) -> dict[str, Any]:
    """Build canonical capability / skill identity metadata.

    The ``capability_kind`` distinguishes local tools, MCP-backed
    capabilities, retrieval operations, and higher-level skills.
    """
    d: dict[str, Any] = {"capability_kind": capability_kind}
    _set(d, "capability_name", capability_name)
    _set(d, "capability_label", capability_label)
    _set(d, "capability_namespace", capability_namespace)
    _set(d, "server_name", server_name)
    _set(d, "server_id", server_id)
    _set(d, "skill_name", skill_name)
    _set(d, "skill_label", skill_label)
    return d


# ---------------------------------------------------------------------------
# Retrieval metadata
# ---------------------------------------------------------------------------

def retrieval_metadata(
    *,
    retrieval_stage: str | None = None,
    retrieval_backend: str | None = None,
    index_name: str | None = None,
    query_text: str | None = None,
    query_count: int | None = None,
    candidate_count: int | None = None,
    selected_count: int | None = None,
    context_token_estimate: int | None = None,
    latency_ms: int | float | None = None,
    parent_llm_step_id: str | None = None,
    include_capability_kind: bool = True,
) -> dict[str, Any]:
    """Build canonical retrieval / RAG metadata.

    Sets ``capability_kind="retrieval"`` by default so the frontend can
    detect retrieval steps from metadata alone.  Pass
    ``include_capability_kind=False`` to omit it (useful when merging
    with a ``capability_metadata()`` dict that already sets it).
    """
    d: dict[str, Any] = {}
    if include_capability_kind:
        d["capability_kind"] = "retrieval"
    _set(d, "retrieval_stage", retrieval_stage)
    _set(d, "retrieval_backend", retrieval_backend)
    _set(d, "index_name", index_name)
    _set(d, "query_text", query_text)
    _set(d, "query_count", query_count)
    _set(d, "candidate_count", candidate_count)
    _set(d, "selected_count", selected_count)
    _set(d, "context_token_estimate", context_token_estimate)
    _set(d, "latency_ms", latency_ms)
    _set(d, "parent_llm_step_id", parent_llm_step_id)
    return d


def retrieval_output_summary(
    *,
    retrieval_stage: str | None = None,
    retrieval_backend: str | None = None,
    index_name: str | None = None,
    query_text: str | None = None,
    candidate_count: int | None = None,
    selected_count: int | None = None,
    context_token_estimate: int | None = None,
    latency_ms: int | float | None = None,
) -> dict[str, Any]:
    """Build a compact retrieval output summary for ``step.output_summary``.

    This is the compare-friendly shape: lightweight counts and identifiers
    that diff cleanly in the compare page without requiring artifact
    inspection.
    """
    d: dict[str, Any] = {"kind": "retrieval"}
    _set(d, "retrieval_stage", retrieval_stage)
    _set(d, "retrieval_backend", retrieval_backend)
    _set(d, "index_name", index_name)
    _set(d, "query_text", query_text)
    _set(d, "candidate_count", candidate_count)
    _set(d, "selected_count", selected_count)
    _set(d, "context_token_estimate", context_token_estimate)
    _set(d, "latency_ms", latency_ms)
    return d


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _set(d: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        d[key] = value
