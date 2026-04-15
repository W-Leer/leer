"""Tests that SDK-produced metadata matches frontend detection conventions.

These mirror the TypeScript detection helpers in
``apps/web/src/lib/step-metadata.ts`` to ensure the SDK metadata shapes
are always detectable by the frontend without drift.
"""

from __future__ import annotations

import pytest
from leer.metadata import (
    mcp_metadata,
    capability_metadata,
    retrieval_metadata,
    retrieval_output_summary,
)


# ---------------------------------------------------------------------------
# Pure-Python mirrors of frontend detection helpers
# ---------------------------------------------------------------------------

def is_mcp_step(meta: dict) -> bool:
    return meta.get("protocol_kind") == "mcp"


def get_capability_kind(meta: dict) -> str | None:
    v = meta.get("capability_kind")
    if v in ("tool", "mcp_tool", "retrieval", "skill", "unknown"):
        return v
    return None


def is_retrieval_step(meta: dict) -> bool:
    return get_capability_kind(meta) == "retrieval" or isinstance(meta.get("retrieval_stage"), str)


def get_retrieval_stage(meta: dict) -> str | None:
    v = meta.get("retrieval_stage")
    return v if isinstance(v, str) else None


# Metadata keys promoted to dedicated UI rows — must match step-metadata.ts
_TOOL_META_KEYS = {"tool_name", "tool_call_id", "provider", "model"}
_MCP_META_KEYS = {
    "protocol_kind", "operation_kind", "target_name",
    "server_name", "server_id", "transport_kind",
}
_CAPABILITY_META_KEYS = {
    "capability_kind", "capability_name", "capability_label",
    "capability_namespace", "skill_name", "skill_label",
}
_RETRIEVAL_META_KEYS = {
    "retrieval_stage", "retrieval_backend", "index_name",
    "query_text", "query_count", "candidate_count",
    "selected_count", "context_token_estimate", "latency_ms",
}
_LINKAGE_KEYS = {"parent_llm_step_id", "parent_tool_step_id"}

# Load-bearing retrieval keys for compare diffing — must match step-metadata.ts
_RETRIEVAL_DIFF_KEYS = [
    "retrieval_stage",
    "retrieval_backend",
    "index_name",
    "candidate_count",
    "selected_count",
    "context_token_estimate",
]


def extra_metadata_entries(meta: dict, is_tool: bool) -> list[tuple[str, object]]:
    """Python mirror of extraMetadataEntries()."""
    exclude: set[str] = set()
    if is_tool:
        exclude |= _TOOL_META_KEYS
    if meta.get("protocol_kind") == "mcp":
        exclude |= _MCP_META_KEYS
    if isinstance(meta.get("capability_kind"), str):
        exclude |= _CAPABILITY_META_KEYS
    if isinstance(meta.get("retrieval_stage"), str) or meta.get("capability_kind") == "retrieval":
        exclude |= _RETRIEVAL_META_KEYS
    exclude |= _LINKAGE_KEYS
    return [(k, v) for k, v in meta.items() if k not in exclude]


# ---------------------------------------------------------------------------
# MCP detection
# ---------------------------------------------------------------------------

class TestMcpDetection:
    def test_minimal_mcp_is_detected(self):
        meta = mcp_metadata(operation_kind="tool_call")
        assert is_mcp_step(meta) is True

    def test_full_mcp_is_detected(self):
        meta = mcp_metadata(
            operation_kind="tool_call",
            target_name="read_file",
            server_name="fs-server",
            server_id="srv-1",
            transport_kind="stdio",
        )
        assert is_mcp_step(meta) is True

    def test_non_mcp_not_detected(self):
        meta = capability_metadata(capability_kind="tool")
        assert is_mcp_step(meta) is False

    def test_empty_meta_not_detected(self):
        assert is_mcp_step({}) is False


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------

class TestCapabilityDetection:
    @pytest.mark.parametrize("kind", ["tool", "mcp_tool", "retrieval", "skill", "unknown"])
    def test_all_valid_kinds(self, kind: str):
        meta = capability_metadata(capability_kind=kind)
        assert get_capability_kind(meta) == kind

    def test_no_capability_kind_returns_none(self):
        meta = mcp_metadata(operation_kind="tool_call")
        assert get_capability_kind(meta) is None

    def test_empty_meta(self):
        assert get_capability_kind({}) is None


# ---------------------------------------------------------------------------
# Retrieval detection
# ---------------------------------------------------------------------------

class TestRetrievalDetection:
    def test_detected_via_capability_kind(self):
        meta = retrieval_metadata()
        assert is_retrieval_step(meta) is True

    def test_detected_via_retrieval_stage(self):
        meta = retrieval_metadata(
            retrieval_stage="query",
            include_capability_kind=False,
        )
        assert is_retrieval_step(meta) is True

    def test_stage_extracted(self):
        meta = retrieval_metadata(retrieval_stage="rerank")
        assert get_retrieval_stage(meta) == "rerank"

    def test_stage_none_when_absent(self):
        meta = retrieval_metadata()
        assert get_retrieval_stage(meta) is None

    def test_non_retrieval_not_detected(self):
        meta = mcp_metadata(operation_kind="tool_call")
        assert is_retrieval_step(meta) is False


# ---------------------------------------------------------------------------
# Retrieval output_summary
# ---------------------------------------------------------------------------

class TestRetrievalOutputSummary:
    def test_always_has_kind(self):
        s = retrieval_output_summary()
        assert s["kind"] == "retrieval"

    def test_full_shape(self):
        s = retrieval_output_summary(
            retrieval_stage="select",
            candidate_count=50,
            selected_count=5,
            context_token_estimate=1200,
            latency_ms=42,
        )
        assert s["kind"] == "retrieval"
        assert s["candidate_count"] == 50
        assert s["selected_count"] == 5


# ---------------------------------------------------------------------------
# Exclusion logic
# ---------------------------------------------------------------------------

class TestExtraMetadataExclusion:
    def test_tool_keys_excluded_for_tool_steps(self):
        meta = {"tool_name": "x", "tool_call_id": "id-1", "custom_key": 42}
        extras = extra_metadata_entries(meta, is_tool=True)
        keys = [k for k, _ in extras]
        assert "tool_name" not in keys
        assert "tool_call_id" not in keys
        assert "custom_key" in keys

    def test_tool_keys_not_excluded_for_non_tool(self):
        meta = {"tool_name": "x", "custom_key": 42}
        extras = extra_metadata_entries(meta, is_tool=False)
        keys = [k for k, _ in extras]
        assert "tool_name" in keys

    def test_mcp_keys_excluded(self):
        meta = mcp_metadata(
            operation_kind="tool_call",
            target_name="read_file",
            server_name="fs",
        )
        meta["custom"] = "val"
        extras = extra_metadata_entries(meta, is_tool=True)
        keys = [k for k, _ in extras]
        assert "protocol_kind" not in keys
        assert "operation_kind" not in keys
        assert "server_name" not in keys
        assert "custom" in keys

    def test_capability_keys_excluded(self):
        meta = capability_metadata(
            capability_kind="skill",
            skill_name="summarize",
        )
        meta["extra"] = True
        extras = extra_metadata_entries(meta, is_tool=False)
        keys = [k for k, _ in extras]
        assert "capability_kind" not in keys
        assert "skill_name" not in keys
        assert "extra" in keys

    def test_retrieval_keys_excluded(self):
        meta = retrieval_metadata(
            retrieval_stage="query",
            retrieval_backend="pinecone",
            candidate_count=100,
        )
        meta["custom_field"] = "yes"
        extras = extra_metadata_entries(meta, is_tool=False)
        keys = [k for k, _ in extras]
        assert "retrieval_stage" not in keys
        assert "retrieval_backend" not in keys
        assert "candidate_count" not in keys
        assert "custom_field" in keys

    def test_linkage_keys_always_excluded(self):
        meta = mcp_metadata(
            operation_kind="tool_call",
            parent_llm_step_id="llm-1",
            parent_tool_step_id="tool-1",
        )
        extras = extra_metadata_entries(meta, is_tool=True)
        keys = [k for k, _ in extras]
        assert "parent_llm_step_id" not in keys
        assert "parent_tool_step_id" not in keys


# ---------------------------------------------------------------------------
# Null safety
# ---------------------------------------------------------------------------

class TestNullSafety:
    def test_all_detectors_handle_empty_dict(self):
        assert is_mcp_step({}) is False
        assert get_capability_kind({}) is None
        assert is_retrieval_step({}) is False
        assert get_retrieval_stage({}) is None

    def test_extra_entries_on_empty(self):
        assert extra_metadata_entries({}, is_tool=False) == []

    def test_non_string_values_not_misdetected(self):
        assert is_mcp_step({"protocol_kind": 42}) is False
        assert get_capability_kind({"capability_kind": 99}) is None
        assert is_retrieval_step({"retrieval_stage": 0}) is False


# ---------------------------------------------------------------------------
# Key-set parity with step-metadata.ts constants
# ---------------------------------------------------------------------------

class TestKeySetParity:
    def test_retrieval_diff_keys_are_subset_of_retrieval_meta_keys(self):
        """RETRIEVAL_DIFF_KEYS must be a subset of RETRIEVAL_META_KEYS."""
        assert set(_RETRIEVAL_DIFF_KEYS) <= _RETRIEVAL_META_KEYS

    def test_linkage_keys_always_excluded_from_extras(self):
        """Even without MCP/retrieval/capability, linkage keys are excluded."""
        meta = {"parent_llm_step_id": "a", "parent_tool_step_id": "b", "other": 1}
        extras = extra_metadata_entries(meta, is_tool=False)
        keys = [k for k, _ in extras]
        assert keys == ["other"]

    def test_retrieval_diff_keys_produced_by_sdk(self):
        """retrieval_metadata() can produce all RETRIEVAL_DIFF_KEYS."""
        meta = retrieval_metadata(
            retrieval_stage="query",
            retrieval_backend="pinecone",
            index_name="docs",
            candidate_count=50,
            selected_count=5,
            context_token_estimate=1200,
        )
        for key in _RETRIEVAL_DIFF_KEYS:
            assert key in meta, f"retrieval_metadata() missing diff key: {key}"
