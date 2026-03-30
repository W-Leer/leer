import uuid
from typing import Literal

from sqlalchemy import func, or_, select, cast, String
from sqlalchemy.orm import Session

from app.models import Artifact, Event, Project, Run, Step


def get_project_by_slug(session: Session, slug: str) -> Project | None:
    stmt = select(Project).where(Project.slug == slug)
    return session.execute(stmt).scalar_one_or_none()


DEFAULT_LIMIT = 20


def list_runs_for_project(
    session: Session,
    project_id: uuid.UUID,
    *,
    q: str | None = None,
    status: str | None = None,
    sort: Literal["newest", "oldest"] = "newest",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[Run], int]:
    """Return (runs, total_count) for a project with optional filtering."""
    base = select(Run).where(Run.project_id == project_id)

    if status:
        base = base.where(Run.status == status)

    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        base = base.where(
            or_(
                Run.workflow_name.ilike(pattern),
                cast(Run.id, String).ilike(pattern),
                cast(Run.output_summary, String).ilike(pattern),
            )
        )

    total_count = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    order = Run.created_at.desc() if sort == "newest" else Run.created_at.asc()
    rows = base.order_by(order).limit(limit).offset(offset)

    runs = list(session.execute(rows).scalars().all())
    return runs, total_count


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
        .order_by(Artifact.sequence_index.asc())
    )
    return list(session.execute(stmt).scalars().all())
