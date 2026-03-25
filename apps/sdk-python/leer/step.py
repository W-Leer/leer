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


@contextmanager
def step(
    name: str,
    step_type: str = "code",
    metadata: dict[str, Any] | None = None,
    input: dict[str, Any] | None = None,
) -> Generator[TraceStep, None, None]:
    run = get_current_run()

    if run is None:
        dummy = TraceStep(name=name, step_type=step_type)
        yield dummy
        return

    parent = current_step()

    s = TraceStep(
        name=name,
        step_type=step_type,
        sequence_index=len(run.steps),
        parent_step_id=parent.id if parent else None,
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
        s.error_summary = {"traceback": traceback.format_exc()}
        _emit_step_event("step.failed", s.id)
        pop_step()
        raise
    else:
        s.status = "completed"
        s.ended_at = _now()
        if s.output_summary is None and s.output is not None:
            s.output_summary = make_json_safe(s.output)
        _emit_step_event("step.completed", s.id)
        pop_step()
