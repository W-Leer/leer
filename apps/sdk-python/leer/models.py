from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_json_safe(value: Any) -> dict[str, Any]:
    """Convert an arbitrary value into a JSON-safe dict for summary fields."""
    if isinstance(value, dict):
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            pass
    try:
        json.dumps(value)
        return {"result_preview": value}
    except (TypeError, ValueError):
        return {"result_preview": str(value)[:500]}


@dataclass
class TraceEvent:
    event_type: str
    sequence_index: int
    id: str = field(default_factory=_uuid)
    step_id: str | None = None
    timestamp: datetime = field(default_factory=_now)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceArtifact:
    artifact_type: str
    storage_kind: str = "inline"
    id: str = field(default_factory=_uuid)
    step_id: str | None = None
    role: str | None = None
    format: str | None = None
    sequence_index: int | None = None
    mime_type: str | None = None
    filename: str | None = None
    inline_data: dict[str, Any] | None = None
    blob_path: str | None = None
    preview_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    binary_data: bytes | None = field(default=None, repr=False)


@dataclass
class TraceStep:
    """A single execution step within a traced run.

    ``input`` and ``output`` hold the raw payloads set by the caller.
    They are **not** serialized to the API — only their reduced counterparts
    ``input_summary`` and ``output_summary`` are sent.  The raw values are
    used to generate summaries and artifacts on step exit.

    Convention:
        input  = raw payload (args, request body, etc.)
        input_summary  = UI-safe reduced version (auto-generated or explicit)
        output = raw return value
        output_summary = UI-safe reduced version (auto-generated or explicit)
    """

    name: str
    step_type: str = "code"
    id: str = field(default_factory=_uuid)
    parent_step_id: str | None = None
    sequence_index: int = 0
    status: str = "pending"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    input: Any | None = field(default=None, repr=False)
    output: Any | None = field(default=None, repr=False)


@dataclass
class TraceRun:
    workflow_name: str
    id: str = field(default_factory=_uuid)
    status: str = "pending"
    trigger_type: str = "manual"
    source: str = "sdk-python"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    steps: list[TraceStep] = field(default_factory=list)
    events: list[TraceEvent] = field(default_factory=list)
    artifacts: list[TraceArtifact] = field(default_factory=list)
