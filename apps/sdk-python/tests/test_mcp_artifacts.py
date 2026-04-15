"""Tests for MCP protocol artifact helpers."""

import json

from leer.mcp_artifacts import (
    create_mcp_error_artifact,
    create_mcp_request_artifact,
    create_mcp_response_artifact,
)


# -- mcp_request -----------------------------------------------------------


def test_request_minimal():
    a = create_mcp_request_artifact({"method": "tools/call"})
    assert a.artifact_type == "mcp_request"
    assert a.role == "input"
    assert a.format == "json"
    assert a.storage_kind == "inline"
    assert a.inline_data == {"method": "tools/call"}
    assert a.metadata["protocol_kind"] == "mcp"
    assert a.metadata["operation_kind"] == "unknown"


def test_request_full_metadata():
    a = create_mcp_request_artifact(
        {"method": "tools/call", "params": {"name": "search"}},
        step_id="step_1",
        operation_kind="tool_call",
        target_name="search",
        server_name="search-srv",
        server_id="srv-001",
        transport_kind="stdio",
        tool_call_id="call_abc",
        parent_llm_step_id="llm_1",
        parent_tool_step_id="tool_1",
    )
    m = a.metadata
    assert m["protocol_kind"] == "mcp"
    assert m["operation_kind"] == "tool_call"
    assert m["target_name"] == "search"
    assert m["server_name"] == "search-srv"
    assert m["server_id"] == "srv-001"
    assert m["transport_kind"] == "stdio"
    assert m["tool_call_id"] == "call_abc"
    assert m["parent_llm_step_id"] == "llm_1"
    assert m["parent_tool_step_id"] == "tool_1"
    assert a.step_id == "step_1"


def test_request_omits_none_metadata():
    a = create_mcp_request_artifact(
        {"method": "tools/call"},
        operation_kind="tool_call",
        server_name=None,
        transport_kind=None,
    )
    assert "server_name" not in a.metadata
    assert "transport_kind" not in a.metadata


def test_request_preview_text():
    data = {"method": "tools/call", "params": {"name": "x"}}
    a = create_mcp_request_artifact(data)
    assert a.preview_text is not None
    assert len(a.preview_text) <= 200


def test_request_list_payload():
    a = create_mcp_request_artifact([{"id": 1}, {"id": 2}])
    assert a.inline_data == {"data": [{"id": 1}, {"id": 2}]}


def test_request_json_safe():
    a = create_mcp_request_artifact({"key": "value"}, operation_kind="tool_call")
    json.dumps(a.inline_data)
    json.dumps(a.metadata)


# -- mcp_response ----------------------------------------------------------


def test_response_minimal():
    a = create_mcp_response_artifact({"result": {"content": "hello"}})
    assert a.artifact_type == "mcp_response"
    assert a.role == "output"
    assert a.format == "json"
    assert a.metadata["protocol_kind"] == "mcp"
    assert a.metadata["operation_kind"] == "unknown"


def test_response_full_metadata():
    a = create_mcp_response_artifact(
        {"result": "ok"},
        step_id="step_2",
        operation_kind="resource_read",
        target_name="file://x.md",
        server_name="fs-server",
        server_id="fs-001",
        transport_kind="http",
    )
    assert a.metadata["operation_kind"] == "resource_read"
    assert a.metadata["target_name"] == "file://x.md"
    assert a.step_id == "step_2"


def test_response_omits_none():
    a = create_mcp_response_artifact({"ok": True}, server_name=None)
    assert "server_name" not in a.metadata


def test_response_step_id_passthrough():
    a = create_mcp_response_artifact({"r": 1}, step_id="abc-123")
    assert a.step_id == "abc-123"


# -- mcp_error -------------------------------------------------------------


def test_error_minimal():
    a = create_mcp_error_artifact()
    assert a.artifact_type == "mcp_error"
    assert a.role == "error"
    assert a.format == "json"
    assert a.metadata["protocol_kind"] == "mcp"
    assert a.inline_data["error_type"] == "UnknownError"
    assert a.inline_data["message"] == ""
    assert "details" not in a.inline_data
    assert "error_code" not in a.inline_data
    assert a.metadata["error_type"] == "UnknownError"


def test_error_full():
    a = create_mcp_error_artifact(
        error_type="ToolNotFound",
        message="Tool 'foo' not registered",
        details={"available": ["bar", "baz"]},
        error_code=-32601,
        step_id="step_3",
        operation_kind="tool_call",
        target_name="foo",
        server_name="test-srv",
    )
    assert a.inline_data["error_type"] == "ToolNotFound"
    assert a.inline_data["message"] == "Tool 'foo' not registered"
    assert a.inline_data["details"] == {"available": ["bar", "baz"]}
    assert a.inline_data["error_code"] == -32601
    assert a.metadata["error_type"] == "ToolNotFound"
    assert a.metadata["error_code"] == -32601
    assert a.metadata["protocol_kind"] == "mcp"
    assert a.metadata["operation_kind"] == "tool_call"
    assert a.step_id == "step_3"


def test_error_preview():
    a = create_mcp_error_artifact(error_type="Timeout", message="Server did not respond")
    assert a.preview_text == "Timeout: Server did not respond"


def test_error_preview_no_message():
    a = create_mcp_error_artifact(error_type="Timeout")
    assert "Timeout" in a.preview_text


def test_error_omits_none_metadata():
    a = create_mcp_error_artifact(
        error_type="Err",
        server_name=None,
        transport_kind=None,
    )
    assert "server_name" not in a.metadata
    assert "transport_kind" not in a.metadata


def test_error_json_safe():
    a = create_mcp_error_artifact(
        error_type="X",
        message="Y",
        details={"nested": [1, 2]},
        error_code=42,
    )
    json.dumps(a.inline_data)
    json.dumps(a.metadata)


# -- Cross-cutting ---------------------------------------------------------


def test_no_caller_data_mutation():
    """Verify caller dicts are not mutated."""
    data = {"method": "tools/call"}
    original = dict(data)
    create_mcp_request_artifact(data, operation_kind="tool_call")
    assert data == original


def test_independent_artifacts():
    a = create_mcp_request_artifact({"a": 1}, server_name="srv-a")
    b = create_mcp_request_artifact({"b": 2}, server_name="srv-b")
    assert a.metadata["server_name"] == "srv-a"
    assert b.metadata["server_name"] == "srv-b"
    a.metadata["injected"] = True
    assert "injected" not in b.metadata


def test_metadata_delegates_to_step1_helper():
    """Metadata must always include protocol_kind and operation_kind,
    matching the Step 1 mcp_metadata() canonical shape."""
    a = create_mcp_request_artifact({"x": 1})
    assert a.metadata["protocol_kind"] == "mcp"
    assert a.metadata["operation_kind"] == "unknown"

    b = create_mcp_request_artifact({"x": 1}, operation_kind="tool_call")
    assert b.metadata["operation_kind"] == "tool_call"


def test_error_payload_always_stable():
    """error_type and message are always present even with no args."""
    a = create_mcp_error_artifact()
    assert "error_type" in a.inline_data
    assert "message" in a.inline_data
    assert isinstance(a.inline_data["error_type"], str)
    assert isinstance(a.inline_data["message"], str)


def test_import_from_package():
    """Verify artifacts are importable from the top-level package."""
    from leer import (
        create_mcp_error_artifact,
        create_mcp_request_artifact,
        create_mcp_response_artifact,
    )
    assert callable(create_mcp_request_artifact)
    assert callable(create_mcp_response_artifact)
    assert callable(create_mcp_error_artifact)
