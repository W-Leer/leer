from collections import defaultdict
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Artifact, Step
from app.schemas import (
    CompareResponse,
    CompareRunSummary,
    ProjectRunsResponse,
    ProjectSummary,
    RunDetailResponse,
    StepArtifactRef,
    TimelineResponse,
    TimelineStep,
)
from app.services.compare import build_run_diff, build_step_diffs
from app.services.reads import (
    get_artifacts_for_run,
    get_events_for_run,
    get_project_by_slug,
    get_run_by_id,
    get_steps_for_run,
    list_runs_for_project,
)

router = APIRouter(prefix="/v1")


@router.get("/projects/{project_slug}/runs", response_model=ProjectRunsResponse)
def list_project_runs(
    project_slug: str,
    q: str | None = Query(None),
    status: str | None = Query(None),
    sort: Literal["newest", "oldest"] = Query("newest"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ProjectRunsResponse:
    project = get_project_by_slug(session, project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runs, total_count = list_runs_for_project(
        session,
        project.id,
        q=q,
        status=status,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return ProjectRunsResponse(
        project=ProjectSummary.model_validate(project),
        runs=runs,
        total_count=total_count,
        limit=limit,
        offset=offset,
        has_more=(offset + len(runs)) < total_count,
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> RunDetailResponse:
    run = get_run_by_id(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetailResponse(run=run)


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
def get_run_timeline(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> TimelineResponse:
    run = get_run_by_id(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = get_steps_for_run(session, run_id)
    events = get_events_for_run(session, run_id)
    artifacts = get_artifacts_for_run(session, run_id)

    artifact_refs = [_artifact_ref(a) for a in artifacts]
    refs_by_step: dict[UUID | None, list[StepArtifactRef]] = defaultdict(list)
    for a, ref in zip(artifacts, artifact_refs):
        refs_by_step[a.step_id].append(ref)

    enriched_steps = [
        _enrich_step(s, refs_by_step.get(s.id, []))
        for s in steps
    ]

    return TimelineResponse(
        run=run,
        steps=enriched_steps,
        events=events,
        artifacts=artifact_refs,
    )


_INLINE_DATA_ARTIFACT_TYPES = {"llm_stream"}


def _artifact_ref(a: Artifact) -> StepArtifactRef:
    return StepArtifactRef(
        id=a.id,
        kind=a.artifact_type,
        role=a.role,
        format=a.format_,
        preview_text=a.preview_text,
        sequence_index=a.sequence_index,
        storage_kind=a.storage_kind,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        inline_data=a.inline_data if a.artifact_type in _INLINE_DATA_ARTIFACT_TYPES else None,
    )


def _enrich_step(s: Step, artifact_refs: list[StepArtifactRef]) -> TimelineStep:
    raw_meta: dict[str, Any] = dict(s.metadata_ or {})
    llm = raw_meta.pop("llm", None)

    sorted_refs = sorted(artifact_refs, key=lambda r: r.sequence_index or 0)

    return TimelineStep(
        id=s.id,
        parent_step_id=s.parent_step_id,
        sequence_index=s.sequence_index,
        name=s.name,
        step_type=s.step_type,
        status=s.status,
        started_at=s.started_at,
        ended_at=s.ended_at,
        input_summary=s.input_summary,
        output_summary=s.output_summary,
        error_summary=s.error_summary,
        metadata=raw_meta,
        model_provider=s.model_provider,
        model_name=s.model_name,
        duration_ms=s.duration_ms,
        llm=llm,
        artifacts=sorted_refs,
    )


@router.get("/runs/{run_id}/compare/{other_run_id}", response_model=CompareResponse)
def compare_runs(
    run_id: UUID,
    other_run_id: UUID,
    session: Session = Depends(get_session),
) -> CompareResponse:
    run_a = get_run_by_id(session, run_id)
    if run_a is None:
        raise HTTPException(status_code=404, detail="Run A not found")

    run_b = get_run_by_id(session, other_run_id)
    if run_b is None:
        raise HTTPException(status_code=404, detail="Run B not found")

    if run_a.project_id != run_b.project_id:
        raise HTTPException(status_code=400, detail="Runs belong to different projects")

    steps_a = get_steps_for_run(session, run_a.id)
    steps_b = get_steps_for_run(session, run_b.id)

    return CompareResponse(
        run_a=CompareRunSummary.model_validate(run_a),
        run_b=CompareRunSummary.model_validate(run_b),
        run_diff=build_run_diff(run_a, run_b),
        steps=build_step_diffs(steps_a, steps_b),
    )
