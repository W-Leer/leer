from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import (
    ProjectRunsResponse,
    ProjectSummary,
    RunDetailResponse,
    TimelineResponse,
)
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
    session: Session = Depends(get_session),
) -> ProjectRunsResponse:
    project = get_project_by_slug(session, project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runs = list_runs_for_project(session, project.id)
    return ProjectRunsResponse(
        project=ProjectSummary.model_validate(project),
        runs=runs,
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

    return TimelineResponse(run=run, steps=steps, events=events, artifacts=artifacts)
