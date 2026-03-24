import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Event, Project, Run, Step


def get_project_by_slug(session: Session, slug: str) -> Project | None:
    stmt = select(Project).where(Project.slug == slug)
    return session.execute(stmt).scalar_one_or_none()


def list_runs_for_project(session: Session, project_id: uuid.UUID) -> list[Run]:
    stmt = (
        select(Run)
        .where(Run.project_id == project_id)
        .order_by(Run.created_at.desc())
    )
    return list(session.execute(stmt).scalars().all())


def get_run_by_id(session: Session, run_id: uuid.UUID) -> Run | None:
    stmt = select(Run).where(Run.id == run_id)
    return session.execute(stmt).scalar_one_or_none()


def get_steps_for_run(session: Session, run_id: uuid.UUID) -> list[Step]:
    stmt = (
        select(Step)
        .where(Step.run_id == run_id)
        .order_by(Step.sequence_index.asc())
    )
    return list(session.execute(stmt).scalars().all())


def get_events_for_run(session: Session, run_id: uuid.UUID) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.run_id == run_id)
        .order_by(Event.sequence_index.asc())
    )
    return list(session.execute(stmt).scalars().all())


def get_artifacts_for_run(session: Session, run_id: uuid.UUID) -> list[Artifact]:
    stmt = (
        select(Artifact)
        .where(Artifact.run_id == run_id)
    )
    return list(session.execute(stmt).scalars().all())
