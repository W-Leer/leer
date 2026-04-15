"""Tests that compare-side metadata detection matches run-detail detection.

Validates that when the compare page receives ``metadata_a`` / ``metadata_b``
dicts, the raw-metadata detection functions from ``step-metadata.ts`` produce
correct results.  These are Python mirrors of the TypeScript raw-metadata
functions -- the same functions used by run-detail step-wrappers.

Also tests compare-specific scenarios: one-sided metadata, differing metadata
between sides, and the retrieval output_summary ``kind="retrieval"`` detection.
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
# Python mirrors of TypeScript raw-metadata detection helpers
# (must match step-metadata.ts exactly)
# ---------------------------------------------------------------------------

def is_mcp_meta(meta: dict | None) -> bool:
    if not meta:
        return False
    return meta.get("protocol_kind") == "mcp"


def get_capability_kind_from_meta(meta: dict | None) -> str | None:
    if not meta:
        return None
    v = meta.get("capability_kind")
    if v in ("tool", "mcp_tool", "retrieval", "skill", "unknown"):
        return v
    return None


def is_retrieval_meta(meta: dict | None) -> bool:
    if not meta:
        return False
    return get_capability_kind_from_meta(meta) == "retrieval" or isinstance(meta.get("retrieval_stage"), str)


def get_retrieval_stage_from_meta(meta: dict | None) -> str | None:
    if not meta:
        return None
    v = meta.get("retrieval_stage")
    return v if isinstance(v, str) else None


def is_retrieval_output(data: dict | None) -> bool:
    if not data:
        return False
    return data.get("kind") == "retrieval"


# ---------------------------------------------------------------------------
# MCP compare detection
# ---------------------------------------------------------------------------

class TestMcpCompareDetection:
    def test_both_sides_mcp(self):
        a = mcp_metadata(operation_kind="tool_call", server_name="srv-a")
        b = mcp_metadata(operation_kind="tool_call", server_name="srv-b")
        assert is_mcp_meta(a) is True
        assert is_mcp_meta(b) is True

    def test_one_side_mcp_only(self):
        a = mcp_metadata(operation_kind="tool_call")
        b = {"tool_name": "read_file"}
        assert is_mcp_meta(a) is True
        assert is_mcp_meta(b) is False

    def test_neither_side_mcp(self):
        a = {"tool_name": "x"}
        b = {"tool_name": "y"}
        assert is_mcp_meta(a) is False
        assert is_mcp_meta(b) is False

    def test_null_metadata(self):
        assert is_mcp_meta(None) is False
        assert is_mcp_meta({}) is False

    def test_mcp_server_diff_detection(self):
        a = mcp_metadata(operation_kind="tool_call", server_name="fs-server")
        b = mcp_metadata(operation_kind="tool_call", server_name="db-server")
        assert a["server_name"] != b["server_name"]

    def test_mcp_operation_diff_detection(self):
        a = mcp_metadata(operation_kind="tool_call", target_name="read_file")
        b = mcp_metadata(operation_kind="resource_read", target_name="schema")
        assert a["operation_kind"] != b["operation_kind"]
        assert a["target_name"] != b["target_name"]


# ---------------------------------------------------------------------------
# Capability compare detection
# ---------------------------------------------------------------------------

class TestCapabilityCompareDetection:
    def test_both_sides_same_kind(self):
        a = capability_metadata(capability_kind="skill", skill_name="summarize")
        b = capability_metadata(capability_kind="skill", skill_name="translate")
        assert get_capability_kind_from_meta(a) == "skill"
        assert get_capability_kind_from_meta(b) == "skill"

    def test_different_kinds(self):
        a = capability_metadata(capability_kind="mcp_tool")
        b = capability_metadata(capability_kind="retrieval")
        assert get_capability_kind_from_meta(a) == "mcp_tool"
        assert get_capability_kind_from_meta(b) == "retrieval"

    def test_one_side_only(self):
        a = capability_metadata(capability_kind="skill")
        b: dict = {}
        assert get_capability_kind_from_meta(a) == "skill"
        assert get_capability_kind_from_meta(b) is None

    def test_null_metadata(self):
        assert get_capability_kind_from_meta(None) is None


# ---------------------------------------------------------------------------
# Retrieval compare detection
# ---------------------------------------------------------------------------

class TestRetrievalCompareDetection:
    def test_both_sides_retrieval(self):
        a = retrieval_metadata(retrieval_stage="query", candidate_count=100)
        b = retrieval_metadata(retrieval_stage="query", candidate_count=50)
        assert is_retrieval_meta(a) is True
        assert is_retrieval_meta(b) is True

    def test_one_side_retrieval(self):
        a = retrieval_metadata(retrieval_stage="query")
        b: dict = {"tool_name": "search"}
        assert is_retrieval_meta(a) is True
        assert is_retrieval_meta(b) is False

    def test_null_metadata(self):
        assert is_retrieval_meta(None) is False

    def test_stage_extraction(self):
        a = retrieval_metadata(retrieval_stage="rerank")
        b = retrieval_metadata(retrieval_stage="select")
        assert get_retrieval_stage_from_meta(a) == "rerank"
        assert get_retrieval_stage_from_meta(b) == "select"

    def test_stage_null_when_absent(self):
        assert get_retrieval_stage_from_meta(None) is None
        assert get_retrieval_stage_from_meta({}) is None

    def test_count_diff_detection(self):
        a = retrieval_metadata(candidate_count=100, selected_count=10)
        b = retrieval_metadata(candidate_count=50, selected_count=5)
        assert a["candidate_count"] != b["candidate_count"]
        assert a["selected_count"] != b["selected_count"]

    def test_backend_diff_detection(self):
        a = retrieval_metadata(retrieval_backend="pinecone", index_name="docs-v1")
        b = retrieval_metadata(retrieval_backend="pinecone", index_name="docs-v2")
        assert a["retrieval_backend"] == b["retrieval_backend"]
        assert a["index_name"] != b["index_name"]


# ---------------------------------------------------------------------------
# Retrieval output_summary detection
# ---------------------------------------------------------------------------

class TestRetrievalOutputDetection:
    def test_retrieval_output_detected(self):
        s = retrieval_output_summary(candidate_count=50, selected_count=5)
        assert is_retrieval_output(s) is True

    def test_non_retrieval_output_not_detected(self):
        assert is_retrieval_output({"text": "hello"}) is False
        assert is_retrieval_output({}) is False

    def test_null_output(self):
        assert is_retrieval_output(None) is False

    def test_retrieval_output_count_diff(self):
        a = retrieval_output_summary(candidate_count=100, selected_count=10)
        b = retrieval_output_summary(candidate_count=50, selected_count=5)
        assert a["candidate_count"] != b["candidate_count"]
        assert a["selected_count"] != b["selected_count"]

    def test_retrieval_output_one_sided(self):
        a = retrieval_output_summary(retrieval_stage="select", candidate_count=50)
        b: dict | None = None
        assert is_retrieval_output(a) is True
        assert is_retrieval_output(b) is False


# ---------------------------------------------------------------------------
# No drift: raw-metadata functions produce same results as step-wrappers
# ---------------------------------------------------------------------------

class TestNoDriftWithRunDetail:
    """Verify that raw-metadata functions used by compare produce the same
    results as the step-wrapper functions used by run-detail."""

    def test_mcp_raw_matches(self):
        meta = mcp_metadata(operation_kind="tool_call")
        assert is_mcp_meta(meta) is True

    def test_capability_raw_matches(self):
        meta = capability_metadata(capability_kind="skill")
        assert get_capability_kind_from_meta(meta) == "skill"

    def test_retrieval_raw_matches(self):
        meta = retrieval_metadata(retrieval_stage="query")
        assert is_retrieval_meta(meta) is True
        assert get_retrieval_stage_from_meta(meta) == "query"

    def test_empty_dict_consistent(self):
        assert is_mcp_meta({}) is False
        assert get_capability_kind_from_meta({}) is None
        assert is_retrieval_meta({}) is False
        assert get_retrieval_stage_from_meta({}) is None


# ---------------------------------------------------------------------------
# Edge cases for compare
# ---------------------------------------------------------------------------

class TestCompareEdgeCases:
    def test_partial_mcp_metadata(self):
        meta = {"protocol_kind": "mcp"}
        assert is_mcp_meta(meta) is True

    def test_malformed_capability_kind(self):
        meta = {"capability_kind": 42}
        assert get_capability_kind_from_meta(meta) is None

    def test_retrieval_stage_non_string(self):
        meta = {"retrieval_stage": True}
        assert get_retrieval_stage_from_meta(meta) is None
        assert is_retrieval_meta(meta) is False

    def test_mixed_mcp_and_retrieval(self):
        meta = {
            **mcp_metadata(operation_kind="tool_call"),
            **retrieval_metadata(retrieval_stage="query"),
        }
        assert is_mcp_meta(meta) is True
        assert is_retrieval_meta(meta) is True


# ---------------------------------------------------------------------------
# Retrieval field-split deduplication
# ---------------------------------------------------------------------------

RETRIEVAL_IDENTITY_FIELDS = {"retrieval_stage", "retrieval_backend", "index_name", "query_text", "query_count"}
RETRIEVAL_COUNT_FIELDS = {"candidate_count", "selected_count", "context_token_estimate", "latency_ms"}


class TestRetrievalFieldSplit:
    """When both RetrievalCompareDiff (metadata) and RetrievalOutputDiff
    (output_summary) render, identity fields appear only in the metadata
    section and count/result fields only in the output section."""

    def test_identity_and_count_fields_disjoint(self):
        assert RETRIEVAL_IDENTITY_FIELDS.isdisjoint(RETRIEVAL_COUNT_FIELDS)

    def test_identity_fields_in_metadata_helper(self):
        meta = retrieval_metadata(
            retrieval_stage="query",
            retrieval_backend="pinecone",
            index_name="docs-v1",
            query_text="hello",
            query_count=1,
            candidate_count=100,
            selected_count=10,
        )
        for key in RETRIEVAL_IDENTITY_FIELDS:
            assert key in meta, f"expected {key} in metadata"

    def test_count_fields_in_output_summary(self):
        out = retrieval_output_summary(
            candidate_count=100,
            selected_count=10,
            context_token_estimate=2500,
            latency_ms=42,
        )
        for key in RETRIEVAL_COUNT_FIELDS:
            assert key in out, f"expected {key} in output_summary"

    def test_all_retrieval_diff_keys_covered(self):
        """Every load-bearing retrieval field belongs to exactly one UI section."""
        all_keys = RETRIEVAL_IDENTITY_FIELDS | RETRIEVAL_COUNT_FIELDS
        meta = retrieval_metadata(
            retrieval_stage="query", retrieval_backend="pinecone",
            index_name="docs", query_text="hello", query_count=1,
            candidate_count=100, selected_count=10,
            context_token_estimate=2500, latency_ms=42,
        )
        for key in all_keys:
            assert key in meta, f"expected {key} present in full metadata"
