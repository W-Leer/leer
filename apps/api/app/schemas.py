from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


# --- Run ---

class RunPayload(BaseModel):
    id: UUID
    workflow_name: str
    status: str
    trigger_type: str
    source: str
    started_at: datetime
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = {}


# --- Step ---

class StepPayload(BaseModel):
    id: UUID
    parent_step_id: UUID | None = None
    sequence_index: int
    name: str
    step_type: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = {}


# --- Event ---

class EventPayload(BaseModel):
    id: UUID
    step_id: UUID | None = None
    event_type: str
    sequence_index: int
    timestamp: datetime
    payload: dict[str, Any] = {}


# --- Artifact ---

class ArtifactPayload(BaseModel):
    id: UUID
    step_id: UUID | None = None
    artifact_type: str
    storage_kind: str
    mime_type: str | None = None
    inline_data: dict[str, Any] | None = None
    blob_path: str | None = None
    metadata: dict[str, Any] = {}


# --- Replay ---

class ReplayPayload(BaseModel):
    source_run_id: UUID
    source_step_id: UUID | None = None
    replay_mode: str
    reason: str | None = None
    metadata: dict[str, Any] = {}


# --- Ingest Request ---

class IngestRunRequest(BaseModel):
    project_slug: str
    run: RunPayload
    steps: list[StepPayload] = []
    events: list[EventPayload] = []
    artifacts: list[ArtifactPayload] = []
    replay: ReplayPayload | None = None


# --- Responses ---

class IngestRunResponse(BaseModel):
    status: str = "ok"
    run_id: UUID


class HealthResponse(BaseModel):
    status: str = "ok"
