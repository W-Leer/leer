from __future__ import annotations

import traceback
from contextlib import contextmanager
from typing import Any, Generator

from leer.context import current_step, get_current_run, next_event_index, pop_step, push_step
from leer.models import TraceEvent, TraceStep, _now, make_json_safe


def _emit_step_event(event_type: str, step_id: str) -> None:
    run = get_current_run()
    if run is None:
        return
    run.events.append(
        TraceEvent(
            event_type=event_type,
            sequence_index=next_event_index(),
            step_id=step_id,
        )
    )


_UNSET = object()


@contextmanager
def step(
    name: str,
    step_type: str = "code",
    metadata: dict[str, Any] | None = None,
    input: dict[str, Any] | None = None,
    parent_step_id: str | None | object = _UNSET,
) -> Generator[TraceStep, None, None]:
    run = get_current_run()

    if run is None:
        dummy = TraceStep(name=name, step_type=step_type)
        yield dummy
        return

    if parent_step_id is _UNSET:
        parent = current_step()
        resolved_parent_id = parent.id if parent else None
    else:
        resolved_parent_id = parent_step_id  # type: ignore[assignment]

    s = TraceStep(
        name=name,
        step_type=step_type,
        sequence_index=len(run.steps),
        parent_step_id=resolved_parent_id,
        status="running",
        started_at=_now(),
        metadata=metadata or {},
    )

    if input is not None:
        s.input_summary = make_json_safe(input)

    run.steps.append(s)
    push_step(s)

    _emit_step_event("step.created", s.id)
    _emit_step_event("step.started", s.id)

    try:
        yield s
    except Exception:
        s.status = "failed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        s.error_summary = {"traceback": traceback.format_exc()}
        _emit_step_event("step.failed", s.id)
        pop_step()
        raise
    else:
        s.status = "completed"
        s.ended_at = _now()
        s.duration_ms = _duration_ms(s)
        if s.output_summary is None and s.output is not None:
            s.output_summary = make_json_safe(s.output)
        _emit_step_event("step.completed", s.id)
        pop_step()


def _duration_ms(s: Any) -> int | None:
    if s.started_at is not None and s.ended_at is not None:
        return int((s.ended_at - s.started_at).total_seconds() * 1000)
    return None
