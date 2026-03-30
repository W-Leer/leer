import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Event, Project, Replay, Run, Step
from app.schemas import IngestRunRequest


def resolve_or_create_project(session: Session, slug: str) -> Project:
    stmt = select(Project).where(Project.slug == slug)
    project = session.execute(stmt).scalar_one_or_none()
    if project is not None:
        return project

    project = Project(id=uuid.uuid4(), name=slug, slug=slug)
    session.add(project)
    session.flush()
    return project


def ingest_run(session: Session, request: IngestRunRequest) -> uuid.UUID:
    project = resolve_or_create_project(session, request.project_slug)

    completed = sum(1 for s in request.steps if s.status == "completed")
    failed = sum(1 for s in request.steps if s.status == "failed")

    duration_ms = None
    if request.run.started_at and request.run.ended_at:
        delta = request.run.ended_at - request.run.started_at
        duration_ms = int(delta.total_seconds() * 1000)

    run = Run(
        id=request.run.id,
        project_id=project.id,
        workflow_name=request.run.workflow_name,
        trigger_type=request.run.trigger_type,
        source=request.run.source,
        status=request.run.status,
        started_at=request.run.started_at,
        ended_at=request.run.ended_at,
        input_summary=request.run.input_summary,
        output_summary=request.run.output_summary,
        error_summary=request.run.error_summary,
        metadata_=request.run.metadata,
        total_steps=len(request.steps),
        completed_steps=completed,
        failed_steps=failed,
        total_duration_ms=duration_ms,
    )
    session.add(run)

    total_tokens_in = 0
    total_tokens_out = 0
    run_provider: str | None = None
    run_model: str | None = None

    for s in request.steps:
        step_duration = None
        if s.started_at and s.ended_at:
            step_duration = int((s.ended_at - s.started_at).total_seconds() * 1000)

        step_provider = s.metadata.get("provider") if s.metadata else None
        step_model = s.metadata.get("model") if s.metadata else None

        usage = s.metadata.get("usage", {}) if s.metadata else {}
        step_tokens_in = usage.get("prompt_tokens")
        step_tokens_out = usage.get("completion_tokens")

        if step_provider and not run_provider:
            run_provider = step_provider
        if step_model and not run_model:
            run_model = step_model
        if step_tokens_in:
            total_tokens_in += step_tokens_in
        if step_tokens_out:
            total_tokens_out += step_tokens_out

        step = Step(
            id=s.id,
            run_id=request.run.id,
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
            metadata_=s.metadata,
            model_provider=step_provider,
            model_name=step_model,
            duration_ms=step_duration,
            token_input=step_tokens_in,
            token_output=step_tokens_out,
        )
        session.add(step)

    if run_provider:
        run.model_provider = run_provider
    if run_model:
        run.model_name = run_model
    if total_tokens_in:
        run.total_tokens_input = total_tokens_in
    if total_tokens_out:
        run.total_tokens_output = total_tokens_out

    for e in request.events:
        event = Event(
            id=e.id,
            run_id=request.run.id,
            step_id=e.step_id,
            event_type=e.event_type,
            sequence_index=e.sequence_index,
            timestamp=e.timestamp,
            payload=e.payload,
        )
        session.add(event)

    for a in request.artifacts:
        artifact = Artifact(
            id=a.id,
            project_id=project.id,
            run_id=request.run.id,
            step_id=a.step_id,
            artifact_type=a.artifact_type,
            role=a.role,
            format_=a.format,
            storage_kind=a.storage_kind,
            sequence_index=a.sequence_index,
            mime_type=a.mime_type,
            inline_data=a.inline_data,
            blob_path=a.blob_path,
            preview_text=a.preview_text,
            metadata_=a.metadata,
        )
        session.add(artifact)

    if request.replay is not None:
        replay = Replay(
            id=uuid.uuid4(),
            source_run_id=request.replay.source_run_id,
            source_step_id=request.replay.source_step_id,
            replay_run_id=request.run.id,
            replay_mode=request.replay.replay_mode,
            reason=request.replay.reason,
            metadata_=request.replay.metadata,
        )
        session.add(replay)

    session.commit()
    return request.run.id
