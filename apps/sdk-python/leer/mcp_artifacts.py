"""MCP protocol artifact helpers for Leer SDK.

Create canonical ``mcp_request``, ``mcp_response``, and ``mcp_error``
artifacts that carry consistent protocol metadata.

Artifact metadata is built via :func:`leer.metadata.mcp_metadata` so
the canonical key set is defined in exactly one place.

Usage::

    from leer.mcp_artifacts import create_mcp_request_artifact
    from leer.metadata import mcp_metadata
    from leer import tool_step, attach_artifact

    meta = mcp_metadata(
        operation_kind="tool_call",
        target_name="read_file",
        server_name="filesystem-server",
    )

    with tool_step("read_file", metadata=meta) as s:
        req = {"method": "tools/call", "params": {"name": "read_file"}}
        attach_artifact(create_mcp_request_artifact(req, step_id=s.id, **meta))
        ...
"""

from __future__ import annotations

import json
from typing import Any

from leer.artifacts import create_json_artifact
from leer.metadata import mcp_metadata as _mcp_metadata
from leer.models import TraceArtifact


def create_mcp_request_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    operation_kind: str | None = None,
    target_name: str | None = None,
    server_name: str | None = None,
    server_id: str | None = None,
    transport_kind: str | None = None,
    tool_call_id: str | None = None,
    parent_llm_step_id: str | None = None,
    parent_tool_step_id: str | None = None,
) -> TraceArtifact:
    """Create an ``mcp_request`` artifact for the protocol request payload."""
    return create_json_artifact(
        artifact_type="mcp_request",
        role="input",
        data=data,
        preview_text=_json_preview(data),
        metadata=_artifact_meta(
            operation_kind=operation_kind,
            target_name=target_name,
            server_name=server_name,
            server_id=server_id,
            transport_kind=transport_kind,
            tool_call_id=tool_call_id,
            parent_llm_step_id=parent_llm_step_id,
            parent_tool_step_id=parent_tool_step_id,
        ),
        step_id=step_id,
    )


def create_mcp_response_artifact(
    data: dict[str, Any] | list[Any],
    *,
    step_id: str | None = None,
    operation_kind: str | None = None,
    target_name: str | None = None,
    server_name: str | None = None,
    server_id: str | None = None,
    transport_kind: str | None = None,
    tool_call_id: str | None = None,
    parent_llm_step_id: str | None = None,
    parent_tool_step_id: str | None = None,
) -> TraceArtifact:
    """Create an ``mcp_response`` artifact for the protocol response payload."""
    return create_json_artifact(
        artifact_type="mcp_response",
        role="output",
        data=data,
        preview_text=_json_preview(data),
        metadata=_artifact_meta(
            operation_kind=operation_kind,
            target_name=target_name,
            server_name=server_name,
            server_id=server_id,
            transport_kind=transport_kind,
            tool_call_id=tool_call_id,
            parent_llm_step_id=parent_llm_step_id,
            parent_tool_step_id=parent_tool_step_id,
        ),
        step_id=step_id,
    )


def create_mcp_error_artifact(
    *,
    error_type: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    step_id: str | None = None,
    operation_kind: str | None = None,
    target_name: str | None = None,
    server_name: str | None = None,
    server_id: str | None = None,
    transport_kind: str | None = None,
    tool_call_id: str | None = None,
    parent_llm_step_id: str | None = None,
    parent_tool_step_id: str | None = None,
    error_code: str | int | None = None,
) -> TraceArtifact:
    """Create an ``mcp_error`` artifact for a protocol failure.

    The payload always contains ``error_type`` and ``message`` (defaulting
    to ``"UnknownError"`` / ``""``).  ``details`` and ``error_code`` are
    included only when provided.
    """
    payload: dict[str, Any] = {
        "error_type": error_type or "UnknownError",
        "message": message or "",
    }
    if details is not None:
        payload["details"] = details
    if error_code is not None:
        payload["error_code"] = error_code

    meta = _artifact_meta(
        operation_kind=operation_kind,
        target_name=target_name,
        server_name=server_name,
        server_id=server_id,
        transport_kind=transport_kind,
        tool_call_id=tool_call_id,
        parent_llm_step_id=parent_llm_step_id,
        parent_tool_step_id=parent_tool_step_id,
    )
    meta["error_type"] = payload["error_type"]
    if error_code is not None:
        meta["error_code"] = error_code

    preview = f"{payload['error_type']}: {payload['message']}"[:200]

    return create_json_artifact(
        artifact_type="mcp_error",
        role="error",
        data=payload,
        preview_text=preview,
        metadata=meta,
        step_id=step_id,
    )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _artifact_meta(
    *,
    operation_kind: str | None,
    target_name: str | None,
    server_name: str | None,
    server_id: str | None,
    transport_kind: str | None,
    tool_call_id: str | None,
    parent_llm_step_id: str | None,
    parent_tool_step_id: str | None,
) -> dict[str, Any]:
    """Build artifact metadata by delegating to the Step 1 canonical helper.

    Uses ``mcp_metadata()`` as the single source of truth for key names,
    with ``operation_kind`` defaulting to ``"unknown"`` to satisfy the
    required parameter.
    """
    return _mcp_metadata(
        operation_kind=operation_kind or "unknown",
        target_name=target_name,
        server_name=server_name,
        server_id=server_id,
        transport_kind=transport_kind,
        tool_call_id=tool_call_id,
        parent_llm_step_id=parent_llm_step_id,
        parent_tool_step_id=parent_tool_step_id,
    )


def _json_preview(data: Any, max_len: int = 200) -> str:
    try:
        return json.dumps(data, default=str)[:max_len]
    except Exception:
        return str(data)[:max_len]
