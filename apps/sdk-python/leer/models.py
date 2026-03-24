from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    mime_type: str | None = None
    inline_data: dict[str, Any] | None = None
    blob_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceStep:
    name: str
    step_type: str = "code"
    id: str = field(default_factory=_uuid)
    parent_step_id: str | None = None
    sequence_index: int = 0
    status: str = "pending"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
