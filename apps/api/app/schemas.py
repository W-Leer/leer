from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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
    role: str | None = None
    format: str | None = None
    storage_kind: str
    sequence_index: int | None = None
    mime_type: str | None = None
    inline_data: dict[str, Any] | None = None
    blob_path: str | None = None
    preview_text: str | None = None
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


# --- Read Responses ---

class ProjectSummary(BaseModel):
    id: UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class RunListItem(BaseModel):
    id: UUID
    workflow_name: str
    status: str
    source: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    total_duration_ms: int | None = None
    model_provider: str | None = None
    model_name: str | None = None
    output_summary: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ProjectRunsResponse(BaseModel):
    project: ProjectSummary
    runs: list[RunListItem]
    total_count: int
    limit: int
    offset: int
    has_more: bool


class RunDetail(BaseModel):
    id: UUID
    project_id: UUID
    workflow_name: str
    status: str
    trigger_type: str
    source: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default={}, validation_alias="metadata_")
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    total_duration_ms: int | None = None
    model_provider: str | None = None
    model_name: str | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class RunDetailResponse(BaseModel):
    run: RunDetail


class TimelineRun(BaseModel):
    id: UUID
    workflow_name: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    total_duration_ms: int | None = None

    model_config = {"from_attributes": True}


class StepArtifactRef(BaseModel):
    """Lightweight artifact reference — no inline_data or blob_path."""
    id: UUID
    kind: str
    role: str | None = None
    format: str | None = None
    preview_text: str | None = None
    sequence_index: int | None = None


class TimelineStep(BaseModel):
    id: UUID
    parent_step_id: UUID | None = None
    sequence_index: int
    name: str
    step_type: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_provider: str | None = None
    model_name: str | None = None
    duration_ms: int | None = None

    llm: dict[str, Any] | None = None
    artifacts: list[StepArtifactRef] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    id: UUID
    step_id: UUID | None = None
    event_type: str
    sequence_index: int
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    run: TimelineRun
    steps: list[TimelineStep]
    events: list[TimelineEvent]
    artifacts: list[StepArtifactRef]


# --- Compare Responses ---

class CompareRunSummary(BaseModel):
    id: UUID
    workflow_name: str
    status: str
    created_at: datetime
    total_steps: int = 0
    total_duration_ms: int | None = None

    model_config = {"from_attributes": True}


class CompareStepDiff(BaseModel):
    match_kind: str  # exact_name | fallback_type_index | missing
    exists_in_a: bool
    exists_in_b: bool

    sequence_index_a: int | None = None
    sequence_index_b: int | None = None

    name_a: str | None = None
    name_b: str | None = None
    step_type_a: str | None = None
    step_type_b: str | None = None

    status_a: str | None = None
    status_b: str | None = None
    status_diff: bool

    input_summary_a: dict[str, Any] | None = None
    input_summary_b: dict[str, Any] | None = None
    input_diff: bool = False

    output_summary_a: dict[str, Any] | None = None
    output_summary_b: dict[str, Any] | None = None
    output_diff: bool

    error_summary_a: dict[str, Any] | None = None
    error_summary_b: dict[str, Any] | None = None
    error_diff: bool

    duration_ms_a: int | None = None
    duration_ms_b: int | None = None

    model_provider_a: str | None = None
    model_provider_b: str | None = None

    model_name_a: str | None = None
    model_name_b: str | None = None

    llm_a: dict[str, Any] | None = None
    llm_b: dict[str, Any] | None = None


class CompareRunDiff(BaseModel):
    status_a: str
    status_b: str
    status_diff: bool
    output_summary_a: dict[str, Any] | None = None
    output_summary_b: dict[str, Any] | None = None
    output_diff: bool
    error_summary_a: dict[str, Any] | None = None
    error_summary_b: dict[str, Any] | None = None
    error_diff: bool


class CompareResponse(BaseModel):
    run_a: CompareRunSummary
    run_b: CompareRunSummary
    run_diff: CompareRunDiff
    steps: list[CompareStepDiff]
